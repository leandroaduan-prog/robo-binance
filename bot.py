"""Robô de trade — Futuros USDⓈ-M Binance.

Regra (validada em backtest):
- Sinal: checklist >= 4/5 em candle de 1h fechado.
- Entrada: LIMIT na média de Bollinger(20) do 5m, repreçada a cada 5 min, válida 4h.
- Tamanho: 37,5% da banca como margem, 2x isolada, máx. 2 posições.
- Saída: 50% no +2% (LIMIT) + 50% em trailing 1% ativado no +2%; o que sobrar fecha em 48h.
- Sem stop de prejuízo.

Ordens do robô usam IDs "rb_...". Posições com ordens de outra origem são tratadas como manuais e não são mexidas.
"""
import math
import time
import traceback
from datetime import datetime, timezone, timedelta

import config as C
import strategy as S
from binance import BinanceError, Client
from telegram import Telegram

H = 3_600_000
M5 = 300_000
BRT = timezone(timedelta(hours=-3))


def now_ms():
    return int(time.time() * 1000)


def hora(ms):
    return datetime.fromtimestamp(ms / 1000, tz=BRT).strftime("%d/%m %H:%M")


def cid_ts(cid):
    """rb_ent_<seg>_<ATIVO>_<n> / rb_tp1_<seg>_<ATIVO> / rb_trl_<seg>_<ATIVO> -> ms"""
    try:
        return int(cid.split("_")[2]) * 1000
    except (IndexError, ValueError):
        return None


class Robo:
    def __init__(self):
        self.cli = Client(C.BINANCE_API_KEY, C.BINANCE_API_SECRET)
        self.tg = Telegram(C.TELEGRAM_BOT_TOKEN, C.TELEGRAM_CHAT_ID)
        self.cli.sync_time()
        self.rules = self._load_rules()
        self.paused = False
        self.last_signal_hour = None
        self.last_5m = {}
        self.prev_amt = None
        self.manual_warned = set()
        self.err_sent = {}
        self.dry_entries = {}  # simulação: sym -> dados do sinal

    # ---------------- utilidades ----------------
    def _load_rules(self):
        info = self.cli.exchange_info()
        rules = {}
        for s in info["symbols"]:
            if s["symbol"] in C.SYMBOLS:
                f = {x["filterType"]: x for x in s["filters"]}
                rules[s["symbol"]] = dict(
                    tick=float(f["PRICE_FILTER"]["tickSize"]), step=float(f["LOT_SIZE"]["stepSize"]),
                    min_qty=float(f["LOT_SIZE"]["minQty"]), min_notional=float(f.get("MIN_NOTIONAL", {}).get("notional", 5)),
                    pp=int(s["pricePrecision"]), qp=int(s["quantityPrecision"]))
        return rules

    def fp(self, sym, price, up=False):
        t = self.rules[sym]["tick"]
        v = (math.ceil if up else math.floor)(price / t + 1e-9) * t
        return f"{v:.{self.rules[sym]['pp']}f}"

    def fq(self, sym, qty):
        st = self.rules[sym]["step"]
        v = math.floor(qty / st + 1e-9) * st
        return f"{v:.{self.rules[sym]['qp']}f}"

    def err(self, msg):
        k = msg[:80]
        if now_ms() - self.err_sent.get(k, 0) > 30 * 60_000:
            self.err_sent[k] = now_ms()
            self.tg.send("⚠️ " + msg)
        else:
            print("ERRO", msg, flush=True)

    def act(self, desc, fn, **kw):
        """Executa ordem real (ou só avisa no modo simulação)."""
        if C.DRY_RUN:
            print("[SIMULAÇÃO]", desc, kw, flush=True)
            return {"dry": True}
        return fn(**kw)

    # ---------------- leitura do estado ----------------
    def snapshot(self):
        bal, avail = self.cli.usdt_balance()
        pos = {}
        for p in self.cli.positions():
            if p["symbol"] in C.SYMBOLS:
                pos[p["symbol"]] = p
        orders = {s: [] for s in C.SYMBOLS}
        for o in self.cli.open_orders():
            if o["symbol"] in orders:
                orders[o["symbol"]].append(o)
        algos = {s: [] for s in C.SYMBOLS}
        try:
            for a in self.cli.open_algo_orders():
                if a.get("symbol") in algos:
                    algos[a["symbol"]].append(a)
        except BinanceError as e:
            self.err(f"Não consegui ler ordens condicionais: {e}")
        return bal, avail, pos, orders, algos

    # ---------------- saídas ----------------
    def place_exits(self, sym, amt, entry, ts):
        r = self.rules[sym]
        tp = self.fp(sym, entry * (1 + C.TP1_PCT), up=True)
        q1 = float(self.fq(sym, amt * C.TP1_FRACTION))
        q2 = float(self.fq(sym, amt - q1))
        tag = f"{int(ts // 1000)}_{sym[:-4]}"
        split = q1 >= r["min_qty"] and q2 >= r["min_qty"]
        try:
            if split:
                self.act(f"TP1 {sym}", self.cli.new_order, symbol=sym, side="SELL", type="LIMIT", timeInForce="GTC",
                         quantity=self.fq(sym, q1), price=tp, reduceOnly="true", newClientOrderId=f"rb_tp1_{tag}")
                try:
                    self.act(f"Trailing {sym}", self.cli.new_algo_order, symbol=sym, side="SELL", type="TRAILING_STOP_MARKET",
                             quantity=self.fq(sym, q2), activatePrice=tp, callbackRate=C.TRAIL_CALLBACK,
                             workingType="CONTRACT_PRICE", reduceOnly="true", clientAlgoId=f"rb_trl_{tag}")
                except BinanceError as e:
                    # trailing recusado (ex.: valor mínimo): volta para 100% no alvo
                    self.cli.cancel_order(sym, f"rb_tp1_{tag}")
                    split = False
                    self.err(f"{sym}: trailing recusado ({e.msg}). Usando alvo único de +{C.TP1_PCT*100:g}% na posição toda.")
            if not split:
                self.act(f"TP único {sym}", self.cli.new_order, symbol=sym, side="SELL", type="LIMIT", timeInForce="GTC",
                         quantity=self.fq(sym, amt), price=tp, reduceOnly="true", newClientOrderId=f"rb_tp1_{tag}")
            lim = hora(ts + C.MAX_HOURS * H)
            modo = f"50% em {tp} + 50% trailing {C.TRAIL_CALLBACK:g}% ativado em {tp}" if split else f"100% em {tp}"
            self.tg.send(f"✅ ENTRADA EXECUTADA {sym}\nQtd {amt:g} a {entry:.{r['pp']}f}\nSaída: {modo}\nPrazo máximo: {lim}")
        except BinanceError as e:
            self.err(f"{sym}: falha ao colocar saídas ({e}). Verifique a posição!")

    def place_missing_trailing(self, sym, amt, tp1, ts):
        left = float(tp1["origQty"]) - float(tp1["executedQty"])
        q2 = float(self.fq(sym, amt - left))
        if q2 < self.rules[sym]["min_qty"]:
            return
        try:
            self.act(f"Trailing {sym}", self.cli.new_algo_order, symbol=sym, side="SELL", type="TRAILING_STOP_MARKET",
                     quantity=self.fq(sym, q2), activatePrice=tp1["price"], callbackRate=C.TRAIL_CALLBACK,
                     workingType="CONTRACT_PRICE", reduceOnly="true", clientAlgoId=f"rb_trl_{int(ts // 1000)}_{sym[:-4]}")
        except BinanceError as e:
            self.err(f"{sym}: não consegui recolocar o trailing ({e.msg}).")

    def close_all(self, sym, amt, orders, algos, motivo):
        for o in orders:
            if o["clientOrderId"].startswith("rb_"):
                self._safe(lambda o=o: self.cli.cancel_order(sym, o["clientOrderId"]))
        for a in algos:
            if str(a.get("clientAlgoId", "")).startswith("rb_"):
                self._safe(lambda a=a: self.cli.cancel_algo_order(a["clientAlgoId"]))
        if amt > 0:
            self.act(f"Fechar {sym}", self.cli.new_order, symbol=sym, side="SELL", type="MARKET",
                     quantity=self.fq(sym, amt), reduceOnly="true", newClientOrderId=f"rb_out_{now_ms()//1000}_{sym[:-4]}")
        self.tg.send(f"⏱️ {sym} encerrada: {motivo}")

    def _safe(self, fn):
        if C.DRY_RUN:
            return
        try:
            fn()
        except BinanceError as e:
            if e.code not in (-2011, -2013):  # ordem já não existe
                self.err(f"Cancelamento falhou: {e}")

    # ---------------- entradas ----------------
    def bb_mid(self, sym):
        k = S.closed(self.cli.klines(sym, "5m", 30), now_ms())
        return S.bollinger_mid(k)

    def place_entry(self, sym, bal, avail, sig_hour, det, pts):
        r = self.rules[sym]
        mid = self.bb_mid(sym)
        if not mid:
            return False
        price = float(self.fp(sym, mid))
        margin = min(bal * C.MARGIN_PCT, avail * 0.95)
        qty = float(self.fq(sym, margin * C.LEVERAGE / price))
        if qty < r["min_qty"] or qty * price < r["min_notional"]:
            print(f"{sym}: banca pequena para o mínimo da Binance (${qty*price:.2f})", flush=True)
            return False
        exp = sig_hour + int(C.ENTRY_VALID_HOURS * H)
        cid = f"rb_ent_{sig_hour // 1000}_{sym[:-4]}_0"
        try:
            self.act(f"Entrada {sym}", self.cli.new_order, symbol=sym, side="BUY", type="LIMIT", timeInForce="GTD",
                     goodTillDate=exp, quantity=self.fq(sym, qty), price=self.fp(sym, price), newClientOrderId=cid)
        except BinanceError as e:
            self.err(f"{sym}: entrada recusada ({e.msg}).")
            return False
        if C.DRY_RUN:
            self.dry_entries[sym] = dict(t=sig_hour, price=price, qty=qty)
        self.tg.send(f"🎯 SINAL {sym} ({pts}/5){' [SIMULAÇÃO]' if C.DRY_RUN else ''}\n"
                     f"Compra limitada {qty:g} a {self.fp(sym, price)} (média Bollinger 5m)\n"
                     f"Margem ${qty*price/C.LEVERAGE:.2f} · {C.LEVERAGE}x · válida até {hora(exp)}\n"
                     f"RSI {det['rsi']} · volume {det['vol']}x")
        return True

    def reprice_entry(self, sym, o):
        exp = cid_ts(o["clientOrderId"]) + int(C.ENTRY_VALID_HOURS * H)
        if now_ms() > exp:
            self._safe(lambda: self.cli.cancel_order(sym, o["clientOrderId"]))
            return
        filled = float(o["executedQty"])
        if filled > 0:  # parcialmente executada: cancela o resto e segue com o que entrou
            self._safe(lambda: self.cli.cancel_order(sym, o["clientOrderId"]))
            return
        mid = self.bb_mid(sym)
        if not mid:
            return
        newp = self.fp(sym, mid)
        if abs(float(newp) - float(o["price"])) < self.rules[sym]["tick"] / 2:
            return
        try:
            self.cli.modify_order(symbol=sym, origClientOrderId=o["clientOrderId"], side="BUY",
                                  quantity=o["origQty"], price=newp)
        except BinanceError:
            # alguns casos não aceitam modificação: cancela e recria
            try:
                self.cli.cancel_order(sym, o["clientOrderId"])
                parts = o["clientOrderId"].split("_")
                n = int(parts[-1]) + 1 if parts[-1].isdigit() else 1
                self.cli.new_order(symbol=sym, side="BUY", type="LIMIT", timeInForce="GTD", goodTillDate=exp,
                                   quantity=o["origQty"], price=newp, newClientOrderId=f"rb_ent_{parts[2]}_{sym[:-4]}_{n}")
            except BinanceError as e:
                self.err(f"{sym}: não consegui reposicionar a entrada ({e.msg}).")

    # ---------------- sinais ----------------
    def scores(self, now):
        btc1h = S.closed(self.cli.klines("BTCUSDT", "1h", 3), now)
        btc1d = self.cli.klines("BTCUSDT", "1d", 60)
        btc_ok = S.btc_filter(btc1h, btc1d, now)
        out = {}
        for sym in C.SYMBOLS:
            k1 = S.closed(self.cli.klines(sym, "1h", 500), now)
            k4 = S.closed(self.cli.klines(sym, "4h", 300), now)
            out[sym] = S.checklist(k1, k4, btc_ok)
        return out

    def ensure_setup(self, pos, orders):
        for sym in C.SYMBOLS:
            p = pos.get(sym)
            if not p or float(p["positionAmt"]) != 0 or orders[sym]:
                continue
            try:
                if p.get("marginType", "").lower() != "isolated":
                    self.act(f"Isolada {sym}", self.cli.set_isolated, symbol=sym)
                if int(float(p.get("leverage", C.LEVERAGE))) != C.LEVERAGE:
                    self.act(f"Alavancagem {sym}", self.cli.set_leverage, symbol=sym, leverage=C.LEVERAGE)
            except BinanceError as e:
                self.err(f"{sym}: não consegui ajustar alavancagem/margem ({e.msg}).")

    # ---------------- ciclo ----------------
    def tick(self):
        now = now_ms()
        bal, avail, pos, orders, algos = self.snapshot()
        amts = {s: float(pos[s]["positionAmt"]) if s in pos else 0.0 for s in C.SYMBOLS}
        new5m = {}
        cur5 = now - now % M5
        for sym in C.SYMBOLS:
            new5m[sym] = self.last_5m.get(sym) != cur5 and now - cur5 > 5_000
        busy = set()

        for sym in C.SYMBOLS:
            amt = amts[sym]
            my = [o for o in orders[sym] if o["clientOrderId"].startswith("rb_")]
            other = [o for o in orders[sym] if not o["clientOrderId"].startswith("rb_")] + \
                    [a for a in algos[sym] if not str(a.get("clientAlgoId", "")).startswith("rb_")]
            ent = [o for o in my if o["clientOrderId"].startswith("rb_ent_")]
            tp1 = [o for o in my if o["clientOrderId"].startswith("rb_tp1_")]
            trl = [a for a in algos[sym] if str(a.get("clientAlgoId", "")).startswith("rb_trl_")]

            if amt > 0:
                busy.add(sym)
                if C.DRY_RUN:
                    continue  # simulação não mexe em posições reais
                if other and not tp1 and not trl:
                    if sym not in self.manual_warned:
                        self.manual_warned.add(sym)
                        self.tg.send(f"ℹ️ {sym}: posição com ordens manuais — o robô não mexe nela, mas ela ocupa uma vaga.")
                    continue
                self.manual_warned.discard(sym)
                if ent:
                    if float(ent[0]["executedQty"]) < float(ent[0]["origQty"]) and not new5m[sym]:
                        continue  # ainda executando; espera o próximo 5m
                    self._safe(lambda: self.cli.cancel_order(sym, ent[0]["clientOrderId"]))
                entry = float(pos[sym]["entryPrice"])
                if not tp1 and not trl:
                    self.place_exits(sym, amt, entry, now)
                    continue
                ts = cid_ts((tp1 or [{}])[0].get("clientOrderId", "")) or cid_ts(str((trl or [{}])[0].get("clientAlgoId", "")))
                if tp1 and not trl and float(tp1[0]["executedQty"]) == 0 and amt > float(tp1[0]["origQty"]) * 1.01:
                    self.place_missing_trailing(sym, amt, tp1[0], ts or now)
                if ts and now - ts >= C.MAX_HOURS * H:
                    self.close_all(sym, amt, orders[sym], algos[sym], f"prazo de {C.MAX_HOURS:g}h")
            else:
                if tp1 or trl:  # posição acabou: limpa sobras
                    for o in tp1:
                        self._safe(lambda o=o: self.cli.cancel_order(sym, o["clientOrderId"]))
                    for a in trl:
                        self._safe(lambda a=a: self.cli.cancel_algo_order(a["clientAlgoId"]))
                if ent:
                    busy.add(sym)
                    if new5m[sym]:
                        self.reprice_entry(sym, ent[0])
            if new5m[sym]:
                self.last_5m[sym] = cur5

        # avisos de mudança de posição
        if self.prev_amt is not None:
            for sym in C.SYMBOLS:
                a0, a1 = self.prev_amt.get(sym, 0), amts[sym]
                if a0 > 0 and a1 == 0:
                    self.tg.send(f"🏁 {sym} encerrada. Banca agora: ${bal:.2f}")
                elif a0 > 0 and 0 < a1 < a0 * 0.99:
                    self.tg.send(f"💰 {sym}: TP1 atingido, {a0 - a1:g} vendidos. Resto segue no trailing. Banca: ${bal:.2f}")
        self.prev_amt = amts

        # simulação: sinais expiram após a validade
        for sym in list(self.dry_entries):
            if now > self.dry_entries[sym]["t"] + C.ENTRY_VALID_HOURS * H:
                del self.dry_entries[sym]
        busy |= set(self.dry_entries)

        # sinais a cada hora fechada
        hour = now - now % H
        if self.last_signal_hour != hour and now - hour >= 20_000:
            self.last_signal_hour = hour
            self.ensure_setup(pos, orders)
            slots = C.MAX_POSITIONS - len(busy)
            sc = self.scores(now)
            linha = " · ".join(f"{s.replace('USDT','')} {v[0]}" for s, v in sc.items())
            print(f"[{hora(now)}] banca ${bal:.2f} | vagas {slots} | {linha}", flush=True)
            if self.paused or slots <= 0:
                return
            cands = sorted(((v[2], s) for s, v in sc.items() if v[0] >= C.MIN_SCORE and s not in busy), reverse=True)
            for _, sym in cands:
                if slots <= 0:
                    break
                if self.place_entry(sym, bal, avail, hour, sc[sym][1], sc[sym][0]):
                    slots -= 1

    # ---------------- comandos Telegram ----------------
    def handle(self, cmd):
        if cmd in ("/pausar", "/pause"):
            self.paused = True
            self.tg.send("⏸️ Novas entradas pausadas. Posições abertas continuam sendo geridas. /retomar para voltar.")
        elif cmd in ("/retomar", "/resume"):
            self.paused = False
            self.tg.send("▶️ Novas entradas retomadas.")
        elif cmd == "/status":
            self.tg.send(self.status())
        elif cmd == "/checklist":
            sc = self.scores(now_ms())
            self.tg.send("📋 Checklist agora (1h fechado):\n" + "\n".join(
                f"{s.replace('USDT','')}: {v[0]}/5 · RSI {v[1]['rsi']} · vol {v[1]['vol']}x" for s, v in sc.items()))
        else:
            self.tg.send("Comandos: /status · /checklist · /pausar · /retomar")

    def status(self):
        bal, avail, pos, orders, algos = self.snapshot()
        lin = [f"🤖 Robô {'SIMULAÇÃO' if C.DRY_RUN else 'REAL'}{' · PAUSADO' if self.paused else ''}",
               f"Banca ${bal:.2f} · livre ${avail:.2f}"]
        for sym in C.SYMBOLS:
            p = pos.get(sym)
            if p and float(p["positionAmt"]) > 0:
                lin.append(f"• {sym} {p['positionAmt']} @ {p['entryPrice']} · agora {float(p['markPrice']):.4g} · PnL ${float(p['unRealizedProfit']):+.2f}")
            for o in orders[sym]:
                if o["clientOrderId"].startswith("rb_ent_"):
                    lin.append(f"• {sym} compra pendente {o['origQty']} a {o['price']}")
        if len(lin) == 2:
            lin.append("Sem posições nem ordens.")
        return "\n".join(lin)


def main():
    robo = Robo()
    robo.tg.send(f"🤖 Robô iniciado em modo {'SIMULAÇÃO (não envia ordens)' if C.DRY_RUN else 'REAL'}\n"
                 f"{', '.join(s.replace('USDT','') for s in C.SYMBOLS)} · {C.MARGIN_PCT*100:g}% · {C.LEVERAGE}x · máx {C.MAX_POSITIONS}\n"
                 f"Saída: {C.TP1_FRACTION*100:g}% em +{C.TP1_PCT*100:g}% + trailing {C.TRAIL_CALLBACK:g}% · prazo {C.MAX_HOURS:g}h\n"
                 f"Comandos: /status /checklist /pausar /retomar")
    last_sync = time.time()
    while True:
        try:
            for cmd in robo.tg.commands():
                robo.handle(cmd)
            robo.tick()
            if time.time() - last_sync > 3600:
                robo.cli.sync_time()
                last_sync = time.time()
        except BinanceError as e:
            robo.err(f"Erro Binance: {e}")
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            robo.err(f"Erro inesperado: {e}")
        time.sleep(C.LOOP_SECONDS)


if __name__ == "__main__":
    main()

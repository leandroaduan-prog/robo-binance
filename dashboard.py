"""Painel web do robô (somente leitura), protegido por senha.

Abre em http://IP-DO-SERVIDOR:8080 — usuário: robo · senha: PANEL_PASSWORD.
"""
import base64
import html
import threading
import time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import config as C
import stats
from binance import Client

BRT = timezone(timedelta(hours=-3))
_cli = None
_cache = {"t": 0, "data": None}
_lock = threading.Lock()


def _account():
    with _lock:
        if time.time() - _cache["t"] < 15 and _cache["data"]:
            return _cache["data"]
        bal, avail = _cli.usdt_balance()
        pos = [p for p in _cli.positions() if p["symbol"] in C.SYMBOLS and float(p["positionAmt"]) != 0]
        orders = [o for o in _cli.open_orders() if o["symbol"] in C.SYMBOLS and o["clientOrderId"].startswith("rb_ent_")]
        _cache.update(t=time.time(), data=(bal, avail, pos, orders))
        return _cache["data"]


def esc(x):
    return html.escape(str(x))


def money(v, sign=True):
    return f"{'+' if sign and v > 0 else ''}{'-' if v < 0 else ''}${abs(v):,.2f}"


def equity_svg(bals):
    if len(bals) < 2:
        return '<p class="muted">O gráfico aparece após algumas horas de funcionamento.</p>'
    W, Hh, pl, pr, pt, pb = 640, 220, 48, 12, 12, 26
    xs = [t for t, _ in bals]
    ys = [b for _, b in bals]
    x0, x1 = min(xs), max(xs)
    lo, hi = min(ys), max(ys)
    pad = max((hi - lo) * 0.1, 1)
    lo, hi = lo - pad, hi + pad

    def X(t):
        return pl + (t - x0) / max(x1 - x0, 1) * (W - pl - pr)

    def Y(v):
        return pt + (hi - v) / (hi - lo) * (Hh - pt - pb)

    pts = " ".join(f"{X(t):.1f},{Y(v):.1f}" for t, v in bals)
    grid = ""
    for i in range(4):
        v = lo + (hi - lo) * i / 3
        grid += (f'<line x1="{pl}" x2="{W-pr}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" class="grid"/>'
                 f'<text x="{pl-6}" y="{Y(v)+4:.1f}" class="axis" text-anchor="end">${v:,.0f}</text>')
    labels = ""
    for t in (x0, x1):
        labels += (f'<text x="{X(t):.1f}" y="{Hh-6}" class="axis" text-anchor="{"start" if t == x0 else "end"}">'
                   f'{datetime.fromtimestamp(t/1000, tz=BRT).strftime("%d/%m %Hh")}</text>')
    step = max(1, len(bals) // 60)
    hits = "".join(
        f'<g class="hit"><circle cx="{X(t):.1f}" cy="{Y(v):.1f}" r="9" fill="transparent"/>'
        f'<circle cx="{X(t):.1f}" cy="{Y(v):.1f}" r="4" class="dot"/>'
        f'<title>{datetime.fromtimestamp(t/1000, tz=BRT).strftime("%d/%m %H:%M")} — ${v:,.2f}</title></g>'
        for t, v in bals[::step] + [bals[-1]])
    return (f'<svg viewBox="0 0 {W} {Hh}" role="img" aria-label="Evolução da banca">{grid}{labels}'
            f'<polyline points="{pts}" class="line"/>{hits}</svg>')


def daily_svg(days):
    W, Hh, pt, pb = 640, 170, 14, 26
    m = max([abs(v) for _, v in days] + [1])
    zero = pt + (Hh - pt - pb) / 2
    bw = (W - 20) / len(days)
    out = f'<line x1="10" x2="{W-10}" y1="{zero}" y2="{zero}" class="grid"/>'
    for i, (d, v) in enumerate(days):
        h = abs(v) / m * ((Hh - pt - pb) / 2)
        x = 10 + i * bw + 2
        y = zero - h if v >= 0 else zero
        cls = "pos" if v >= 0 else "neg"
        out += (f'<g class="hit"><rect x="{x:.1f}" y="{pt}" width="{bw-4:.1f}" height="{Hh-pt-pb}" fill="transparent"/>'
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw-4:.1f}" height="{max(h, 0.5):.1f}" rx="3" class="{cls}"/>'
                f'<title>{d}: {money(v)}</title></g>')
        if i % 2 == 1 or len(days) <= 7:
            out += f'<text x="{x + (bw-4)/2:.1f}" y="{Hh-6}" class="axis" text-anchor="middle">{d}</text>'
    return f'<svg viewBox="0 0 {W} {Hh}" role="img" aria-label="Resultado por dia">{out}</svg>'


def page():
    bal, avail, pos, orders = _account()
    now = int(time.time() * 1000)
    s = stats.compute(now)
    upnl = sum(float(p["unRealizedProfit"]) for p in pos)
    base = s["start_bal"] or bal
    total_pct = 100 * (bal + upnl - base) / base if base else 0

    open_rows = ""
    opened = {o["sym"]: o for o in s["open"]}
    for p in pos:
        sym = p["symbol"]
        o = opened.get(sym, {})
        age = f"{(now - o['t']) / 3_600_000:.0f}h" if o.get("t") else "—"
        limit = stats.fmt_t(o["t"] + int(C.MAX_HOURS * 3_600_000)) if o.get("t") else "—"
        if o.get("exc_t"):
            limit = f"<span class='exc'>⚠️ exceção até {stats.fmt_t(o['exc_t'] + int(C.EXC_MAX_DAYS * 86_400_000))}</span>"
        u = float(p["unRealizedProfit"])
        open_rows += (f"<tr><td><b>{esc(sym.replace('USDT',''))}</b></td><td>{esc(p['positionAmt'])}</td>"
                      f"<td>{float(p['entryPrice']):.4g}</td><td>{float(p['markPrice']):.4g}</td>"
                      f"<td class='{'up' if u >= 0 else 'down'}'>{money(u)}</td><td>{age}</td><td>{limit}</td>"
                      f"<td>{'✓' if o.get('tp1_t') else '—'}</td></tr>")
    for od in orders:
        open_rows += (f"<tr class='muted'><td><b>{esc(od['symbol'].replace('USDT',''))}</b></td><td>{esc(od['origQty'])}</td>"
                      f"<td colspan='6'>compra pendente a {esc(od['price'])} (média Bollinger 5m)</td></tr>")
    if not open_rows:
        open_rows = "<tr><td colspan='8' class='muted'>Nenhuma posição aberta — aguardando sinal.</td></tr>"

    hist = ""
    for o in s["closed"][::-1][:50]:
        pct = 100 * o["pnl"] / o["margin"] if o.get("margin") else 0
        dur = (o["close_t"] - o["t"]) / 3_600_000
        hist += (f"<tr><td>{stats.fmt_t(o['close_t'])}</td><td><b>{esc(o['sym'].replace('USDT',''))}</b></td>"
                 f"<td>{o['entry']:.4g}</td><td class='{'up' if o['pnl'] >= 0 else 'down'}'>{money(o['pnl'])}</td>"
                 f"<td>{pct:+.1f}%</td><td>{dur:.1f}h</td><td>{esc(stats.REASONS.get(o.get('reason'), o.get('reason','')))}</td></tr>")
    if not hist:
        hist = "<tr><td colspan='7' class='muted'>Ainda não há operações fechadas.</td></tr>"

    def tile(label, value, sub="", cls=""):
        return f"<div class='tile'><div class='lbl'>{label}</div><div class='val {cls}'>{value}</div><div class='sub'>{sub}</div></div>"

    tiles = "".join([
        tile("Banca", f"${bal + upnl:,.2f}", f"início ${base:,.2f} · {total_pct:+.1f}%"),
        tile("Hoje", money(s["today"]), "operações fechadas", "up" if s["today"] >= 0 else "down"),
        tile("7 dias", money(s["week"]), "", "up" if s["week"] >= 0 else "down"),
        tile("Total", money(s["total"]), f"{s['n']} operações", "up" if s["total"] >= 0 else "down"),
        tile("Acertos", f"{s['winrate']:.0f}%", f"{s['wins']} de {s['n']}"),
        tile("Em aberto", money(upnl), f"{len(pos)} posição(ões)", "up" if upnl >= 0 else "down"),
    ])
    mode = "SIMULAÇÃO" if C.DRY_RUN else "REAL"
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="refresh" content="60">
<title>Painel do Robô</title><style>
:root{{--bg:#f6f6f4;--card:#fcfcfb;--line:#e4e3de;--t1:#0b0b0b;--t2:#52514e;--t3:#8a897f;--up:#2a78d6;--down:#e34948;--series:#2a78d6}}
@media (prefers-color-scheme:dark){{:root{{--bg:#111110;--card:#1a1a19;--line:#2e2e2b;--t1:#fff;--t2:#c3c2b7;--t3:#8f8e85;--up:#3987e5;--down:#e66767;--series:#3987e5}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--t1);font:15px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}}
main{{max-width:980px;margin:0 auto;padding:20px 16px 40px}}h1{{font-size:20px;margin:0}}h2{{font-size:15px;margin:0 0 10px;color:var(--t2);font-weight:600}}
header{{display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:6px;margin-bottom:16px}}
.badge{{font-size:12px;padding:2px 8px;border-radius:99px;border:1px solid var(--line);color:var(--t2)}}
.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr));gap:10px;margin-bottom:14px}}
.tile,.card{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px}}
.lbl{{font-size:12px;color:var(--t2)}}.val{{font-size:22px;font-weight:650;margin-top:2px;font-variant-numeric:tabular-nums}}.sub{{font-size:12px;color:var(--t3)}}
.card{{margin-bottom:14px;overflow-x:auto}}svg{{width:100%;height:auto;display:block}}
.line{{fill:none;stroke:var(--series);stroke-width:2;stroke-linejoin:round}}.dot{{fill:var(--series);stroke:var(--card);stroke-width:2;opacity:0}}
.hit:hover .dot{{opacity:1}}.hit:hover rect.pos,.hit:hover rect.neg{{opacity:.8}}
.grid{{stroke:var(--line);stroke-width:1}}.axis{{fill:var(--t3);font-size:13px}}.pos{{fill:var(--up)}}.neg{{fill:var(--down)}}
table{{width:100%;border-collapse:collapse;font-size:14px;font-variant-numeric:tabular-nums}}th,td{{text-align:left;padding:7px 8px;border-bottom:1px solid var(--line);white-space:nowrap}}
th{{font-size:12px;color:var(--t2);font-weight:600}}.up{{color:var(--t1)}}.up::before{{content:"▲ ";color:var(--up);font-size:.75em}}
.down{{color:var(--t1)}}.down::before{{content:"▼ ";color:var(--down);font-size:.75em}}.muted{{color:var(--t3)}}.exc{{font-weight:600}}
.val.up::before,.val.down::before{{font-size:.55em}}footer{{font-size:12px;color:var(--t3);margin-top:8px}}
</style></head><body><main>
<header><h1>Painel do Robô</h1><span class="badge">modo {mode} · {C.LEVERAGE}x · {C.MARGIN_PCT*100:g}% · máx {C.MAX_POSITIONS} · exceção {'ligada' if C.EXC_ENABLED else 'desligada'}</span></header>
<div class="tiles">{tiles}</div>
<div class="card"><h2>Evolução da banca</h2>{equity_svg(s['bals'])}</div>
<div class="card"><h2>Resultado por dia (últimos 14 dias)</h2>{daily_svg(s['days'])}</div>
<div class="card"><h2>Posições abertas</h2><table><tr><th>Ativo</th><th>Qtd</th><th>Entrada</th><th>Agora</th><th>Resultado</th><th>Tempo</th><th>Prazo</th><th>TP1</th></tr>{open_rows}</table></div>
<div class="card"><h2>Histórico</h2><table><tr><th>Fechou</th><th>Ativo</th><th>Entrada</th><th>Resultado</th><th>% margem</th><th>Duração</th><th>Saída</th></tr>{hist}</table></div>
<footer>Atualiza sozinho a cada 60 s · {datetime.now(BRT).strftime('%d/%m %H:%M')} (Brasília) · somente leitura</footer>
</main></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _auth(self):
        want = "Basic " + base64.b64encode(f"robo:{C.PANEL_PASSWORD}".encode()).decode()
        if self.headers.get("Authorization") == want:
            return True
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="Painel do Robo"')
        self.end_headers()
        return False

    def do_GET(self):
        if not self._auth():
            return
        try:
            body = page().encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
        except Exception as e:  # noqa: BLE001
            body = f"Erro ao montar o painel: {esc(e)}".encode()
            self.send_response(500)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def start(robo):
    global _cli
    _cli = Client(C.BINANCE_API_KEY, C.BINANCE_API_SECRET)
    _cli.offset = robo.cli.offset
    srv = ThreadingHTTPServer(("0.0.0.0", C.PANEL_PORT), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print(f"Painel no ar na porta {C.PANEL_PORT}", flush=True)

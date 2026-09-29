"""Números consolidados do robô a partir do diário (journal)."""
from datetime import datetime, timezone, timedelta

import journal

BRT = timezone(timedelta(hours=-3))
DAY = 86_400_000
REASONS = {"PRAZO": "prazo 48h", "ALVO+TRAILING": "alvo + trailing", "ALVO/TRAILING": "alvo",
           "EXC_BE": "exceção: voltou ao zero", "EXC_PRAZO": "exceção: prazo máximo"}


def fmt_t(ms):
    return datetime.fromtimestamp(ms / 1000, tz=BRT).strftime("%d/%m %H:%M")


def closed():
    return [o for o in journal.trades() if "close_t" in o]


def compute(now_ms):
    cl = closed()
    wins = [o for o in cl if o["pnl"] > 0]
    total = sum(o["pnl"] for o in cl)
    day0 = int(datetime.now(BRT).replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)
    today = sum(o["pnl"] for o in cl if o["close_t"] >= day0)
    week = sum(o["pnl"] for o in cl if o["close_t"] >= now_ms - 7 * DAY)
    bals = journal.balances()
    start_bal = bals[0][1] if bals else None
    # lucro por dia (BRT), últimos 14 dias
    daily = {}
    for o in cl:
        d = datetime.fromtimestamp(o["close_t"] / 1000, tz=BRT).strftime("%d/%m")
        daily[d] = daily.get(d, 0) + o["pnl"]
    days = []
    for i in range(13, -1, -1):
        d = (datetime.now(BRT) - timedelta(days=i)).strftime("%d/%m")
        days.append((d, round(daily.get(d, 0.0), 2)))
    return dict(n=len(cl), wins=len(wins), winrate=(100 * len(wins) / len(cl)) if cl else 0,
                total=total, today=today, week=week, start_bal=start_bal, bals=bals, days=days,
                best=max((o["pnl"] for o in cl), default=0), worst=min((o["pnl"] for o in cl), default=0),
                closed=cl, open=[o for o in journal.trades() if "close_t" not in o])


def m(v):
    return f"{'+' if v > 0 else '-' if v < 0 else ''}${abs(v):.2f}"


def summary_text(bal):
    import time
    s = compute(int(time.time() * 1000))
    lines = ["📊 Resumo do robô",
             f"Banca: ${bal:.2f}" + (f" (início ${s['start_bal']:.2f})" if s["start_bal"] else ""),
             f"Hoje: {m(s['today'])} · 7 dias: {m(s['week'])} · total: {m(s['total'])}",
             f"Operações fechadas: {s['n']} · acertos {s['wins']} ({s['winrate']:.0f}%)"]
    if s["n"]:
        lines.append(f"Melhor {m(s['best'])} · pior {m(s['worst'])}")
    lines.append(f"Abertas agora: {len(s['open'])}")
    return "\n".join(lines)


def history_text(n=10):
    cl = closed()[-n:][::-1]
    if not cl:
        return "📜 Ainda não há operações fechadas."
    out = ["📜 Últimas operações:"]
    for o in cl:
        pct = 100 * o["pnl"] / o["margin"] if o.get("margin") else 0
        out.append(f"{'🟢' if o['pnl'] > 0 else '🔴'} {fmt_t(o['close_t'])} {o['sym'].replace('USDT','')} "
                   f"{m(o['pnl'])} ({pct:+.1f}% margem) · {REASONS.get(o.get('reason'), o.get('reason', ''))}")
    return "\n".join(out)

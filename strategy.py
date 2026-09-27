"""Indicadores e checklist — mesma lógica usada nos backtests.

Todas as funções recebem klines no formato da Binance
[openTime, open, high, low, close, volume, closeTime, ...] e usam só candles FECHADOS.
"""
DAY = 86_400_000


def closed(klines, now_ms):
    return [k for k in klines if int(k[6]) < now_ms]


def ema(values, n):
    k = 2 / (n + 1)
    e = values[0]
    out = []
    for v in values:
        e = v * k + e * (1 - k)
        out.append(e)
    return out


def rsi_wilder(closes, n=14):
    if len(closes) <= n + 1:
        return None
    g = l = 0.0
    for i in range(1, n + 1):
        d = closes[i] - closes[i - 1]
        g += max(d, 0)
        l += max(-d, 0)
    g /= n
    l /= n
    for i in range(n + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        g = (g * (n - 1) + max(d, 0)) / n
        l = (l * (n - 1) + max(-d, 0)) / n
    return 100 - 100 / (1 + g / l) if l else 100.0


def btc_filter(btc_1h, btc_1d, now_ms):
    """Ponto 1: último fechamento de 1h do BTC acima da média dos 50 fechamentos diários anteriores ao dia atual (UTC)."""
    last = btc_1h[-1]
    t = int(last[0])
    day0 = t - t % DAY
    prev = [float(k[4]) for k in btc_1d if int(k[0]) < day0][-50:]
    if len(prev) < 50:
        return False
    return float(last[4]) > sum(prev) / 50


def checklist(k1h, k4h, btc_ok):
    """Retorna (pontos, detalhes, volume_relativo). k1h/k4h já filtrados só com candles fechados."""
    c = [float(k[4]) for k in k1h]
    h = [float(k[2]) for k in k1h]
    v = [float(k[5]) for k in k1h]
    c4 = [float(k[4]) for k in k4h]
    e50 = ema(c4, 50)
    p2 = c4[-1] > e50[-1] and e50[-1] > e50[-7]
    r = rsi_wilder(c)
    p3 = r is not None and 45 <= r <= 65
    va = sum(v[-21:-1]) / 20
    p4 = va > 0 and v[-1] > 1.5 * va
    p5 = c[-1] < max(h[-24:]) * 0.99
    pts = sum([btc_ok, p2, p3, p4, p5])
    det = dict(btc=btc_ok, tend4h=p2, rsi=round(r, 1) if r else None, rsi_ok=p3, vol=round(v[-1] / va, 2) if va else 0, vol_ok=p4, abaixo_max=p5)
    return pts, det, (v[-1] / va if va else 0)


def bollinger_mid(k5m_closed, n=20):
    cl = [float(k[4]) for k in k5m_closed[-n:]]
    return sum(cl) / len(cl) if len(cl) == n else None

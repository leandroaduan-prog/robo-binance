"""Diário do robô: guarda aberturas, fechamentos e a banca por hora em data/journal.jsonl."""
import json
import os
import threading

import config as C

_lock = threading.Lock()
PATH = os.path.join(C.DATA_DIR, "journal.jsonl")


def add(rec):
    os.makedirs(C.DATA_DIR, exist_ok=True)
    with _lock, open(PATH, "a") as f:
        f.write(json.dumps(rec) + "\n")


def read():
    if not os.path.exists(PATH):
        return []
    out = []
    with _lock, open(PATH) as f:
        for line in f:
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
    return out


def trades():
    """Lista de operações: aberturas pareadas com fechamentos (abertas ficam sem 'close')."""
    ops, open_by_sym = [], {}
    for r in read():
        if r.get("type") == "open":
            op = dict(r)
            ops.append(op)
            open_by_sym[r["sym"]] = op
        elif r.get("type") == "tp1" and r["sym"] in open_by_sym:
            open_by_sym[r["sym"]]["tp1_t"] = r["t"]
        elif r.get("type") == "exc" and r["sym"] in open_by_sym:
            open_by_sym[r["sym"]]["exc_t"] = r["t"]
        elif r.get("type") == "close" and r["sym"] in open_by_sym:
            op = open_by_sym.pop(r["sym"])
            op.update(close_t=r["t"], pnl=r["pnl"], reason=r.get("reason", ""))
    return ops


def open_syms():
    return {o["sym"]: o for o in trades() if "close_t" not in o}


def balances():
    return [(r["t"], r["bal"]) for r in read() if r.get("type") == "bal"]

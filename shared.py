"""Coordenação entre robôs no mesmo servidor: um não abre posição numa moeda que o outro já está usando.

Cada robô publica, a cada ciclo, as moedas que estão ocupadas (posição aberta, exceção ou ordem de entrada
pendente) num arquivo da pasta compartilhada. Antes de abrir uma entrada, lê o que os outros publicaram.
"""
import fcntl
import json
import os
import re
import time
from contextlib import contextmanager

import config as C

STALE_SEC = 600  # publicação mais velha que 10 min é ignorada (robô parado)


def _me():
    return re.sub(r"[^a-z0-9]+", "-", C.ROBOT_NAME.lower()).strip("-") or "robo"


def _dir():
    if not C.AVOID_PEER_DUPES:
        return None
    try:
        os.makedirs(C.SHARED_DIR, exist_ok=True)
        return C.SHARED_DIR
    except OSError:
        return None


def publish(syms):
    d = _dir()
    if not d:
        return
    path = os.path.join(d, f"{_me()}.json")
    tmp = path + ".tmp"
    try:
        with open(tmp, "w") as f:
            json.dump({"syms": sorted(syms), "t": time.time()}, f)
        os.replace(tmp, path)
    except OSError as e:
        print("Falha ao publicar moedas ocupadas:", e, flush=True)


def peers_busy():
    d = _dir()
    if not d:
        return set()
    out, me = set(), f"{_me()}.json"
    try:
        names = os.listdir(d)
    except OSError:
        return set()
    for n in names:
        if not n.endswith(".json") or n == me:
            continue
        try:
            with open(os.path.join(d, n)) as f:
                data = json.load(f)
            if time.time() - float(data.get("t", 0)) <= STALE_SEC:
                out |= set(data.get("syms", []))
        except (OSError, ValueError):
            continue
    return out


@contextmanager
def lock():
    d = _dir()
    if not d:
        yield
        return
    f = open(os.path.join(d, ".lock"), "w")
    try:
        fcntl.flock(f, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(f, fcntl.LOCK_UN)
        f.close()

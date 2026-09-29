"""Cliente mínimo da API de Futuros USDⓈ-M da Binance."""
import hashlib
import hmac
import time
from urllib.parse import urlencode

import requests

BASE = "https://fapi.binance.com"


class BinanceError(Exception):
    def __init__(self, code, msg, status=None):
        super().__init__(f"Binance {code}: {msg}")
        self.code, self.msg, self.status = code, msg, status


class Client:
    def __init__(self, key, secret):
        self.key, self.secret = key, secret.encode()
        self.s = requests.Session()
        if key:
            self.s.headers["X-MBX-APIKEY"] = key
        self.offset = 0

    # ---------- transporte ----------
    def _handle(self, r):
        try:
            data = r.json()
        except ValueError:
            r.raise_for_status()
            raise
        if r.status_code >= 400:
            if isinstance(data, dict):
                raise BinanceError(data.get("code"), data.get("msg"), r.status_code)
            raise BinanceError(r.status_code, str(data), r.status_code)
        return data

    def public(self, path, **params):
        return self._handle(self.s.get(BASE + path, params=params, timeout=15))

    def signed(self, method, path, **params):
        params = {k: (str(v).lower() if isinstance(v, bool) else v) for k, v in params.items() if v is not None}
        params["timestamp"] = int(time.time() * 1000) + self.offset
        params["recvWindow"] = 10000
        q = urlencode(params)
        sig = hmac.new(self.secret, q.encode(), hashlib.sha256).hexdigest()
        return self._handle(self.s.request(method, f"{BASE}{path}?{q}&signature={sig}", timeout=15))

    def sync_time(self):
        self.offset = self.public("/fapi/v1/time")["serverTime"] - int(time.time() * 1000)

    # ---------- mercado ----------
    def exchange_info(self):
        return self.public("/fapi/v1/exchangeInfo")

    def klines(self, symbol, interval, limit):
        return self.public("/fapi/v1/klines", symbol=symbol, interval=interval, limit=limit)

    def price(self, symbol):
        return float(self.public("/fapi/v1/ticker/price", symbol=symbol)["price"])

    # ---------- conta ----------
    def usdt_balance(self):
        for b in self.signed("GET", "/fapi/v3/balance"):
            if b["asset"] == "USDT":
                return float(b["balance"]), float(b["availableBalance"])
        return 0.0, 0.0

    def positions(self):
        return self.signed("GET", "/fapi/v2/positionRisk")

    def open_orders(self):
        return self.signed("GET", "/fapi/v1/openOrders")

    def open_algo_orders(self):
        r = self.signed("GET", "/fapi/v1/openAlgoOrders")
        return r.get("orders", r) if isinstance(r, dict) else r

    # ---------- ordens ----------
    def new_order(self, **p):
        return self.signed("POST", "/fapi/v1/order", **p)

    def modify_order(self, **p):
        return self.signed("PUT", "/fapi/v1/order", **p)

    def cancel_order(self, symbol, client_id):
        return self.signed("DELETE", "/fapi/v1/order", symbol=symbol, origClientOrderId=client_id)

    def new_algo_order(self, **p):
        return self.signed("POST", "/fapi/v1/algoOrder", algoType="CONDITIONAL", **p)

    def cancel_algo_order(self, client_algo_id):
        return self.signed("DELETE", "/fapi/v1/algoOrder", clientAlgoId=client_algo_id)

    def set_leverage(self, symbol, leverage):
        return self.signed("POST", "/fapi/v1/leverage", symbol=symbol, leverage=leverage)

    def set_isolated(self, symbol):
        try:
            return self.signed("POST", "/fapi/v1/marginType", symbol=symbol, marginType="ISOLATED")
        except BinanceError as e:
            if e.code == -4046:  # já está isolada
                return None
            raise

    def income(self, symbol=None, start=None, income_type=None, limit=1000):
        return self.signed("GET", "/fapi/v1/income", symbol=symbol, startTime=start,
                           incomeType=income_type, limit=limit)

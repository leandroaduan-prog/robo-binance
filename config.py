"""Configurações do robô. Tudo pode ser mudado por variável de ambiente no Render."""
import os


def _env(name, default):
    v = os.getenv(name)
    return default if v is None or v.strip() == "" else v.strip()


BINANCE_API_KEY = _env("BINANCE_API_KEY", "")
BINANCE_API_SECRET = _env("BINANCE_API_SECRET", "")
TELEGRAM_BOT_TOKEN = _env("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = _env("TELEGRAM_CHAT_ID", "")

# true = só simula e avisa no Telegram, não envia ordens de compra/venda
DRY_RUN = _env("DRY_RUN", "true").lower() in ("1", "true", "sim", "yes")

SYMBOLS = [s.strip().upper() for s in _env("SYMBOLS", "SUIUSDT,SOLUSDT,ZECUSDT,BNBUSDT,ETHUSDT,BTCUSDT").split(",") if s.strip()]
LEVERAGE = int(_env("LEVERAGE", "2"))
MARGIN_PCT = float(_env("MARGIN_PCT", "0.375"))        # fração da banca usada como margem por entrada
MAX_POSITIONS = int(_env("MAX_POSITIONS", "2"))
MIN_SCORE = int(_env("MIN_SCORE", "4"))                # pontos mínimos do checklist (de 5)
ENTRY_VALID_HOURS = float(_env("ENTRY_VALID_HOURS", "4"))
TP1_PCT = float(_env("TP1_PCT", "0.02"))               # +2%
TP1_FRACTION = float(_env("TP1_FRACTION", "0.5"))      # metade sai no TP1
TRAIL_CALLBACK = float(_env("TRAIL_CALLBACK", "1.0"))  # trailing 1% abaixo da máxima
MAX_HOURS = float(_env("MAX_HOURS", "48"))             # saída por tempo
LOOP_SECONDS = int(_env("LOOP_SECONDS", "20"))

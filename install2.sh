#!/usr/bin/env bash
# Instala o ROBÔ 2 (BCH, BNB, LTC, NEAR, SOL, UNI) no mesmo servidor do robô 1.
# Use outra subconta da Binance e outro bot do Telegram. Rode com: sudo bash install2.sh
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
NAME=robo-binance-2
ENV=/etc/$NAME.env
PORT=8081

if [ "$DIR" = "/root/robo-binance" ]; then
  echo "ERRO: rode este script a partir da pasta ~/robo-binance-2 (cópia separada), não da pasta do robô 1."
  exit 1
fi

echo "== Instalando Python =="
apt-get update -qq && apt-get install -y -qq python3 python3-venv git >/dev/null
python3 -m venv "$DIR/venv"
"$DIR/venv/bin/pip" install -q -r "$DIR/requirements.txt"

if [ ! -f "$ENV" ]; then
  echo
  echo "== Chaves do ROBÔ 2 (o que você digitar NÃO aparece na tela, é normal) =="
  read -rsp "BINANCE_API_KEY (subconta nova): " K; echo
  read -rsp "BINANCE_API_SECRET (subconta nova): " S; echo
  read -rsp "TELEGRAM_BOT_TOKEN (bot novo): " T; echo
  read -rp  "TELEGRAM_CHAT_ID (o mesmo de sempre): " C; echo
  read -rp  "Senha do painel do robô 2 (letras e números): " P; echo
  umask 077
  cat > "$ENV" <<CFG
BINANCE_API_KEY=$K
BINANCE_API_SECRET=$S
TELEGRAM_BOT_TOKEN=$T
TELEGRAM_CHAT_ID=$C
DRY_RUN=false
PYTHONUNBUFFERED=1
ROBOT_NAME=Robô 2
SYMBOLS=BCHUSDT,BNBUSDT,LTCUSDT,NEARUSDT,SOLUSDT,UNIUSDT
SIGNAL_DELAY_SEC=60
PANEL_PASSWORD=$P
PANEL_PORT=$PORT
CFG
  chmod 600 "$ENV"
fi

if command -v ufw >/dev/null && ufw status | grep -q "Status: active"; then ufw allow $PORT/tcp >/dev/null; fi

cat > /etc/systemd/system/$NAME.service <<SVC
[Unit]
Description=Robo Binance 2
After=network-online.target
Wants=network-online.target

[Service]
WorkingDirectory=$DIR
EnvironmentFile=$ENV
ExecStart=$DIR/venv/bin/python $DIR/bot.py
Restart=always
RestartSec=15

[Install]
WantedBy=multi-user.target
SVC

systemctl daemon-reload
systemctl enable --now $NAME
sleep 6
systemctl --no-pager status $NAME | head -5
IP=$(curl -s https://api.ipify.org || hostname -I | awk '{print $1}')
echo
echo "== Pronto! Confira a mensagem 'Robô 2 iniciado' no Telegram (no bot novo). =="
echo "Painel:        http://$IP:$PORT  (usuário: robo)"
echo "Ver logs:      journalctl -u $NAME -f"
echo "Reiniciar:     systemctl restart $NAME"
echo "Atualizar:     cd $DIR && git pull && systemctl restart $NAME"

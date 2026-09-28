#!/usr/bin/env bash
# Instalação do robô num servidor Ubuntu (DigitalOcean). Rode com: sudo bash install.sh
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
ENV=/etc/robo-binance.env
echo "== Instalando Python =="
apt-get update -qq && apt-get install -y -qq python3 python3-venv git >/dev/null
python3 -m venv "$DIR/venv"
"$DIR/venv/bin/pip" install -q -r "$DIR/requirements.txt"

if [ ! -f "$ENV" ]; then
  echo
  echo "== Cole suas chaves (o que você digitar NÃO aparece na tela, é normal) =="
  read -rsp "BINANCE_API_KEY: " K; echo
  read -rsp "BINANCE_API_SECRET: " S; echo
  read -rsp "TELEGRAM_BOT_TOKEN: " T; echo
  read -rp  "TELEGRAM_CHAT_ID: " C; echo
  umask 077
  cat > "$ENV" <<CFG
BINANCE_API_KEY=$K
BINANCE_API_SECRET=$S
TELEGRAM_BOT_TOKEN=$T
TELEGRAM_CHAT_ID=$C
DRY_RUN=false
PYTHONUNBUFFERED=1
CFG
  chmod 600 "$ENV"
fi

cat > /etc/systemd/system/robo-binance.service <<SVC
[Unit]
Description=Robo Binance
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
systemctl enable --now robo-binance
sleep 5
systemctl --no-pager status robo-binance | head -5
echo
echo "== Pronto! Confira a mensagem 'Robô iniciado' no Telegram. =="
echo "Ver logs:      journalctl -u robo-binance -f"
echo "Reiniciar:     systemctl restart robo-binance"
echo "Atualizar:     cd $DIR && git pull && systemctl restart robo-binance"

#!/usr/bin/env bash
# Liga o painel web do robô. Rode com: sudo bash painel.sh
set -e
ENV=/etc/robo-binance.env
read -rp "Crie uma senha para o painel (letras e números): " P
sed -i '/^PANEL_PASSWORD=/d' "$ENV"
echo "PANEL_PASSWORD=$P" >> "$ENV"
if command -v ufw >/dev/null && ufw status | grep -q "Status: active"; then ufw allow 8080/tcp >/dev/null; fi
systemctl restart robo-binance
sleep 4
IP=$(curl -s https://api.ipify.org || hostname -I | awk '{print $1}')
echo
echo "== Painel ligado! =="
echo "Endereço:  http://$IP:8080"
echo "Usuário:   robo"
echo "Senha:     a que você acabou de criar"

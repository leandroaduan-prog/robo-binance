# Robô Binance — Futuros USDⓈ-M

Robô 100% automático que segue as regras validadas nos backtests. Roda num servidor com IP fixo, avisa tudo no Telegram e não precisa de confirmação por ordem.

## As regras

| Item | Regra |
|---|---|
| Ativos | SUI, SOL, ZEC, BNB, ETH, BTC (ETH e BTC entram sozinhos quando a banca atinge o mínimo da Binance) |
| Direção | Só compra (long) |
| Sinal | Checklist ≥ 4 de 5 no candle de 1h **fechado** |
| Entrada | Compra LIMIT na **média de Bollinger (20) do 5m**, **reposicionada a cada 5 min**, válida por 4h |
| Tamanho | **37,5% da banca** como margem por entrada, **2x isolada** |
| Vagas | Máximo **2 posições** (ordens pendentes também ocupam vaga) |
| Saída 1 | **50% no +2%** (LIMIT reduce-only) |
| Saída 2 | **50% em trailing stop de 1%**, ativado no +2% (fica na própria Binance) |
| Prazo | O que sobrar fecha a mercado em **48h** |
| Stop de prejuízo | **Não tem** (testado: todos os níveis pioraram o resultado) |
| Prioridade | Se houver mais sinais que vagas, entra o de maior volume relativo |

**Checklist (1 ponto cada):**
1. BTC (1h) acima da média dos 50 fechamentos diários;
2. 4h acima da EMA50, com a EMA50 subindo (maior que 6 candles atrás);
3. RSI(14) de 1h entre 45 e 65;
4. Volume da última hora > 1,5× a média das 20 anteriores;
5. Preço pelo menos 1% abaixo da máxima de 24h.

**Backtest ($1.000):** 30 dias +48% · 115 dias +101% · 3 anos +257% (pior queda −63%, zero liquidações). Resultado passado não garante resultado futuro.

## Comandos no Telegram

- `/status` — banca, posições e ordens pendentes
- `/checklist` — pontuação de cada ativo agora
- `/pausar` — para de abrir novas entradas (as posições abertas continuam sendo geridas)
- `/retomar` — volta a abrir entradas

Se o robô reiniciar, ele volta **despausado**.

## Passo a passo — servidor com IP fixo (DigitalOcean)

A Binance exige chave com IP fixo para operar; por isso o robô roda num servidor próprio (~US$ 6/mês).

1. **Telegram** — bot criado no @BotFather + seu ID do @userinfobot.
2. **DigitalOcean** — Create → Droplets → Ubuntu 24.04 · Frankfurt · Basic/Regular US$ 6 · senha (Password). Anote o **IPv4**.
3. **Binance** — na subconta do robô: abrir **Futuros** → criar API (Leitura + Futuros, sem saque/transferência) **restrita ao IPv4 do servidor**. Depositar USDT e transferir para a carteira **Futuros USDⓈ-M**.
4. **Instalar** — no Droplet, abra o **Console** (navegador) e rode:
   ```
   git clone https://github.com/leandroaduan-prog/robo-binance.git && cd robo-binance && sudo bash install.sh
   ```
   O script pede as chaves (não aparecem na tela), instala e liga o robô em modo **REAL**, reiniciando sozinho se o servidor reiniciar.
5. **Conferir** — no Telegram chega "Robô iniciado em modo REAL" com o IP do servidor. Mande `/status`.

**Comandos no servidor:** ver logs `journalctl -u robo-binance -f` · reiniciar `systemctl restart robo-binance` · atualizar `cd ~/robo-binance && git pull && systemctl restart robo-binance` · trocar chaves `nano /etc/robo-binance.env`.

### Ajustes sem mexer no código (arquivo /etc/robo-binance.env)
`MARGIN_PCT` (0.375) · `LEVERAGE` (2) · `MAX_POSITIONS` (2) · `TP1_PCT` (0.02) · `TP1_FRACTION` (0.5) · `TRAIL_CALLBACK` (1.0) · `MAX_HOURS` (48) · `MIN_SCORE` (4) · `SYMBOLS`

## Como o robô se protege
- **Ordens identificadas:** as ordens do robô começam com `rb_`. Posições com ordens de outra origem ficam intocadas.
- **Saídas na Binance:** alvo e trailing ficam registrados na própria Binance. Se o robô cair, eles continuam valendo. Só o prazo de 48h depende do robô estar rodando.
- **Estado recuperável:** ao reiniciar, o robô reconstrói tudo a partir das ordens abertas. Não precisa de banco de dados.
- **Posição pequena demais:** se a Binance recusar a divisão em duas saídas por ficar abaixo do mínimo, o robô usa um alvo único de +2% e te avisa.

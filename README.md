# Robô Binance — Futuros USDⓈ-M

Robô 100% automático que segue as regras validadas nos backtests. Roda no Render (serviço "Background Worker"), avisa tudo no Telegram e não precisa de confirmação por ordem.

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

## Passo a passo (siga nesta ordem)

### 1. Bot do Telegram (5 min)
1. No Telegram, abra **@BotFather** → `/newbot` → escolha um nome → copie o **token**.
2. Abra o seu bot novo e mande **"oi"** (sem isso ele não consegue te escrever).
3. Abra **@userinfobot** → ele mostra seu **Id** (um número). Esse é o `TELEGRAM_CHAT_ID`.

### 2. GitHub (5 min)
1. No GitHub Desktop: **File → New repository** → nome `robo-binance` → **Create**.
2. Copie **todos os arquivos desta pasta** para dentro da pasta do repositório.
3. Faça o **Commit** e depois **Publish repository**, deixando marcado **"Keep this code private"**.

### 3. Render, primeiro em modo simulação (10 min)
1. Em render.com: **New → Blueprint** → conecte o repositório `robo-binance`.
2. O Render lê o `render.yaml`: worker **Starter** (~US$ 7/mês), região **Frankfurt**, `DRY_RUN=true`.
3. Preencha `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID`. Nas chaves da Binance, coloque `x` por enquanto.
4. Crie o serviço. Ele vai dar erro de chave, o que é esperado nesta etapa.
5. No serviço, abra **Connect → Outbound** e anote os **IPs de saída**.

### 4. Chave da API na Binance (10 min)
1. Na conta principal: **Subcontas → Gestão de API** da subconta do robô → **Criar API** (tipo "gerada pelo sistema").
2. Permissões: **Leitura + Futuros**. **Nunca** habilite saque nem transferência.
3. **Restrinja o acesso aos IPs do Render** anotados no passo 3.
4. Cole a API Key e a Secret **direto nas variáveis do Render** (`BINANCE_API_KEY`, `BINANCE_API_SECRET`). **Nunca cole essas chaves em chat.**
5. Salve. O Render reinicia e você recebe no Telegram: **"Robô iniciado em modo SIMULAÇÃO"**.

> Se a Binance não deixar criar chave para a subconta de IA, crie uma subconta comum e transfira o saldo para ela.
> Se aparecer erro 451 ("restricted location"), troque a região do serviço para Singapore e atualize os IPs na chave.

### 5. Simulação por 24–48h
- O robô avisa os sinais e as entradas que faria, sem enviar ordens.
- Use `/status` e `/checklist` para conferir se está tudo funcionando.

### 6. Ligar o modo real
1. As posições antigas (SUI e BNB, abertas fora do robô) são tratadas como manuais: o robô não mexe nelas, mas elas ocupam vaga. O ideal é ligar depois que elas fecharem.
2. No Render, mude `DRY_RUN` para `false` e salve.
3. No Telegram deve aparecer **"Robô iniciado em modo REAL"**.

### Ajustes sem mexer no código (variáveis do Render)
`MARGIN_PCT` (0.375) · `LEVERAGE` (2) · `MAX_POSITIONS` (2) · `TP1_PCT` (0.02) · `TP1_FRACTION` (0.5) · `TRAIL_CALLBACK` (1.0) · `MAX_HOURS` (48) · `MIN_SCORE` (4) · `SYMBOLS`

## Como o robô se protege
- **Ordens identificadas:** as ordens do robô começam com `rb_`. Posições com ordens de outra origem ficam intocadas.
- **Saídas na Binance:** alvo e trailing ficam registrados na própria Binance. Se o robô cair, eles continuam valendo. Só o prazo de 48h depende do robô estar rodando.
- **Estado recuperável:** ao reiniciar, o robô reconstrói tudo a partir das ordens abertas. Não precisa de banco de dados.
- **Posição pequena demais:** se a Binance recusar a divisão em duas saídas por ficar abaixo do mínimo, o robô usa um alvo único de +2% e te avisa.

# BOT SUPERTREND PROFISSIONAL — WEBSOCKET REALTIME

```python
import os
import json
import time
import requests
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo
from threading import Thread
from flask import Flask, jsonify
from websocket import WebSocketApp
from binance.client import Client

# ==========================================
# FLASK
# ==========================================
app = Flask(__name__)

@app.route("/")
def home():
    return "🚀 BOT SUPERTREND WEBSOCKET ONLINE"

@app.route("/dashboard")
def dashboard():
    return jsonify(signals[-100:])

@app.route("/api/signals")
def api_signals():
    return jsonify(signals[-100:])


def run():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


def keep_alive():
    Thread(target=run).start()

# ==========================================
# CONFIG
# ==========================================
TOKEN = os.getenv("TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

BINANCE_KEY = os.getenv("BINANCE_KEY")
BINANCE_SECRET = os.getenv("BINANCE_SECRET")

client = Client(BINANCE_KEY, BINANCE_SECRET)

timezone = ZoneInfo("America/Sao_Paulo")

# ==========================================
# MOEDAS
# ==========================================
symbols = [
    "btcusdt",
    "ethusdt",
    "solusdt",
    "dogeusdt",
    "adausdt",
    "atomusdt",
    "avaxusdt",
    "dotusdt",
    "aptusdt",
    "ondousdt",
    "seiusdt"
]

# ==========================================
# ESTADO
# ==========================================
signals = []
sent_alerts = {}
market_data = {}

# ==========================================
# TELEGRAM
# ==========================================
def send(msg):
    try:
        agora = datetime.now(timezone).strftime("%H:%M:%S")

        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

        requests.post(
            url,
            json={
                "chat_id": CHAT_ID,
                "text": f"{msg}\n\n🕒 {agora} (SC)"
            },
            timeout=10
        )

    except Exception as e:
        print("Erro Telegram:", e)

# ==========================================
# HISTÓRICO INICIAL
# ==========================================
def load_history(symbol):

    klines = client.get_klines(
        symbol=symbol.upper(),
        interval=Client.KLINE_INTERVAL_5MINUTE,
        limit=200
    )

    df = pd.DataFrame(klines, columns=[
        "time","open","high","low","close","volume",
        "close_time","qav","num_trades",
        "taker_base","taker_quote","ignore"
    ])

    df = df[["time","open","high","low","close","volume"]]

    for col in ["open","high","low","close","volume"]:
        df[col] = pd.to_numeric(df[col])

    return df

# ==========================================
# SUPERTREND
# ==========================================
def calculate_supertrend(df, period=10, multiplier=2):

    hl2 = (df['high'] + df['low']) / 2

    df['tr'] = (
        df[['high', 'close']].max(axis=1) -
        df[['low', 'close']].min(axis=1)
    )

    atr = df['tr'].rolling(period).mean()

    upperband = hl2 + (multiplier * atr)
    lowerband = hl2 - (multiplier * atr)

    trend = [True]
    st = [lowerband.iloc[0]]

    for i in range(1, len(df)):

        if df['close'].iloc[i] > st[i - 1]:
            trend.append(True)

        elif df['close'].iloc[i] < st[i - 1]:
            trend.append(False)

        else:
            trend.append(trend[i - 1])

        if trend[i]:
            st.append(lowerband.iloc[i])
        else:
            st.append(upperband.iloc[i])

    df['trend'] = trend
    df['supertrend'] = st

    return df

# ==========================================
# SCORE DE FORÇA
# ==========================================
def calculate_score(df):

    last = df.iloc[-1]

    score = 0

    body = abs(last['close'] - last['open'])
    candle_size = last['high'] - last['low']

    if candle_size > 0:
        body_percent = (body / candle_size) * 100
    else:
        body_percent = 0

    # FORÇA DO CANDLE
    if body_percent > 70:
        score += 35

    elif body_percent > 50:
        score += 20

    # VOLUME
    vol_ma = df['volume'].rolling(20).mean().iloc[-1]

    if last['volume'] > vol_ma * 2:
        score += 35

    elif last['volume'] > vol_ma * 1.5:
        score += 20

    # DISTÂNCIA DA ST
    dist = abs(
        (last['close'] - last['supertrend']) /
        last['close']
    ) * 100

    if dist > 1:
        score += 20

    else:
        score += 10

    # MOMENTUM
    if abs(last['close'] - df['close'].iloc[-2]) > 0:
        score += 10

    return min(score, 100)

# ==========================================
# ALERTAS
# ==========================================
def process_signal(symbol, df):

    df = calculate_supertrend(df)

    last = df.iloc[-1]
    prev = df.iloc[-2]

    virou_compra = (
        prev['trend'] == False and
        last['trend'] == True
    )

    virou_venda = (
        prev['trend'] == True and
        last['trend'] == False
    )

    score = calculate_score(df)

    preco = round(last['close'], 4)

    # ==========================================
    # COMPRA
    # ==========================================
    if virou_compra and sent_alerts.get(symbol) != 'buy':

        msg = f"""
🟢⬆️ VIRADA SUPERTREND REALTIME

📊 {symbol.upper()}
⏱ TIMEFRAME: 5m

💰 PREÇO:
{preco}

📈 SUPERTREND VIROU PARA ALTA

🔥 FORÇA:
{score}%

🎯 Entrada:
{preco}

🛑 Stop:
{round(last['supertrend'],4)}

⚡ DETECÇÃO INTRABAR
⚡ WEBSOCKET REALTIME
"""

        send(msg)

        signals.append({
            "symbol": symbol.upper(),
            "type": "BUY",
            "price": preco,
            "score": score,
            "time": datetime.now(timezone).strftime("%H:%M:%S")
        })

        sent_alerts[symbol] = 'buy'

    # ==========================================
    # VENDA
    # ==========================================
    elif virou_venda and sent_alerts.get(symbol) != 'sell':

        msg = f"""
🔴⬇️ VIRADA SUPERTREND REALTIME

📊 {symbol.upper()}
⏱ TIMEFRAME: 5m

💰 PREÇO:
{preco}

📉 SUPERTREND VIROU PARA BAIXA

🔥 FORÇA:
{score}%

🎯 Entrada:
{preco}

🛑 Stop:
{round(last['supertrend'],4)}

⚡ DETECÇÃO INTRABAR
⚡ WEBSOCKET REALTIME
"""

        send(msg)

        signals.append({
            "symbol": symbol.upper(),
            "type": "SELL",
            "price": preco,
            "score": score,
            "time": datetime.now(timezone).strftime("%H:%M:%S")
        })

        sent_alerts[symbol] = 'sell'

# ==========================================
# WEBSOCKET
# ==========================================
def on_message(ws, message):

    data = json.loads(message)

    if 'k' not in data:
        return

    kline = data['k']

    symbol = data['s'].lower()

    close = float(kline['c'])
    high = float(kline['h'])
    low = float(kline['l'])
    open_price = float(kline['o'])
    volume = float(kline['v'])

    if symbol not in market_data:
        return

    df = market_data[symbol]

    # Atualiza última vela EM TEMPO REAL
    df.iloc[-1, df.columns.get_loc('open')] = open_price
    df.iloc[-1, df.columns.get_loc('high')] = high
    df.iloc[-1, df.columns.get_loc('low')] = low
    df.iloc[-1, df.columns.get_loc('close')] = close
    df.iloc[-1, df.columns.get_loc('volume')] = volume

    market_data[symbol] = df

    process_signal(symbol, df)

# ==========================================
# START
# ==========================================
if __name__ == '__main__':

    keep_alive()

    send("""
🤖 BOT SUPERTREND PRO ATIVO

⚡ MODO:
WEBSOCKET REALTIME

⚡ ESTRATÉGIA:
Virada instantânea da Supertrend

⚡ DETECÇÃO:
Intrabar

⚡ SISTEMA:
Score de força
""")

    # Carrega histórico
    for symbol in symbols:
        try:
            market_data[symbol] = load_history(symbol)
            print(f"{symbol} carregado")

        except Exception as e:
            print(symbol, e)

    streams = '/'.join([
        f"{symbol}@kline_5m"
        for symbol in symbols
    ])

    socket = (
        f"wss://stream.binance.com:9443/stream?streams={streams}"
    )

    ws = WebSocketApp(
        socket,
        on_message=on_message
    )

    ws.run_forever()
```

# requirements.txt

```txt
flask
requests
pandas
python-binance
websocket-client
gunicorn
```

# COMO FUNCIONA AGORA

## 1. Binance envia dados em tempo real

```text
BINANCE
   ↓
WEBSOCKET
   ↓
BOT RECEBE TICK INSTANTÂNEO
```

## 2. O bot recalcula a Supertrend DURANTE a vela

```text
VELA AINDA FORMANDO
       ↓
SUPERTREND MUDA
       ↓
ALERTA IMEDIATO
```

## 3. O Telegram recebe instantaneamente

Exemplo:

🟢⬆️ VIRADA SUPERTREND REALTIME

📊 SOLUSDT
🔥 FORÇA: 92%
⚡ DETECÇÃO INTRABAR

# O QUE MELHOROU

✅ Não espera candle fechar
✅ Detecção quase instantânea
✅ Menos atraso
✅ Dashboard continua funcionando
✅ Multi-moedas
✅ Tempo real verdadeiro
✅ Score de força
✅ Websocket profissional

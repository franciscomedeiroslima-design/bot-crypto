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
    return "🚀 BOT EMA CROSS REALTIME ONLINE"

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
    "dotusdt",
    "avaxusdt",
    "atomusdt",
    "aptusdt",
    "ondousdt",
    "seiUsdt".lower(),
    "imxusdt",
    "galausdt",
    "algoUsdt".lower(),
    "jasmyusdt",
    "tonusdt"
]

# ==========================================
# ESTADO
# ==========================================
signals = []
sent_alerts = {}
market_data = {}

state = {
    "last_heartbeat": time.time(),
    "api_error_sent": False,
    "bot_error_sent": False
}

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
# HISTÓRICO
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

    df = df[[
        "time",
        "open",
        "high",
        "low",
        "close",
        "volume"
    ]]

    for col in ["open","high","low","close","volume"]:
        df[col] = pd.to_numeric(df[col])

    return df

# ==========================================
# EMA
# ==========================================
def calculate_ema(df):

    df["ema8"] = (
        df["close"]
        .ewm(span=8, adjust=False)
        .mean()
    )

    df["ema21"] = (
        df["close"]
        .ewm(span=21, adjust=False)
        .mean()
    )

    return df

# ==========================================
# SCORE
# ==========================================
def calculate_score(df):

    last = df.iloc[-1]

    distancia = abs(
        (last["ema8"] - last["ema21"])
        / last["ema21"]
    ) * 100

    volume_ma = (
        df["volume"]
        .rolling(20)
        .mean()
        .iloc[-1]
    )

    score = 0

    # ==========================================
    # DISTÂNCIA ENTRE EMAs
    # ==========================================
    if distancia > 0.30:
        score += 40

    elif distancia > 0.15:
        score += 25

    else:
        score += 10

    # ==========================================
    # VOLUME
    # ==========================================
    if last["volume"] > volume_ma * 2:
        score += 40

    elif last["volume"] > volume_ma * 1.5:
        score += 25

    else:
        score += 10

    # ==========================================
    # FORÇA DO CANDLE
    # ==========================================
    candle = abs(
        last["close"] - last["open"]
    )

    range_candle = (
        last["high"] - last["low"]
    )

    if range_candle > 0:

        body_percent = (
            candle / range_candle
        ) * 100

        if body_percent > 70:
            score += 20

        elif body_percent > 50:
            score += 10

    return min(round(score), 100)

# ==========================================
# DETECÇÃO EMA CROSS REALTIME
# ==========================================
def process_signal(symbol, df):

    df = calculate_ema(df)

    last = df.iloc[-1]
    prev = df.iloc[-2]

    preco = round(last["close"], 4)

    # ==========================================
    # DISTÂNCIA ENTRE EMAs
    # ==========================================
    dist_prev = (
        prev["ema8"] - prev["ema21"]
    )

    dist_now = (
        last["ema8"] - last["ema21"]
    )

    # ==========================================
    # COMPRA
    # ==========================================
    cruzando_compra = (
        dist_prev < 0 and
        dist_now > 0
    )

    # ==========================================
    # VENDA
    # ==========================================
    cruzando_venda = (
        dist_prev > 0 and
        dist_now < 0
    )

    score = calculate_score(df)

    # ==========================================
    # ALERTA COMPRA
    # ==========================================
    if cruzando_compra and sent_alerts.get(symbol) != "buy":

        distancia = round(
            abs(dist_now),
            5
        )

        msg = f"""
🟢⬆️ CRUZAMENTO EMA REALTIME

📊 {symbol.upper()}
⏱ TF: 5m

⚡ EMA 8 cruzou EMA 21 PARA CIMA

🔥 FORÇA:
{score}%

📍 Distância EMAs:
{distancia}

💰 PREÇO:
{preco}

📡 WEBSOCKET REALTIME
⚡ DETECÇÃO INTRABAR
"""

        send(msg)

        signals.append({
            "symbol": symbol.upper(),
            "type": "BUY",
            "score": score,
            "price": preco,
            "time": datetime.now(timezone).strftime("%H:%M:%S")
        })

        sent_alerts[symbol] = "buy"

    # ==========================================
    # ALERTA VENDA
    # ==========================================
    elif cruzando_venda and sent_alerts.get(symbol) != "sell":

        distancia = round(
            abs(dist_now),
            5
        )

        msg = f"""
🔴⬇️ CRUZAMENTO EMA REALTIME

📊 {symbol.upper()}
⏱ TF: 5m

⚡ EMA 8 cruzou EMA 21 PARA BAIXO

🔥 FORÇA:
{score}%

📍 Distância EMAs:
{distancia}

💰 PREÇO:
{preco}

📡 WEBSOCKET REALTIME
⚡ DETECÇÃO INTRABAR
"""

        send(msg)

        signals.append({
            "symbol": symbol.upper(),
            "type": "SELL",
            "score": score,
            "price": preco,
            "time": datetime.now(timezone).strftime("%H:%M:%S")
        })

        sent_alerts[symbol] = "sell"

# ==========================================
# WEBSOCKET
# ==========================================
def on_message(ws, message):

    try:

        data = json.loads(message)

        if "data" not in data:
            return

        kline = data["data"]["k"]

        symbol = data["data"]["s"].lower()

        close = float(kline["c"])
        high = float(kline["h"])
        low = float(kline["l"])
        open_price = float(kline["o"])
        volume = float(kline["v"])

        if symbol not in market_data:
            return

        df = market_data[symbol]

        # ==========================================
        # ATUALIZA ÚLTIMA VELA EM TEMPO REAL
        # ==========================================
        df.iloc[-1, df.columns.get_loc("open")] = open_price
        df.iloc[-1, df.columns.get_loc("high")] = high
        df.iloc[-1, df.columns.get_loc("low")] = low
        df.iloc[-1, df.columns.get_loc("close")] = close
        df.iloc[-1, df.columns.get_loc("volume")] = volume

        market_data[symbol] = df

        # ==========================================
        # PROCESSA SINAL
        # ==========================================
        process_signal(symbol, df)

    except Exception as e:

        print("Erro websocket:", e)

# ==========================================
# START
# ==========================================
if __name__ == "__main__":

    keep_alive()

    send("""
🤖 BOT EMA CROSS REALTIME ATIVO

⚡ ESTRATÉGIA:
EMA 8 x EMA 21

⚡ MODO:
INTRABAR REALTIME

⚡ DETECÇÃO:
CRUZAMENTO INSTANTÂNEO

📡 WEBSOCKET BINANCE ATIVO
""")

    # ==========================================
    # CARREGA HISTÓRICO
    # ==========================================
    for symbol in symbols:

        try:

            market_data[symbol] = load_history(symbol)

            print(f"{symbol} carregado")

        except Exception as e:

            print(symbol, e)

    # ==========================================
    # STREAMS
    # ==========================================
    streams = "/".join([
        f"{symbol}@kline_5m"
        for symbol in symbols
    ])

    socket = (
        f"wss://stream.binance.com:9443/stream?streams={streams}"
    )

    # ==========================================
    # WEBSOCKET
    # ==========================================
    ws = WebSocketApp(
        socket,
        on_message=on_message
    )

    ws.run_forever()

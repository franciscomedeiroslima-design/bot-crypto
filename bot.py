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
    "seiusdt",
    "imxusdt",
    "galausdt",
    "algousdt",
    "jasmyusdt",
    "tonusdt"
]

# ==========================================
# ESTADO
# ==========================================
signals = []

sent_alerts = {}

market_data = {}

last_candle_time = {}

state = {
    "last_heartbeat": time.time()
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

    try:

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
        # DISTÂNCIA EMAs
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
        if volume_ma > 0:

            if last["volume"] > volume_ma * 2:
                score += 40

            elif last["volume"] > volume_ma * 1.5:
                score += 25

            else:
                score += 10

        # ==========================================
        # FORÇA CANDLE
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

    except:
        return 0

# ==========================================
# PROCESSA SINAL
# ==========================================
def process_signal(symbol):

    try:

        df = market_data[symbol]

        if len(df) < 25:
            return

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
        # CRUZAMENTO COMPRA
        # ==========================================
        cruzou_compra = (
            dist_prev < 0 and
            dist_now > 0
        )

        # ==========================================
        # CRUZAMENTO VENDA
        # ==========================================
        cruzou_venda = (
            dist_prev > 0 and
            dist_now < 0
        )

        score = calculate_score(df)

        # ==========================================
        # COMPRA
        # ==========================================
        if cruzou_compra and sent_alerts.get(symbol) != "buy":

            msg = f"""
🟢⬆️ CRUZAMENTO EMA REALTIME

📊 {symbol.upper()}
⏱ TF: 5m

⚡ EMA 8 cruzou EMA 21 PARA CIMA

🔥 FORÇA:
{score}%

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
        # VENDA
        # ==========================================
        elif cruzou_venda and sent_alerts.get(symbol) != "sell":

            msg = f"""
🔴⬇️ CRUZAMENTO EMA REALTIME

📊 {symbol.upper()}
⏱ TF: 5m

⚡ EMA 8 cruzou EMA 21 PARA BAIXO

🔥 FORÇA:
{score}%

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

        market_data[symbol] = df

    except Exception as e:

        print("Erro signal:", e)

# ==========================================
# WEBSOCKET MESSAGE
# ==========================================
def on_message(ws, message):

    try:

        data = json.loads(message)

        if "data" not in data:
            return

        if "k" not in data["data"]:
            return

        kline = data["data"]["k"]

        symbol = data["data"]["s"].lower()

        candle_time = kline["t"]

        open_price = float(kline["o"])
        high = float(kline["h"])
        low = float(kline["l"])
        close = float(kline["c"])
        volume = float(kline["v"])

        candle_closed = kline["x"]

        # ==========================================
        # PRIMEIRA VEZ
        # ==========================================
        if symbol not in market_data:

            market_data[symbol] = pd.DataFrame(columns=[
                "open",
                "high",
                "low",
                "close",
                "volume"
            ])

        df = market_data[symbol]

        # ==========================================
        # SEM DADOS AINDA
        # ==========================================
        if len(df) == 0:

            new_row = {
                "open": open_price,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume
            }

            df.loc[len(df)] = new_row

            market_data[symbol] = df

            return

        # ==========================================
        # NOVA VELA
        # ==========================================
        if symbol not in last_candle_time:

            last_candle_time[symbol] = candle_time

        if candle_time != last_candle_time[symbol]:

            new_row = {
                "open": open_price,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume
            }

            df.loc[len(df)] = new_row

            last_candle_time[symbol] = candle_time

            # ==========================================
            # LIMITA MEMÓRIA
            # ==========================================
            if len(df) > 200:
                df = df.iloc[-200:]

        else:

            # ==========================================
            # ATUALIZA VELA ATUAL
            # ==========================================
            df.iloc[-1, df.columns.get_loc("open")] = open_price
            df.iloc[-1, df.columns.get_loc("high")] = high
            df.iloc[-1, df.columns.get_loc("low")] = low
            df.iloc[-1, df.columns.get_loc("close")] = close
            df.iloc[-1, df.columns.get_loc("volume")] = volume

        market_data[symbol] = df

        # ==========================================
        # PROCESSA EM TEMPO REAL
        # ==========================================
        process_signal(symbol)

    except Exception as e:

        print("Erro websocket:", e)

# ==========================================
# WEBSOCKET OPEN
# ==========================================
def on_open(ws):

    print("WebSocket conectado")

    params = [
        f"{symbol}@kline_5m"
        for symbol in symbols
    ]

    payload = {
        "method": "SUBSCRIBE",
        "params": params,
        "id": 1
    }

    ws.send(json.dumps(payload))

    send("""
🤖 BOT EMA CROSS REALTIME ATIVO

⚡ Estratégia:
EMA 8 x EMA 21

⚡ MODO:
INTRABAR REALTIME

📡 Binance WebSocket conectado
""")

# ==========================================
# WEBSOCKET ERROR
# ==========================================
def on_error(ws, error):

    print("Erro websocket:", error)

# ==========================================
# WEBSOCKET CLOSE
# ==========================================
def on_close(ws, close_status_code, close_msg):

    print("WebSocket fechado")

# ==========================================
# HEARTBEAT
# ==========================================
def heartbeat():

    while True:

        try:

            if time.time() - state["last_heartbeat"] >= 14400:

                send("""
📡 BOT ONLINE

✅ WebSocket ativo
✅ EMA Cross ativo
✅ Tempo real funcionando
""")

                state["last_heartbeat"] = time.time()

            time.sleep(60)

        except:
            pass

# ==========================================
# START
# ==========================================
if __name__ == "__main__":

    keep_alive()

    Thread(target=heartbeat).start()

    while True:

        try:

            socket = (
                "wss://stream.binance.com:9443/ws"
            )

            ws = WebSocketApp(
                socket,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close
            )

            ws.run_forever()

        except Exception as e:

            print("Reconectando:", e)

            time.sleep(5)

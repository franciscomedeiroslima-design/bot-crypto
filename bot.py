import os
import time
import requests
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo
from flask import Flask, jsonify
from threading import Thread
from binance.client import Client

# ==========================================
# FLASK
# ==========================================
app = Flask(__name__)

@app.route("/")
def home():
    return "🚀 BOT SUPERTREND REALTIME ONLINE"

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
BINANCE_KEY = os.getenv("BINANCE_KEY")
BINANCE_SECRET = os.getenv("BINANCE_SECRET")

TOKEN = os.getenv("TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

client = Client(BINANCE_KEY, BINANCE_SECRET)

timezone = ZoneInfo("America/Sao_Paulo")

# ==========================================
# MOEDAS
# ==========================================
symbols = [
    "DOTUSDT",
    "IMXUSDT",
    "ETCUSDT",
    "ATOMUSDT",
    "AVAXUSDT",
    "GALAUSDT",
    "AXSUSDT",
    "ONDOUSDT",
    "APTUSDT",
    "ALGOUSDT",
    "LDOUSDT",
    "HBARUSDT",
    "APEUSDT",
    "JASMYUSDT",
    "TRXUSDT",
    "NEOUSDT",
    "XTZUSDT",
    "TONUSDT",
    "BTCUSDT",
    "DOGEUSDT",
    "SOLUSDT",
    "SEIUSDT",
    "ETHUSDT"
]

# ==========================================
# ESTADO
# ==========================================
signals = []
sent_alerts = {}

state = {
    "api_error_sent": False,
    "bot_error_sent": False,
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
# DADOS BINANCE REALTIME
# ==========================================
def get_data(symbol):

    try:
        klines = client.get_klines(
            symbol=symbol,
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

        if state["api_error_sent"]:
            send("✅ API Binance normalizada")
            state["api_error_sent"] = False

        return df

    except Exception as e:

        print("Erro API Binance:", e)

        if not state["api_error_sent"]:
            send("🚨 ERRO API BINANCE")
            state["api_error_sent"] = True

        return None

# ==========================================
# SUPERTREND
# ==========================================
def calculate_supertrend(df, period=10, multiplier=2):

    hl2 = (df["high"] + df["low"]) / 2

    df["tr"] = (
        df[["high", "close"]].max(axis=1) -
        df[["low", "close"]].min(axis=1)
    )

    atr = df["tr"].rolling(period).mean()

    upperband = hl2 + (multiplier * atr)
    lowerband = hl2 - (multiplier * atr)

    trend = [True]
    supertrend = [lowerband.iloc[0]]

    for i in range(1, len(df)):

        if df["close"].iloc[i] > supertrend[i - 1]:
            trend.append(True)

        elif df["close"].iloc[i] < supertrend[i - 1]:
            trend.append(False)

        else:
            trend.append(trend[i - 1])

        if trend[i]:
            supertrend.append(lowerband.iloc[i])
        else:
            supertrend.append(upperband.iloc[i])

    df["trend"] = trend
    df["supertrend"] = supertrend

    return df

# ==========================================
# ESTRATÉGIA
# DETECTAR VIRADA EXATA DA SUPERTREND
# ==========================================
def check(symbol):

    df = get_data(symbol)

    if df is None or len(df) < 50:
        return

    df = calculate_supertrend(df)

    last = df.iloc[-1]
    prev = df.iloc[-2]

    preco = round(last["close"], 4)

    # ==========================================
    # VIRADA REAL DA SUPERTREND
    # ==========================================
    virou_compra = (
        prev["trend"] == False and
        last["trend"] == True
    )

    virou_venda = (
        prev["trend"] == True and
        last["trend"] == False
    )

    distancia = abs(
        (last["close"] - last["supertrend"])
        / last["close"]
    ) * 100

    # ==========================================
    # COMPRA
    # ==========================================
    if virou_compra and sent_alerts.get(symbol) != "buy":

        msg = f"""
🟢⬆️ VIRADA SUPERTREND COMPRA

📊 {symbol}
⏱ TIMEFRAME: 5m

💰 PREÇO: {preco}

📈 SUPERTREND VIROU PARA ALTA

📍 DISTÂNCIA ST:
{round(distancia,2)}%

🎯 Entrada:
{preco}

🛑 Stop:
{round(last['supertrend'],4)}

🔥 ALERTA EM TEMPO REAL
"""

        send(msg)

        signals.append({
            "symbol": symbol,
            "type": "BUY",
            "price": preco,
            "time": datetime.now(timezone).strftime("%H:%M:%S")
        })

        sent_alerts[symbol] = "buy"

    # ==========================================
    # VENDA
    # ==========================================
    elif virou_venda and sent_alerts.get(symbol) != "sell":

        msg = f"""
🔴⬇️ VIRADA SUPERTREND VENDA

📊 {symbol}
⏱ TIMEFRAME: 5m

💰 PREÇO: {preco}

📉 SUPERTREND VIROU PARA BAIXA

📍 DISTÂNCIA ST:
{round(distancia,2)}%

🎯 Entrada:
{preco}

🛑 Stop:
{round(last['supertrend'],4)}

🔥 ALERTA EM TEMPO REAL
"""

        send(msg)

        signals.append({
            "symbol": symbol,
            "type": "SELL",
            "price": preco,
            "time": datetime.now(timezone).strftime("%H:%M:%S")
        })

        sent_alerts[symbol] = "sell"

# ==========================================
# LOOP REALTIME
# ==========================================
if __name__ == "__main__":

    keep_alive()

    time.sleep(5)

    send("""
🤖 BOT SUPERTREND REALTIME ATIVO

⚡ Estratégia:
Virada exata da Supertrend

⏱ Timeframe:
5 minutos

📡 Monitoramento em tempo real iniciado
""")

    while True:

        try:

            for symbol in symbols:

                check(symbol)

                # PEQUENO DELAY
                time.sleep(0.5)

            # HEARTBEAT
            if time.time() - state["last_heartbeat"] >= 14400:

                send("""
📡 BOT ONLINE

✅ Monitorando mercado
✅ Supertrend ativa
✅ Tempo real funcionando
""")

                state["last_heartbeat"] = time.time()

            # LOOP RÁPIDO
            time.sleep(5)

        except Exception as e:

            print("Erro geral:", e)

            if not state["bot_error_sent"]:

                send(f"""
🚨 ERRO CRÍTICO NO BOT

{str(e)}
""")

                state["bot_error_sent"] = True

            time.sleep(10)

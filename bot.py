import os
import time
import requests
import pandas as pd
import pandas_ta as ta

from datetime import datetime
from zoneinfo import ZoneInfo

from flask import Flask, jsonify
from threading import Thread

from binance.client import Client

# =========================================================
# FLASK
# =========================================================
app = Flask(__name__)

# =========================================================
# CONFIG
# =========================================================
BINANCE_KEY = os.environ.get("BINANCE_KEY")
BINANCE_SECRET = os.environ.get("BINANCE_SECRET")

TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

client = Client(BINANCE_KEY, BINANCE_SECRET)

timezone = ZoneInfo("America/Sao_Paulo")

# =========================================================
# MOEDAS
# =========================================================
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
    "ETHUSDT",
    "ADAUSDT"
]

# =========================================================
# CONTROLE
# =========================================================
signals = []

sent_alerts = {}

state = {
    "api_error_sent": False,
    "bot_error_sent": False,
    "last_heartbeat": time.time()
}

# =========================================================
# FLASK ROUTES
# =========================================================
@app.route('/')
def home():
    return "🤖 BOT SUPERtrend ONLINE"

@app.route('/dashboard')
def dashboard():
    return jsonify(signals[-50:])

@app.route('/api/signals')
def api_signals():
    return jsonify(signals[-50:])

def run():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    Thread(target=run).start()

# =========================================================
# TELEGRAM
# =========================================================
def send(msg):
    try:

        agora = datetime.now(timezone).strftime("%H:%M")

        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

        requests.post(
            url,
            json={
                "chat_id": CHAT_ID,
                "text": f"{msg}\n🕒 {agora} (SC)"
            },
            timeout=10
        )

    except Exception as e:
        print("Erro Telegram:", e)

# =========================================================
# BINANCE DATA
# =========================================================
def get_data(symbol):

    try:

        klines = client.get_klines(
            symbol=symbol,
            interval=Client.KLINE_INTERVAL_5MINUTE,
            limit=200
        )

        df = pd.DataFrame(klines, columns=[
            'time',
            'open',
            'high',
            'low',
            'close',
            'volume',
            'close_time',
            'qav',
            'num_trades',
            'taker_base',
            'taker_quote',
            'ignore'
        ])

        df['open'] = pd.to_numeric(df['open'])
        df['high'] = pd.to_numeric(df['high'])
        df['low'] = pd.to_numeric(df['low'])
        df['close'] = pd.to_numeric(df['close'])
        df['volume'] = pd.to_numeric(df['volume'])

        if state["api_error_sent"]:
            send("✅ API Binance normalizada")
            state["api_error_sent"] = False

        return df

    except Exception as e:

        print("Erro Binance:", e)

        if not state["api_error_sent"]:
            send("🚨 ERRO API BINANCE")
            state["api_error_sent"] = True

        return None

# =========================================================
# SUPERTREND
# =========================================================
def calculate(df):

    st = ta.supertrend(
        high=df['high'],
        low=df['low'],
        close=df['close'],
        length=10,
        multiplier=2
    )

    df['supertrend'] = st['SUPERT_10_2.0']
    df['direction'] = st['SUPERTd_10_2.0']

    return df

# =========================================================
# ESTRATÉGIA
# ANTECIPAÇÃO DA VIRADA DA SUPERTREND
# =========================================================
def check(symbol):

    df_raw = get_data(symbol)

    if df_raw is None or len(df_raw) < 50:
        return

    df = calculate(df_raw)

    last = df.iloc[-1]

    close = float(last['close'])
    st = float(last['supertrend'])

    direction = int(last['direction'])

    # =====================================================
    # DISTÂNCIA ENTRE PREÇO E SUPERTREND
    # =====================================================
    dist = abs(close - st) / close

    preco = round(close, 4)

    # =====================================================
    # COMPRA ANTECIPADA
    # =====================================================
    compra_antecipada = (
        direction == -1 and
        close >= st * 0.997
    )

    # =====================================================
    # VENDA ANTECIPADA
    # =====================================================
    venda_antecipada = (
        direction == 1 and
        close <= st * 1.003
    )

    # =====================================================
    # ALERTA COMPRA
    # =====================================================
    if compra_antecipada:

        last_signal = sent_alerts.get(symbol)

        if last_signal != "buy":

            msg = f"""
🟢⚡ POSSÍVEL VIRADA SUPERTREND

📊 {symbol}
💰 Preço: {preco}
⏱ Timeframe: 5m

📍 Preço atacando a Supertrend
📈 Possível COMPRA iminente

🎯 Entrada: {preco}
🛑 Stop: {round(preco * 0.992, 4)}
🎯 Alvo: {round(preco * 1.015, 4)}

🔥 ALERTA ANTECIPADO
"""

            send(msg)

            signals.append({
                "symbol": symbol,
                "type": "BUY",
                "price": preco,
                "time": datetime.now(timezone).strftime("%H:%M")
            })

            sent_alerts[symbol] = "buy"

    # =====================================================
    # ALERTA VENDA
    # =====================================================
    elif venda_antecipada:

        last_signal = sent_alerts.get(symbol)

        if last_signal != "sell":

            msg = f"""
🔴⚡ POSSÍVEL VIRADA SUPERTREND

📊 {symbol}
💰 Preço: {preco}
⏱ Timeframe: 5m

📍 Preço perdendo a Supertrend
📉 Possível VENDA iminente

🎯 Entrada: {preco}
🛑 Stop: {round(preco * 1.008, 4)}
🎯 Alvo: {round(preco * 0.985, 4)}

🔥 ALERTA ANTECIPADO
"""

            send(msg)

            signals.append({
                "symbol": symbol,
                "type": "SELL",
                "price": preco,
                "time": datetime.now(timezone).strftime("%H:%M")
            })

            sent_alerts[symbol] = "sell"

    # =====================================================
    # RESET ALERTA
    # =====================================================
    else:

        sent_alerts[symbol] = None

# =========================================================
# LOOP PRINCIPAL
# =========================================================
if __name__ == "__main__":

    keep_alive()

    time.sleep(5)

    send("🤖 BOT SUPERTREND ANTECIPADO ONLINE")

    while True:

        try:

            for symbol in symbols:

                check(symbol)

                time.sleep(1)

            # HEARTBEAT
            if time.time() - state["last_heartbeat"] >= 14400:

                send("📡 BOT ONLINE E MONITORANDO")

                state["last_heartbeat"] = time.time()

        except Exception as e:

            print("Erro geral:", e)

            if not state["bot_error_sent"]:

                send(f"🚨 ERRO CRÍTICO NO BOT\n{str(e)}")

                state["bot_error_sent"] = True

        time.sleep(15)

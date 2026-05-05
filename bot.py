import os
import requests
import pandas as pd
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from flask import Flask, render_template
from threading import Thread

app = Flask(__name__)

# =========================
# CONFIG
# =========================
TOKEN = os.environ.get("TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

timezone = ZoneInfo("America/Sao_Paulo")

symbols = [
    "BTCUSDT","ETHUSDT","SOLUSDT","DOTUSDT","AVAXUSDT","DOGEUSDT",
    "ATOMUSDT","APTUSDT","GALAUSDT","FILUSDT","ICPUSDT","LINKUSDT"
]

sent_alerts = {}
signals = []

api_error_sent = False
bot_error_sent = False
last_heartbeat = time.time()

# =========================
# FLASK
# =========================
@app.route('/')
def home():
    return "Bot PRO Online 🚀"

@app.route('/dashboard')
def dashboard():
    return render_template("index.html")

@app.route('/signals')
def get_signals():
    return {"signals": signals[-50:]}

def run():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    Thread(target=run).start()

# =========================
# TELEGRAM
# =========================
def send(msg):
    try:
        agora = datetime.now(timezone).strftime("%H:%M")
        msg_final = f"{msg}\n🕒 {agora} (SC)"

        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        requests.get(url, params={"chat_id": CHAT_ID, "text": msg_final}, timeout=10)
    except Exception as e:
        print("Erro Telegram:", e)

# =========================
# DADOS
# =========================
def get_data(symbol):
    global api_error_sent

    try:
        url = f"https://api.bybit.com/v5/market/kline?category=linear&symbol={symbol}&interval=30&limit=200"
        data = requests.get(url, timeout=10).json()

        df = pd.DataFrame(data['result']['list'])
        df = df.iloc[::-1]
        df.columns = ["time","open","high","low","close","volume","turnover"]

        if api_error_sent:
            send("✅ API restabelecida")
            api_error_sent = False

        return df.astype(float)

    except Exception as e:
        print("Erro API:", e)

        if not api_error_sent:
            send("🚨 ERRO: API Bybit offline")
            api_error_sent = True

        return None

# =========================
# SUPERTREND
# =========================
def supertrend(df, period=10, factor=2):
    hl2 = (df['high'] + df['low']) / 2
    atr = (df['high'] - df['low']).rolling(period).mean()

    upper = hl2 + factor * atr
    lower = hl2 - factor * atr

    trend = [True]
    st = [lower.iloc[0]]

    for i in range(1, len(df)):
        if df['close'].iloc[i] > st[i-1]:
            trend.append(True)
        elif df['close'].iloc[i] < st[i-1]:
            trend.append(False)
        else:
            trend.append(trend[i-1])

        st.append(lower.iloc[i] if trend[i] else upper.iloc[i])

    df['st'] = st
    df['trend'] = trend

    return df

# =========================
# INDICADORES + SNIPER
# =========================
def calculate(df):
    df['sma8'] = df['close'].rolling(8).mean()
    df['sma21'] = df['close'].rolling(21).mean()

    df['branca_subindo'] = df['sma8'] > df['sma8'].shift(1)

    # SNIPER (antecipação)
    df['sniper_buy'] = (
        (df['close'] > df['sma8']) &
        (df['sma8'] > df['sma21']) &
        (df['close'].shift(1) <= df['sma8'])
    )

    df['sniper_sell'] = (
        (df['close'] < df['sma8']) &
        (df['sma8'] < df['sma21']) &
        (df['close'].shift(1) >= df['sma8'])
    )

    return supertrend(df)

# =========================
# SINAIS
# =========================
def check(symbol):
    try:
        df_raw = get_data(symbol)
        if df_raw is None:
            return

        df = calculate(df_raw)

        last = df.iloc[-1]
        prev = df.iloc[-2]

        # CONFIRMADO
        compra = (
            prev['trend'] and
            prev['close'] > prev['st'] and
            last['close'] > last['sma8'] > last['sma21']
        )

        venda = (
            not prev['trend'] and
            prev['close'] < prev['st'] and
            last['close'] < last['sma8'] < last['sma21']
        )

        # SNIPER
        sniper_buy = last['sniper_buy']
        sniper_sell = last['sniper_sell']

        agora = datetime.now(timezone).strftime("%H:%M")

        # COMPRA
        if compra and sent_alerts.get(symbol) != "buy":
            msg = f"🚀 COMPRA CONFIRMADA: {symbol}"
            send(msg)

            signals.append({"symbol": symbol, "type": "BUY", "time": agora})
            sent_alerts[symbol] = "buy"

        elif sniper_buy and sent_alerts.get(symbol) != "sniper_buy":
            msg = f"🎯 SNIPER COMPRA: {symbol}"
            send(msg)

            signals.append({"symbol": symbol, "type": "SNIPER BUY", "time": agora})
            sent_alerts[symbol] = "sniper_buy"

        # VENDA
        if venda and sent_alerts.get(symbol) != "sell":
            msg = f"🔻 VENDA CONFIRMADA: {symbol}"
            send(msg)

            signals.append({"symbol": symbol, "type": "SELL", "time": agora})
            sent_alerts[symbol] = "sell"

        elif sniper_sell and sent_alerts.get(symbol) != "sniper_sell":
            msg = f"🎯 SNIPER VENDA: {symbol}"
            send(msg)

            signals.append({"symbol": symbol, "type": "SNIPER SELL", "time": agora})
            sent_alerts[symbol] = "sniper_sell"

    except Exception as e:
        print("Erro:", e)

# =========================
# LOOP
# =========================
if __name__ == "__main__":
    keep_alive()
    time.sleep(10)

    send("🤖 BOT PRO ATIVO")

    while True:
        try:
            for s in symbols:
                check(s)
                time.sleep(1)

            if time.time() - last_heartbeat >= 14400:
                send("📡 Monitoramento ativo")
                last_heartbeat = time.time()

        except Exception as e:
            print("Erro geral:", e)

            global bot_error_sent
            if not bot_error_sent:
                send("🚨 ERRO CRÍTICO NO BOT")
                bot_error_sent = True

        time.sleep(60)

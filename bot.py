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

state = {
    "api_error": False,
    "bot_error": False,
    "last_heartbeat": time.time()
}

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
        msg_final = f"{msg}\n🕒 {agora}"

        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        requests.get(url, params={"chat_id": CHAT_ID, "text": msg_final}, timeout=10)
    except Exception as e:
        print("Erro Telegram:", e)

# =========================
# DADOS
# =========================
def get_data(symbol):
    try:
        url = f"https://api.bybit.com/v5/market/kline?category=linear&symbol={symbol}&interval=30&limit=200"
        data = requests.get(url, timeout=10).json()

        df = pd.DataFrame(data['result']['list'])
        df = df.iloc[::-1]
        df.columns = ["time","open","high","low","close","volume","turnover"]

        if state["api_error"]:
            send("✅ API normalizada")
            state["api_error"] = False

        return df.astype(float)

    except Exception as e:
        print("Erro API:", e)

        if not state["api_error"]:
            send("🚨 ERRO API")
            state["api_error"] = True

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
# INDICADORES PRO
# =========================
def calculate(df):

    df['sma8'] = df['close'].rolling(8).mean()
    df['sma21'] = df['close'].rolling(21).mean()

    # inclinação
    df['sma8_slope'] = df['sma8'] - df['sma8'].shift(1)

    # força candle
    df['body'] = abs(df['close'] - df['open'])
    df['range'] = df['high'] - df['low']
    df['strong_candle'] = df['body'] > (df['range'] * 0.6)

    # volume
    df['vol_mean'] = df['volume'].rolling(20).mean()
    df['vol_ok'] = df['volume'] > df['vol_mean']

    # lateralização
    df['lateral'] = abs(df['sma8'] - df['sma21']) < 0.001

    # =========================
    # SNIPER REAL
    # =========================

    df['sniper_buy'] = (
        (df['close'] > df['sma8']) &
        (df['sma8_slope'] > 0) &
        (df['sma8'] > df['sma21']) &
        (df['close'].shift(1) < df['sma8']) &
        (df['strong_candle']) &
        (df['vol_ok']) &
        (~df['lateral'])
    )

    df['sniper_sell'] = (
        (df['close'] < df['sma8']) &
        (df['sma8_slope'] < 0) &
        (df['sma8'] < df['sma21']) &
        (df['close'].shift(1) > df['sma8']) &
        (df['strong_candle']) &
        (df['vol_ok']) &
        (~df['lateral'])
    )

    return supertrend(df)

# =========================
# SINAIS
# =========================
def check(symbol):

    df_raw = get_data(symbol)
    if df_raw is None:
        return

    df = calculate(df_raw)

    last = df.iloc[-1]
    prev = df.iloc[-2]

    agora = datetime.now(timezone).strftime("%H:%M")

    # =========================
    # CONFIRMAÇÃO
    # =========================
    compra = prev['trend'] == False and last['trend'] == True
    venda = prev['trend'] == True and last['trend'] == False

    # =========================
    # SNIPER
    # =========================
    sniper_buy = last['sniper_buy']
    sniper_sell = last['sniper_sell']

    # =========================
    # EXECUÇÃO
    # =========================

    if sniper_buy and sent_alerts.get(symbol) != "sniper_buy":
        send(f"🎯 SNIPER COMPRA: {symbol}")
        signals.append({"symbol": symbol, "type": "SNIPER BUY", "time": agora})
        sent_alerts[symbol] = "sniper_buy"

    elif compra and sent_alerts.get(symbol) != "buy":
        send(f"🚀 COMPRA CONFIRMADA: {symbol}")
        signals.append({"symbol": symbol, "type": "BUY", "time": agora})
        sent_alerts[symbol] = "buy"

    if sniper_sell and sent_alerts.get(symbol) != "sniper_sell":
        send(f"🎯 SNIPER VENDA: {symbol}")
        signals.append({"symbol": symbol, "type": "SNIPER SELL", "time": agora})
        sent_alerts[symbol] = "sniper_sell"

    elif venda and sent_alerts.get(symbol) != "sell":
        send(f"🔻 VENDA CONFIRMADA: {symbol}")
        signals.append({"symbol": symbol, "type": "SELL", "time": agora})
        sent_alerts[symbol] = "sell"

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

            if time.time() - state["last_heartbeat"] >= 14400:
                send("📡 Monitoramento ativo")
                state["last_heartbeat"] = time.time()

        except Exception as e:
            print("Erro geral:", e)

            if not state["bot_error"]:
                send("🚨 ERRO CRÍTICO")
                state["bot_error"] = True

        time.sleep(60)

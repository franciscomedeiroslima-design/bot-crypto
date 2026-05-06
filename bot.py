import os
import requests
import pandas as pd
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from flask import Flask, jsonify
from threading import Thread

app = Flask(__name__)

# =========================
# CONFIG
# =========================
TOKEN = os.environ.get("TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

timezone = ZoneInfo("America/Sao_Paulo")

symbols = [
    "DOTUSDT","IMXUSDT","ETCUSDT","ATOMUSDT","AVAXUSDT","GALAUSDT",
    "AXSUSDT","ONDOUSDT","APTUSDT","ALGOUSDT","LDOUSDT","HBARUSDT",
    "APEUSDT","JASMYUSDT","TRXUSDT","NEOUSDT","XTZUSDT","TONUSDT",
    "BTCUSDT","DOGEUSDT","SOLUSDT","SEIUSDT","ETHUSDT"
]

signals = []
sent_alerts = {}

state = {
    "api_error_sent": False,
    "bot_error_sent": False,
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
    return jsonify(signals[-50:])

@app.route('/api/signals')
def api_signals():
    return jsonify(signals[-50:])

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

        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        requests.get(
            url,
            params={
                "chat_id": CHAT_ID,
                "text": f"{msg}\n🕒 {agora} (SC)"
            },
            timeout=10
        )
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

        if state["api_error_sent"]:
            send("✅ API normalizada")
            state["api_error_sent"] = False

        return df.astype(float)

    except Exception as e:
        print("Erro API:", e)

        if not state["api_error_sent"]:
            send("🚨 ERRO: API Bybit")
            state["api_error_sent"] = True

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

    df['trend'] = trend
    df['st'] = st

    return df

# =========================
# INDICADORES
# =========================
def calculate(df):
    df['sma8'] = df['close'].rolling(8).mean()
    df['sma21'] = df['close'].rolling(21).mean()
    df['vol_ma'] = df['volume'].rolling(20).mean()

    return supertrend(df)

# =========================
# ESTRATÉGIA (NÍVEIS + ROMPIMENTO REAL)
# =========================
def check(symbol):
    df_raw = get_data(symbol)
    if df_raw is None or len(df_raw) < 50:
        return

    df = calculate(df_raw)

    last = df.iloc[-1]
    prev = df.iloc[-2]

    resistencia = df['high'].rolling(20).max().iloc[-2]
    suporte = df['low'].rolling(20).min().iloc[-2]

    volume_forte = last['volume'] > last['vol_ma'] * 1.5

    rompimento_compra = (
        last['close'] > resistencia and
        volume_forte and
        last['trend'] == True
    )

    rompimento_venda = (
        last['close'] < suporte and
        volume_forte and
        last['trend'] == False
    )

    preco = round(last['close'], 4)
    agora = datetime.now(timezone).strftime("%H:%M")

    # =========================
    # COMPRA
    # =========================
    if rompimento_compra and sent_alerts.get(symbol) != "buy":

        msg = f"""
🟢📈 COMPRA FORTE (ROMPIMENTO)

📊 {symbol}
💰 Preço: {preco}
⏱ TF: 30m
🔥 Volume: Forte
📍 Rompendo resistência

🎯 Entrada: {preco}
🛑 Stop: {round(preco * 0.985,4)}
🎯 Alvo: {round(preco * 1.03,4)}
"""

        send(msg)

        signals.append({
            "symbol": symbol,
            "type": "BUY",
            "price": preco,
            "time": agora
        })

        sent_alerts[symbol] = "buy"

    # =========================
    # VENDA
    # =========================
    elif rompimento_venda and sent_alerts.get(symbol) != "sell":

        msg = f"""
🔴📉 VENDA FORTE (ROMPIMENTO)

📊 {symbol}
💰 Preço: {preco}
⏱ TF: 30m
🔥 Volume: Forte
📍 Rompendo suporte

🎯 Entrada: {preco}
🛑 Stop: {round(preco * 1.015,4)}
🎯 Alvo: {round(preco * 0.97,4)}
"""

        send(msg)

        signals.append({
            "symbol": symbol,
            "type": "SELL",
            "price": preco,
            "time": agora
        })

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

            if not state["bot_error_sent"]:
                send("🚨 ERRO CRÍTICO NO BOT")
                state["bot_error_sent"] = True

        time.sleep(60)

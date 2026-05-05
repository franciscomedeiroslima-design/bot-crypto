import os
import requests
import pandas as pd
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from flask import Flask
from threading import Thread

# =========================
# SERVIDOR (Render)
# =========================
app = Flask('')

@app.route('/')
def home():
    return "Bot SNIPER BIDIRECIONAL 🚀"

def run():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    Thread(target=run).start()

# =========================
# CONFIG
# =========================
TOKEN = os.environ.get("TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

timezone = ZoneInfo("America/Sao_Paulo")

symbols = [
    "BTCUSDT","ETHUSDT","SOLUSDT","DOTUSDT","AVAXUSDT",
    "DOGEUSDT","ATOMUSDT","APTUSDT","GALAUSDT","FILUSDT"
]

sent_alerts = {}

# =========================
# TELEGRAM
# =========================
def send(msg):
    try:
        hora = datetime.now(timezone).strftime("%H:%M")
        msg_final = f"{msg}\n🕒 {hora} (SC)"

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

        return df.astype(float)

    except Exception as e:
        print("Erro API:", e)
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
# INDICADORES
# =========================
def calculate(df):
    df['sma_branca'] = df['close'].rolling(8).mean()
    df['sma_amarela'] = df['close'].rolling(21).mean()
    return supertrend(df)

# =========================
# LÓGICA SNIPER + CONFIRMAÇÃO
# =========================
def check(symbol):
    df = get_data(symbol)
    if df is None:
        return

    df = calculate(df)

    last = df.iloc[-1]
    prev = df.iloc[-2]

    # =========================
    # 🟢 SNIPER COMPRA
    # =========================
    fundo = df['low'].rolling(10).min()

    cruzou_cima = prev['close'] < prev['sma_branca'] and last['close'] > last['sma_branca']
    virada_cima = last['sma_branca'] > prev['sma_branca']
    acima_fundo = last['close'] > fundo.iloc[-1]

    sniper_buy = cruzou_cima and virada_cima and acima_fundo

    # =========================
    # 🔻 SNIPER VENDA
    # =========================
    topo = df['high'].rolling(10).max()

    cruzou_baixo = prev['close'] > prev['sma_branca'] and last['close'] < last['sma_branca']
    virada_baixo = last['sma_branca'] < prev['sma_branca']
    abaixo_topo = last['close'] < topo.iloc[-1]

    sniper_sell = cruzou_baixo and virada_baixo and abaixo_topo

    # =========================
    # 🚀 COMPRA CONFIRMADA
    # =========================
    confirm_buy = (
        prev['trend'] == True and
        prev['close'] > prev['st'] and
        last['close'] > last['sma_branca'] and
        last['sma_branca'] > last['sma_amarela']
    )

    # =========================
    # 💀 VENDA CONFIRMADA
    # =========================
    confirm_sell = (
        prev['trend'] == False and
        prev['close'] < prev['st'] and
        last['close'] < last['sma_branca'] and
        last['sma_branca'] < last['sma_amarela']
    )

    # =========================
    # ALERTAS
    # =========================
    if sniper_buy and sent_alerts.get(symbol) != "sniper_buy":
        send(f"🟢 SNIPER BUY: {symbol}\n↗️ Início de reversão")
        sent_alerts[symbol] = "sniper_buy"

    elif confirm_buy and sent_alerts.get(symbol) != "confirm_buy":
        send(f"🚀 BUY CONFIRMADO: {symbol}\n📈 Tendência validada")
        sent_alerts[symbol] = "confirm_buy"

    elif sniper_sell and sent_alerts.get(symbol) != "sniper_sell":
        send(f"🔻 SNIPER SELL: {symbol}\n↘️ Início de queda")
        sent_alerts[symbol] = "sniper_sell"

    elif confirm_sell and sent_alerts.get(symbol) != "confirm_sell":
        send(f"💀 SELL CONFIRMADO: {symbol}\n📉 Tendência de baixa")
        sent_alerts[symbol] = "confirm_sell"

# =========================
# LOOP PRINCIPAL
# =========================
if __name__ == "__main__":
    keep_alive()
    time.sleep(10)

    send("🤖 Bot SNIPER BIDIRECIONAL iniciado")

    while True:
        try:
            for s in symbols:
                check(s)
                time.sleep(1)

        except Exception as e:
            print("Erro geral:", e)

        time.sleep(60)

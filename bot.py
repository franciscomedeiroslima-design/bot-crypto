import os
import requests
import pandas as pd
import numpy as np
import time
from datetime import datetime
import pytz
from flask import Flask
from threading import Thread

# ================================
# SERVIDOR (mantém online)
# ================================
app = Flask('')

@app.route('/')
def home():
    return "Bot Estratégia DOC Online!"

def run():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

# ================================
# CONFIG
# ================================
TOKEN = os.environ.get("TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

# FUSO HORÁRIO (Santa Catarina = São Paulo)
tz = pytz.timezone("America/Sao_Paulo")

symbols = [
    "BTCUSDT","ETHUSDT","SOLUSDT","DOTUSDT","AVAXUSDT","DOGEUSDT",
    "ATOMUSDT","APTUSDT","GALAUSDT","FILUSDT","ICPUSDT","LINKUSDT"
]

sent_alerts = {}
last_heartbeat = 0 

# ================================
# TELEGRAM
# ================================
def send(msg):
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        requests.get(url, params={"chat_id": CHAT_ID, "text": msg}, timeout=10)
    except Exception as e:
        print(f"Erro Telegram: {e}")

# ================================
# DADOS
# ================================
def get_data(symbol):
    try:
        url = f"https://api.bybit.com/v5/market/kline?category=linear&symbol={symbol}&interval=30&limit=200"
        data = requests.get(url).json()
        df = pd.DataFrame(data['result']['list'])
        df = df.iloc[::-1]
        df.columns = ["time","open","high","low","close","volume","turnover"]
        return df.astype(float)
    except:
        return None

# ================================
# SUPER TREND (PST)
# ================================
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

# ================================
# INDICADORES
# ================================
def calculate(df):
    df['sma_branca'] = df['close'].rolling(8).mean()
    df['sma_amarela'] = df['close'].rolling(21).mean()

    df['vol_ma'] = df['volume'].rolling(20).mean()
    df['volume_forte'] = df['volume'] > (df['vol_ma'] * 1.1)

    df['subindo'] = (df['sma_branca'] > df['sma_branca'].shift(1)) & (df['sma_amarela'] > df['sma_amarela'].shift(1))
    df['descendo'] = (df['sma_branca'] < df['sma_branca'].shift(1)) & (df['sma_amarela'] < df['sma_amarela'].shift(1))

    return supertrend(df)

# ================================
# LÓGICA DE SINAL
# ================================
def check(symbol, btc_up, btc_down):
    try:
        df_raw = get_data(symbol)
        if df_raw is None:
            return

        df = calculate(df_raw)

        last = df.iloc[-1]
        prev = df.iloc[-2]

        now_sp = datetime.now(tz)

        # COMPRA
        compra = (
            prev['close'] > prev['st'] and prev['trend'] == True and
            last['close'] > last['sma_branca'] and last['close'] > last['sma_amarela'] and
            last['volume_forte'] and last['subindo'] and btc_up
        )

        # VENDA
        venda = (
            prev['close'] < prev['st'] and prev['trend'] == False and
            last['close'] < last['sma_branca'] and last['close'] < last['sma_amarela'] and
            last['volume_forte'] and last['descendo'] and btc_down
        )

        if compra and sent_alerts.get(symbol) != "buy":
            send(
                f"🚨 ESTRATÉGIA DOC: COMPRA {symbol}\n"
                f"⏰ {now_sp.strftime('%d/%m %H:%M')} (SC)\n"
                f"Volume e Médias confirmados!"
            )
            sent_alerts[symbol] = "buy"

        elif venda and sent_alerts.get(symbol) != "sell":
            send(
                f"🚨 ESTRATÉGIA DOC: VENDA {symbol}\n"
                f"⏰ {now_sp.strftime('%d/%m %H:%M')} (SC)\n"
                f"Volume e Médias confirmados!"
            )
            sent_alerts[symbol] = "sell"

    except:
        pass

# ================================
# MAIN LOOP
# ================================
if __name__ == "__main__":
    keep_alive()
    time.sleep(10)

    now_sp = datetime.now(tz)
    send(f"🤖 Bot ativo às {now_sp.strftime('%d/%m %H:%M')} (SC) e monitorando o mercado!")

    last_heartbeat = time.time()

    while True:
        try:
            df_btc = get_data("BTCUSDT")

            if df_btc is not None:
                df_btc['sma21'] = df_btc['close'].rolling(21).mean()

                btc_up = df_btc.iloc[-1]['close'] > df_btc.iloc[-1]['sma21']
                btc_down = df_btc.iloc[-1]['close'] < df_btc.iloc[-1]['sma21']

                for s in symbols:
                    check(s, btc_up, btc_down)
                    time.sleep(1)

            # STATUS A CADA 1H
            if time.time() - last_heartbeat >= 3600:
                now_sp = datetime.now(tz)
                send(f"✅ Status {now_sp.strftime('%H:%M')} (SC): Monitorando mercado...")
                last_heartbeat = time.time()

        except:
            pass

        time.sleep(60)

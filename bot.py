import os
import requests
import pandas as pd
import time
from datetime import datetime
from flask import Flask
from threading import Thread
import pytz

# =========================
# FUSO HORÁRIO (SC)
# =========================
timezone = pytz.timezone("America/Sao_Paulo")

# =========================
# KEEP ALIVE (Render)
# =========================
app = Flask('')

@app.route('/')
def home():
    return "Bot rodando 24h 🚀"

def run():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    Thread(target=run).start()

# =========================
# TELEGRAM
# =========================
TOKEN = os.environ.get("TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

def send(msg):
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        requests.get(url, params={"chat_id": CHAT_ID, "text": msg}, timeout=10)
    except Exception as e:
        print(f"Erro Telegram: {e}")

# =========================
# PARES
# =========================
symbols = [
    "BTCUSDT","ETHUSDT","SOLUSDT","DOTUSDT","AVAXUSDT","DOGEUSDT",
    "ATOMUSDT","APTUSDT","GALAUSDT","FILUSDT","ICPUSDT","LINKUSDT"
]

sent_alerts = {}
last_heartbeat = 0

# =========================
# DADOS
# =========================
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

# =========================
# SUPER TREND
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
# CALCULO (SEM VOLUME)
# =========================
def calculate(df):
    df['sma_branca'] = df['close'].rolling(8).mean()
    df['sma_amarela'] = df['close'].rolling(21).mean()

    return supertrend(df)

# =========================
# VERIFICAR SINAIS (REVERSÃO)
# =========================
def check(symbol, btc_up, btc_down):
    try:
        df_raw = get_data(symbol)
        if df_raw is None:
            return

        df = calculate(df_raw)

        last = df.iloc[-1]
        prev = df.iloc[-2]

        agora = datetime.now(timezone).strftime("%H:%M")

        # COMPRA
        compra = (
            prev['trend'] == False and
            last['trend'] == True and
            last['close'] > last['open'] and
            last['close'] > last['sma_branca'] and
            btc_up
        )

        # VENDA
        venda = (
            prev['trend'] == True and
            last['trend'] == False and
            last['close'] < last['open'] and
            last['close'] < last['sma_branca'] and
            btc_down
        )

        if compra and sent_alerts.get(symbol) != "buy":
            send(
                f"🚀 BUY IMEDIATO: {symbol}\n"
                f"⏰ {agora} (SC)\n"
                f"🔥 Reversão detectada\n"
                f"📈 Médias a favor"
            )
            sent_alerts[symbol] = "buy"

        elif venda and sent_alerts.get(symbol) != "sell":
            send(
                f"🔻 SELL IMEDIATO: {symbol}\n"
                f"⏰ {agora} (SC)\n"
                f"🔥 Reversão detectada\n"
                f"📉 Médias a favor"
            )
            sent_alerts[symbol] = "sell"

    except Exception as e:
        print(f"Erro no check {symbol}: {e}")

# =========================
# LOOP PRINCIPAL
# =========================
if __name__ == "__main__":
    keep_alive()
    time.sleep(10)

    agora = datetime.now(timezone).strftime("%H:%M")
    send(f"🤖 Bot iniciado às {agora} (SC)\nMonitorando mercado...")

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
                agora = datetime.now(timezone).strftime("%H:%M")
                send(f"✅ STATUS {agora} (SC): Bot ativo.")
                last_heartbeat = time.time()

        except Exception as e:
            print(f"Erro geral: {e}")

        time.sleep(60)

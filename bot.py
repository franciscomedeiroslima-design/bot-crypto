import os
import requests
import pandas as pd
import time
from datetime import datetime
from flask import Flask
from threading import Thread
import pytz

# ================= SERVER =================
app = Flask('')

@app.route('/')
def home():
    return "Bot rodando 24h 🚀"

def run():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

# ================= CONFIG =================
TOKEN = os.environ.get("TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

if not TOKEN or not CHAT_ID:
    print("❌ ERRO: TOKEN ou CHAT_ID não definidos!")
else:
    print("✅ Telegram configurado")

timezone = pytz.timezone("America/Sao_Paulo")

symbols = [
    "BTCUSDT","ETHUSDT","SOLUSDT","DOTUSDT","AVAXUSDT","DOGEUSDT",
    "ATOMUSDT","APTUSDT","GALAUSDT","FILUSDT","ICPUSDT","LINKUSDT"
]

sent_alerts = {}

# ================= TELEGRAM =================
def send(msg):
    if not TOKEN or not CHAT_ID:
        print("⚠️ Mensagem não enviada (TOKEN/CHAT_ID ausente)")
        return

    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        requests.get(url, params={"chat_id": CHAT_ID, "text": msg}, timeout=10)
    except Exception as e:
        print(f"Erro Telegram: {e}")

# ================= DADOS =================
def get_data(symbol):
    try:
        url = f"https://api.bybit.com/v5/market/kline?category=linear&symbol={symbol}&interval=30&limit=200"
        res = requests.get(url, timeout=10).json()

        if "result" not in res or "list" not in res["result"]:
            print(f"Erro dados {symbol}")
            return None

        df = pd.DataFrame(res['result']['list'])
        df = df.iloc[::-1]

        df.columns = ["time","open","high","low","close","volume","turnover"]
        return df.astype(float)

    except Exception as e:
        print(f"Erro get_data {symbol}: {e}")
        return None

# ================= SUPERTREND =================
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

# ================= CALCULO =================
def calculate(df):
    df['sma_branca'] = df['close'].rolling(8).mean()
    df['sma_amarela'] = df['close'].rolling(21).mean()

    df['branca_subindo'] = df['sma_branca'] > df['sma_branca'].shift(1)

    return supertrend(df)

# ================= LÓGICA =================
def check(symbol, btc_up, btc_down):
    try:
        df_raw = get_data(symbol)
        if df_raw is None:
            return

        df = calculate(df_raw)

        if len(df) < 30:
            return

        last = df.iloc[-1]
        prev = df.iloc[-2]

        compra = (
            prev['trend'] == True and
            prev['close'] > prev['st'] and
            last['close'] > last['sma_branca'] and
            last['sma_branca'] > last['sma_amarela'] and
            last['branca_subindo'] and
            btc_up
        )

        venda = (
            prev['trend'] == False and
            prev['close'] < prev['st'] and
            last['close'] < last['sma_branca'] and
            last['sma_branca'] < last['sma_amarela'] and
            not last['branca_subindo'] and
            btc_down
        )

        agora = datetime.now(timezone).strftime("%H:%M")

        if compra and sent_alerts.get(symbol) != "buy":
            send(f"🚀 COMPRA {symbol}\n🕒 {agora}\n📈 Tendência confirmada")
            sent_alerts[symbol] = "buy"
            print(f"COMPRA {symbol}")

        elif venda and sent_alerts.get(symbol) != "sell":
            send(f"🔻 VENDA {symbol}\n🕒 {agora}\n📉 Tendência confirmada")
            sent_alerts[symbol] = "sell"
            print(f"VENDA {symbol}")

    except Exception as e:
        print(f"Erro no check {symbol}: {e}")

# ================= LOOP =================
if __name__ == "__main__":
    keep_alive()
    time.sleep(5)

    send("🤖 Bot iniciado com sucesso (SC)")

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

        except Exception as e:
            print(f"Erro geral: {e}")

        time.sleep(60)

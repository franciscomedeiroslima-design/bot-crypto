import os
import requests
import pandas as pd
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "Bot Estratégia DOC Online!"

def run():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port, threaded=True)

def keep_alive():
    t = Thread(target=run)
    t.start()

# =========================
# CONFIG
# =========================
TOKEN = os.environ.get("TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

if not TOKEN or not CHAT_ID:
    raise ValueError("TOKEN ou CHAT_ID não definidos!")

timezone = ZoneInfo("America/Sao_Paulo")

symbols = [
    "BTCUSDT","ETHUSDT","SOLUSDT","DOTUSDT","AVAXUSDT","DOGEUSDT",
    "ATOMUSDT","APTUSDT","GALAUSDT","FILUSDT","ICPUSDT","LINKUSDT"
]

sent_alerts = {}
last_heartbeat = time.time()

api_error_sent = False
bot_error_sent = False

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
        print(f"Erro Telegram: {e}")

# =========================
# DADOS
# =========================
def get_data(symbol):
    global api_error_sent

    try:
        url = f"https://api.bybit.com/v5/market/kline?category=linear&symbol={symbol}&interval=30&limit=200"
        data = requests.get(url, timeout=10).json()

        if 'result' not in data or 'list' not in data['result']:
            raise Exception("Resposta inválida da API")

        df = pd.DataFrame(data['result']['list'])

        if df.empty:
            raise Exception("DataFrame vazio")

        df = df.iloc[::-1]
        df.columns = ["time","open","high","low","close","volume","turnover"]

        if api_error_sent:
            send("✅ API restabelecida")
            api_error_sent = False

        return df.astype(float)

    except Exception as e:
        print(f"Erro API {symbol}: {e}")

        if not api_error_sent:
            send("🚨 ERRO: Falha ao conectar com API (Bybit)")
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
# INDICADORES
# =========================
def calculate(df):
    df['sma_branca'] = df['close'].rolling(8).mean()
    df['sma_amarela'] = df['close'].rolling(21).mean()
    df['branca_subindo'] = df['sma_branca'] > df['sma_branca'].shift(1)

    return supertrend(df)

# =========================
# SINAIS
# =========================
def check(symbol):
    try:
        df_raw = get_data(symbol)
        if df_raw is None or len(df_raw) < 30:
            return

        df = calculate(df_raw)

        last = df.iloc[-1]
        prev = df.iloc[-2]

        compra = (
            prev['trend'] == True and
            prev['close'] > prev['st'] and
            last['close'] > last['sma_branca'] and
            last['sma_branca'] > last['sma_amarela'] and
            last['branca_subindo']
        )

        venda = (
            prev['trend'] == False and
            prev['close'] < prev['st'] and
            last['close'] < last['sma_branca'] and
            last['sma_branca'] < last['sma_amarela'] and
            not last['branca_subindo']
        )

        if compra and sent_alerts.get(symbol) != "buy":
            send(f"🚀 COMPRA: {symbol}\n📈 Rompimento + tendência")
            sent_alerts[symbol] = "buy"

        elif venda and sent_alerts.get(symbol) != "sell":
            send(f"🔻 VENDA: {symbol}\n📉 Rompimento + tendência")
            sent_alerts[symbol] = "sell"

    except Exception as e:
        print(f"Erro no check de {symbol}: {e}")

# =========================
# MAIN
# =========================
if __name__ == "__main__":
    keep_alive()
    time.sleep(10)

    send("🤖 Bot iniciado com sucesso")

    while True:
        try:
            for s in symbols:
                check(s)
                time.sleep(1)

            # STATUS A CADA 4H
            if time.time() - last_heartbeat >= 14400:
                send("📡 Monitoramento ativo")
                last_heartbeat = time.time()

            # reset erro se tudo ok
            if bot_error_sent:
                bot_error_sent = False

        except Exception as e:
            print(f"Erro geral: {e}")

            if not bot_error_sent:
                send("🚨 ERRO CRÍTICO: Bot falhou")
                bot_error_sent = True

        time.sleep(60)

import os
import requests
import pandas as pd
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from flask import Flask, jsonify
from threading import Thread

app = Flask(__name__)

signals = []

# =========================
# CONFIG
# =========================
TOKEN = os.environ.get("TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
timezone = ZoneInfo("America/Sao_Paulo")

# 🔥 LISTA ATUALIZADA
symbols = [
    "DOTUSDT","IMXUSDT","ETCUSDT","ATOMUSDT","AVAXUSDT",
    "GALAUSDT","AXSUSDT","ONDOUSDT","APTUSDT","ALGOUSDT",
    "LDOUSDT","HBARUSDT","APEUSDT","JASMYUSDT","TRXUSDT",
    "NEOUSDT","XTZUSDT","TONUSDT","BTCUSDT","DOGEUSDT",
    "SOLUSDT","SEIUSDT","ETHUSDT"
]

sent_alerts = {}
last_heartbeat = time.time()

# =========================
# FLASK
# =========================
@app.route('/')
def home():
    return "Bot PRO Online 🚀"

@app.route('/signals')
def get_signals():
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
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        requests.get(url, params={"chat_id": CHAT_ID, "text": msg}, timeout=10)
    except Exception as e:
        print("Erro Telegram:", e)

# =========================
# DADOS
# =========================
def get_data(symbol):
    try:
        url = f"https://api.bybit.com/v5/market/kline?category=linear&symbol={symbol}&interval=30&limit=200"
        response = requests.get(url, timeout=10)

        if response.status_code != 200:
            return None

        data = response.json()

        if 'result' not in data or 'list' not in data['result']:
            return None

        df = pd.DataFrame(data['result']['list'])
        df = df.iloc[::-1]
        df.columns = ["time","open","high","low","close","volume","turnover"]

        return df.astype(float)

    except:
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

    df['sma8'] = df['close'].rolling(8).mean()
    df['sma21'] = df['close'].rolling(21).mean()
    df['slope8'] = df['sma8'] - df['sma8'].shift(1)

    df['body'] = abs(df['close'] - df['open'])
    df['range'] = df['high'] - df['low']
    df['strong'] = df['body'] > (df['range'] * 0.6)

    df['vol_mean'] = df['volume'].rolling(20).mean()
    df['vol_ratio'] = df['volume'] / df['vol_mean']

    df['lateral'] = abs(df['sma8'] - df['sma21']) < 0.0015

    return supertrend(df)

# =========================
# SCORE
# =========================
def calc_score(last):
    score = 0

    if last['strong']:
        score += 30

    if last['vol_ratio'] > 1:
        score += 25

    if abs(last['slope8']) > 0:
        score += 20

    if not last['lateral']:
        score += 25

    return min(score, 100)

# =========================
# MENSAGEM PREMIUM
# =========================
def format_msg(symbol, side, level, score, price):

    agora = datetime.now(timezone).strftime("%H:%M")

    emoji = "🟢📈" if side == "BUY" else "🔴📉"

    nivel_emoji = {
        "FORTE": "🔥",
        "MEDIO": "⚡",
        "LEVE": "🔵"
    }

    volume_txt = "Alto" if score > 80 else "Normal" if score > 60 else "Baixo"

    return f"""{emoji}{nivel_emoji[level]} {side} {level}

Ativo: {symbol}
Preço: {price:.4f}
Timeframe: 30m

📊 Força: {score}%
📦 Volume: {volume_txt}
⚡ Estratégia: Rompimento + Tendência

📊 Gráfico:
https://www.tradingview.com/chart/?symbol=BYBIT:{symbol}

🕒 {agora} (SC)
"""

# =========================
# CHECK
# =========================
def check(symbol):

    df_raw = get_data(symbol)
    if df_raw is None or df_raw.empty or len(df_raw) < 50:
        return

    df = calculate(df_raw)

    last = df.iloc[-1]
    prev = df.iloc[-2]

    score = calc_score(last)
    price = last['close']

    # 🔥 FORTE
    buy_forte = (
        prev['close'] < prev['st'] and
        last['close'] > last['st'] and
        score >= 80
    )

    sell_forte = (
        prev['close'] > prev['st'] and
        last['close'] < last['st'] and
        score >= 80
    )

    # ⚡ MÉDIO
    buy_medio = (
        last['close'] > last['sma8'] > last['sma21'] and
        score >= 60
    )

    sell_medio = (
        last['close'] < last['sma8'] < last['sma21'] and
        score >= 60
    )

    # 🔵 LEVE
    buy_leve = last['close'] > last['sma8']
    sell_leve = last['close'] < last['sma8']

    # PRIORIDADE
    if buy_forte and sent_alerts.get(symbol) != "buy_forte":
        send(format_msg(symbol, "BUY", "FORTE", score, price))
        signals.append({"symbol": symbol, "type": "BUY FORTE", "score": score})
        sent_alerts[symbol] = "buy_forte"

    elif sell_forte and sent_alerts.get(symbol) != "sell_forte":
        send(format_msg(symbol, "SELL", "FORTE", score, price))
        signals.append({"symbol": symbol, "type": "SELL FORTE", "score": score})
        sent_alerts[symbol] = "sell_forte"

    elif buy_medio and sent_alerts.get(symbol) != "buy_medio":
        send(format_msg(symbol, "BUY", "MEDIO", score, price))
        signals.append({"symbol": symbol, "type": "BUY MEDIO", "score": score})
        sent_alerts[symbol] = "buy_medio"

    elif sell_medio and sent_alerts.get(symbol) != "sell_medio":
        send(format_msg(symbol, "SELL", "MEDIO", score, price))
        signals.append({"symbol": symbol, "type": "SELL MEDIO", "score": score})
        sent_alerts[symbol] = "sell_medio"

    elif buy_leve and sent_alerts.get(symbol) != "buy_leve":
        send(format_msg(symbol, "BUY", "LEVE", score, price))
        signals.append({"symbol": symbol, "type": "BUY LEVE", "score": score})
        sent_alerts[symbol] = "buy_leve"

    elif sell_leve and sent_alerts.get(symbol) != "sell_leve":
        send(format_msg(symbol, "SELL", "LEVE", score, price))
        signals.append({"symbol": symbol, "type": "SELL LEVE", "score": score})
        sent_alerts[symbol] = "sell_leve"

# =========================
# LOOP
# =========================
if __name__ == "__main__":
    keep_alive()
    time.sleep(5)

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

        time.sleep(60)

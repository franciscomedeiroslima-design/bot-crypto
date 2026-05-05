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
    "BTCUSDT","ETHUSDT","SOLUSDT","AVAXUSDT","DOGEUSDT",
    "ATOMUSDT","APTUSDT","GALAUSDT","FILUSDT"
]

sent_alerts = {}
signals = []
history = []

# =========================
# TELEGRAM
# =========================
def send(msg):
    try:
        hora = datetime.now(timezone).strftime("%H:%M")
        msg_final = f"{msg}\n🕒 {hora}"

        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        requests.get(url, params={"chat_id": CHAT_ID, "text": msg_final}, timeout=10)
    except:
        pass

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

    except:
        return None

# =========================
# INDICADORES
# =========================
def calculate(df):
    df['sma8'] = df['close'].rolling(8).mean()
    df['sma21'] = df['close'].rolling(21).mean()
    return df

# =========================
# FILTRO LATERAL
# =========================
def is_lateral(df):
    diff = abs(df.iloc[-1]['sma8'] - df.iloc[-1]['sma21'])
    return diff < (df.iloc[-1]['close'] * 0.002)

# =========================
# FORÇA (RANKING)
# =========================
def strength(df):
    return abs(df.iloc[-1]['sma8'] - df.iloc[-1]['sma21'])

# =========================
# CHECK
# =========================
def check(symbol):
    df = get_data(symbol)
    if df is None:
        return

    df = calculate(df)

    last = df.iloc[-1]
    prev = df.iloc[-2]

    if is_lateral(df):
        return

    # SNIPER BUY
    sniper_buy = (
        prev['close'] < prev['sma8'] and
        last['close'] > last['sma8']
    )

    # SNIPER SELL
    sniper_sell = (
        prev['close'] > prev['sma8'] and
        last['close'] < last['sma8']
    )

    # CONFIRMAÇÃO
    confirm_buy = last['sma8'] > last['sma21']
    confirm_sell = last['sma8'] < last['sma21']

    signal = None

    if sniper_buy:
        signal = "SNIPER BUY"
    elif sniper_sell:
        signal = "SNIPER SELL"
    elif confirm_buy:
        signal = "BUY"
    elif confirm_sell:
        signal = "SELL"

    if signal and sent_alerts.get(symbol) != signal:
        data = {
            "symbol": symbol,
            "signal": signal,
            "time": datetime.now(timezone).strftime("%H:%M"),
            "strength": round(strength(df), 4)
        }

        signals.append(data)
        history.append(data)
        send(f"{signal} - {symbol}")

        sent_alerts[symbol] = signal

# =========================
# LOOP
# =========================
def loop():
    while True:
        for s in symbols:
            check(s)
            time.sleep(1)
        time.sleep(60)

# =========================
# API
# =========================
@app.route("/api/signals")
def api_signals():
    return jsonify(signals[-10:])

@app.route("/api/history")
def api_history():
    return jsonify(history[-50:])

@app.route("/api/ranking")
def api_ranking():
    ranking = []
    for s in symbols:
        df = get_data(s)
        if df is None:
            continue
        df = calculate(df)
        ranking.append({
            "symbol": s,
            "score": strength(df)
        })

    ranking = sorted(ranking, key=lambda x: x['score'], reverse=True)
    return jsonify(ranking)

# =========================
# FRONT (PAINEL)
# =========================
@app.route("/")
def dashboard():
    return """
    <html>
    <head>
    <title>BOT PRO</title>
    <style>
    body { background:#0e0e0e; color:white; font-family:Arial; }
    .card { padding:10px; margin:10px; background:#1c1c1c; border-radius:10px;}
    </style>
    </head>
    <body>

    <h1>📊 BOT SNIPER PRO</h1>

    <div class="card">
    <h2>🔥 Sinais</h2>
    <div id="signals"></div>
    </div>

    <div class="card">
    <h2>🏆 Ranking</h2>
    <div id="ranking"></div>
    </div>

    <script>
    async function load(){
        let s = await fetch('/api/signals').then(r=>r.json())
        let r = await fetch('/api/ranking').then(r=>r.json())

        document.getElementById('signals').innerHTML =
            s.map(x=>`${x.symbol} - ${x.signal}`).join('<br>')

        document.getElementById('ranking').innerHTML =
            r.map(x=>`${x.symbol} ⭐ ${x.score}`).join('<br>')
    }

    setInterval(load, 3000)
    load()
    </script>

    </body>
    </html>
    """

# =========================
# START
# =========================
if __name__ == "__main__":
    Thread(target=loop).start()

    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

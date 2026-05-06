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
    "last_heartbeat": time.time()
}

# =========================
# DASHBOARD HTML
# =========================
@app.route('/')
def dashboard():
    return """
    <html>
    <head>
        <title>Bot PRO Dashboard</title>
        <style>
            body { background:#0f172a; color:white; font-family:Arial; }
            h1 { text-align:center; }
            table { width:100%; border-collapse:collapse; }
            th, td { padding:10px; text-align:center; }
            th { background:#1e293b; }
            tr:nth-child(even) { background:#111827; }
        </style>
    </head>
    <body>
        <h1>🚀 BOT PRO - SINAIS</h1>
        <table id="tabela">
            <tr>
                <th>Moeda</th>
                <th>Tipo</th>
                <th>Preço</th>
                <th>Hora</th>
            </tr>
        </table>

        <script>
            async function load(){
                let res = await fetch('/api/signals');
                let data = await res.json();

                let tabela = document.getElementById("tabela");
                tabela.innerHTML = `
                    <tr>
                        <th>Moeda</th>
                        <th>Tipo</th>
                        <th>Preço</th>
                        <th>Hora</th>
                    </tr>
                `;

                data.reverse().forEach(s => {
                    tabela.innerHTML += `
                        <tr>
                            <td>${s.symbol}</td>
                            <td>${s.type}</td>
                            <td>${s.price}</td>
                            <td>${s.time}</td>
                        </tr>
                    `;
                });
            }

            setInterval(load, 3000);
            load();
        </script>
    </body>
    </html>
    """

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
            params={"chat_id": CHAT_ID, "text": f"{msg}\n🕒 {agora}"},
            timeout=10
        )
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
    return supertrend(df)

# =========================
# CHECK (NÍVEIS + SUPERTREND)
# =========================
def check(symbol):
    df_raw = get_data(symbol)
    if df_raw is None or len(df_raw) < 50:
        return

    df = calculate(df_raw)

    last = df.iloc[-1]
    prev = df.iloc[-2]

    price = round(last['close'], 4)
    agora = datetime.now(timezone).strftime("%H:%M")

    # 🔥 FORTE (ROMPIMENTO SUPERTREND)
    buy_forte = prev['trend'] == False and last['trend'] == True
    sell_forte = prev['trend'] == True and last['trend'] == False

    # ⚡ MÉDIO
    buy_medio = last['sma8'] > last['sma21']
    sell_medio = last['sma8'] < last['sma21']

    # 🔵 LEVE
    buy_leve = last['close'] > last['sma8']
    sell_leve = last['close'] < last['sma8']

    # PRIORIDADE
    if buy_forte and sent_alerts.get(symbol) != "buy_forte":
        msg = f"🟢📈🔥 COMPRA FORTE\n{symbol}\nPreço: {price}"
        send(msg)
        signals.append({"symbol": symbol, "type": "BUY FORTE", "price": price, "time": agora})
        sent_alerts[symbol] = "buy_forte"

    elif sell_forte and sent_alerts.get(symbol) != "sell_forte":
        msg = f"🔴📉🔥 VENDA FORTE\n{symbol}\nPreço: {price}"
        send(msg)
        signals.append({"symbol": symbol, "type": "SELL FORTE", "price": price, "time": agora})
        sent_alerts[symbol] = "sell_forte"

    elif buy_medio and sent_alerts.get(symbol) != "buy_medio":
        msg = f"🟢📈⚡ COMPRA MÉDIA\n{symbol}\nPreço: {price}"
        send(msg)
        signals.append({"symbol": symbol, "type": "BUY MEDIO", "price": price, "time": agora})
        sent_alerts[symbol] = "buy_medio"

    elif sell_medio and sent_alerts.get(symbol) != "sell_medio":
        msg = f"🔴📉⚡ VENDA MÉDIA\n{symbol}\nPreço: {price}"
        send(msg)
        signals.append({"symbol": symbol, "type": "SELL MEDIO", "price": price, "time": agora})
        sent_alerts[symbol] = "sell_medio"

    elif buy_leve and sent_alerts.get(symbol) != "buy_leve":
        msg = f"🟢📈🔵 COMPRA LEVE\n{symbol}\nPreço: {price}"
        send(msg)
        signals.append({"symbol": symbol, "type": "BUY LEVE", "price": price, "time": agora})
        sent_alerts[symbol] = "buy_leve"

    elif sell_leve and sent_alerts.get(symbol) != "sell_leve":
        msg = f"🔴📉🔵 VENDA LEVE\n{symbol}\nPreço: {price}"
        send(msg)
        signals.append({"symbol": symbol, "type": "SELL LEVE", "price": price, "time": agora})
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

            if time.time() - state["last_heartbeat"] >= 14400:
                send("📡 Monitoramento ativo")
                state["last_heartbeat"] = time.time()

        except Exception as e:
            print("Erro:", e)

        time.sleep(60)

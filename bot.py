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
# FLASK / DASHBOARD
# =========================
@app.route('/')
def dashboard():

    return """
    <html>
    <head>
        <title>BOT SUPERTREND PRO</title>

        <style>
            body{
                background:#0f172a;
                color:white;
                font-family:Arial;
                padding:20px;
            }

            h1{
                text-align:center;
                margin-bottom:30px;
            }

            table{
                width:100%;
                border-collapse:collapse;
            }

            th{
                background:#111827;
                padding:12px;
            }

            td{
                padding:10px;
                text-align:center;
                border-bottom:1px solid #1f2937;
            }

            tr:nth-child(even){
                background:#111827;
            }

            .buy{
                color:#00ff88;
                font-weight:bold;
            }

            .sell{
                color:#ff4d4d;
                font-weight:bold;
            }
        </style>
    </head>

    <body>

        <h1>🚀 BOT SUPERTREND SNIPER M5</h1>

        <table id="tabela">

            <tr>
                <th>MOEDA</th>
                <th>SINAL</th>
                <th>PREÇO</th>
                <th>HORÁRIO</th>
            </tr>

        </table>

        <script>

        async function carregar(){

            let req = await fetch('/api/signals');
            let data = await req.json();

            let tabela = document.getElementById("tabela");

            tabela.innerHTML = `
                <tr>
                    <th>MOEDA</th>
                    <th>SINAL</th>
                    <th>PREÇO</th>
                    <th>HORÁRIO</th>
                </tr>
            `;

            data.reverse().forEach(s => {

                let classe = s.type == "BUY" ? "buy" : "sell";

                tabela.innerHTML += `
                    <tr>
                        <td>${s.symbol}</td>
                        <td class="${classe}">${s.type}</td>
                        <td>${s.price}</td>
                        <td>${s.time}</td>
                    </tr>
                `;
            });
        }

        setInterval(carregar, 3000);

        carregar();

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
            params={
                "chat_id": CHAT_ID,
                "text": f"{msg}\n🕒 {agora} (SC)"
            },
            timeout=10
        )

    except Exception as e:
        print("Erro Telegram:", e)

# =========================
# DADOS BYBIT
# =========================
def get_data(symbol):

    try:

        # TIMEFRAME 5m
        url = f"https://api.bybit.com/v5/market/kline?category=linear&symbol={symbol}&interval=5&limit=200"

        response = requests.get(url, timeout=10)

        data = response.json()

        df = pd.DataFrame(data['result']['list'])

        df = df.iloc[::-1]

        df.columns = [
            "time",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "turnover"
        ]

        return df.astype(float)

    except Exception as e:

        print("Erro API:", e)

        return None

# =========================
# SUPERTREND REAL
# =========================
def supertrend(df, period=10, factor=2):

    hl2 = (df['high'] + df['low']) / 2

    atr = (df['high'] - df['low']).rolling(period).mean()

    upperband = hl2 + (factor * atr)
    lowerband = hl2 - (factor * atr)

    trend = [True]
    st = [lowerband.iloc[0]]

    for i in range(1, len(df)):

        if df['close'].iloc[i] > st[i-1]:
            trend.append(True)

        elif df['close'].iloc[i] < st[i-1]:
            trend.append(False)

        else:
            trend.append(trend[i-1])

        if trend[i]:
            st.append(lowerband.iloc[i])
        else:
            st.append(upperband.iloc[i])

    df['trend'] = trend
    df['st'] = st

    return df

# =========================
# INDICADORES
# =========================
def calculate(df):

    df['sma8'] = df['close'].rolling(8).mean()

    df['vol_ma'] = df['volume'].rolling(20).mean()

    return supertrend(df)

# =========================
# ESTRATÉGIA
# VIRADA EXATA SUPERTREND
# =========================
def check(symbol):

    df_raw = get_data(symbol)

    if df_raw is None or len(df_raw) < 50:
        return

    df = calculate(df_raw)

    last = df.iloc[-1]
    prev = df.iloc[-2]

    preco = round(last['close'], 4)

    agora = datetime.now(timezone).strftime("%H:%M")

    # =========================
    # FILTROS
    # =========================
    volume_forte = (
        last['volume'] > last['vol_ma'] * 1.3
    )

    corpo = abs(last['close'] - last['open'])

    range_candle = last['high'] - last['low']

    corpo_forte = (
        corpo > (range_candle * 0.5)
    )

    # =========================
    # VIRADA EXATA
    # =========================
    buy_signal = (

        prev['trend'] == False and
        last['trend'] == True and

        last['close'] > last['st'] and

        volume_forte and
        corpo_forte
    )

    sell_signal = (

        prev['trend'] == True and
        last['trend'] == False and

        last['close'] < last['st'] and

        volume_forte and
        corpo_forte
    )

    # =========================
    # COMPRA
    # =========================
    if buy_signal and sent_alerts.get(symbol) != "buy":

        stop = round(preco * 0.992, 4)
        alvo = round(preco * 1.015, 4)

        msg = f"""
🟢📈 VIRADA SUPERTREND

📊 {symbol}
⏱ TF: 5m
💰 Preço: {preco}

⚡ Supertrend virou para COMPRA
🔥 Volume forte detectado

🎯 Entrada: {preco}
🛑 Stop: {stop}
🎯 Alvo: {alvo}
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
    elif sell_signal and sent_alerts.get(symbol) != "sell":

        stop = round(preco * 1.008, 4)
        alvo = round(preco * 0.985, 4)

        msg = f"""
🔴📉 VIRADA SUPERTREND

📊 {symbol}
⏱ TF: 5m
💰 Preço: {preco}

⚡ Supertrend virou para VENDA
🔥 Volume forte detectado

🎯 Entrada: {preco}
🛑 Stop: {stop}
🎯 Alvo: {alvo}
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
# LOOP PRINCIPAL
# =========================
if __name__ == "__main__":

    keep_alive()

    time.sleep(5)

    send("🤖 BOT SUPERTREND SNIPER M5 ATIVO")

    while True:

        try:

            for symbol in symbols:

                check(symbol)

                time.sleep(1)

            # HEARTBEAT
            if time.time() - state["last_heartbeat"] >= 14400:

                send("📡 Monitoramento ativo")

                state["last_heartbeat"] = time.time()

        except Exception as e:

            print("Erro geral:", e)

        # verifica a cada 60s
        time.sleep(60)

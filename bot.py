import os
import requests
import pandas as pd
import numpy as np
import time
from datetime import datetime
from flask import Flask
from threading import Thread

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

# Configurações de ambiente
TOKEN = os.environ.get("TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

symbols = [
    "BTCUSDT","ETHUSDT","SOLUSDT","DOTUSDT","AVAXUSDT","DOGEUSDT",
    "ATOMUSDT","APTUSDT","GALAUSDT","FILUSDT","ICPUSDT","LINKUSDT"
]

sent_alerts = {}
last_heartbeat = 0 

def send(msg):
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        requests.get(url, params={"chat_id": CHAT_ID, "text": msg}, timeout=10)
    except Exception as e:
        print(f"Erro Telegram: {e}")

def get_data(symbol):
    try:
        # Gráfico de 30 minutos conforme o DOC
        url = f"https://api.bybit.com/v5/market/kline?category=linear&symbol={symbol}&interval=30&limit=200"
        data = requests.get(url).json()
        df = pd.DataFrame(data['result']['list'])
        df = df.iloc[::-1]
        df.columns = ["time","open","high","low","close","volume","turnover"]
        return df.astype(float)
    except:
        return None

def supertrend(df, period=10, factor=2):
    hl2 = (df['high'] + df['low']) / 2
    atr = (df['high'] - df['low']).rolling(period).mean()
    upper = hl2 + factor * atr
    lower = hl2 - factor * atr
    trend, st = [True], [lower.iloc[0]]
    for i in range(1, len(df)):
        if df['close'].iloc[i] > st[i-1]: trend.append(True)
        elif df['close'].iloc[i] < st[i-1]: trend.append(False)
        else: trend.append(trend[i-1])
        st.append(lower.iloc[i] if trend[i] else upper.iloc[i])
    df['st'], df['trend'] = st, trend
    return df

def calculate(df):
    # SMA Branca (8) e SMA Amarela (21)
    df['sma_branca'] = df['close'].rolling(8).mean()
    df['sma_amarela'] = df['close'].rolling(21).mean()
    
    # Volume a favor da tendência (Bastante Volume)
    df['vol_ma'] = df['volume'].rolling(20).mean()
    df['volume_forte'] = df['volume'] > (df['vol_ma'] * 1.1) # 10% acima da média
    
    # Inclinação das Médias (Slope) para garantir tendência definida[cite: 1]
    df['subindo'] = (df['sma_branca'] > df['sma_branca'].shift(1)) & (df['sma_amarela'] > df['sma_amarela'].shift(1))
    df['descendo'] = (df['sma_branca'] < df['sma_branca'].shift(1)) & (df['sma_amarela'] < df['sma_amarela'].shift(1))
    
    return supertrend(df)

def check(symbol, btc_up, btc_down):
    try:
        df_raw = get_data(symbol)
        if df_raw is None: return
        df = calculate(df_raw)
        last = df.iloc[-1]   # Candle atual (2º candle iniciando)[cite: 1]
        prev = df.iloc[-2]   # Candle que rompeu o PST[cite: 1]
        
        # CONDIÇÃO DE COMPRA[cite: 1]
        # 1. Rompimento PST + 2. Volume Forte + 3. Acima das SMAs + 4. SMAs subindo + 5. BTC em alta
        compra = (prev['close'] > prev['st'] and prev['trend'] == True and 
                  last['close'] > last['sma_branca'] and last['close'] > last['sma_amarela'] and
                  last['volume_forte'] and last['subindo'] and btc_up)
        
        # CONDIÇÃO DE VENDA[cite: 1]
        # 1. Rompimento PST + 2. Volume Forte + 3. Abaixo das SMAs + 4. SMAs descendo + 5. BTC em queda
        venda = (prev['close'] < prev['st'] and prev['trend'] == False and 
                 last['close'] < last['sma_branca'] and last['close'] < last['sma_amarela'] and
                 last['volume_forte'] and last['descendo'] and btc_down)

        if compra and sent_alerts.get(symbol) != "buy":
            send(f"🚨 ESTRATÉGIA DOC: COMPRA {symbol}\nVolume e Médias confirmados!")
            sent_alerts[symbol] = "buy"
        elif venda and sent_alerts.get(symbol) != "sell":
            send(f"🚨 ESTRATÉGIA DOC: VENDA {symbol}\nVolume e Médias confirmados!")
            sent_alerts[symbol] = "sell"
    except:
        pass

if __name__ == "__main__":
    keep_alive()
    time.sleep(10)
    send("🤖 Bot estabilizado e monitorando o mercado!")
    last_heartbeat = time.time()

    while True:
        try:
            # Filtro BTC sempre a favor[cite: 1]
            df_btc = get_data("BTCUSDT")
            if df_btc is not None:
                df_btc['sma21'] = df_btc['close'].rolling(21).mean()
                btc_up = df_btc.iloc[-1]['close'] > df_btc.iloc[-1]['sma21']
                btc_down = df_btc.iloc[-1]['close'] < df_btc.iloc[-1]['sma21']

                for s in symbols:
                    check(s, btc_up, btc_down)
                    time.sleep(1) 
            
            # Mensagem de Status (1h)
            if time.time() - last_heartbeat >= 3600:
                send(f"✅ Status {datetime.now().strftime('%H:%M')}: Monitorando conforme o DOC.")
                last_heartbeat = time.time()
        except:
            pass
        time.sleep(60)

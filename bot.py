# ==========================================
# PARTE 1: O TOPO (Configurações e Segurança)
# ==========================================
from flask import Flask
from threading import Thread
import os
import requests
import pandas as pd
import numpy as np
import time

app = Flask('')

@app.route('/')
def home():
    return "Bot Online!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# Pega as chaves que você vai cadastrar no painel do Render
TOKEN = os.environ.get("TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

symbols = [
    "BTCUSDT","ETHUSDT","SOLUSDT","DOTUSDT","AVAXUSDT","DOGEUSDT",
    "ATOMUSDT","APTUSDT","GALAUSDT","FILUSDT","ICPUSDT","LINKUSDT"
]

sent_alerts = {}

# ==========================================
# PARTE 2: O MIOLO (Suas Funções de Análise)
# ==========================================

def send(msg):
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        requests.get(url, params={"chat_id": CHAT_ID, "text": msg}, timeout=10)
    except:
        pass

def get_data(symbol):
    url = f"https://api.bybit.com/v5/market/kline?category=linear&symbol={symbol}&interval=30&limit=200"
    data = requests.get(url).json()
    df = pd.DataFrame(data['result']['list'])
    df = df.iloc[::-1]
    df.columns = ["time","open","high","low","close","volume","turnover"]
    return df.astype(float)

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
    df['st'], df['trend'] = st, trend
    return df

def calculate(df):
    df['sma8'] = df['close'].rolling(8).mean()
    df['sma21'] = df['close'].rolling(21).mean()
    df['vol_ma'] = df['volume'].rolling(20).mean()
    df['vol_forte'] = df['volume'] > df['vol_ma']
    df['alta'], df['baixa'] = df['close'] > df['open'], df['close'] < df['open']
    return supertrend(df)

def check(symbol, btc_up, btc_down):
    try:
        df = calculate(get_data(symbol))
        last, prev = df.iloc[-1], df.iloc[-2]
        
        compra = (last['alta'] and prev['close'] <= prev['st'] and last['close'] > last['st'] and 
                  last['close'] > last['sma8'] and last['vol_forte'] and btc_up)
        
        venda = (last['baixa'] and prev['close'] >= prev['st'] and last['close'] < last['st'] and 
                 last['close'] < last['sma8'] and last['vol_forte'] and btc_down)

        if compra and sent_alerts.get(symbol) != "buy":
            send(f"🚀 COMPRA {symbol}")
            sent_alerts[symbol] = "buy"
        elif venda and sent_alerts.get(symbol) != "sell":
            send(f"🔻 VENDA {symbol}")
            sent_alerts[symbol] = "sell"
    except:
        pass

# ==========================================
# PARTE 3: A BASE (O Loop de Execução)
# ==========================================

if __name__ == "__main__":
    keep_alive() # Liga o servidor para o Render não dormir[cite: 1]
    send("Estou vivo e configurado corretamente!")
    # ADICIONE ESTA LINHA PARA TESTAR ASSIM QUE LIGAR:
    send("🤖 Bot iniciado com sucesso no Render!")
    
    while True:
        try:
            # Otimização: Checa o BTC uma vez por minuto[cite: 1]
            df_btc = get_data("BTCUSDT")
            df_btc['sma21'] = df_btc['close'].rolling(21).mean()
            btc_up = df_btc.iloc[-1]['close'] > df_btc.iloc[-1]['sma21']
            btc_down = df_btc.iloc[-1]['close'] < df_btc.iloc[-1]['sma21']

            for s in symbols:
                check(s, btc_up, btc_down)
                time.sleep(1) # Pausa curta para não travar
        except Exception as e:
            print(f"Erro no loop: {e}")
            
        time.sleep(60) # Espera 1 minuto para a próxima rodada

import requests
import time
import pandas as pd

# =========================
# CONFIG
# =========================
TOKEN = 8582837299:AAHmZ4KOoEGem6PNOLNTYxPpWShixxDSDZg
CHAT_ID = 8722379778
SYMBOLS = ["BTCUSDT", "ETHUSDT"]
INTERVAL = "30"
LIMIT = 200

# =========================
# TELEGRAM
# =========================
def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = {
        "chat_id": CHAT_ID,
        "text": msg
    }
    try:
        requests.post(url, data=data)
    except:
        print("Erro ao enviar Telegram")

# =========================
# BYBIT DATA
# =========================
def get_data(symbol):
    url = f"https://api.bybit.com/v5/market/kline?category=linear&symbol={symbol}&interval={INTERVAL}&limit={LIMIT}"
    r = requests.get(url).json()
    data = r["result"]["list"]

    df = pd.DataFrame(data, columns=[
        "time","open","high","low","close","volume","turnover"
    ])

    df = df.astype(float)
    df = df.sort_values("time")

    return df

# =========================
# PST (simples)
# =========================
def calc_pst(df):
    df["pst_high"] = df["high"].rolling(5).max()
    df["pst_low"] = df["low"].rolling(5).min()
    return df

# =========================
# LOOP
# =========================
print("BOT INICIADO...")

while True:
    for symbol in SYMBOLS:
        try:
            df = get_data(symbol)
            df = calc_pst(df)

            last = df.iloc[-1]

            price = last["close"]
            pst_high = last["pst_high"]
            pst_low = last["pst_low"]

            if price > pst_high:
                send_telegram(f"🚀 BUY {symbol}\nPreço: {price}")

            if price < pst_low:
                send_telegram(f"🔻 SELL {symbol}\nPreço: {price}")

            print(f"{symbol} ok")

        except Exception as e:
            print("Erro:", e)

    time.sleep(60)
    import time

print("BOT INICIADO COM SUCESSO...")

while True:
    try:
        print("Bot rodando 24h...")
        
        # CHAME SUA FUNÇÃO PRINCIPAL AQUI
        # exemplo:
        # run_strategy()

        time.sleep(60)  # roda a cada 60 segundos

    except Exception as e:
        print("Erro:", e)
        time.sleep(30)

import os
import time
import json
import numpy as np
from binance.client import Client
from binance.enums import *

from dotenv import load_dotenv
load_dotenv()

# Connexion Binance
api_key = os.getenv("API_KEY")
api_secret = os.getenv("API_SECRET")
client = Client(api_key, api_secret, testnet=True)

symbol = "BTCUSDT"
interval = Client.KLINE_INTERVAL_1HOUR
quantity = 0.001  # à ajuster selon ton solde Testnet

# Charger la position
if os.path.exists("position.json"):
    with open("position.json") as f:
        position = json.load(f)
else:
    position = {"in_position": False, "buy_price": 0}

def get_rsi(prices, period=14):
    deltas = np.diff(prices)
    gains = deltas[deltas > 0].sum() / period
    losses = -deltas[deltas < 0].sum() / period
    rs = gains / losses if losses != 0 else 0
    return 100 - (100 / (1 + rs))

while True:
    candles = client.get_klines(symbol=symbol, interval=interval, limit=100)
    closes = [float(c[4]) for c in candles]
    rsi = get_rsi(closes)
    last_price = closes[-1]

    print(f"RSI: {rsi:.2f} - Last Price: {last_price}")

    if rsi < 30 and not position["in_position"]:
        print("💰 Achat déclenché")
        client.order_market_buy(symbol=symbol, quantity=quantity)
        position["in_position"] = True
        position["buy_price"] = last_price

    elif position["in_position"]:
        buy_price = position["buy_price"]
        pnl = (last_price - buy_price) / buy_price * 100

        if pnl > 5 or rsi > 70 or pnl < -2:
            print("🚨 Vente déclenchée")
            client.order_market_sell(symbol=symbol, quantity=quantity)
            position["in_position"] = False
            position["buy_price"] = 0

    with open("position.json", "w") as f:
        json.dump(position, f)

    time.sleep(3600)  # Attendre 1h

import os
import json
import time
import pandas as pd
import numpy as np
import yfinance as yf
from sklearn.ensemble import RandomForestClassifier
from binance.client import Client
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()
api_key = os.getenv('BINANCE_API_KEY')
api_secret = os.getenv('BINANCE_API_SECRET')

# Initialiser Binance testnet
client = Client(api_key, api_secret)
client.API_URL = 'https://testnet.binance.vision/api'

# Fichier pour stocker la position actuelle
POSITION_FILE = "position.json"

# Lire/écrire la position
def read_position():
    if not os.path.exists(POSITION_FILE):
        return {"position": "none", "buy_price": 0.0}
    with open(POSITION_FILE, "r") as f:
        return json.load(f)

def write_position(position, buy_price):
    with open(POSITION_FILE, "w") as f:
        json.dump({"position": position, "buy_price": buy_price}, f)

# Charger les données BTC pour IA
def get_btc_data():
    df = yf.download('BTC-USD', start='2023-01-01', end='2024-01-01', interval='1d')
    df['MA5'] = df['Close'].rolling(window=5).mean()
    df['MA20'] = df['Close'].rolling(window=20).mean()
    df['Return'] = df['Close'].pct_change()
    df.dropna(inplace=True)
    df['Target'] = np.where(df['Close'].shift(-1) > df['Close'], 1, 0)
    return df

# Calcul automatique de la quantité de BTC à acheter pour un montant donné
def get_btc_quantity(usdt_amount, current_price):
    return round(usdt_amount / current_price, 6)

# Fonction principale
def run_bot():
    print(">>> BOT IA DE TRADING - DÉBUT <<<")
    data = get_btc_data()
    features = ['Open', 'High', 'Low', 'Close', 'Volume', 'MA5', 'MA20']
    X = data[features]
    y = data['Target']

    model = RandomForestClassifier(n_estimators=100, random_state=42)
    model.fit(X, y)

    last_data = X.iloc[-1].values.reshape(1, -1)
    prediction = model.predict(last_data)[0]

    position_data = read_position()
    ticker = client.get_symbol_ticker(symbol="BTCUSDT")
    current_price = float(ticker['price'])

    print(f"Prix actuel : {current_price:.2f} USDT")

    if position_data["position"] == "none":
        if prediction == 1:
            print("📈 Prédiction HAUSSE → Achat BTC")
            quantity = get_btc_quantity(10, current_price)
            try:
                order = client.order_market_buy(
                    symbol='BTCUSDT',
                    quoteOrderQty=10
                )
                print("✅ Ordre d'achat passé :", order['fills'][0]['price'], "USDT")
                write_position("long", current_price)
            except Exception as e:
                print("❌ Erreur lors de l'achat :", e)
        else:
            print("🕒 Pas de signal d'achat aujourd'hui.")

    elif position_data["position"] == "long":
        buy_price = position_data["buy_price"]
        pnl = (current_price - buy_price) / buy_price * 100
        print(f"💼 Position ouverte | Buy @ {buy_price} | PnL = {pnl:.2f}%")

        if pnl <= -2:
            print("🔻 Stop-loss déclenché → Vente BTC")
            balance = client.get_asset_balance(asset='BTC')
            quantity = float(balance['free'])
            try:
                client.order_market_sell(
                    symbol='BTCUSDT',
                    quantity=round(quantity, 6)
                )
                print("✅ Ordre de vente exécuté (stop-loss)")
                write_position("none", 0.0)
            except Exception as e:
                print("❌ Erreur lors de la vente :", e)

        elif pnl >= 3:
            print("🚀 Take-profit atteint → Vente BTC")
            balance = client.get_asset_balance(asset='BTC')
            quantity = float(balance['free'])
            try:
                client.order_market_sell(
                    symbol='BTCUSDT',
                    quantity=round(quantity, 6)
                )
                print("✅ Ordre de vente exécuté (take-profit)")
                write_position("none", 0.0)
            except Exception as e:
                print("❌ Erreur lors de la vente :", e)
        else:
            print("🔄 Position conservée.")

    print(">>> BOT TERMINÉ <<<\n")

# Lancer le bot
if __name__ == "__main__":
    run_bot()

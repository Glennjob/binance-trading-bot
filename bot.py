import time
import numpy as np
from binance.client import Client
from binance.enums import *
from dotenv import load_dotenv
import os

load_dotenv()

API_KEY = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_API_SECRET")

client = Client(API_KEY, API_SECRET, testnet=True)

SYMBOL = "BTCUSDT"
INTERVAL = Client.KLINE_INTERVAL_1HOUR
RSI_PERIOD = 14

STOP_LOSS_PERCENT = 0.02  # 2%
TAKE_PROFIT_PERCENT = 0.05  # 5%
MAX_TRADE_RISK_PERCENT = 0.02  # Risquer max 2% du capital par trade

position = {
    "in_position": False,
    "entry_price": 0.0,
    "quantity": 0.0,
}

def get_klines(symbol, interval, limit=100):
    klines = client.get_klines(symbol=symbol, interval=interval, limit=limit)
    return klines

def close_prices(klines):
    return np.array([float(kline[4]) for kline in klines])

def volumes(klines):
    return np.array([float(kline[5]) for kline in klines])

def rsi(prices, period=14):
    deltas = np.diff(prices)
    seed = deltas[:period]
    up = seed[seed >= 0].sum() / period
    down = -seed[seed < 0].sum() / period
    rs = up / down if down != 0 else 0
    rsi = np.zeros_like(prices)
    rsi[:period] = 100. - 100. / (1. + rs)

    for i in range(period, len(prices)):
        delta = deltas[i - 1]
        upval = max(delta, 0)
        downval = -min(delta, 0)
        up = (up * (period - 1) + upval) / period
        down = (down * (period - 1) + downval) / period
        rs = up / down if down != 0 else 0
        rsi[i] = 100. - 100. / (1. + rs)

    return rsi

def moving_average(prices, window):
    return np.convolve(prices, np.ones(window), 'valid') / window

def macd(prices, fast=12, slow=26, signal=9):
    ema_fast = ema(prices, fast)
    ema_slow = ema(prices, slow)
    macd_line = ema_fast - ema_slow
    signal_line = ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram

def ema(prices, period):
    ema = np.zeros_like(prices)
    k = 2 / (period + 1)
    ema[0] = prices[0]
    for i in range(1, len(prices)):
        ema[i] = prices[i] * k + ema[i - 1] * (1 - k)
    return ema

def calculate_volatility(prices, window=14):
    returns = np.diff(np.log(prices))
    volatility = np.std(returns[-window:])
    return volatility

def adjust_rsi_thresholds(volatility, base_lower=30, base_upper=70):
    # Plus la volatilité est haute, plus on élargit les seuils RSI
    # Pour éviter faux signaux en marché très volatile
    factor = min(max(volatility * 100, 0), 10)  # normaliser à 0-10
    lower = base_lower - factor
    upper = base_upper + factor
    # Clamp entre 10 et 40 pour lower, 60 et 90 pour upper
    lower = max(10, min(lower, 40))
    upper = max(60, min(upper, 90))
    return lower, upper

def get_balance(asset="USDT"):
    balances = client.get_account()["balances"]
    for b in balances:
        if b["asset"] == asset:
            return float(b["free"])
    return 0.0

def calculate_order_quantity(balance, price, risk_percent, volatility):
    # On limite la taille du trade à 2% du capital ajustée par la volatilité (plus vol, moins on risque)
    risk_adjusted = risk_percent / (volatility * 100 + 1)
    amount = balance * risk_adjusted
    quantity = amount / price
    # Arrondir selon précision Binance (ex: 0.000001 BTC)
    precision = 6
    quantity = round(quantity, precision)
    return quantity

def buy_order(quantity):
    print(f"Passer un ordre d'achat de {quantity} {SYMBOL[:-4]}")
    order = client.create_order(
        symbol=SYMBOL,
        side=SIDE_BUY,
        type=ORDER_TYPE_MARKET,
        quantity=quantity
    )
    return order

def sell_order(quantity):
    print(f"Passer un ordre de vente de {quantity} {SYMBOL[:-4]}")
    order = client.create_order(
        symbol=SYMBOL,
        side=SIDE_SELL,
        type=ORDER_TYPE_MARKET,
        quantity=quantity
    )
    return order

def main():
    global position

    while True:
        try:
            klines = get_klines(SYMBOL, INTERVAL, limit=100)
            closes = close_prices(klines)
            vols = volumes(klines)
            last_price = closes[-1]

            # Calcul des indicateurs
            rsi_values = rsi(closes, RSI_PERIOD)
            volatility = calculate_volatility(closes)
            rsi_lower, rsi_upper = adjust_rsi_thresholds(volatility)

            ma_fast = moving_average(closes, 9)
            ma_slow = moving_average(closes, 26)

            macd_line, signal_line, histogram = macd(closes)

            avg_volume = np.mean(vols[-14:])

            print(f"RSI: {rsi_values[-1]:.2f} (seuils ajustés {rsi_lower:.1f}/{rsi_upper:.1f}) - Prix: {last_price:.2f} - Volatilité: {volatility:.5f}")

            balance_usdt = get_balance("USDT")

            if position["in_position"]:
                entry_price = position["entry_price"]
                quantity = position["quantity"]

                stop_loss_price = entry_price * (1 - STOP_LOSS_PERCENT)
                take_profit_price = entry_price * (1 + TAKE_PROFIT_PERCENT)

                # Gestion stop-loss / take-profit
                if last_price <= stop_loss_price:
                    print(f"Stop loss déclenché à {last_price:.2f}, vente pour limiter la perte.")
                    sell_order(quantity)
                    position = {"in_position": False, "entry_price": 0.0, "quantity": 0.0}

                elif last_price >= take_profit_price:
                    print(f"Take profit atteint à {last_price:.2f}, vente pour sécuriser le gain.")
                    sell_order(quantity)
                    position = {"in_position": False, "entry_price": 0.0, "quantity": 0.0}

                else:
                    # Si MACD négatif et RSI > upper seuil => vendre (confirmation tendance baissière)
                    if macd_line[-1] < signal_line[-1] and rsi_values[-1] > rsi_upper:
                        print("Signal de vente confirmé par MACD et RSI.")
                        sell_order(quantity)
                        position = {"in_position": False, "entry_price": 0.0, "quantity": 0.0}

                    else:
                        print("Position ouverte, attente...")

            else:
                # Conditions pour acheter :
                # RSI < seuil bas ajusté, MA rapide > MA lente (tendance haussière), MACD positif, volume au-dessus de la moyenne
                if (rsi_values[-1] < rsi_lower and
                    ma_fast[-1] > ma_slow[-1] and
                    macd_line[-1] > signal_line[-1] and
                    vols[-1] > avg_volume and
                    balance_usdt > 10):  # minimum 10 USDT pour trader

                    qty = calculate_order_quantity(balance_usdt, last_price, MAX_TRADE_RISK_PERCENT, volatility)
                    if qty > 0:
                        print("Signal d'achat détecté, passage ordre.")
                        buy_order(qty)
                        position = {"in_position": True, "entry_price": last_price, "quantity": qty}
                    else:
                        print("Quantité d'achat calculée trop faible, attente...")

                else:
                    print("Pas de signal d'achat, attente...")

            time.sleep(3600)  # attend 1 heure avant prochaine analyse

        except Exception as e:
            print(f"Erreur: {e}")
            time.sleep(60)  # attend 1 minute avant réessayer

if __name__ == "__main__":
    main()

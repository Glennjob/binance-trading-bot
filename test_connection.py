from binance.client import Client
import os
from dotenv import load_dotenv

# Charger les variables du fichier .env
load_dotenv()

# Connexion au client Binance en mode testnet
client = Client(os.getenv("API_KEY"), os.getenv("API_SECRET"), testnet=True)

# Récupérer les informations du compte
try:
    account = client.get_account()
    print("✅ Connexion réussie ! Solde disponible :")

    for asset in account['balances']:
        free_balance = float(asset['free'])
        if free_balance > 0:
            print(f"{asset['asset']}: {free_balance}")

except Exception as e:
    print("❌ Erreur de connexion :", e)

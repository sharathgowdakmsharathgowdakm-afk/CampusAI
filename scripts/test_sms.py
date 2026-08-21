import requests
import os
from dotenv import load_dotenv

load_dotenv()

api_key = os.environ.get('FAST2SMS_API_KEY', '').strip()

if api_key:
    print(f"API Key loaded: {api_key[:12]}...")
else:
    print("ERROR: FAST2SMS_API_KEY not loaded from .env!")
    exit(1)

# Test wallet/balance endpoint — no SMS is sent, no cost
headers = {"authorization": api_key}
try:
    r = requests.get("https://www.fast2sms.com/dev/wallet", headers=headers, timeout=30)
    result = r.json()
    print(f"\nAPI Response: {result}")
    
    if result.get("return") is True:
        balance = result.get("wallet", "N/A")
        print(f"\n[SUCCESS] Fast2SMS API key is VALID.")
        print(f"   Wallet Balance: Rs. {balance}")
    else:
        print(f"\n[ERROR] from Fast2SMS: {result}")
        
except requests.exceptions.Timeout:
    print("[ERROR] Request timed out. Check your internet connection.")
except Exception as e:
    print(f"[ERROR] Connection error: {e}")

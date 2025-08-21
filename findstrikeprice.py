import requests
from datetime import datetime
from typing import Optional

# LIVE TOKEN
ACCESS_TOKEN = "eyJ0eXAiOiJKV1QiLCJrZXlfaWQiOiJza192MS4wIiwiYWxnIjoiSFMyNTYifQ.eyJzdWIiOiI0QUNQVEYiLCJqdGkiOiI2OGE2OTc4MjRhODgyMTQ0YWNlM2M5MzUiLCJpc011bHRpQ2xpZW50IjpmYWxzZSwiaXNQbHVzUGxhbiI6ZmFsc2UsImlhdCI6MTc1NTc0ODIyNiwiaXNzIjoidWRhcGktZ2F0ZXdheS1zZXJ2aWNlIiwiZXhwIjoxNzU1ODEzNjAwfQ.IOObzM6ci0FvHWCE6YgYkrzAXzX60xeFcPisGAJ-Thg"

BASE_URL = "https://api.upstox.com/v2"
INSTRUMENT_KEY = "NSE_INDEX|Nifty 50"  # as per official docs :contentReference[oaicite:0]{index=0}

HEADERS = {
    "Authorization": f"Bearer {ACCESS_TOKEN}",
    "Accept": "application/json"
}

def get_expiries():
    url = f"{BASE_URL}/option/contract"
    resp = requests.get(url, headers=HEADERS, params={"instrument_key": INSTRUMENT_KEY}, timeout=10).json()
    expiries = {
        item.get("expiry") or item.get("expiry_date")
        for item in resp.get("data", [])
    }
    return sorted(expiries, key=lambda d: datetime.fromisoformat(d))

def get_option_chain(expiry_date):
    url = f"{BASE_URL}/option/chain"
    resp = requests.get(
        url,
        headers=HEADERS,
        params={"instrument_key": INSTRUMENT_KEY, "expiry_date": expiry_date},
        timeout=10
    ).json()
    if resp.get("status") != "success":
        print("Error fetching option chain:", resp)
        return []
    return resp.get("data", [])

def strike_prices(price1,price2):
    expiries = get_expiries()
    if not expiries:
        print("No expiry data — check your token scopes or instrument key.")
        return 0, 0

    expiry = expiries[0]  # nearest expiry
    # print("Expiry in use:", expiry)

    chain = get_option_chain(expiry)
    if not chain:
        print("No option chain data available.")
        return 0, 0

    ce_match = None
    pe_match = None

    for opt in chain:
        strike = opt["strike_price"]
        ce_ltp = opt.get("call_options", {}).get("market_data", {}).get("ltp", 0)
        pe_ltp = opt.get("put_options", {}).get("market_data", {}).get("ltp", 0)

        if ce_match is None and price1 <= ce_ltp <= price2:
            ce_match = (strike, ce_ltp)

        if pe_match is None and price1 <= pe_ltp <= price2:
            pe_match = (strike, pe_ltp)

        if ce_match and pe_match:
            break
    CE = 0
    PE = 0
    if ce_match:
        # print(f"CE Strike in ₹{price1}–{price2} LTP range: {ce_match[0]} – LTP: ₹{ce_match[1]}")
        CE = ce_match[0]
    else:
        print("No CE strike found in ₹{price1}–{price2} LTP range.")

    if pe_match:
        # print(f"PE Strike in ₹{price1}–{price2} LTP range: {pe_match[0]} – LTP: ₹{pe_match[1]}")
        PE = pe_match[0]
    else:
        print("No PE strike found in ₹{price1}–{price2} LTP range.")
    
    return expiry, CE, PE

def get_instrument_token(expiry: str, strike: float, option_type: str) -> Optional[str]:
    
    # Option chain API endpoint
    url = "https://api.upstox.com/v2/option/chain"
    params = {
        'instrument_key': 'NSE_INDEX|Nifty 50',
        'expiry_date': expiry
    }
    
    try:
        response = requests.get(url, headers=HEADERS, params=params)
        response.raise_for_status()
        data = response.json()
        
        if data.get('status') == 'success':
            for chain_item in data.get('data', []):
                if chain_item.get('strike_price') == strike:
                    option_data = chain_item.get('call_options' if option_type == 'CE' else 'put_options')
                    if option_data and option_data.get('instrument_key'):
                        # Extract token from instrument_key (format: NSE_FO|TOKEN)
                        return option_data['instrument_key'].split('|')[-1]
        
        return None
        
    except requests.exceptions.RequestException:
        return None



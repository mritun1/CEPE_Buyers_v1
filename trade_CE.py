import time
import requests
from datetime import datetime as dt, time as dtime
from findstrikeprice import strike_prices, get_instrument_token   # ✅ using your functions

# CONFIG
ACCESS_TOKEN = "eyJ0eXAiOiJKV1QiLCJrZXlfaWQiOiJza192MS4wIiwiYWxnIjoiSFMyNTYifQ.eyJzdWIiOiI0QUNQVEYiLCJqdGkiOiI2OGE2OTc4MjRhODgyMTQ0YWNlM2M5MzUiLCJpc011bHRpQ2xpZW50IjpmYWxzZSwiaXNQbHVzUGxhbiI6ZmFsc2UsImlhdCI6MTc1NTc0ODIyNiwiaXNzIjoidWRhcGktZ2F0ZXdheS1zZXJ2aWNlIiwiZXhwIjoxNzU1ODEzNjAwfQ.IOObzM6ci0FvHWCE6YgYkrzAXzX60xeFcPisGAJ-Thg"
USE_LIVE = False
LOT_SIZE = 75
STOP_LOSS_OFFSET = 5 # stop loss point
TRAIL_OFFSET = 3 # profit trail exit point
INTERVAL = 1 # second chart
BASE = "https://api.upstox.com/v3"
HEADERS = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Accept": "application/json"}

# CONSTANTS: Fees for Equity Options (Nifty weekly)
BROKERAGE_PER_ORDER = 20  # ₹20 or 0.05% of trade value (choose lower)
STT_RATE = 0.000625       # 0.0625% on sell-side premium
TRANSACTION_RATE = 0.0003503  # 0.03503% on premium
STAMP_DUTY_RATE = 0.00003     # 0.003% on buy side
SEBI_TURNOVER = 10 / 1e7      # ₹10 per crore = 10 / 10^7 per rupee
IPFT_RATE = 0.50 / 1e5        # ₹0.50 per lakh = 0.50 / 100000 per rupee
GST_RATE = 0.18               # 18%

day_pnl = 0.0
capital_used = 0.0  # Accumulate total cost of all entries


def log(msg):
    print(f"{dt.now()} - {msg}")


def is_market_open(now=None):
    now = now or dt.now()
    return dtime(9, 20) <= now.time() <= dtime(15, 10) # Market Open Close Time


def get_ltp(key):
    url = f"{BASE}/market-quote/ltp"
    resp = requests.get(url, headers=HEADERS, params={"instrument_key": key})
    resp.raise_for_status()
    data = resp.json().get("data", {})
    if not data:
        raise ValueError("No data returned")
    _, info = next(iter(data.items()))
    return info.get("last_price")


def place_order(key, side):
    if not USE_LIVE:
        log(f"[Paper] {side} {LOT_SIZE} of {key}")
        return True
    url = f"{BASE}/order/place"
    payload = {
        "instrument_key": key,
        "quantity": LOT_SIZE,
        "product": "M",
        "order_type": "MARKET",
        "transaction_type": side,
    }
    resp = requests.post(url, headers=HEADERS, json=payload)
    resp.raise_for_status()
    log(f"[LIVE] {side} order placed.")
    return True


def calculate_charges(price, side):
    total_value = price * LOT_SIZE
    brokerage = BROKERAGE_PER_ORDER   # flat ₹20 per order always
    transaction = total_value * TRANSACTION_RATE
    ipft = total_value * IPFT_RATE
    gst = GST_RATE * (brokerage + transaction + ipft)
    sebi = SEBI_TURNOVER * total_value
    stamp = total_value * STAMP_DUTY_RATE if side == "BUY" else 0
    stt = total_value * STT_RATE if side == "SELL" else 0
    return brokerage + transaction + gst + sebi + stamp + stt


# ✅ NEW: Dynamic instrument fetcher
def get_new_instrument():
    strikes = strike_prices(100, 200)  # (Expiry, Strike CE, Strike PE)
    token = get_instrument_token(strikes[0], strikes[1], 'CE')
    instrument_key = f"NSE_FO|{token}"   # ✅ prepend exchange
    log(f"🔄 Switched to new instrument: {instrument_key}")
    return instrument_key


def run_strategy(initial_key):
    global day_pnl, capital_used

    instrument_key = initial_key
    log(f"Starting strategy on {instrument_key}")
    prev = get_ltp(instrument_key)
    log(f"Initial LTP = {prev}")

    bought = False
    entry = peak = stop = None

    while is_market_open():
        time.sleep(INTERVAL)
        ltp = get_ltp(instrument_key)
        log(f"LTP: {ltp}, Prev: {prev}")

        if not bought and ltp > prev:
            place_order(instrument_key, "BUY")
            entry = ltp
            capital_used += entry * LOT_SIZE
            stop = entry - STOP_LOSS_OFFSET
            peak = entry
            bought = True
            log(f"Bought @ {entry}, SL = {stop}")

        elif bought:
            if ltp > peak:
                peak = ltp
                log(f"New peak: {peak}")

            running_pnl = (ltp - entry) * LOT_SIZE
            log(f"Running PnL (gross): {running_pnl:.2f}")

            if ltp <= peak - TRAIL_OFFSET or ltp <= stop:
                exit_side = "SELL"
                place_order(instrument_key, exit_side)
                exit_price = ltp
                gross_pnl = (exit_price - entry) * LOT_SIZE
                charges = calculate_charges(entry, "BUY") + calculate_charges(exit_price, "SELL")
                net_pnl = gross_pnl - charges
                day_pnl += net_pnl
                log(f"Exit @ {exit_price}, Gross PnL = {gross_pnl:.2f}, Charges = {charges:.2f}, Net PnL = {net_pnl:.2f}, Day PnL = {day_pnl:.2f}")
                
                # ✅ Switch to new instrument after exit
                instrument_key = get_new_instrument()
                prev = get_ltp(instrument_key)
                bought = False
                entry = peak = stop = None
                continue

        prev = ltp

    # Final square-off at market close
    if bought:
        exit_price = get_ltp(instrument_key)
        place_order(instrument_key, "SELL")
        gross_pnl = (exit_price - entry) * LOT_SIZE
        charges = calculate_charges(entry, "BUY") + calculate_charges(exit_price, "SELL")
        net_pnl = gross_pnl - charges
        day_pnl += net_pnl
        log(f"Market closed—square off @ {exit_price}, Net PnL = {net_pnl:.2f}, Day PnL = {day_pnl:.2f}")

    return day_pnl, capital_used


if __name__ == "__main__":
    # ✅ Start with first instrument
    start_instrument = get_new_instrument()
    pnl, used = run_strategy(start_instrument)
    return_pct = (pnl / used * 100) if used else 0.0
    log(f"Final Day PnL = {pnl:.2f}, Total Capital Used = {used:.2f}, Net Return = {return_pct:.2f}%")

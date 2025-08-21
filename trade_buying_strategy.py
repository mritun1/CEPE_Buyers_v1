import time
import requests
from datetime import datetime as dt, time as dtime
from findstrikeprice import strike_prices, get_instrument_token   # ✅ using your functions

# CONFIG
ACCESS_TOKEN = "eyJ0eXAiOiJKV1QiLCJrZXlfaWQiOiJza192MS4wIiwiYWxnIjoiSFMyNTYifQ.eyJzdWIiOiI0QUNQVEYiLCJqdGkiOiI2OGE2OTc4MjRhODgyMTQ0YWNlM2M5MzUiLCJpc011bHRpQ2xpZW50IjpmYWxzZSwiaXNQbHVzUGxhbiI6ZmFsc2UsImlhdCI6MTc1NTc0ODIyNiwiaXNzIjoidWRhcGktZ2F0ZXdheS1zZXJ2aWNlIiwiZXhwIjoxNzU1ODEzNjAwfQ.IOObzM6ci0FvHWCE6YgYkrzAXzX60xeFcPisGAJ-Thg"

USE_LIVE = False
LOT_SIZE = 75
STOP_LOSS_OFFSET = 5   # stop loss point
TRAIL_OFFSET = 3       # trail profit exit point
INTERVAL = 1           # 1 sec chart
BASE = "https://api.upstox.com/v3"
HEADERS = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Accept": "application/json"}

# CONSTANTS: Fees for Equity Options (Nifty weekly)
BROKERAGE_PER_ORDER = 20  # ₹20 or 0.05% of trade value (choose lower)
STT_RATE = 0.000625       # 0.0625% on sell-side premium
TRANSACTION_RATE = 0.0003503
STAMP_DUTY_RATE = 0.00003
SEBI_TURNOVER = 10 / 1e7
IPFT_RATE = 0.50 / 1e5
GST_RATE = 0.18

day_pnl = 0.0
capital_used = 0.0


def log(msg):
    print(f"{dt.now()} - {msg}")


def is_market_open(now=None):
    now = now or dt.now()
    return dtime(9, 20) <= now.time() <= dtime(15, 10)


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
    brokerage = BROKERAGE_PER_ORDER
    transaction = total_value * TRANSACTION_RATE
    ipft = total_value * IPFT_RATE
    gst = GST_RATE * (brokerage + transaction + ipft)
    sebi = SEBI_TURNOVER * total_value
    stamp = total_value * STAMP_DUTY_RATE if side == "BUY" else 0
    stt = total_value * STT_RATE if side == "SELL" else 0
    return brokerage + transaction + gst + sebi + stamp + stt


# ✅ Get CE & PE instruments dynamically
def get_instruments():
    strikes = strike_prices(100, 200)  # (expiry, ce_strike, pe_strike)
    ce_token = get_instrument_token(strikes[0], strikes[1], "CE")
    pe_token = get_instrument_token(strikes[0], strikes[2], "PE")
    ce_key = f"NSE_FO|{ce_token}"
    pe_key = f"NSE_FO|{pe_token}"
    log(f"Loaded instruments: CE={ce_key}, PE={pe_key}")
    return ce_key, pe_key


def run_strategy():
    global day_pnl, capital_used

    ce_key, pe_key = get_instruments()
    prev_ce = get_ltp(ce_key)
    prev_pe = get_ltp(pe_key)
    log(f"Initial CE LTP={prev_ce}, PE LTP={prev_pe}")

    bought = False
    entry = peak = stop = None
    active_key = None  # Will hold CE or PE key

    while is_market_open():
        time.sleep(INTERVAL)

        ce_ltp = get_ltp(ce_key)
        pe_ltp = get_ltp(pe_key)
        log(f"CE LTP={ce_ltp}, Prev={prev_ce} | PE LTP={pe_ltp}, Prev={prev_pe}")

        if not bought:
            if ce_ltp > prev_ce:  # ✅ Buy CE
                place_order(ce_key, "BUY")
                entry = ce_ltp
                capital_used += entry * LOT_SIZE
                stop = entry - STOP_LOSS_OFFSET
                peak = entry
                bought = True
                active_key = ce_key
                log(f"Bought CE @ {entry}, SL = {stop}")

            elif pe_ltp > prev_pe:  # ✅ Buy PE
                place_order(pe_key, "BUY")
                entry = pe_ltp
                capital_used += entry * LOT_SIZE
                stop = entry - STOP_LOSS_OFFSET
                peak = entry
                bought = True
                active_key = pe_key
                log(f"Bought PE @ {entry}, SL = {stop}")

        elif bought:
            ltp = get_ltp(active_key)
            if ltp > peak:
                peak = ltp
                log(f"New peak: {peak}")

            running_pnl = (ltp - entry) * LOT_SIZE
            log(f"Running PnL (gross): {running_pnl:.2f}")

            if ltp <= peak - TRAIL_OFFSET or ltp <= stop:
                place_order(active_key, "SELL")
                exit_price = ltp
                gross_pnl = (exit_price - entry) * LOT_SIZE
                charges = calculate_charges(entry, "BUY") + calculate_charges(exit_price, "SELL")
                net_pnl = gross_pnl - charges
                day_pnl += net_pnl
                log(f"Exit @ {exit_price}, Gross={gross_pnl:.2f}, Charges={charges:.2f}, Net={net_pnl:.2f}, Day={day_pnl:.2f}")

                # Reset for next trade
                bought = False
                entry = peak = stop = None
                active_key = None
                prev_ce, prev_pe = ce_ltp, pe_ltp
                continue

        prev_ce, prev_pe = ce_ltp, pe_ltp

    # ✅ Final square-off
    if bought:
        exit_price = get_ltp(active_key)
        place_order(active_key, "SELL")
        gross_pnl = (exit_price - entry) * LOT_SIZE
        charges = calculate_charges(entry, "BUY") + calculate_charges(exit_price, "SELL")
        net_pnl = gross_pnl - charges
        day_pnl += net_pnl
        log(f"Market closed—square off @ {exit_price}, Net={net_pnl:.2f}, Day={day_pnl:.2f}")

    return day_pnl, capital_used


if __name__ == "__main__":
    pnl, used = run_strategy()
    return_pct = (pnl / used * 100) if used else 0.0
    log(f"Final Day PnL={pnl:.2f}, Capital Used={used:.2f}, Net Return={return_pct:.2f}%")

from findstrikeprice import strike_prices,get_instrument_token


print(f"The result: {strike_prices(100,200)}")

strikes = strike_prices(100,200) # (Expiry date,Strike price CE,Strike price PE)
instrument_key = get_instrument_token(strikes[0], strikes[1], 'CE')
print(f"Instrument: {instrument_key}")
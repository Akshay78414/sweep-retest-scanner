import yfinance as yf
import pandas as pd
import numpy as np
import time
import requests
import os
from datetime import datetime

WEBHOOK_URL = os.environ.get("https://script.google.com/macros/s/AKfycbyi32CC0DvCcRc909il79vg4ODZOoZ__KUZLtn-zup69Izh2l8xqu7HXSNGmSH8jsUqJw/exec")

auto_stocks = ["MARUTI.NS", "M&M.NS", "BAJAJ-AUTO.NS", "EICHERMOT.NS",
               "HEROMOTOCO.NS", "ASHOKLEY.NS", "TVSMOTOR.NS", "BOSCHLTD.NS",
               "MRF.NS", "BALKRISIND.NS"]
pharma_stocks = ["SUNPHARMA.NS", "CIPLA.NS", "DRREDDY.NS", "DIVISLAB.NS",
                  "AUROPHARMA.NS", "LUPIN.NS", "TORNTPHARM.NS", "ALKEM.NS",
                  "BIOCON.NS", "ZYDUSLIFE.NS"]

sector_map = {t: "Auto" for t in auto_stocks}
sector_map.update({t: "Pharma" for t in pharma_stocks})
all_tickers = auto_stocks + pharma_stocks

def detect_fvgs(df):
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df['Bullish_FVG'] = df['Low'] > df['High'].shift(2)
    df['Bearish_FVG'] = df['High'] < df['Low'].shift(2)
    return df

def scan_for_live_setup(df, direction='Bullish', swing_lookback=10,
                          max_bars_to_shift=20, max_bars_to_retest=15):
    n = len(df)
    fvg_col = f'{direction}_FVG'
    search_start = max(swing_lookback, n - (max_bars_to_shift + max_bars_to_retest + 5))

    for i in range(search_start, n - 1):
        recent_low = df['Low'].iloc[i - swing_lookback:i].min()
        recent_high = df['High'].iloc[i - swing_lookback:i].max()

        if direction == 'Bullish':
            swept = df['Low'].iloc[i] < recent_low and df['Close'].iloc[i] > recent_low
        else:
            swept = df['High'].iloc[i] > recent_high and df['Close'].iloc[i] < recent_high
        if not swept:
            continue

        sweep_loc = i
        shift_loc = None
        for j in range(sweep_loc + 1, min(sweep_loc + 1 + max_bars_to_shift, n)):
            if direction == 'Bullish':
                if df['Close'].iloc[j] > recent_high:
                    shift_loc = j; break
            else:
                if df['Close'].iloc[j] < recent_low:
                    shift_loc = j; break
        if shift_loc is None:
            continue

        fvg_loc = None
        for k in range(sweep_loc + 1, shift_loc + 1):
            if df[fvg_col].iloc[k]:
                fvg_loc = k
        if fvg_loc is None:
            continue

        if direction == 'Bullish':
            gap_bottom = df['High'].iloc[fvg_loc - 2]
            gap_top = df['Low'].iloc[fvg_loc]
        else:
            gap_top = df['Low'].iloc[fvg_loc - 2]
            gap_bottom = df['High'].iloc[fvg_loc]

        entry_loc = None
        for m in range(shift_loc + 1, n):
            if direction == 'Bullish':
                if df['Low'].iloc[m] <= gap_top:
                    entry_loc = m; break
            else:
                if df['High'].iloc[m] >= gap_bottom:
                    entry_loc = m; break

        if direction == 'Bullish':
            entry_price = gap_top; stop_loss = gap_bottom; target = recent_high
        else:
            entry_price = gap_bottom; stop_loss = gap_top; target = recent_low

        if entry_loc is None:
            return {'Status': 'WATCHING', 'Entry_Price': round(entry_price, 2),
                    'Stop_Loss': round(stop_loss, 2), 'Target': round(target, 2)}
        elif entry_loc >= n - 2:
            return {'Status': 'TRIGGERED', 'Entry_Price': round(entry_price, 2),
                    'Stop_Loss': round(stop_loss, 2), 'Target': round(target, 2)}

    return None

def log_signal_to_sheet(ticker, sector, direction, result):
    payload = {
        "action": "SIGNAL",
        "date": datetime.now().strftime("%Y-%m-%d"),
        "ticker": ticker,
        "sector": sector,
        "direction": direction,
        "status": result['Status'],
        "entry_price": result['Entry_Price'],
        "stop_loss": result['Stop_Loss'],
        "target": result['Target'],
        "verdict": "Pending"
    }
    try:
        response = requests.post(WEBHOOK_URL, json=payload, timeout=15)
        print(f"  Logged {ticker} {direction}: {response.status_code}")
    except Exception as e:
        print(f"  Failed to log {ticker}: {e}")

print(f"Scanning as of {datetime.now().strftime('%Y-%m-%d %H:%M')}...")

for t in all_tickers:
    for direction in ['Bullish', 'Bearish']:
        try:
            raw = yf.download(t, start="2024-01-01", progress=False)
            if raw.empty:
                continue
            raw = detect_fvgs(raw)
            result = scan_for_live_setup(raw, direction=direction)
            if result:
                print(f"{t} ({sector_map[t]}) {direction}: {result}")
                log_signal_to_sheet(t, sector_map[t], direction, result)
            time.sleep(1)
        except Exception as e:
            print(f"Error on {t} ({direction}): {e}")

print("Scan complete.")

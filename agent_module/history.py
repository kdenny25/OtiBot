# Candle history for the agent backtest. Kraken only serves the last 720
# candles (2.5 days at 5 minutes), so history comes from Coinbase's public
# API, which pages back as far as needed. Saved as one CSV per pair.
import glob
import json
import os
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

API_URL = 'https://api.exchange.coinbase.com'
HISTORY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'history')
PAGE = 300                      # most candles Coinbase returns per request
# Kraken's old names for some coins
RENAMES = {'XBT': 'BTC', 'XDG': 'DOGE'}
# used when Kraken can't be reached to pick the most traded pairs
DEFAULT_PAIRS = ['BTC/USD', 'ETH/USD', 'SOL/USD', 'XRP/USD', 'DOGE/USD', 'ADA/USD', 'LINK/USD',
                 'AVAX/USD', 'SUI/USD', 'LTC/USD', 'DOT/USD', 'BCH/USD', 'PEPE/USD', 'SHIB/USD',
                 'UNI/USD', 'AAVE/USD', 'NEAR/USD', 'HBAR/USD', 'XLM/USD', 'BONK/USD']


def product_id(name):
    """ 'XBT/USD' -> 'BTC-USD' """
    base, quote = name.split('/')
    return f'{RENAMES.get(base, base)}-{quote}'


def display_name(name):
    base, quote = name.split('/')
    return f'{RENAMES.get(base, base)}/{quote}'


def top_pairs(limit=25):
    """ The most traded Kraken USD pairs right now, like the scan agent watches. """
    try:
        from agent_module.market import KrakenMarket
        market = KrakenMarket()
        pairs = market.usd_pairs()
        tickers = market.tickers(list(pairs))
        ranked = sorted(tickers, key=lambda p: tickers[p]['quote_volume'], reverse=True)
        return [display_name(pairs[p]) for p in ranked[:limit]]
    except Exception:
        return DEFAULT_PAIRS[:limit]


def fetch(name, days, interval=5, session=None, pause=0.15):
    """
    :return:
        pandas.DataFrame: time, open, high, low, close, volume, oldest first.
                          Empty when Coinbase doesn't list the pair.
    """
    session = session or requests.Session()
    step = timedelta(minutes=interval * (PAGE - 1))
    end = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    start = end - timedelta(days=days)
    rows = []
    while end > start:
        page_start = max(start, end - step)
        for attempt in range(4):
            resp = session.get(f'{API_URL}/products/{product_id(name)}/candles', timeout=15,
                               params={'granularity': interval * 60,
                                       'start': page_start.isoformat(), 'end': end.isoformat()})
            if resp.status_code != 429:
                break
            time.sleep(1 + attempt)
        if resp.status_code in (400, 404):
            break
        resp.raise_for_status()
        rows += resp.json()
        end = page_start
        time.sleep(pause)

    df = pd.DataFrame(rows, columns=['time', 'low', 'high', 'open', 'close', 'volume'])
    df['time'] = pd.to_datetime(df['time'], unit='s')
    return df[['time', 'open', 'high', 'low', 'close', 'volume']] \
        .drop_duplicates('time').sort_values('time').reset_index(drop=True)


def _file(name, path):
    return os.path.join(path, name.replace('/', '-') + '.csv')


def download(days=30, pairs=None, path=HISTORY_DIR, progress=None, session=None):
    """
    Downloads 5 minute candles for the top pairs plus BTC, replacing what was saved.

    :param:
        progress (function): called with (done, total, pair) before each pair
    :return:
        dict: pairs saved and pairs Coinbase doesn't list
    """
    pairs = pairs or top_pairs()
    if 'BTC/USD' not in pairs:
        pairs = ['BTC/USD'] + list(pairs)
    session = session or requests.Session()
    os.makedirs(path, exist_ok=True)
    saved, missing = [], []
    for i, name in enumerate(pairs):
        if progress:
            progress(i, len(pairs), name)
        df = fetch(name, days, session=session)
        if df.empty:
            missing.append(name)
            continue
        df.to_csv(_file(name, path), index=False)
        saved.append(name)
    if not saved:
        raise RuntimeError('Coinbase returned no candles for any pair')

    for old in glob.glob(os.path.join(path, '*.csv')):
        if os.path.basename(old)[:-4].replace('-', '/') not in saved:
            os.remove(old)
    info = {'updated': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'),
            'days': days, 'pairs': saved, 'missing': missing}
    with open(os.path.join(path, 'info.json'), 'w') as f:
        json.dump(info, f)
    return info


def info(path=HISTORY_DIR):
    try:
        with open(os.path.join(path, 'info.json')) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def load(path=HISTORY_DIR):
    """
    :return:
        dict: pair name to candles, empty when nothing was downloaded
    """
    candles = {}
    for file in sorted(glob.glob(os.path.join(path, '*.csv'))):
        df = pd.read_csv(file, parse_dates=['time'])
        candles[os.path.basename(file)[:-4].replace('-', '/')] = df
    return candles

# Candle history for the stock agent backtest, from Yahoo Finance. Yahoo
# keeps 5 minute candles for the last 60 days, regular hours only. Saved as
# one CSV per stock, in its own folder so it never mixes with crypto.
import glob
import json
import os
from datetime import datetime, timezone

from agent_module.stock_market import UNIVERSE, download as yahoo_download

HISTORY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'history_stocks')
MAX_DAYS = 60
BENCHMARK = 'SPY'


def top_pairs(limit=25):
    """ The stocks the scan agent picks from, benchmark first. """
    return UNIVERSE[:limit]


def _file(name, path):
    return os.path.join(path, name + '.csv')


def download(days=30, pairs=None, path=HISTORY_DIR, progress=None, fetch=yahoo_download):
    """
    Downloads 5 minute candles for the stock universe plus SPY, replacing what was saved.

    :param:
        progress (function): called with (done, total, symbol) before each stock
        fetch (function): (symbols, interval, period) to dict of candles, for tests
    :return:
        dict: stocks saved and stocks Yahoo returned nothing for
    """
    days = min(int(days), MAX_DAYS)
    pairs = list(pairs or UNIVERSE)
    if BENCHMARK not in pairs:
        pairs = [BENCHMARK] + pairs
    os.makedirs(path, exist_ok=True)
    saved, missing = [], []
    # a few at a time so the page can show progress
    chunk = 10
    for i in range(0, len(pairs), chunk):
        batch = pairs[i:i + chunk]
        if progress:
            progress(i, len(pairs), batch[0])
        data = fetch(batch, 5, f'{days}d')
        for name in batch:
            df = data.get(name)
            if df is None or df.empty:
                missing.append(name)
                continue
            df.to_csv(_file(name, path), index=False)
            saved.append(name)
    if not saved:
        raise RuntimeError('Yahoo Finance returned no candles for any stock')

    for old in glob.glob(os.path.join(path, '*.csv')):
        if os.path.basename(old)[:-4] not in saved:
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
        dict: symbol to candles, empty when nothing was downloaded
    """
    import pandas as pd
    candles = {}
    for file in sorted(glob.glob(os.path.join(path, '*.csv'))):
        candles[os.path.basename(file)[:-4]] = pd.read_csv(file, parse_dates=['time'])
    return candles

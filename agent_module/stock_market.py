# US stock market data for the stock agents, from Yahoo Finance through
# yfinance, the same source as the dividend screener. Free and keyless, a
# few minutes delayed at worst, and with no live bid and ask: quotes are
# the last trade with an assumed spread either side.
#
# Same three calls as KrakenMarket, so the agents don't know the difference.
import threading
import time

import pandas as pd

# liquid stocks and ETFs, where a volume spike can be traded at a fair price.
# SPY is the benchmark for the market filter.
UNIVERSE = ['SPY', 'QQQ', 'IWM', 'TQQQ', 'SQQQ', 'SOXL',
            'NVDA', 'TSLA', 'AAPL', 'MSFT', 'AMZN', 'META', 'GOOGL', 'AMD', 'AVGO', 'NFLX',
            'PLTR', 'MU', 'INTC', 'SMCI', 'ARM', 'ORCL', 'CRM', 'UBER', 'COIN', 'MSTR', 'HOOD',
            'SOFI', 'JPM', 'BAC', 'WFC', 'XOM', 'CVX', 'UNH', 'LLY', 'PFE', 'BA', 'DIS',
            'WMT', 'COST', 'V', 'MA', 'F', 'T', 'KO', 'NKE', 'SNOW', 'RIVN', 'MARA', 'RKLB']

YF_INTERVALS = {5: '5m', 15: '15m', 60: '60m'}
QUOTE_SPREAD = 0.0004       # large caps trade a cent or two apart; 0.04% is on the safe side
DAY_CANDLES_5M = 78         # 5 minute candles in a regular session


def _frame(raw, symbol):
    """ One symbol's candles from a yfinance download, naive UTC times, oldest first. """
    if isinstance(raw.columns, pd.MultiIndex):
        if symbol not in raw.columns.get_level_values(0):
            return pd.DataFrame(columns=['time', 'open', 'high', 'low', 'close', 'volume'])
        df = raw[symbol]
    else:
        df = raw
    df = df.rename(columns=str.lower).dropna(subset=['close'])
    index = df.index
    times = index.tz_convert('UTC').tz_localize(None) if index.tz is not None else index
    out = pd.DataFrame({'time': times, 'open': df['open'].to_numpy(float), 'high': df['high'].to_numpy(float),
                        'low': df['low'].to_numpy(float), 'close': df['close'].to_numpy(float),
                        'volume': df['volume'].to_numpy(float)})
    return out.drop_duplicates('time').sort_values('time').reset_index(drop=True)


def download(symbols, interval=5, period=None):
    """ :return: dict symbol to candles, from one batched yfinance call """
    import yfinance as yf
    # enough candles for the 24 candle volume baseline at every size
    period = period or ('5d' if interval < 60 else '1mo')
    raw = yf.download(list(symbols), period=period, interval=YF_INTERVALS.get(interval, f'{interval}m'),
                      group_by='ticker', prepost=False, progress=False, threads=True, auto_adjust=False)
    return {s: _frame(raw, s) for s in symbols}


class YahooStockMarket:
    def __init__(self, universe=None, ttl=45, fetch=download):
        self.universe = list(universe or UNIVERSE)
        self.ttl = ttl
        self.fetch = fetch
        self._cache = {}
        self._lock = threading.Lock()

    def _candles(self, interval):
        """ Every symbol's candles, fetched at most once per ttl. """
        with self._lock:
            hit = self._cache.get(interval)
            if hit and time.time() - hit[0] < self.ttl:
                return hit[1]
            data = self.fetch(self.universe, interval)
            self._cache[interval] = (time.time(), data)
            return data

    def usd_pairs(self):
        """ :return: dict symbol to display name, the same for stocks """
        return {s: s for s in self.universe}

    def tickers(self, pairs):
        """
        :return:
            dict: symbol to {'bid', 'ask', 'last', 'open', 'quote_volume'}
                  where open is today's opening price and quote_volume the
                  dollars traded over the last full session of candles
        """
        data = self._candles(5)
        half = QUOTE_SPREAD / 2
        result = {}
        for s in pairs:
            df = data.get(s)
            if df is None or df.empty:
                continue
            last = float(df['close'].iloc[-1])
            day = df['time'].dt.tz_localize('UTC').dt.tz_convert('America/New_York').dt.date
            today = df[day == day.iloc[-1]]
            tail = df.iloc[-DAY_CANDLES_5M:]
            result[s] = {'bid': last * (1 - half), 'ask': last * (1 + half), 'last': last,
                         'open': float(today['open'].iloc[0]),
                         'quote_volume': float((tail['close'] * tail['volume']).sum())}
        return result

    def candles(self, pair, interval):
        """ Closed candles only: drops the one still forming. """
        df = self._candles(interval).get(pair)
        if df is None or df.empty:
            return pd.DataFrame(columns=['time', 'open', 'high', 'low', 'close', 'volume'])
        now = pd.Timestamp.now(tz='UTC').tz_localize(None)
        return df[df['time'] + pd.Timedelta(minutes=interval) <= now].reset_index(drop=True)

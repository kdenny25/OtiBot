# Kraken public market data for the agent pipeline.
import pandas as pd
import requests

API_URL = 'https://api.kraken.com/0/public'

# fiat and stablecoins, nothing to trade against USD
SKIP_BASES = {'USD', 'EUR', 'GBP', 'CAD', 'AUD', 'CHF', 'JPY', 'USDT', 'USDC', 'DAI',
              'PYUSD', 'TUSD', 'USDG', 'RLUSD', 'EURT', 'USDS', 'FDUSD', 'USDQ', 'USDR'}


class KrakenMarket:
    """ Same three calls as the fake market in the tests. """

    def __init__(self, session=None, timeout=10):
        self.session = session or requests.Session()
        self.timeout = timeout

    def _get(self, path, params=None):
        resp = self.session.get(f'{API_URL}/{path}', params=params, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        if data.get('error'):
            raise RuntimeError(f'Kraken {path}: {data["error"]}')
        return data['result']

    def usd_pairs(self):
        """
        :return:
            dict: Kraken pair key to display name, e.g. {'XETHZUSD': 'ETH/USD'}
        """
        pairs = {}
        for key, info in self._get('AssetPairs').items():
            wsname = info.get('wsname', '')
            if '/' not in wsname or info.get('status', 'online') != 'online':
                continue
            base, quote = wsname.split('/')
            if quote == 'USD' and base not in SKIP_BASES and not key.endswith('.d'):
                pairs[key] = wsname
        return pairs

    def tickers(self, pairs):
        """
        :param:
            pairs (list): Kraken pair keys
        :return:
            dict: pair key to {'bid', 'ask', 'last', 'quote_volume'}
        """
        result = {}
        pairs = list(pairs)
        for i in range(0, len(pairs), 50):
            chunk = self._get('Ticker', {'pair': ','.join(pairs[i:i + 50])})
            for key, t in chunk.items():
                last = float(t['c'][0])
                vwap = float(t['p'][1]) or last
                result[key] = {'bid': float(t['b'][0]),
                               'ask': float(t['a'][0]),
                               'last': last,
                               'quote_volume': float(t['v'][1]) * vwap}
        return result

    def candles(self, pair, interval):
        """
        Closed candles only. Kraken's last row is the candle still forming.

        :return:
            pandas.DataFrame: time, open, high, low, close, volume
        """
        result = self._get('OHLC', {'pair': pair, 'interval': interval})
        rows = next(v for k, v in result.items() if k != 'last')
        df = pd.DataFrame(rows, columns=['time', 'open', 'high', 'low', 'close',
                                         'vwap', 'volume', 'trades'])
        df = df.iloc[:-1]
        df[['open', 'high', 'low', 'close', 'volume']] = \
            df[['open', 'high', 'low', 'close', 'volume']].astype(float)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        return df[['time', 'open', 'high', 'low', 'close', 'volume']].reset_index(drop=True)

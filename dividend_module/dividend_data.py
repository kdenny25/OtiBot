# Collects dividend stock and ETF data from Yahoo Finance (yfinance) and
# saves it to a JSON cache that the screener page reads.
#
# Refresh the cache from the project root with:
#     python -m dividend_module.dividend_data
import json
import math
import os
import warnings
from datetime import datetime, timezone

import pandas as pd

from dividend_module import metrics
from dividend_module.universe import DEFAULT_UNIVERSE

# yfinance still calls pandas with inplace=True, which pandas 3.1 deprecates.
# It's inside yfinance and harmless, so keep it out of the log.
warnings.filterwarnings('ignore', message='The inplace keyword', module='yfinance')

CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'dividend_data.json')


def _clean(value):
    """ Converts NaN/inf and numpy types to JSON friendly values. """
    if value is None:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return value
    return None if math.isnan(value) or math.isinf(value) else value


def _naive(series):
    """ Drops the timezone so dates compare cleanly. """
    if series is not None and not series.empty and series.index.tz is not None:
        series = series.copy()
        series.index = series.index.tz_localize(None)
    return series


def _expense_ratio(info):
    # newer yfinance reports netExpenseRatio as a percent (0.06 = 0.06%),
    # older versions report annualReportExpenseRatio as a fraction
    if info.get('netExpenseRatio') is not None:
        return info['netExpenseRatio'] / 100
    return info.get('annualReportExpenseRatio')


def build_record(symbol, info, dividends, close, adj_close, as_of=None):
    """
    Builds one screener row from provider data.

    :param:
        symbol (str): ticker

        info (dict): yfinance Ticker.info

        dividends (pandas.Series): dividend per share by date

        close (pandas.Series): daily close prices (price only)

        adj_close (pandas.Series): daily adjusted close (includes dividends)

        as_of (datetime): Default today
    :return:
        dict: screener row, fractions for all percentages
    """
    as_of = pd.Timestamp.now() if as_of is None else pd.Timestamp(as_of)
    if dividends is None or dividends.empty:
        dividends = pd.Series(dtype=float, index=pd.DatetimeIndex([]))
    dividends = _naive(dividends)
    close, adj_close = _naive(close), _naive(adj_close)

    is_etf = info.get('quoteType') == 'ETF'
    price = info.get('regularMarketPrice') or info.get('currentPrice') or info.get('navPrice')
    if price is None and close is not None and not close.empty:
        price = close.iloc[-1]

    # trailing twelve month dividends, calculated so stocks and ETFs match
    ttm = dividends[dividends.index > as_of - pd.DateOffset(years=1)].sum()
    dividend_yield = ttm / price if price else None

    ex_div = info.get('exDividendDate')
    if isinstance(ex_div, (int, float)):
        ex_div = datetime.fromtimestamp(ex_div, tz=timezone.utc).strftime('%Y-%m-%d')

    record = {
        'symbol': symbol,
        'name': info.get('longName') or info.get('shortName') or symbol,
        'type': 'ETF' if is_etf else 'Stock',
        'sector': info.get('category') if is_etf else info.get('sector'),
        'price': price,
        'dividend_yield': dividend_yield,
        'annual_dividend': ttm,
        'dividend_growth_5y': metrics.dividend_cagr(dividends, 5, as_of),
        'dividend_growth_10y': metrics.dividend_cagr(dividends, 10, as_of),
        'years_of_increases': metrics.consecutive_increase_years(dividends, as_of),
        'payout_frequency': metrics.payout_frequency(dividends, as_of),
        'payout_ratio': None if is_etf else info.get('payoutRatio'),
        'expense_ratio': _expense_ratio(info) if is_etf else None,
        'price_growth_1y': metrics.annualized_return(close, 1),
        'price_growth_5y': metrics.annualized_return(close, 5),
        'total_return_5y': metrics.annualized_return(adj_close, 5),
        'total_return_10y': metrics.annualized_return(adj_close, 10),
        'volatility': metrics.annualized_volatility(close.iloc[-252 * 3:]),
        'max_drawdown_5y': metrics.max_drawdown(
            adj_close[adj_close.index > as_of - pd.DateOffset(years=5)]),
        'beta': info.get('beta') if not is_etf else info.get('beta3Year', info.get('beta')),
        'pe_ratio': None if is_etf else info.get('trailingPE'),
        'size': info.get('totalAssets') if is_etf else info.get('marketCap'),
        'ex_dividend_date': ex_div,
    }
    return {k: _clean(v) if k not in ('symbol', 'name', 'type', 'sector',
                                      'payout_frequency', 'ex_dividend_date') else v
            for k, v in record.items()}


def fetch_record(symbol):
    """ Downloads one ticker from Yahoo Finance and builds its row. """
    import yfinance as yf

    ticker = yf.Ticker(symbol)
    info = ticker.info or {}
    history = ticker.history(period='max', auto_adjust=False)
    return build_record(symbol, info, ticker.dividends,
                        history['Close'], history['Adj Close'])


def refresh(symbols=None, path=CACHE_PATH, progress=None):
    """
    Downloads every symbol and writes the cache. Symbols that fail are
    skipped and listed in the cache under 'errors'.

    :param:
        progress (function): optional, called with (done, total, symbol)
                             before each download

    :return:
        dict: the cache contents
    """
    symbols = symbols or DEFAULT_UNIVERSE
    records, errors = [], {}
    for i, symbol in enumerate(symbols, 1):
        print(f'{i}/{len(symbols)} {symbol}')
        if progress:
            progress(i - 1, len(symbols), symbol)
        try:
            records.append(fetch_record(symbol))
        except Exception as e:
            errors[symbol] = str(e)

    if not records:
        # e.g. Yahoo is down or blocked, so keep the data we already have
        first = next(iter(errors.items()), ('', 'no symbols'))
        raise RuntimeError(f'Every download failed, kept the existing data. {first[0]}: {first[1]}')

    cache = {'updated': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'),
             'records': records,
             'errors': errors}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        json.dump(cache, f, indent=1)
    return cache


def load(path=CACHE_PATH):
    """ Reads the cache, or an empty cache if it hasn't been built yet. """
    if not os.path.exists(path):
        return {'updated': None, 'records': [], 'errors': {}}
    with open(path) as f:
        return json.load(f)


if __name__ == '__main__':
    cache = refresh()
    print(f"saved {len(cache['records'])} records to {CACHE_PATH}")
    if cache['errors']:
        print('failed:', ', '.join(cache['errors']))

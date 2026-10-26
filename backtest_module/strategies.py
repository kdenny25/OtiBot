# Built in strategies for the backtest page. Each one takes the candle
# dataframe plus its parameters and returns (buy, sell) boolean series.
import pandas as pd

from indicators import SMA, EMA, RSI, MACD, BBANDS


def sma_rsi(df, sma_window=20, rsi_window=14, oversold=30, overbought=70):
    sma = SMA(df['close'], sma_window)
    rsi = RSI(df['close'], rsi_window)
    buy = (sma > sma.shift(1)) & (rsi < oversold)
    sell = (sma < sma.shift(1)) | (rsi > overbought)
    return buy, sell


def sma_cross(df, fast=10, slow=30):
    fast_sma = SMA(df['close'], fast)
    slow_sma = SMA(df['close'], slow)
    above = fast_sma > slow_sma
    buy = above & ~above.shift(1, fill_value=False)
    sell = ~above & above.shift(1, fill_value=False) & slow_sma.notna()
    return buy, sell


def ema_trend(df, span=50):
    ema = EMA(df['close'], span=span)
    ema.iloc[:span] = float('nan')
    buy = (df['close'] > ema) & (ema > ema.shift(1))
    sell = df['close'] < ema
    return buy, sell


def macd_cross(df, fast=12, slow=26, signal=9):
    macd = MACD(df['close'], slow, fast, signal)
    above = macd['macd'] > macd['macd_signal']
    buy = above & ~above.shift(1, fill_value=False)
    sell = ~above & above.shift(1, fill_value=False) & macd['macd_signal'].notna()
    return buy, sell


def bollinger_reversion(df, window=20, n_std=2):
    candles = df.rename(columns={'high': 'High', 'low': 'Low', 'close': 'Close'})
    upper, lower = BBANDS(candles, window, n_std)
    middle = (upper + lower) / 2
    buy = df['close'] < lower
    sell = df['close'] > middle
    return buy, sell


def _param(name, label, default, minimum, maximum, step=1):
    return {'name': name, 'label': label, 'default': default,
            'min': minimum, 'max': maximum, 'step': step}


STRATEGIES = {
    'ema_trend': {
        'name': 'Trend following (EMA)',
        'description': 'Buys when price is above a rising EMA and exits when it closes below it.',
        'fn': ema_trend,
        'params': [_param('span', 'EMA length', 50, 5, 400)]},
    'sma_cross': {
        'name': 'Moving average crossover',
        'description': 'Buys when the fast SMA crosses above the slow SMA and sells on the cross back.',
        'fn': sma_cross,
        'params': [_param('fast', 'Fast SMA', 10, 2, 200), _param('slow', 'Slow SMA', 30, 5, 400)]},
    'macd_cross': {
        'name': 'MACD crossover',
        'description': 'Buys when MACD crosses above its signal line and sells when it crosses below.',
        'fn': macd_cross,
        'params': [_param('fast', 'Fast EMA', 12, 2, 100), _param('slow', 'Slow EMA', 26, 5, 200),
                   _param('signal', 'Signal', 9, 2, 50)]},
    'sma_rsi': {
        'name': 'SMA trend + RSI dip',
        'description': 'Buys oversold RSI while the SMA is rising, sells on overbought RSI or a falling SMA.',
        'fn': sma_rsi,
        'params': [_param('sma_window', 'SMA length', 20, 2, 200), _param('rsi_window', 'RSI length', 14, 2, 50),
                   _param('oversold', 'Oversold', 30, 5, 50), _param('overbought', 'Overbought', 70, 50, 95)]},
    'bollinger_reversion': {
        'name': 'Bollinger mean reversion',
        'description': 'Buys a close below the lower band and sells once price gets back to the middle.',
        'fn': bollinger_reversion,
        'params': [_param('window', 'Lookback', 20, 5, 200), _param('n_std', 'Std devs', 2, 1, 4, 0.5)]},
}


def build(key, params=None):
    """
    :return:
        function: strategy with its parameters filled in, clamped to their limits
    """
    spec = STRATEGIES[key]
    params = params or {}
    values = {}
    for p in spec['params']:
        value = float(params.get(p['name'], p['default']))
        value = min(max(value, p['min']), p['max'])
        values[p['name']] = int(value) if float(p['step']).is_integer() else value
    return lambda df: spec['fn'](df, **values)


def catalog():
    """ Strategies without their functions, for the page. """
    return [{'key': k, 'name': s['name'], 'description': s['description'], 'params': s['params']}
            for k, s in STRATEGIES.items()]

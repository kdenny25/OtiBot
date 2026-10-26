# Flask page and API for running backtests from the browser.
import math
import os

import pandas as pd
from flask import Blueprint, jsonify, render_template, request

from backtest_module.backtest import backtest
from backtest_module.strategies import STRATEGIES, build, catalog

backtest_bp = Blueprint('backtest', __name__)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE_PATH = os.path.join(ROOT, 'test_data', 'test_ohlc.csv')
SOURCES = {'database': 'Candle database', 'kraken': 'Kraken (last 720 candles)', 'sample': 'Sample data (offline)'}
PAIRS = ['ETHUSD', 'BTCUSD', 'SOLUSD', 'XRPUSD', 'DOGEUSD']
INTERVALS = [1, 5, 15, 60, 240, 1440]
MAX_POINTS = 600

# last run summary for the home page
last_run = {}


def load_candles(source, pair, interval, start=None, end=None):
    """
    :return:
        pandas.DataFrame: time, open, high, low, close, volume in time order
    """
    if source == 'sample':
        df = pd.read_csv(SAMPLE_PATH)
        df['time'] = pd.to_datetime(df['opentime'], unit='ms')
        # the file starts with flat placeholder candles before real trading
        df = df.iloc[(df['close'] != df['close'].iloc[0]).to_numpy().argmax():]
    elif source == 'database':
        if not start or not end:
            raise ValueError('Pick a start and end date')
        bt = backtest()
        bt.set_tradable_pair(pair)
        df = bt.get_historical_data(interval, start, end)
        if df.empty:
            raise ValueError(f'No {interval} minute {pair} candles in the database for those dates')
        df['time'] = pd.to_datetime(df['opentime'].astype('int64'), unit='ms')
    elif source == 'kraken':
        from agent_module.market import KrakenMarket
        df = KrakenMarket().candles(pair, interval)
    else:
        raise ValueError(f'Unknown data source {source}')

    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = df[col].astype(float)
    return df.sort_values('time').reset_index(drop=True)


def _clean(value):
    if value is None:
        return None
    value = float(value)
    return None if math.isnan(value) or math.isinf(value) else value


def _downsample(times, values):
    step = max(1, math.ceil(len(values) / MAX_POINTS))
    idx = list(range(0, len(values), step))
    if idx[-1] != len(values) - 1:
        idx.append(len(values) - 1)
    return [{'t': times[i].isoformat(), 'v': float(values[i])} for i in idx]


def run_backtest(options, candles=None):
    key = options.get('strategy', 'ema_trend')
    if key not in STRATEGIES:
        raise ValueError(f'Unknown strategy {key}')
    interval = int(options.get('interval', 15))
    if candles is None:
        candles = load_candles(options.get('source', 'sample'), options.get('pair', 'ETHUSD'),
                               interval, options.get('start'), options.get('end'))
    if len(candles) < 50:
        raise ValueError('Need at least 50 candles to backtest')

    capital = float(options.get('capital', 10000))
    bt = backtest(capital=capital, allow_short=bool(options.get('allow_short')),
                  slippage=float(options.get('slippage', 0.0005)))
    bt.set_fees(float(options.get('fee', 0.0026)))
    bt.periods_per_year = int(365 * 24 * 60 / interval)
    bt.set_data(candles)
    bt.set_strategy(build(key, options.get('params')))
    result = bt.run()

    times = candles['time'].tolist()
    closes = candles['close'].to_numpy()
    buy_hold = capital * closes / closes[0]
    trades = result['trades']
    stats = {k: _clean(v) for k, v in result['stats'].items()}
    stats['buy_hold_return'] = _clean(buy_hold[-1] / capital - 1)

    windows = []
    n_windows = int(options.get('windows', 0) or 0)
    if n_windows > 1:
        for _, row in bt.run_split_window(n_windows).iterrows():
            windows.append({'window': int(row['window']) + 1,
                            'start': times[int(row['start_index'])].isoformat(),
                            'end': times[int(row['end_index'])].isoformat(),
                            **{k: _clean(row[k]) for k in ['total_return', 'max_drawdown', 'sharpe',
                                                            'num_trades', 'win_rate']}})

    response = {
        'strategy': STRATEGIES[key]['name'],
        'candles': len(candles),
        'start': times[0].isoformat(),
        'end': times[-1].isoformat(),
        'stats': stats,
        'equity': _downsample(times, result['equity'].to_numpy()),
        'buy_hold': _downsample(times, buy_hold),
        'trades': [{'side': t['side'],
                    'entry_time': times[int(t['entry_index'])].isoformat(),
                    'exit_time': times[int(t['exit_index'])].isoformat(),
                    'entry_price': float(t['entry_price']),
                    'exit_price': float(t['exit_price']),
                    'pnl': float(t['pnl']),
                    'return': float(t['return'])} for _, t in trades.iloc[::-1].head(200).iterrows()],
        'windows': windows,
    }
    last_run.clear()
    last_run.update({'strategy': response['strategy'], 'pair': options.get('pair', 'ETHUSD'),
                     'source': options.get('source', 'sample'), 'start': response['start'],
                     'end': response['end'], 'stats': stats})
    return response


@backtest_bp.route('/backtest')
def backtest_page():
    return render_template('backtest.html', sources=SOURCES, pairs=PAIRS, intervals=INTERVALS)


@backtest_bp.route('/api/backtest/strategies')
def backtest_strategies():
    return jsonify(catalog())


@backtest_bp.route('/api/backtest/run', methods=['POST'])
def backtest_run():
    try:
        return jsonify(run_backtest(request.get_json(force=True) or {}))
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@backtest_bp.route('/api/backtest/last')
def backtest_last():
    return jsonify(last_run or None)

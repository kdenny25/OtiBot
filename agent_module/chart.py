# Price chart data for one pair in an agent backtest: candles, the volume
# spike threshold the entry rule uses, every spike it scored and each trade
# with the levels its exit rules watched (stop, target, trailing stop).
import pandas as pd

from agent_module.rules import PASS, SHORT, describe, spike_signals, trail_level
from agent_module.simulate import resample

def _num(x):
    """ Rounded to 6 significant digits, so tiny coin prices keep their detail. """
    return None if x is None or pd.isna(x) else float(f'{x:.6g}')


def pair_chart(candles, trades, config):
    """
    :param:
        candles (pandas.DataFrame): the pair's candles, any size up to config.candle_interval
        trades (list): the pair's trades from simulate()
    :return:
        dict: columns t (ISO time, like trade times), o, h, l, c, v and threshold (volume a
              candle needs to count as a spike), signals (every scored spike)
              and trades with their entry/exit candle and exit levels
    """
    df = resample(candles, config.candle_interval, config.market == 'stocks').drop_duplicates('time') \
        .sort_values('time').reset_index(drop=True)
    times = pd.DatetimeIndex(df['time'])
    volume = df['volume'].astype(float)
    threshold = volume.shift(1).rolling(config.spike_lookback).median() * config.min_spike
    scored = spike_signals(df, config)

    def index(t):
        return int(min(times.searchsorted(pd.Timestamp(t)), len(times) - 1))

    # a signal fills on a later candle: the next one at market, or within the limit wait
    lag = 1 if config.confirm_spike else 0
    wait = max(1, round(config.limit_wait_minutes / config.candle_interval)) if config.limit_orders else 1
    entries = {index(t['entry_time']) for t in trades}
    signals = []
    for i, row in scored[scored['signal'].notna()].iterrows():
        traded = any(i < e <= i + wait for e in entries)
        text = describe(row, config)
        if row['signal'] in (PASS, SHORT) and not traded:
            text += ', not taken (market filter, open positions, 24h volume or unfilled limit)'
        signals.append({'i': int(i), 'spike_i': int(i) - lag, 'kind': row['signal'], 'traded': traded, 'text': text})

    fee_rate = config.maker_fee if config.limit_orders else config.taker_fee
    out = []
    for t in sorted(trades, key=lambda t: t['entry_time']):
        side = 1 if t['side'] == 'long' else -1
        entry, ei, xi = t['entry_price'], index(t['entry_time']), index(t['exit_time'])
        # a limit fill can't exit on its own candle, like simulate()
        first = ei + 1 if config.limit_orders else ei
        pos = {'side': side, 'entry_price': entry, 'peak': entry, 'fee_rate': fee_rate}
        trail = []
        for k in range(first, xi + 1):
            trail.append(_num(trail_level(pos, config)))
            pos['peak'] = max(pos['peak'], df['high'][k]) if side == 1 else min(pos['peak'], df['low'][k])
        out.append({'side': t['side'], 'reason': t['reason'], 'pnl': float(t['pnl']),
                    'entry_i': ei, 'exit_i': xi, 'entry_price': _num(entry), 'exit_price': _num(t['exit_price']),
                    'stop': _num(entry * (1 - side * config.stop_loss)),
                    'target': _num(entry * (1 + side * config.take_profit)),
                    'trail_on': _num(entry * (1 + side * config.trail_trigger)),
                    'trail_start': first, 'trail': trail})

    return {'interval': config.candle_interval, 'min_spike': config.min_spike,
            't': [x.isoformat() for x in times],
            'o': [_num(x) for x in df['open']], 'h': [_num(x) for x in df['high']],
            'l': [_num(x) for x in df['low']], 'c': [_num(x) for x in df['close']],
            'v': [_num(x) for x in volume], 'threshold': [_num(x) for x in threshold],
            'signals': signals, 'trades': out,
            'settings': {'take_profit': config.take_profit, 'stop_loss': config.stop_loss,
                         'trail_trigger': config.trail_trigger, 'trail_pct': config.trail_pct}}


def traded_pairs(trades):
    """ :return: list of (pair, trade count), most traded first """
    counts = pd.Series([t['symbol'] for t in trades], dtype=object).value_counts()
    return [(str(p), int(n)) for p, n in counts.items()]

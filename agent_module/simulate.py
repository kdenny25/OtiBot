# Agent backtest: replays the agent rules over historical candles for many
# pairs at once, with the same sizing, position limit, fees and exits.
#
# Each candle stands in for a cycle. Signals use closed candles only and
# fill on the next one: a market order at its open, a limit order at the
# signal candle's close on our side of the spread, filled only if a later
# candle trades through it. Stops are checked before targets inside a
# candle, so a candle that touches both counts as a loss.
import numpy as np
import pandas as pd

from agent_module.config import AgentConfig
from agent_module.rules import SIDES, margin_cost, round_trip_cost, spike_signals
from backtest_module.evaluations import max_drawdown, trade_stats

DAY_CANDLES = 24 * 60


def resample(df, minutes):
    """ Joins candles into bigger ones, e.g. 5 minute candles into 15 minute ones. """
    df = df.drop_duplicates('time').set_index('time').sort_index()
    if len(df) < 2 or (df.index[1] - df.index[0]) >= pd.Timedelta(minutes=minutes):
        return df.reset_index()
    out = df.resample(f'{minutes}min').agg({'open': 'first', 'high': 'max', 'low': 'min',
                                            'close': 'last', 'volume': 'sum'})
    return out.dropna(subset=['close']).reset_index()


def _arrays(df, times, config):
    df = df.drop_duplicates('time').set_index('time').reindex(times)
    # a gap is a candle with no trades: zero volume at the last price
    filled = df.reset_index()
    filled['volume'] = filled['volume'].fillna(0)
    filled = filled.ffill()
    signals = spike_signals(filled, config)
    signals.index = times
    traded = df['close'].notna().to_numpy()
    side = np.array([SIDES.get(s, 0) for s in signals['signal']]) * traded
    volume_usd = (df['volume'] * df['close']).fillna(0)
    window = max(1, DAY_CANDLES // config.candle_interval)
    return {'open': df['open'].to_numpy(), 'high': df['high'].to_numpy(),
            'low': df['low'].to_numpy(), 'close': df['close'].to_numpy(),
            'traded': traded, 'side': side,
            'spike': signals['spike'].to_numpy(),
            'volume_24h': volume_usd.rolling(window, min_periods=1).sum().to_numpy()}


def _btc_up(btc, times):
    """ True where BTC closed at or above that UTC day's open. """
    df = btc.drop_duplicates('time').set_index('time').reindex(times).ffill()
    day_open = df.groupby(df.index.normalize())['open'].transform('first')
    return (df['close'] >= day_open).fillna(True).to_numpy()


def simulate(candles, config=None, btc=None, spread=0.001):
    """
    :param:
        candles (dict): pair name to a DataFrame of time, open, high, low,
                        close, volume, joined into config.candle_interval
                        minute candles when smaller
        btc (pandas.DataFrame): BTC/USD candles for the market filter,
                                defaults to candles['BTC/USD'] when present
        spread (float): assumed bid/ask spread, history has no quotes
    :return:
        dict: stats, equity (time, value), trades and exits (count and pnl by reason)
    """
    c = config or AgentConfig()
    if not candles:
        raise ValueError('No candle history to test on')
    candles = {name: resample(df, c.candle_interval) for name, df in candles.items()}
    times = pd.DatetimeIndex(sorted(set().union(*(df['time'] for df in candles.values()))))
    data = {name: _arrays(df, times, c) for name, df in candles.items()}
    if btc is None:
        btc = candles.get('BTC/USD')
    else:
        btc = resample(btc, c.candle_interval)
    if c.market_filter and btc is not None:
        btc_up = _btc_up(btc, times)
        allowed = {1: btc_up, -1: ~btc_up}
    else:
        allowed = {1: np.ones(len(times), bool), -1: np.ones(len(times), bool)}

    half = spread / 2
    step = c.candle_interval * 60
    wait = max(1, round(c.limit_wait_minutes / c.candle_interval))
    cash = c.start_balance
    positions, orders, trades, equity = {}, {}, [], []

    def value_of(pos, price):
        if pos['side'] == 1:
            return pos['units'] * price
        return pos['cost'] + pos['units'] * (pos['entry_price'] - price)

    def close(name, i, price, reason, maker=False):
        nonlocal cash
        pos = positions.pop(name)
        side = pos['side']
        fill = price if maker else price * (1 - side * (half + c.slippage))
        proceeds = value_of(pos, fill)
        fee = pos['units'] * fill * (c.maker_fee if maker else c.taker_fee)
        if side == -1:
            fee += margin_cost(c, pos['cost'], (i - pos['entry_i'] + 1) * step)
        cash += proceeds - fee
        trades.append({'symbol': name, 'side': 'long' if side == 1 else 'short',
                       'entry_time': times[pos['entry_i']].isoformat(),
                       'exit_time': times[i].isoformat(), 'entry_price': pos['entry_price'],
                       'exit_price': fill, 'fees': pos['fees'] + fee,
                       'pnl': proceeds - fee - pos['cost'] - pos['fees'], 'reason': reason})

    def open_position(name, i, side, fill, value, maker, first_i):
        nonlocal cash
        fee_rate = c.maker_fee if maker else c.taker_fee
        cash -= value * (1 + fee_rate)
        positions[name] = {'side': side, 'entry_i': i, 'first_i': first_i, 'entry_price': fill,
                           'units': value / fill, 'cost': value, 'fees': value * fee_rate,
                           'fee_rate': fee_rate, 'peak': fill}

    for i in range(len(times)):
        # 1. orders from the last candle's signals
        if i > 0:
            value_now = cash + sum(value_of(p, data[n]['close'][i - 1]) for n, p in positions.items()
                                   if not np.isnan(data[n]['close'][i - 1]))
            ranked = sorted((n for n in data if data[n]['side'][i - 1]),
                            key=lambda n: -data[n]['spike'][i - 1])
            for name in ranked:
                d = data[name]
                side = int(d['side'][i - 1])
                if (name in positions or name in orders or not allowed[side][i - 1] or not d['traded'][i]
                        or d['volume_24h'][i - 1] < c.min_quote_volume
                        or len(positions) + len(orders) >= c.max_open_positions):
                    continue
                reserved = sum(o['value'] * (1 + c.maker_fee) for o in orders.values())
                value = min(value_now * c.risk_per_trade / c.stop_loss, value_now * c.max_position_pct,
                            (cash - reserved) / (1 + c.taker_fee))
                if value < 10:
                    continue
                if c.limit_orders:
                    # a buy waits at the bid, a short at the ask
                    orders[name] = {'side': side, 'price': d['close'][i - 1] * (1 - side * half),
                                    'value': value, 'placed': i}
                else:
                    fill = d['open'][i] * (1 + side * (half + c.slippage))
                    open_position(name, i, side, fill, value, False, i)

        # 2. limit orders the market traded through
        for name, order in list(orders.items()):
            d = data[name]
            hit = d['low'][i] < order['price'] if order['side'] == 1 else d['high'][i] > order['price']
            if d['traded'][i] and hit:
                del orders[name]
                open_position(name, i, order['side'], order['price'], order['value'], True, i + 1)
            elif i - order['placed'] + 1 >= wait:
                del orders[name]

        # 3. exits, using the candle's range in the order prices most likely moved
        for name, pos in list(positions.items()):
            d = data[name]
            if i < pos['first_i'] or not d['traded'][i]:
                continue
            side, entry = pos['side'], pos['entry_price']
            o, h, l, cl = d['open'][i], d['high'][i], d['low'][i], d['close'][i]
            # against is the price that hurts this side most inside the candle, best the one that helps
            against, best = (l, h) if side == 1 else (h, l)
            stop = entry * (1 - side * c.stop_loss)
            target = entry * (1 + side * c.take_profit)
            trail = None
            if side * (pos['peak'] / entry - 1) >= c.trail_trigger:
                trail = pos['peak'] * (1 - side * c.trail_pct)
                if c.trail_covers_costs and side * (trail / entry - 1) < round_trip_cost(c, pos['fee_rate'], side):
                    trail = None
            # the exit closest to the price: the higher of the two for a long, the lower for a short
            floor = stop if trail is None else (max(stop, trail) if side == 1 else min(stop, trail))
            if side * (against - floor) <= 0:
                worse = min(o, floor) if side == 1 else max(o, floor)
                close(name, i, worse, 'stop loss' if floor == stop else 'trailing stop')
                continue
            if side * (best - target) >= 0:
                if c.limit_orders:
                    close(name, i, target, 'take profit', maker=True)
                else:
                    close(name, i, max(o, target) if side == 1 else min(o, target), 'take profit')
                continue
            pos['peak'] = max(pos['peak'], h) if side == 1 else min(pos['peak'], l)
            held = (i - pos['entry_i'] + 1) * step
            change = side * (cl / entry - 1)
            if c.stale_minutes and held >= c.stale_minutes * 60 and change < c.stale_move:
                close(name, i, cl, 'went nowhere')
            elif held >= c.max_hold_minutes * 60:
                close(name, i, cl, 'time limit')

        marked = cash
        for name, pos in positions.items():
            price = data[name]['close'][i]
            marked += value_of(pos, pos['entry_price'] if np.isnan(price) else price)
        equity.append(marked)

    for name in list(positions):
        last = data[name]['close'][~np.isnan(data[name]['close'])][-1]
        close(name, len(times) - 1, last, 'end of test')
    equity[-1] = cash

    return _summary(c, times, equity, trades)


def _summary(c, times, equity, trades):
    df = pd.DataFrame(trades, columns=['symbol', 'side', 'entry_time', 'exit_time', 'entry_price',
                                       'exit_price', 'fees', 'pnl', 'reason'])
    stats = trade_stats(df)
    wins, losses = df.loc[df['pnl'] > 0, 'pnl'], df.loc[df['pnl'] < 0, 'pnl']
    curve = pd.Series(equity)

    def clean(x):
        return None if x is None or pd.isna(x) or np.isinf(x) else float(x)

    exits = df.groupby('reason')['pnl'].agg(['count', 'sum']).reset_index() if len(df) else pd.DataFrame()
    sides = df.groupby('side')['pnl'].agg(['count', 'sum']) if len(df) else pd.DataFrame()
    return {'stats': {'final_equity': float(curve.iloc[-1]),
                      'total_return': float(curve.iloc[-1] / c.start_balance - 1),
                      'max_drawdown': clean(max_drawdown(curve)),
                      'trades': int(stats['num_trades']),
                      'win_rate': clean(stats['win_rate']),
                      'profit_factor': clean(stats['profit_factor']),
                      'avg_win': clean(wins.mean()) if len(wins) else None,
                      'avg_loss': clean(losses.mean()) if len(losses) else None,
                      'fees': float(df['fees'].sum()),
                      'pnl_before_fees': float((df['pnl'] + df['fees']).sum()),
                      'sides': {s: {'trades': int(r['count']), 'pnl': float(r['sum'])}
                                for s, r in sides.iterrows()}},
            'equity': [{'t': t.isoformat(), 'v': float(v)} for t, v in zip(times, equity)],
            'trades': df.iloc[::-1].to_dict('records'),
            'exits': [{'reason': r['reason'], 'count': int(r['count']), 'pnl': float(r['sum'])}
                      for _, r in exits.iterrows()]}

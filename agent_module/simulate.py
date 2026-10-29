# Agent backtest: replays the agent rules over historical candles for many
# pairs at once, with the same sizing, position limit, fees and exits.
#
# Each candle stands in for a cycle. Signals use closed candles only and
# fill on the next one: a market buy at its open, a limit buy at the
# signal candle's close less half the spread, filled only if a later
# candle trades below it. Stops are checked before targets inside a candle,
# so a candle that touches both counts as a loss.
import numpy as np
import pandas as pd

from agent_module.config import AgentConfig
from agent_module.rules import PASS, round_trip_cost, spike_signals
from backtest_module.evaluations import max_drawdown, trade_stats

DAY_CANDLES = 24 * 60


def _arrays(df, times, config):
    df = df.drop_duplicates('time').set_index('time').reindex(times)
    # a gap is a candle with no trades: zero volume at the last price
    filled = df.reset_index()
    filled['volume'] = filled['volume'].fillna(0)
    filled = filled.ffill()
    signals = spike_signals(filled, config)
    signals.index = times
    volume_usd = (df['volume'] * df['close']).fillna(0)
    window = max(1, DAY_CANDLES // config.candle_interval)
    return {'open': df['open'].to_numpy(), 'high': df['high'].to_numpy(),
            'low': df['low'].to_numpy(), 'close': df['close'].to_numpy(),
            'traded': df['close'].notna().to_numpy(),
            'signal': np.where(df['close'].notna().to_numpy(), signals['signal'].to_numpy(), None),
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
                        close, volume at config.candle_interval minutes
        btc (pandas.DataFrame): BTC/USD candles for the market filter,
                                defaults to candles['BTC/USD'] when present
        spread (float): assumed bid/ask spread, history has no quotes
    :return:
        dict: stats, equity (time, value), trades and exits (count and pnl by reason)
    """
    c = config or AgentConfig()
    if not candles:
        raise ValueError('No candle history to test on')
    times = pd.DatetimeIndex(sorted(set().union(*(df['time'] for df in candles.values()))))
    data = {name: _arrays(df, times, c) for name, df in candles.items()}
    if btc is None:
        btc = candles.get('BTC/USD')
    btc_up = _btc_up(btc, times) if c.market_filter and btc is not None else np.ones(len(times), bool)

    half = spread / 2
    step = c.candle_interval * 60
    wait = max(1, round(c.limit_wait_minutes / c.candle_interval))
    cash = c.start_balance
    positions, orders, trades, equity = {}, {}, [], []

    def close(name, i, price, reason, maker=False):
        nonlocal cash
        pos = positions.pop(name)
        fill = price if maker else price * (1 - half - c.slippage)
        proceeds = pos['units'] * fill
        fee = proceeds * (c.maker_fee if maker else c.taker_fee)
        cash += proceeds - fee
        trades.append({'symbol': name, 'entry_time': times[pos['entry_i']].isoformat(),
                       'exit_time': times[i].isoformat(), 'entry_price': pos['entry_price'],
                       'exit_price': fill, 'fees': pos['fees'] + fee,
                       'pnl': proceeds - fee - pos['cost'] - pos['fees'], 'reason': reason})

    def open_position(name, i, fill, value, maker, first_i):
        nonlocal cash
        fee_rate = c.maker_fee if maker else c.taker_fee
        cash -= value * (1 + fee_rate)
        positions[name] = {'entry_i': i, 'first_i': first_i, 'entry_price': fill, 'units': value / fill,
                           'cost': value, 'fees': value * fee_rate, 'fee_rate': fee_rate, 'peak': fill}

    for i in range(len(times)):
        # 1. orders from the last candle's signals
        if i > 0:
            value_now = cash + sum(p['units'] * data[n]['close'][i - 1] for n, p in positions.items()
                                   if not np.isnan(data[n]['close'][i - 1]))
            ranked = sorted((n for n in data if data[n]['signal'][i - 1] == PASS),
                            key=lambda n: -data[n]['spike'][i - 1])
            for name in ranked:
                d = data[name]
                if (name in positions or name in orders or not btc_up[i - 1] or not d['traded'][i]
                        or d['volume_24h'][i - 1] < c.min_quote_volume
                        or len(positions) + len(orders) >= c.max_open_positions):
                    continue
                reserved = sum(o['value'] * (1 + c.maker_fee) for o in orders.values())
                value = min(value_now * c.risk_per_trade / c.stop_loss, value_now * c.max_position_pct,
                            (cash - reserved) / (1 + c.taker_fee))
                if value < 10:
                    continue
                if c.limit_orders:
                    orders[name] = {'price': d['close'][i - 1] * (1 - half), 'value': value, 'placed': i}
                else:
                    open_position(name, i, d['open'][i] * (1 + half + c.slippage), value, False, i)

        # 2. limit buys the market traded down to
        for name, order in list(orders.items()):
            d = data[name]
            if d['traded'][i] and d['low'][i] < order['price']:
                del orders[name]
                open_position(name, i, order['price'], order['value'], True, i + 1)
            elif i - order['placed'] + 1 >= wait:
                del orders[name]

        # 3. exits, using the candle's range in the order prices most likely moved
        for name, pos in list(positions.items()):
            d = data[name]
            if i < pos['first_i'] or not d['traded'][i]:
                continue
            o, h, l, cl = d['open'][i], d['high'][i], d['low'][i], d['close'][i]
            entry = pos['entry_price']
            stop = entry * (1 - c.stop_loss)
            target = entry * (1 + c.take_profit)
            trail = None
            if pos['peak'] / entry - 1 >= c.trail_trigger:
                trail = pos['peak'] * (1 - c.trail_pct)
                if c.trail_covers_costs and trail < entry * (1 + round_trip_cost(c, pos['fee_rate'])):
                    trail = None
            floor = max(stop, trail) if trail else stop
            if l <= floor:
                close(name, i, min(o, floor), 'stop loss' if floor == stop else 'trailing stop')
                continue
            if h >= target:
                if c.limit_orders:
                    close(name, i, target, 'take profit', maker=True)
                else:
                    close(name, i, max(o, target), 'take profit')
                continue
            pos['peak'] = max(pos['peak'], h)
            held = (i - pos['entry_i'] + 1) * step
            if c.stale_minutes and held >= c.stale_minutes * 60 and cl / entry - 1 < c.stale_move:
                close(name, i, cl, 'went nowhere')
            elif held >= c.max_hold_minutes * 60:
                close(name, i, cl, 'time limit')

        marked = cash
        for name, pos in positions.items():
            price = data[name]['close'][i]
            marked += pos['units'] * (pos['entry_price'] if np.isnan(price) else price)
        equity.append(marked)

    for name in list(positions):
        last = data[name]['close'][~np.isnan(data[name]['close'])][-1]
        close(name, len(times) - 1, last, 'end of test')
    equity[-1] = cash

    return _summary(c, times, equity, trades)


def _summary(c, times, equity, trades):
    df = pd.DataFrame(trades, columns=['symbol', 'entry_time', 'exit_time', 'entry_price', 'exit_price',
                                       'fees', 'pnl', 'reason'])
    stats = trade_stats(df)
    wins, losses = df.loc[df['pnl'] > 0, 'pnl'], df.loc[df['pnl'] < 0, 'pnl']
    curve = pd.Series(equity)

    def clean(x):
        return None if x is None or pd.isna(x) or np.isinf(x) else float(x)

    exits = df.groupby('reason')['pnl'].agg(['count', 'sum']).reset_index() if len(df) else pd.DataFrame()
    return {'stats': {'final_equity': float(curve.iloc[-1]),
                      'total_return': float(curve.iloc[-1] / c.start_balance - 1),
                      'max_drawdown': clean(max_drawdown(curve)),
                      'trades': int(stats['num_trades']),
                      'win_rate': clean(stats['win_rate']),
                      'profit_factor': clean(stats['profit_factor']),
                      'avg_win': clean(wins.mean()) if len(wins) else None,
                      'avg_loss': clean(losses.mean()) if len(losses) else None,
                      'fees': float(df['fees'].sum()),
                      'pnl_before_fees': float((df['pnl'] + df['fees']).sum())},
            'equity': [{'t': t.isoformat(), 'v': float(v)} for t, v in zip(times, equity)],
            'trades': df.iloc[::-1].to_dict('records'),
            'exits': [{'reason': r['reason'], 'count': int(r['count']), 'pnl': float(r['sum'])}
                      for _, r in exits.iterrows()]}

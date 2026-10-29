# The six agents. Each setup runs left to right:
# scan -> volume -> risk check -> size -> execute -> log
# Every call is logged with its reason, including the ones that say no.
import time as _time

import numpy as np

from agent_module.rules import PASS, describe, exit_reason, spike_signals


class ScanAgent:
    """ Picks the most traded USD pairs and notices new listings. """
    name = 'SCAN'
    pairs_ttl = 3600

    def __init__(self, config, market, store):
        self.config = config
        self.market = market
        self.store = store
        self.pairs = {}
        self.pairs_loaded = 0

    def run(self, now):
        """
        :return:
            (list, dict): watched pair keys, tickers for every USD pair
        """
        new = []
        if not self.pairs or _time.time() - self.pairs_loaded > self.pairs_ttl:
            pairs = self.market.usd_pairs()
            known = set(self.store.get('known_pairs', []))
            new = [p for p in pairs if known and p not in known]
            self.store.set('known_pairs', sorted(pairs))
            self.pairs, self.pairs_loaded = pairs, _time.time()

        tickers = self.market.tickers(list(self.pairs))
        ranked = sorted(tickers, key=lambda p: tickers[p]['quote_volume'], reverse=True)
        watched = ranked[:self.config.max_pairs]
        for pair in new:
            self.store.log(now, self.name, 'PASS', self.pairs[pair], 'new listing')
            if pair in tickers and pair not in watched:
                watched.append(pair)

        self.store.log(now, self.name, 'PASS', None,
                       f'watching {len(watched)} of {len(self.pairs)} USD pairs')
        return watched, tickers


def volume_spike(candles, lookback):
    """
    :return:
        float: last closed candle volume / median volume of the lookback before it
    """
    if len(candles) < lookback + 1:
        return 0.0
    baseline = np.median(candles['volume'].iloc[-lookback - 1:-1])
    if baseline <= 0:
        return 0.0
    return candles['volume'].iloc[-1] / baseline


class VolumeAgent:
    """
    Passes pairs whose last candle traded far above normal and closed green,
    and with the stricter settings on, hadn't already run up and held its gain.
    """
    name = 'VOLUME'

    def __init__(self, config, market, store):
        self.config = config
        self.market = market
        self.store = store

    def run(self, now, pairs, names):
        passed = []
        for pair in pairs:
            candles = self.market.candles(pair, self.config.candle_interval)
            if len(candles) < self.config.spike_lookback + 2:
                continue
            row = spike_signals(candles, self.config).iloc[-1]
            if row['signal'] is None:
                continue
            self.store.log(now, self.name, 'PASS' if row['signal'] == PASS else 'SKIP',
                           names[pair], describe(row, self.config))
            if row['signal'] == PASS:
                passed.append(pair)

        if not passed:
            self.store.log(now, self.name, 'WAIT', None, f'no spikes over {self.config.min_spike:g}x')
        return passed


class RiskAgent:
    """
    Stands in for the rug check. On an exchange the token can't rug, so this
    filters out pairs too thin to get in and out of at a fair price.
    """
    name = 'RISK CHECK'

    def __init__(self, config, store):
        self.config = config
        self.store = store

    def run(self, now, pair, ticker, name):
        mid = (ticker['bid'] + ticker['ask']) / 2
        spread = (ticker['ask'] - ticker['bid']) / mid if mid else 1
        if ticker['quote_volume'] < self.config.min_quote_volume:
            self.store.log(now, self.name, 'SKIP', name,
                           f'only ${ticker["quote_volume"]:,.0f} traded in 24h')
            return False
        if spread > self.config.max_spread:
            self.store.log(now, self.name, 'SKIP', name, f'spread {spread:.2%}')
            return False
        self.store.log(now, self.name, 'PASS', name, f'spread {spread:.2%}')
        return True


class SizeAgent:
    """ Sizes so a stop loss costs risk_per_trade of equity, capped per pair. """
    name = 'SIZE'
    min_order = 10.0

    def __init__(self, config, store):
        self.config = config
        self.store = store

    def run(self, now, name, broker, equity):
        c = self.config
        if len(broker.positions) + len(broker.orders) >= c.max_open_positions:
            self.store.log(now, self.name, 'SKIP', name, f'{c.max_open_positions} positions already open')
            return 0.0
        value = min(equity * c.risk_per_trade / c.stop_loss,
                    equity * c.max_position_pct,
                    broker.free_cash() / (1 + c.taker_fee))
        if value < self.min_order:
            self.store.log(now, self.name, 'SKIP', name, f'${value:,.2f} is below the minimum order')
            return 0.0
        self.store.log(now, self.name, 'PASS', name, f'${value:,.2f} ({value / equity:.1%} of balance)')
        return value


class ExecuteAgent:
    """
    Places paper orders and closes them on take profit, stop, trailing stop,
    a trade that went nowhere, or time.
    """
    name = 'EXECUTE'

    def __init__(self, config, store, broker):
        self.config = config
        self.store = store
        self.broker = broker

    def enter(self, now, now_ts, pair, name, ticker, value):
        if self.config.limit_orders:
            order = self.broker.place_limit_buy(now, now_ts, pair, name, ticker['bid'], value)
            self.store.log(now, self.name, 'WAIT', name,
                           f'limit buy ${value:,.2f} @ {order["price"]:.8g}')
            return
        pos = self.broker.buy(now, now_ts, pair, name, ticker, value)
        self.store.log(now, self.name, 'ENTER', name,
                       f'${value:,.2f} @ {pos["entry_price"]:.8g}')

    def exit_reason(self, pos, bid, now_ts):
        return exit_reason(pos, bid, now_ts, self.config)

    def manage(self, now, now_ts, tickers):
        filled, cancelled = self.broker.check_orders(now, now_ts, tickers)
        for pair, pos in filled:
            self.store.log(now, self.name, 'ENTER', pos['symbol'],
                           f'limit filled ${pos["cost"]:,.2f} @ {pos["entry_price"]:.8g}')
        for pair, order in cancelled:
            self.store.log(now, self.name, 'SKIP', order['symbol'],
                           f'limit not filled in {self.config.limit_wait_minutes} min, cancelled')

        for pair, pos in list(self.broker.positions.items()):
            ticker = tickers.get(pair)
            if ticker is None:
                continue
            self.broker.mark(pair, ticker['bid'])
            reason = self.exit_reason(pos, ticker['bid'], now_ts)
            if reason:
                # a take profit rests on the book as a limit sell, so it fills at its price
                limit = pos['entry_price'] * (1 + self.config.take_profit) \
                    if reason == 'take profit' and self.config.limit_orders else None
                trade = self.broker.sell(now, pair, ticker, reason, limit=limit)
                sign = '+' if trade['pnl'] >= 0 else '-'
                self.store.log(now, self.name, 'EXIT', pos['symbol'],
                               f'{sign}${abs(trade["pnl"]):,.2f} {reason}')


class LogAgent:
    """ Closes each cycle with the balance so the equity curve has a point. """
    name = 'LOG'

    def __init__(self, store):
        self.store = store

    def run(self, now, equity, open_positions):
        self.store.add_equity(now, equity)
        self.store.log(now, self.name, 'PASS', None,
                       f'balance ${equity:,.2f}, {open_positions} open')

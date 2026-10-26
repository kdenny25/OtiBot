# The six agents. Each setup runs left to right:
# scan -> volume -> risk check -> size -> execute -> log
# Every call is logged with its reason, including the ones that say no.
import time as _time

import numpy as np


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
    """ Passes pairs whose last candle traded far above normal and closed green. """
    name = 'VOLUME'

    def __init__(self, config, market, store):
        self.config = config
        self.market = market
        self.store = store

    def run(self, now, pairs, names):
        passed = []
        for pair in pairs:
            candles = self.market.candles(pair, self.config.candle_interval)
            spike = volume_spike(candles, self.config.spike_lookback)
            if spike < self.config.min_spike:
                continue
            last = candles.iloc[-1]
            if last['close'] <= last['open']:
                self.store.log(now, self.name, 'SKIP', names[pair], f'spike {spike:.1f}x on a red candle')
                continue
            self.store.log(now, self.name, 'PASS', names[pair], f'spike {spike:.1f}x')
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
        if len(broker.positions) >= c.max_open_positions:
            self.store.log(now, self.name, 'SKIP', name, f'{c.max_open_positions} positions already open')
            return 0.0
        value = min(equity * c.risk_per_trade / c.stop_loss,
                    equity * c.max_position_pct,
                    broker.cash / (1 + c.taker_fee))
        if value < self.min_order:
            self.store.log(now, self.name, 'SKIP', name, f'${value:,.2f} is below the minimum order')
            return 0.0
        self.store.log(now, self.name, 'PASS', name, f'${value:,.2f} ({value / equity:.1%} of balance)')
        return value


class ExecuteAgent:
    """ Places paper orders and closes them on take profit, stop, trailing stop or time. """
    name = 'EXECUTE'

    def __init__(self, config, store, broker):
        self.config = config
        self.store = store
        self.broker = broker

    def enter(self, now, now_ts, pair, name, ticker, value):
        pos = self.broker.buy(now, now_ts, pair, name, ticker, value)
        self.store.log(now, self.name, 'ENTER', name,
                       f'${value:,.2f} @ {pos["entry_price"]:.8g}')

    def exit_reason(self, pos, bid, now_ts):
        c = self.config
        change = bid / pos['entry_price'] - 1
        if change <= -c.stop_loss:
            return 'stop loss'
        if change >= c.take_profit:
            return 'take profit'
        if pos['peak'] / pos['entry_price'] - 1 >= c.trail_trigger and \
                bid <= pos['peak'] * (1 - c.trail_pct):
            return 'trailing stop'
        if now_ts - pos['entry_ts'] >= c.max_hold_minutes * 60:
            return 'time limit'
        return None

    def manage(self, now, now_ts, tickers):
        for pair, pos in list(self.broker.positions.items()):
            ticker = tickers.get(pair)
            if ticker is None:
                continue
            self.broker.mark(pair, ticker['bid'])
            reason = self.exit_reason(pos, ticker['bid'], now_ts)
            if reason:
                trade = self.broker.sell(now, pair, ticker, reason)
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

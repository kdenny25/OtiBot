# Paper broker. Market orders fill buys at the ask and sells at the bid, plus
# slippage and the taker fee, so results include the cost of crossing the
# spread. Limit orders fill at their own price with the maker fee, and only
# once the market trades down to them.

class PaperBroker:
    def __init__(self, config, store):
        self.config = config
        self.store = store
        self.cash = store.get('cash', config.start_balance)
        self.positions = store.positions()
        # limit buys waiting to fill, pair -> order
        self.orders = store.get('orders', {})

    def equity(self, tickers=None):
        value = self.cash
        for pair, pos in self.positions.items():
            price = tickers[pair]['bid'] if tickers and pair in tickers else pos['last']
            value += pos['units'] * price
        return value

    def free_cash(self):
        """ Cash not set aside for limit buys that haven't filled yet. """
        return self.cash - sum(o['value'] * (1 + self.config.maker_fee) for o in self.orders.values())

    def buy(self, now, now_ts, pair, symbol, ticker, value, limit=None):
        """ Market buy, or with limit the fill of a limit buy at that price. """
        c = self.config
        mid = (ticker['bid'] + ticker['ask']) / 2
        if limit is None:
            fill, fee_rate = ticker['ask'] * (1 + c.slippage), c.taker_fee
        else:
            fill, fee_rate = limit, c.maker_fee
        fee = value * fee_rate
        pos = {'symbol': symbol,
               'entry_time': now,
               'entry_ts': now_ts,
               'entry_price': fill,
               'units': value / fill,
               'cost': value,
               'fees': fee,
               'fee_rate': fee_rate,
               'entry_slip': fill / mid - 1,
               'peak': ticker['bid'],
               'last': ticker['bid']}
        self.cash -= value + fee
        self.positions[pair] = pos
        self.store.save_position(pair, pos)
        self.store.set('cash', self.cash)
        return pos

    def place_limit_buy(self, now, now_ts, pair, symbol, price, value):
        self.orders[pair] = {'symbol': symbol, 'time': now, 'ts': now_ts, 'price': price, 'value': value}
        self.store.set('orders', self.orders)
        return self.orders[pair]

    def cancel(self, pair):
        order = self.orders.pop(pair)
        self.store.set('orders', self.orders)
        return order

    def check_orders(self, now, now_ts, tickers):
        """
        Fills limit buys the market traded down to and cancels the ones
        that waited too long.

        :return:
            (list, list): (pair, position) filled, (pair, order) cancelled
        """
        filled, cancelled = [], []
        for pair, order in list(self.orders.items()):
            ticker = tickers.get(pair)
            if ticker and (ticker['ask'] <= order['price'] or ticker['last'] < order['price']):
                self.cancel(pair)
                filled.append((pair, self.buy(now, now_ts, pair, order['symbol'], ticker,
                                              order['value'], limit=order['price'])))
            elif now_ts - order['ts'] >= self.config.limit_wait_minutes * 60:
                cancelled.append((pair, self.cancel(pair)))
        return filled, cancelled

    def mark(self, pair, bid):
        pos = self.positions[pair]
        pos['last'] = bid
        pos['peak'] = max(pos['peak'], bid)
        self.store.save_position(pair, pos)

    def sell(self, now, pair, ticker, reason, limit=None):
        """ Market sell, or with limit the fill of a resting limit sell at that price. """
        c = self.config
        pos = self.positions.pop(pair)
        mid = (ticker['bid'] + ticker['ask']) / 2
        if limit is None:
            fill, fee_rate = ticker['bid'] * (1 - c.slippage), c.taker_fee
        else:
            fill, fee_rate = limit, c.maker_fee
        proceeds = pos['units'] * fill
        fee = proceeds * fee_rate
        self.cash += proceeds - fee
        trade = {'symbol': pos['symbol'],
                 'entry_time': pos['entry_time'],
                 'exit_time': now,
                 'entry_price': pos['entry_price'],
                 'exit_price': fill,
                 'units': pos['units'],
                 'fees': pos['fees'] + fee,
                 'slippage': pos['entry_slip'] + (1 - fill / mid),
                 'pnl': proceeds - fee - pos['cost'] - pos['fees'],
                 'reason': reason}
        self.store.add_trade(trade)
        self.store.remove_position(pair)
        self.store.set('cash', self.cash)
        return trade

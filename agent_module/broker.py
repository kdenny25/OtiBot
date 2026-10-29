# Paper broker. Market orders cross the spread: a long buys at the ask and
# sells at the bid, a short sells at the bid and buys back at the ask, plus
# slippage and the taker fee. Limit orders fill at their own price with the
# maker fee, and only once the market trades through them.
#
# A short sets aside its value as collateral, like a long's cost, and pays
# Kraken's margin fee to open and every 4 hours it stays open.
from agent_module.rules import margin_cost


class PaperBroker:
    def __init__(self, config, store):
        self.config = config
        self.store = store
        self.cash = store.get('cash', config.start_balance)
        self.positions = store.positions()
        # limit orders waiting to fill, pair -> order
        self.orders = store.get('orders', {})

    @staticmethod
    def close_price(pos, ticker):
        """ What closing trades at: the bid for a long, the ask for a short. """
        return ticker['bid'] if pos.get('side', 1) == 1 else ticker['ask']

    @staticmethod
    def value(pos, price):
        """ What a position is worth at price, before fees to close. """
        if pos.get('side', 1) == 1:
            return pos['units'] * price
        return pos['cost'] + pos['units'] * (pos['entry_price'] - price)

    def equity(self, tickers=None):
        value = self.cash
        for pair, pos in self.positions.items():
            price = self.close_price(pos, tickers[pair]) if tickers and pair in tickers else pos['last']
            value += self.value(pos, price)
        return value

    def free_cash(self):
        """ Cash not set aside for limit orders that haven't filled yet. """
        return self.cash - sum(o['value'] * (1 + self.config.maker_fee) for o in self.orders.values())

    def open(self, now, now_ts, pair, symbol, ticker, value, side=1, limit=None):
        """ Market order, or with limit the fill of a limit order at that price. """
        c = self.config
        mid = (ticker['bid'] + ticker['ask']) / 2
        if limit is not None:
            fill, fee_rate = limit, c.maker_fee
        elif side == 1:
            fill, fee_rate = ticker['ask'] * (1 + c.slippage), c.taker_fee
        else:
            fill, fee_rate = ticker['bid'] * (1 - c.slippage), c.taker_fee
        fee = value * fee_rate
        start = self.close_price({'side': side}, ticker)
        pos = {'symbol': symbol,
               'side': side,
               'entry_time': now,
               'entry_ts': now_ts,
               'entry_price': fill,
               'units': value / fill,
               'cost': value,
               'fees': fee,
               'fee_rate': fee_rate,
               'entry_slip': side * (fill / mid - 1),
               'peak': start,
               'last': start}
        self.cash -= value + fee
        self.positions[pair] = pos
        self.store.save_position(pair, pos)
        self.store.set('cash', self.cash)
        return pos

    def buy(self, now, now_ts, pair, symbol, ticker, value, limit=None):
        return self.open(now, now_ts, pair, symbol, ticker, value, 1, limit)

    def place_limit(self, now, now_ts, pair, symbol, price, value, side=1):
        self.orders[pair] = {'symbol': symbol, 'side': side, 'time': now, 'ts': now_ts,
                             'price': price, 'value': value}
        self.store.set('orders', self.orders)
        return self.orders[pair]

    def cancel(self, pair):
        order = self.orders.pop(pair)
        self.store.set('orders', self.orders)
        return order

    def check_orders(self, now, now_ts, tickers):
        """
        Fills limit orders the market traded through and cancels the ones
        that waited too long.

        :return:
            (list, list): (pair, position) filled, (pair, order) cancelled
        """
        filled, cancelled = [], []
        for pair, order in list(self.orders.items()):
            ticker, price, side = tickers.get(pair), order['price'], order.get('side', 1)
            hit = ticker and ((ticker['ask'] <= price or ticker['last'] < price) if side == 1
                              else (ticker['bid'] >= price or ticker['last'] > price))
            if hit:
                self.cancel(pair)
                filled.append((pair, self.open(now, now_ts, pair, order['symbol'], ticker,
                                               order['value'], side, limit=price)))
            elif now_ts - order['ts'] >= self.config.limit_wait_minutes * 60:
                cancelled.append((pair, self.cancel(pair)))
        return filled, cancelled

    def mark(self, pair, ticker):
        pos = self.positions[pair]
        price = self.close_price(pos, ticker)
        pos['last'] = price
        pos['peak'] = max(pos['peak'], price) if pos.get('side', 1) == 1 else min(pos['peak'], price)
        self.store.save_position(pair, pos)

    def close(self, now, now_ts, pair, ticker, reason, limit=None):
        """ Market order, or with limit the fill of a resting limit order at that price. """
        c = self.config
        pos = self.positions.pop(pair)
        side = pos.get('side', 1)
        mid = (ticker['bid'] + ticker['ask']) / 2
        if limit is not None:
            fill, fee_rate = limit, c.maker_fee
        else:
            fill, fee_rate = self.close_price(pos, ticker) * (1 - side * c.slippage), c.taker_fee
        proceeds = self.value(pos, fill)
        fee = pos['units'] * fill * fee_rate
        if side == -1:
            fee += margin_cost(c, pos['cost'], now_ts - pos['entry_ts'])
        self.cash += proceeds - fee
        trade = {'symbol': pos['symbol'] + (' short' if side == -1 else ''),
                 'entry_time': pos['entry_time'],
                 'exit_time': now,
                 'entry_price': pos['entry_price'],
                 'exit_price': fill,
                 'units': pos['units'],
                 'fees': pos['fees'] + fee,
                 'slippage': pos['entry_slip'] + side * (1 - fill / mid),
                 'pnl': proceeds - fee - pos['cost'] - pos['fees'],
                 'reason': reason}
        self.store.add_trade(trade)
        self.store.remove_position(pair)
        self.store.set('cash', self.cash)
        return trade

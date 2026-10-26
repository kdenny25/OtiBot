# Paper broker. Fills buys at the ask and sells at the bid, plus slippage and
# fees, so results include the cost of crossing the spread.

class PaperBroker:
    def __init__(self, config, store):
        self.config = config
        self.store = store
        self.cash = store.get('cash', config.start_balance)
        self.positions = store.positions()

    def equity(self, tickers=None):
        value = self.cash
        for pair, pos in self.positions.items():
            price = tickers[pair]['bid'] if tickers and pair in tickers else pos['last']
            value += pos['units'] * price
        return value

    def buy(self, now, now_ts, pair, symbol, ticker, value):
        c = self.config
        mid = (ticker['bid'] + ticker['ask']) / 2
        fill = ticker['ask'] * (1 + c.slippage)
        fee = value * c.taker_fee
        pos = {'symbol': symbol,
               'entry_time': now,
               'entry_ts': now_ts,
               'entry_price': fill,
               'units': value / fill,
               'cost': value,
               'fees': fee,
               'entry_slip': fill / mid - 1,
               'peak': ticker['bid'],
               'last': ticker['bid']}
        self.cash -= value + fee
        self.positions[pair] = pos
        self.store.save_position(pair, pos)
        self.store.set('cash', self.cash)
        return pos

    def mark(self, pair, bid):
        pos = self.positions[pair]
        pos['last'] = bid
        pos['peak'] = max(pos['peak'], bid)
        self.store.save_position(pair, pos)

    def sell(self, now, pair, ticker, reason):
        c = self.config
        pos = self.positions.pop(pair)
        mid = (ticker['bid'] + ticker['ask']) / 2
        fill = ticker['bid'] * (1 - c.slippage)
        proceeds = pos['units'] * fill
        fee = proceeds * c.taker_fee
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

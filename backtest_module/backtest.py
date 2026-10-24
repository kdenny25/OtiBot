from utility import local_db
from backtest_module.evaluations import evaluate
import pandas as pd


class backtest(object):
    """
        Backtester for long and (optionally) short strategies. A strategy is
        a function that takes the price dataframe and returns two boolean
        series (buy, sell), the same format as strategies/sample_strategy.py.

        A buy signal closes any short and goes long. A sell signal closes
        any long and, when allow_short is True, goes short. A candle with
        both signals is ignored.

        Signals are calculated on the close of a candle and filled at the
        open of the next candle so results don't use future prices.
        Every fill pays the taker fee and slippage: buys fill slippage
        above the price and sells fill slippage below it.
    """

    def __init__(self, client=None, capital=10000, allow_short=False, slippage=0.0):
        self.client = client
        self.capital = capital
        self.allow_short = allow_short
        self.slippage = slippage
        self.trade_pair = 'ETHUSD'
        self.taker_fees = 0.0
        self.maker_fees = 0.0
        self.strategy = None
        self.data = None
        self.periods_per_year = 365 * 96   # 15 minute candles

    # set tradeable pair
    def set_tradable_pair(self, symbol):
        self.trade_pair = symbol

        # set fees from the exchange when a client is available
        if self.client is not None:
            symbol_info = self.client.get_asset_pair_info(symbol)
            # Kraken returns fee tiers as [volume, percent], use the base tier
            self.maker_fees = symbol_info['fees_maker'][0][1] / 100
            self.taker_fees = symbol_info['fees'][0][1] / 100

    # get historical data
    def get_historical_data(self, interval, start_date, end_date):
        """
        Retrieves historical data from our database and uses it for the
        backtest.
        :param:
            interval (int): interval of timeframe to pull from
            start_date (str): open date to start pulling data for
            end_date (str): open date to stop pulling data for
        :return:
            Pandas dataframe of date
        """
        conn = local_db()
        cur = conn.cursor()
        query = ("SELECT * FROM crypto_pair "
                 "WHERE symbol = %s "
                 "AND interval = %s "
                 "AND opendatetime BETWEEN %s AND %s "
                 "ORDER BY opentime")
        cur.execute(query, (self.trade_pair, interval, start_date, end_date))
        results = cur.fetchall()
        col_names = [desc[0] for desc in cur.description]
        cur.close()
        conn.close()

        results = pd.DataFrame(results, columns=col_names)
        for col in ['open', 'high', 'low', 'close', 'volume']:
            results[col] = results[col].astype(float)
        self.set_data(results)
        return results

    def set_data(self, data):
        """
        :param:
            data (pandas.DataFrame): candles in time order with open and
                                     close columns
        """
        self.data = data.reset_index(drop=True)

    # set capital
    def set_capital(self, capital):
        self.capital = capital

    # set transaction fees
    def set_fees(self, taker, maker=None):
        """
        :param:
            taker (float): fee as a fraction, 0.0026 is 0.26%
            maker (float): defaults to the taker fee
        """
        self.taker_fees = taker
        self.maker_fees = taker if maker is None else maker

    # set slippage
    def set_slippage(self, slippage):
        """
        :param:
            slippage (float): price impact per fill as a fraction, 0.0005 is
                              0.05%
        """
        self.slippage = slippage

    # allow short positions
    def set_allow_short(self, allow_short=True):
        self.allow_short = allow_short

    # set strategy
    def set_strategy(self, strategy):
        self.strategy = strategy

    def buy_price(self, price):
        """ Fill price for a buy after slippage. """
        return price * (1 + self.slippage)

    def sell_price(self, price):
        """ Fill price for a sell after slippage. """
        return price * (1 - self.slippage)

    # buy
    def buy(self, cash, price):
        """ Spends all cash at price. Returns units bought. """
        return cash * (1 - self.taker_fees) / self.buy_price(price)

    # sell
    def sell(self, units, price):
        """ Sells all units at price. Returns cash received. """
        return units * self.sell_price(price) * (1 - self.taker_fees)

    # short
    def short(self, cash, price):
        """
        Opens a short worth all cash at price. The fee is paid from cash.
        Returns (units shorted, fill price, cash left after the fee).
        """
        cash = cash * (1 - self.taker_fees)
        fill = self.sell_price(price)
        return cash / fill, fill, cash

    # cover
    def cover(self, units, entry_fill, cash, price):
        """ Buys back a short at price. Returns cash after profit/loss and fee. """
        fill = self.buy_price(price)
        return cash + units * (entry_fill - fill) - units * fill * self.taker_fees

    # run backtest
    def run(self, data=None):
        """
        Runs the strategy over the data.

        :return:
            dict: stats (dict from evaluations.evaluate), equity (pd.Series of
                  account value at each close) and trades (pd.DataFrame of
                  round trips)
        """
        if self.strategy is None:
            raise ValueError('set a strategy before running a backtest')
        data = self.data if data is None else data.reset_index(drop=True)
        if data is None or data.empty:
            raise ValueError('no data to backtest')

        buy_signal, sell_signal = self.strategy(data.copy())
        buy_signal = pd.Series(buy_signal).fillna(False).astype(bool).to_numpy()
        sell_signal = pd.Series(sell_signal).fillna(False).astype(bool).to_numpy()

        opens = data['open'].to_numpy()
        closes = data['close'].to_numpy()

        cash = self.capital
        position = 0      # 1 long, -1 short, 0 flat
        units = 0.0
        entry = None
        trades = []
        equity = []

        def close_position(i, price):
            nonlocal cash, position, units
            if position == 1:
                cash = self.sell(units, price)
            else:
                cash = self.cover(units, entry['entry_fill'], cash, price)
            trades.append(self._close_trade(entry, i, price, cash))
            position, units = 0, 0.0

        def open_position(i, side, price):
            nonlocal cash, position, units, entry
            entry = {'side': 'long' if side == 1 else 'short', 'entry_index': i,
                     'entry_price': price, 'entry_cash': cash}
            if side == 1:
                units = self.buy(cash, price)
                cash = 0.0
            else:
                units, entry['entry_fill'], cash = self.short(cash, price)
            position = side

        for i in range(len(data)):
            # fill signals from the previous candle at this candle's open
            if i > 0 and buy_signal[i - 1] != sell_signal[i - 1]:
                if buy_signal[i - 1] and position != 1:
                    if position == -1:
                        close_position(i, opens[i])
                    open_position(i, 1, opens[i])
                elif sell_signal[i - 1] and position != -1:
                    if position == 1:
                        close_position(i, opens[i])
                    if self.allow_short:
                        open_position(i, -1, opens[i])

            if position == 1:
                equity.append(units * closes[i])
            elif position == -1:
                equity.append(cash + units * (entry['entry_fill'] - closes[i]))
            else:
                equity.append(cash)

        # close any open position at the final close
        if position != 0:
            close_position(len(data) - 1, closes[-1])
            equity[-1] = cash

        equity = pd.Series(equity, index=data.index, name='equity')
        trades = pd.DataFrame(trades, columns=['side', 'entry_index', 'entry_price', 'exit_index',
                                               'exit_price', 'pnl', 'return'])
        return {'stats': evaluate(equity, trades, self.periods_per_year),
                'equity': equity,
                'trades': trades}

    @staticmethod
    def _close_trade(entry, exit_index, exit_price, cash):
        pnl = cash - entry['entry_cash']
        return {'side': entry['side'], 'entry_index': entry['entry_index'], 'entry_price': entry['entry_price'],
                'exit_index': exit_index, 'exit_price': exit_price,
                'pnl': pnl, 'return': pnl / entry['entry_cash']}

    # run split window backtesting
    def run_split_window(self, n_windows=4):
        """
        Splits the data into equal, back to back windows and runs the
        strategy on each one with fresh capital. Shows whether results hold
        up across different market periods.

        :return:
            pandas.DataFrame: one row of stats per window with its start and
                              end index
        """
        if self.data is None or len(self.data) < n_windows:
            raise ValueError('not enough data for the number of windows')

        size = len(self.data) // n_windows
        rows = []
        for w in range(n_windows):
            start = w * size
            end = len(self.data) if w == n_windows - 1 else start + size
            stats = self.run(self.data.iloc[start:end])['stats']
            rows.append({'window': w, 'start_index': start, 'end_index': end - 1, **stats})
        return pd.DataFrame(rows)

if __name__ == '__main__':
    from exch_apis.kraken import client
    from indicators import SMA, RSI

    def sma_rsi(df):
        df['SMA'] = SMA(df['close'], 20)
        df['RSI'] = RSI(df['close'], 14)
        buy = (df['SMA'] > df['SMA'].shift(1)) & (df['RSI'] < 30)
        sell = (df['SMA'] < df['SMA'].shift(1)) | (df['RSI'] > 70)
        return buy, sell

    bt = backtest(client(), allow_short=True, slippage=0.0005)
    bt.set_tradable_pair('ETHUSD')
    bt.get_historical_data(15, '7/1/2023', '11/5/2023')
    bt.set_strategy(sma_rsi)
    print(bt.run()['stats'])
    print(bt.run_split_window(4))

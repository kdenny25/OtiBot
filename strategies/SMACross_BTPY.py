from backtesting import Strategy, Backtest
from backtesting.lib import crossover
from indicators import SMA
from historical_data import get_historical_data
import pandas as pd


precision = 5
data = get_historical_data('ETHUSD', 15, '1/1/2022', BTPY_format=True)

class SmaCross(Strategy):
    # define two MA lags as class variables
    # for later optimization
    n1 = 6
    n2 = 13

    def init(self):
        # Precompute two moving averages
        self.sma1 = self.I(SMA, self.data.Close, self.n1)
        self.sma2 = self.I(SMA, self.data.Close, self.n2)

    def next(self):
        # if sma1 crosses above sma2, close existing
        # short trades and buy the asset
        if crossover(self.sma1, self.sma2):
            self.position.close()
            self.buy()

        # Else, if sma1 crosses below sma2, close any existing
        # long trades, and sell the asset
        elif crossover(self.sma2, self.sma1):
            self.position.close()
            self.sell()

if __name__ == '__main__':
    bt = Backtest(data, SmaCross, cash=10000, commission=.002)
    #stats = bt.run()
    stats = bt.optimize(n1=range(5, 30, 5),
                        n2=range(10, 70, 5),
                        maximize='Equity Final [$]',
                        constraint=lambda param: param.n1 < param.n2)
    print(stats._strategy)
    bt.plot(resample=False)
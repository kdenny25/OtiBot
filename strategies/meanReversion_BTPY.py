from backtesting import Strategy, Backtest
from indicators import SMA
from historical_data import get_historical_data
import pandas as pd


precision = 5
data = get_historical_data('ETHUSD', 15, '5/1/2023', BTPY_format=True)

def std_3(arr, n):
    return pd.Series(arr).rolling(n).std() * 3

class MeanReversion(Strategy):
    """
    Mean Reversion is good for volatile stocks or crypto with consistent ups and downs
    """
    roll = 25

    def init(self):
        self.he = self.data.Close

        self.he_mean = self.I(SMA, self.he, self.roll)
        self.he_std = self.I(std_3, self.he, self.roll)
        self.he_upper = self.he_mean + self.he_std
        self.he_lower = self.he_mean - self.he_std

        self.he_close = self.I(SMA, self.he, 2)

    def next(self):
        if self.he_close < self.he_lower:
            self.buy(
                tp = self.he_mean
            )

        if self.he_close > self.he_upper:
            self.sell(
                tp = self.he_mean
            )

if __name__ == '__main__':
    bt = Backtest(data, MeanReversion, cash=10000, commission=0.002)
    stats = bt.run()
    bt.plot(resample=False)
    print(stats)
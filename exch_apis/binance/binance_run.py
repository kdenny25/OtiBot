import json
import os
import numpy as np
import matplotlib.pyplot as plt
import time

from binance_interaction import binance
from strategies.SMA import Strategy as stg

client = binance()

#print(client.get_historical_klines('BTCUSDT', '5m', '1 Sep 2023'))

# Backtesting
def backtest(data, Strategy):
    Strategy.calculate_indicators(data)
    buy, sell = Strategy.strategy(data)
    data['buy'] = buy
    data['sell'] = sell
    data['position'] = np.nan
    data.loc[buy, 'position'] = 1
    data.loc[sell, 'position'] = 0
    data['position'].fillna(method='ffill', inplace=True)
    data['position'].fillna(0, inplace=True)
    data['returns'] = np.log(data['close'] / data['close'].shift(1))
    data['strategy'] = data['position'].shift(1) * data['returns']
    data['cumulative_returns'] = data['strategy'].cumsum().apply(np.exp)
    return data

# plot cumulative returns
def plot_results(data):
    data[['cumulative_returns']].plot(figsize=(10,6))
    plt.xlabel('Date')
    plt.ylabel('Cumulative Returns')
    plt.title('Backtesting Results')
    plt.savefig('backtest.png')
    plt.show()

def test_trading():
    data = client.get_historical_klines('BTCUSDT', '5m', '1 Sep 2023')
    data = backtest(data, stg)
    plot_results(data)
    return data

def live_trading():
    prev_buy_signal = False
    prev_sell_signal = False
    while True:
        # Dowload data, calculate indicators and get signals
        data = client.get_historical_klines('BTCUSDT', '5m', '1 Oct 2023')
        stg.calculate_indicators(data)
        buy_signal, sell_signal = stg.strategy(data)
        buy_signal = buy_signal.iloc[-1]
        sell_signal = sell_signal.iloc[-1]
        if buy_signal and not prev_buy_signal:
            client.create_test_order(
                symbol='BTCUSDT',
                side='BUY',
                type='MARKET',
                quantity=0.001,
            )
        elif sell_signal and not prev_sell_signal:
            client.create_test_order(
                symbol='BTCUSDT',
                side='SELL',
                type='MARKET',
                quantity=0.001
            )
        else:
            print('No trade made.')
        prev_buy_signal = buy_signal
        prev_sell_signal = sell_signal
        time.sleep(60)

live_trading()
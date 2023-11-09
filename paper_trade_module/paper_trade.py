import pandas as pd
import requests
import numpy as np
from lightweight_charts import Chart
import time
import asyncio
import nest_asyncio
from exch_apis.kraken.kraken_client import client
from indicators import MACD
nest_asyncio.apply()


if __name__ == '__main__':
    client = client()

    hist_df = client.get_historical_data(symbol='ETHUSD')
    macd = MACD(hist_df['close'], 26, 12, 9)
    macd['time'] = hist_df['time']


    chart = Chart(inner_width=1, inner_height=0.5)
    chart2 = chart.create_subchart( width=1, height=0.5)
    chart.legend(visible=True)
    labels = ['time', 'open', 'high', 'low', 'close']
    chart.set(hist_df[labels])

    line = chart2.create_line('macd', color='red')
    line.set(macd[['time', 'macd']])
    line2 = chart2.create_line('macd_signal', color='orange')
    line2.set(macd[['time', 'macd_signal']])

    hist = chart2.create_histogram('macd_hist')
    hist.set(macd[['time', 'macd_hist']])
    chart.show(block=True)
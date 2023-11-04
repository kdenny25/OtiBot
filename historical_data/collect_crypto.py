# uses access to binance api to collect historical data.
# collected data will be added to a local database.

import os
import psycopg2
import requests
import pandas as pd
import numpy as np
from datetime import datetime as dt
import sys
import time
import math
from utility.progress_bar import printProgressBar

conn = psycopg2.connect(
    host="localhost",
    database="crypto_data",
    user="postgres",
    password="admin",
    port='5433'
)

# open a cursor to perform database operations
cur = conn.cursor()

def _check_api_weight_limit(response):
    """
    Check if weight limit is exceeded
    Binance API only
    """
    #print(response.headers)
    print('Used Weight', response.headers['x-mbx-used-weight'])
    print('Date', response.headers['Date'][23:25])
    print('Status', response.status_code)
    if response.status_code == 429:
        sys.exit("Weight Limit Exceeded")
    elif response.status_code == 200:
        if int(response.headers['x-mbx-used-weight']) > 1180:
            time.sleep(60-int(response.headers['Date'][23:25]))
        else:
            pass
    else:
        pass

def get_crypto(symbol='ETHUSD', interval=15, limit=500, startTime=None, endTime=None):
    """
    interval is in minutes
    maximum limit is 1000
    startTime and endTime are optional

    returned time is epoch ms time
    """
    if type(startTime) != int:
        startTime = dt.strptime(startTime, '%m/%d/%Y')
        startTime = int(dt(startTime.year, startTime.month, startTime.day, 0, 0).timestamp()) * 1000
    #print(f'https://api.binance.us/api/v3/klines?symbol={symbol}&interval={interval}m&limit={limit}&startTime={startTime}')
    resp = requests.get(f'https://api.binance.us/api/v3/klines?symbol={symbol}&interval={interval}m&limit={limit}&startTime={startTime}')
    columns = ['open_time', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_asset_vol',
               'num_trades', 'taker_buy_base_vol', 'taker_buy_quote_vol', 'ignore']

    data_df = pd.DataFrame(resp.json(), columns=columns)
    _check_api_weight_limit(resp)
    return data_df

def get_last_enrty(symbol, interval):
    """
    Returns epoch datetime of last database entry of specified symbol

    :param:
    symbol (str): Trading pair of symbol.

    :return:
    int: Epoch in ms or None if not entries exist
    """
    cur.execute(f"SELECT MAX(opentime) "
                        f"FROM crypto_pair "
                        f"WHERE symbol = '{symbol}' AND interval = {interval}")

    result = cur.fetchall()[0][0] # automatically returns None if empty

    return result

def load_crypto(symbol='ETHUSD', interval=15, limit=500, startTime=None):
    """
    Loads extracted OHLCV to a database.

    :param symbol:
    :param interval:
    :param limit:
    :param startTime:
    :return:
    """

    startTime_temp = dt.strptime(startTime, '%m/%d/%Y')
    start_date_epoch = int(dt(startTime_temp.year, startTime_temp.month, startTime_temp.day, 0, 0).timestamp())*1000

    # check if entries already exist and fill remaining
    last_entry = get_last_enrty(symbol, interval)

    if last_entry != None:
        if last_entry >= start_date_epoch:
            start_date_epoch = last_entry + (interval * 60000)

    current_date = dt.now()
    current_date_epoch = int(dt(current_date.year, current_date.month,
                                               current_date.day, current_date.hour, 0).timestamp()) * 1000
    num_records = (current_date_epoch - start_date_epoch)/(60000*interval)
    print(num_records)
    num_requests = math.ceil(num_records/limit)
    print(num_requests)

    startTime = start_date_epoch # temporary startTime. New assignment after each iteration
    for request in range(num_requests):
        print('Request num:', request, 'of', num_requests)
        printProgressBar(request, num_requests, 'Processing Requests')

        data_df = get_crypto(symbol=symbol, interval=interval, limit=limit, startTime=startTime)
        data_df['open_date_time'] = pd.to_datetime(data_df['open_time'], unit='ms')
        startTime = int(data_df['open_time'].iloc[-1]) + (interval * 60000)   # assign new time based on most recent. Adds next step to selection

        for idx, record in data_df.iterrows():
            table_name = 'crypto_pair'
            Symbol = symbol
            OpenDateTime = record['open_date_time']
            Interval = interval
            OpenTime = record['open_time']
            Open = record['open']
            High = record['high']
            Low = record['low']
            Close = record['close']
            Volume = record['volume']
            CloseTime = record['close_time']
            QuoteAssesVol = record['quote_asset_vol']
            NumTrades = record['num_trades']
            TakerBuyBaseAssetVol = record['taker_buy_base_vol']
            TakerBuyQuoteAssetVol = record['taker_buy_quote_vol']

            cur.execute(
                f"INSERT INTO {table_name} (Symbol, OpenDateTime, Interval, OpenTime, Open, High, Low, Close, Volume, "
                f"CloseTime, QuoteAssesVol, "
                f"NumTrades, TakerBuyBaseAssetVol, TakerBuyQuoteAssetVol)"
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (Symbol, OpenDateTime, Interval, OpenTime, Open, High, Low, Close, Volume, CloseTime, QuoteAssesVol, NumTrades, TakerBuyBaseAssetVol,
                 TakerBuyQuoteAssetVol))

            conn.commit()

    cur.close()
    conn.close()

if __name__ == '__main__':
    load_crypto(interval=5, startTime='9/1/2019')
    load_crypto(interval=15, startTIme='9/1/2019')

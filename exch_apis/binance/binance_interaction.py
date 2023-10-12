from binance.client import Client
import json
import os
import pandas as pd

class binance():
    # class variables
    client = ""
    def __init__(self) -> None:
        # Variable for the location of settings.json
        self.import_filepath = 'settings.json'
        # initialize project settings
        self.connect()


    def connect(self):

        # test the filepath to make sure it exists
        if os.path.exists(self.import_filepath):
            # Open file
            f = open(self.import_filepath  , "r")
            # Get information from the file
            project_settings = json.load(f)
            # Close file
            f.close()
            # return project settings to program
            api_key = project_settings['BinanceKeys']['API_Key']
            api_secret = project_settings['BinanceKeys']['Secret_Key']
            self.client = Client(api_key, api_secret, tld='us')
            return project_settings
        else:
            return ImportError

    # query Binance and retrieve status
    def get_candlestick(self, symbol='ETHBTC'):

        # Query system status

        candles = self.client.get_klines(symbol=symbol, interval=Client.KLINE_INTERVAL_30MINUTE)
        return candles

    def get_historical_klines(self, symbol, interval, start_str):
        print(f'Downloading data for {symbol}. Interval {interval}. Starting from {start_str}')
        klines = self.client.get_historical_klines(symbol, interval, start_str)
        data = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low','close', 'volumne',
                                             'close_time', 'quote_asset_volume', 'number_of_trades',
                                             'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume',
                                             'ignore'])
        data['timestamp'] = pd.to_datetime(data['timestamp'], unit='ms')
        data.set_index('timestamp', inplace=True)
        data['close'] = data['close'].astype(float)
        return data

    def create_test_order(self, symbol, side, type, quantity):
        self.client.create_test_order(symbol=symbol, side=side, type=type, quantity=quantity)
        print(f'{side} signal generated. Placing market {str(side).lower()}.')
import os
import pandas as pd
import time
import sys
import json
import base64
import hashlib
import hmac
import urllib.request
import urllib.parse
import requests
import datetime

# Configure API key (copy/paste from account management)
api_key_public = 'COPY/PASTE API PUBLIC KEY HERE'
api_key_private = 'COPY/PASTE API PRIVATE KEY HERE'

# Configure market/orders/trades
trade_symbol = 'XXBTZUSD'
trade_interval = 1  # OHLC interval in minutes
trade_size = 0.0001  # Trade volume in base currency
trade_leverage = 2

# Initial indicator/trade variables
trade_direction = 0
sma_values = [0.0, 0.0, 0.0]


class client():
    # class variables
    client = ""
    def __init__(self) -> None:
        # Variable for the location of settings.json
        self.import_filepath = r'.../user/credentials.json'
        self.api_url = "https://api.kraken.com"
        # initialize project settings
        #self.connect()
        self.api_key = ''
        self.api_secret = ''

    def set_api_creds(self, cred_path):
        if os.path.exists(cred_path):
            # Open file
            f = open(cred_path, "r")
            # Get information from the file
            project_settings = json.load(f)
            # Close file
            f.close()

            # return project settings to program
            self.api_key = project_settings['Kraken']['API_Key']
            self.api_secret = project_settings['Kraken']['Secret_Key']

    ######################################################################################
    ##### Kraken Specific private connection
    def get_kraken_signature(self, urlpath, data, secret):
        postdata = urllib.parse.urlencode(data)
        encoded = (str(data['nonce']) + postdata).encode()
        message = urlpath.encode() + hashlib.sha256(encoded).digest()

        mac = hmac.new(base64.b64decode(secret), message, hashlib.sha512)
        sigdigest = base64.b64encode(mac.digest())
        return sigdigest.decode()

    def private_request(self, uri_path, data):
        headers = {}
        try:
            headers['API-Key'] = self.api_key
            headers['API-Sign'] = self.get_kraken_signature(uri_path, data, self.api_secret)
            req = requests.post((self.api_url + uri_path), headers=headers, data=data)
            return req
        except:
            print('ERROR')
    #######################################################################################

    #######################################################################################
    ##### Standard functions for 'client' responses
    #######################################################################################
    def get_tradable_asset_pairs(self):
        resp = requests.get('https://api.kraken.com/0/public/AssetPairs?pair=XXBTZUSD,XETHXXBT')
        data = resp.json()
        data_df = pd.DataFrame(data['result'])

        return data_df

    def get_asset_pair_info(self, symbol='ETHUSD'):
        resp = requests.get(f'https://api.kraken.com/0/public/AssetPairs?pair={symbol}')
        data = resp.json()
        symbol_actual = list(data['result'].keys())
        print(symbol_actual[0])
        data = data['result'][symbol_actual[0]]
        return data

    def get_historical_data(self, symbol='ETHUSD', interval=15, since=None):
        """ symbol = Trading pair example (ETHUSD)
            interval = time frame interval in minutes
                       1, 5, 15, 30, 60, 240, 1440, 10080, 21600
            since = return up to 720 OHLC data points since given timestamp
                    format MM/DD/YYYY
            If 'since' is populated then data will be collected from the time specified
            to current date and time.
            The default produces datapoints 720 units from current date time."""

        labels = ['time', 'open', 'high', 'low', 'close', 'vwap', 'volume', 'trades']
        # default if since is None
        if since == None:
            # Kraken API returns up to 720 data points since the given timestamp
            resp = requests.get(f'https://api.kraken.com/0/public/OHLC?pair={symbol}&interval={interval}')
            api_data = resp.json()
            symbol_actual = list(api_data['result'].keys())[0]

            data_df = pd.DataFrame(api_data['result'][symbol_actual], columns=labels)

        else:
            since = datetime.datetime.strptime(since, '%m/%d/%Y')
            since_epoch = int(datetime.datetime(since.year, since.month, since.day, 0, 0).timestamp())
            current_date = datetime.datetime.now()
            current_date_epoch = int(datetime.datetime(current_date.year, current_date.month,
                                                       current_date.day, current_date.hour, 0).timestamp())
            num_records = ((current_date_epoch-since_epoch)/60)/interval
            num_requests = round(num_records/720) # rounded up
            print('Number of expected Records:', num_records)

            data_df = pd.DataFrame()

            for i in range(num_requests):
                resp = requests.get(f'https://api.kraken.com/0/public/OHLC?pair={symbol}&interval={interval}'
                                    f'&since=1696118400')
                api_data = resp.json()
                symbol_actual = list(api_data['result'].keys())[0]

                temp_df = pd.DataFrame(api_data['result'][symbol_actual], columns=labels)
                print(temp_df)
                since_epoch = temp_df['time'].iloc[-1]
                data_df = pd.concat([data_df, temp_df])

        data_df.time = pd.to_datetime(data_df.time, unit='s')
        print(data_df.shape)
        return data_df

    def get_account_balance(self):
        resp = self.private_request('/0/private/Balance', {
                                    'nonce': str(int(1000*time.time()))})
        resp = resp.json()['result']
        return resp

if __name__ == '__main__':
    client = client()
    client.set_api_creds(r'C:\Users\kdenn\PycharmProjects\Crypto_Charts\user\credentials.json')
    print(client.get_historical_data(since='09/10/2023'))
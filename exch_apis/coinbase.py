import requests

class coinbase:

    def __init__(self, key, passphrase):
        self.key = key
        self.passphrase = passphrase


    def get_pairs(self):
        ''' Returns a list of crypto pairs ie. ETH-USD'''
        url = "https://api.exchange.coinbase.com/products"
        response = requests.get(url).json()

        # extracts the pair names
        for i in range(len(response)):
            data = response[i]['id']

        return data

    # Coinbase only allows 300 candles per request
    def get_historic_candles(self, crypto_pair, granularity, start, end):
        ''' Returns a dictionary of candles in the form of
            [timestamp, price_low, price_high, price_open, price_close]'''
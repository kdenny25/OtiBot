from exch_apis.kraken.kraken_client import client

class backtest(object):
    """
        initializes broker api connection and inherits settings
    """

    def __init__(self, client):
        self.client = client
        self.capital = 10000
        self.trade_pair = 'ETHUSD'
        self.taker_fees = []
        self.maker_fees = []


    # set tradeable pair
    def set_tradable_pair(self, symbol):
        self.trade_pair = symbol

        # set fees
        symbol_info = self.client.get_asset_pair_info(symbol)
        self.maker_fees = symbol_info['fees_maker']
        self.taker_fees = symbol_info['fees']
        #print(self.client.get_asset_pair_info(symbol))

    # get historical data
    def get_historical_data(self):
        self.client.get_historical_data()

    # set capital
    def set_capital(self, capital):
        self.capital = capital

    # set historical date range

    # set transaction fees

    # set strategy

    # buy

    # sell

    # run backtest

    # run split window backtesting

if __name__ == '__main__':
    client = client()
    backtest = backtest(client)
    backtest.set_tradable_pair('DOGEUSD')
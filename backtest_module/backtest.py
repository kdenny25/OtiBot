from exch_apis.kraken import client
from utility import local_db
import pandas as pd


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

        self.conn = local_db()
        self.cur = self.conn.cursor()


    # set tradeable pair
    def set_tradable_pair(self, symbol):
        self.trade_pair = symbol

        # set fees
        symbol_info = self.client.get_asset_pair_info(symbol)
        self.maker_fees = symbol_info['fees_maker']
        self.taker_fees = symbol_info['fees']
        #print(self.client.get_asset_pair_info(symbol))

    # get historical data
    def get_historical_data(self, interval, start_date, end_date):
        """
        Retrieves historical data from our database.
        :param:
            interval (int): interval of timeframe to pull from
            start_date (str): open date to start pulling data for
            end_date (str): open date to stop pulling data for
        :return:
            Pandas dataframe of date
        """
        query = (f"SELECT * FROM crypto_pair "
                 f"WHERE symbol = '{self.trade_pair}' "
                 f"AND interval = {interval} "
                 f"AND opendatetime BETWEEN '{start_date}' AND '{end_date}'")
        self.cur.execute(query)
        results = self.cur.fetchall()
        col_names = [desc[0] for desc in self.cur.description]
        results = pd.DataFrame(results, columns=col_names)
        return results
        #self.client.get_historical_data()

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
    print(backtest.get_historical_data('ETHUSD', 15, '7/1/2023', '11/5/2023'))
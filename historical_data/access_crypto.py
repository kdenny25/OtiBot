import psycopg2
import pandas as pd
from utility import local_db
from datetime import datetime as dt

def get_historical_data(trade_pair, interval, start_date, end_date='NOW', BTPY_format=False):
    """
    Pulls data for given trade pair and formats it into a Pandas DataFrame

    :param:
        trade_pair (str): available trading pairs are ETHUSD and BTCUSD

        interval (int): available intervals are 1m, 5m, 15m

        start_date (str): format 'mm/dd/YYYY'

        end_date (optional) (str): format 'mm/dd/YYYY'. If left blank will pull data from
                        start date to current date or most recent date available.
        BTPY_format (optional) (bool): formats data for Backtesting.py library
    :return:
        Pandas Dataframe
    """
    conn = local_db()
    cur = conn.cursor()

    if end_date == 'NOW':
        end_date = dt.now().strftime('%m/%d/%Y')

    query = (f"SELECT * FROM crypto_pair "
             f"WHERE symbol = '{trade_pair}' "
             f"AND interval = {interval} "
             f"AND opendatetime BETWEEN '{start_date}' AND '{end_date}'")
    cur.execute(query)
    results = cur.fetchall()
    col_names = [desc[0] for desc in cur.description]
    data_df = pd.DataFrame(results, columns=col_names)

    if BTPY_format == True:
        data_df['date'] = pd.to_datetime(data_df['opentime'], unit='ms')
        data_df = data_df.set_index('date')
        data_df = data_df[['open', 'high', 'low', 'close', 'volume']]
        data_df.round(5)
        data_df.columns = map(lambda x: str(x).capitalize(), data_df.columns)
        data_df = data_df.astype('float')
        data_df.sort_index(ascending=True, inplace=True)

    return data_df


if __name__ == '__main__':
    print(get_historical_data('ETHUSD', 15, '1/1/2023'))
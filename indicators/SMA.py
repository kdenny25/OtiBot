# simple moving average (SMA)
import pandas as pd

def SMA(pd_series: pd.Series, window_size: int) -> pd.Series:
    """
    Calculate the simple moving average of a Pandas series

    :param:
        pd_series (pandas.Series): Pandas series of values to calculate SMA

        window_size (int): specifies rolling window size.

        kwargs (dict): Pass dictionary of parameter responses
            {'windowSize': 50}
    :return:
        pandas.Series: values are a series of moving averages
    """
    # create Pandas series of SMA values

    return pd.Series(pd_series).rolling(window_size).mean()

if __name__ == "__main__":

    pd.set_option('display.max_columns', None)
    filepath = r"../test_data/test_ohlc.csv"
    test_data = pd.read_csv(filepath)

    window_size = 3

    parameters = {'pd_series':test_data['close'], 'window_size': 3}

    print(SMA(**parameters))
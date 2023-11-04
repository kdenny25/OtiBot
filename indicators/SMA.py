# simple moving average (SMA)
import pandas as pd

def SMA(pd_series, window_size=None):
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
    SMA = pd_series.rolling(window_size).mean()

    return SMA

if __name__ == "__main__":
    arr = [1, 2, 3, 7, 9]
    window_size = 3

    numbers_series = pd.Series(arr)
    parameters = {'pd_series':numbers_series, 'window_size': 3}

    print(SMA(**parameters))
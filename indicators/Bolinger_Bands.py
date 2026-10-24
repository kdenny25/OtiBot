import pandas as pd
def BBANDS(data: pd.DataFrame, n_lookback: int, n_std: int) -> pd.DataFrame:
    """
    Bollinger bands indicator calculated on the typical price (HLC/3).

    :param:
        data (pandas.DataFrame): must contain High, Low and Close columns

        n_lookback (int): rolling window size. Common value 20

        n_std (int): number of standard deviations for the bands. Common value 2
    :return:
        upper, lower (pd.Series): upper and lower bands
    """
    # High, Low, Close mean
    hlc3 = (data.High + data.Low + data.Close) / 3
    mean = hlc3.rolling(n_lookback).mean()
    std = hlc3.rolling(n_lookback).std()
    upper = mean + n_std*std
    lower = mean - n_std*std

    return upper, lower
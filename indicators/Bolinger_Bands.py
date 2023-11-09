import pandas as pd
def BBANDS(data: pd.DataFrame, n_lookback: int, n_std: int) -> pd.DataFrame:
    """
    Bollinger bands indicator
    :param:
        pd_series:
        n_lookback:
        n_std:
    :return:
        upper, lower (pd.Series):
    """
    # High, Low, Close mean
    hlc3 = (data.High + data.Low + data.Close) / 3
    mean = hlc3.rolling(n_lookback).mean()
    std = hlc3.rolling(n_lookback).std()
    upper = mean + n_std*std
    lower = mean - n_std*std
    # df = pd.DataFrame([upper, lower], colums=['upper', 'lower'])

    return upper, lower
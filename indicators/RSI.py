# Relative Strength Index
import pandas as pd

# Relative Strength Index (RSI)
# todo: complete docstring and verify
def RSI(pd_series, window=14, with_wms=True):
    """

    :param
        pd_series (pandas.Series):
        window (int):
        with_wms (bool):
    :return:
    """

    delta = pd_series.diff(1)
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(window=window, min_periods=window).mean()
    avg_loss = loss.rolling(window=window, min_periods=window).mean()

    #Get WMS averages
    if with_wms == True:
        # calculate average Gains
        for i, row in enumerate(avg_gain.iloc[window+1:]):
            avg_gain.iloc[i + window + 1] = \
                (avg_gain.iloc[i + window] *
                 (window - 1) + gain.iloc[i + window + 1])\
                / window

        # calculate average Losses
        for i, row in enumerate(avg_loss.iloc[window+1:]):
            avg_loss.iloc[i + window + 1] = \
                (avg_loss.iloc[i + window] *
                 (window - 1) + loss.iloc[i + window + 1])\
                / window

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    return rsi

if __name__ == '__main__':
    pd.set_option('display.max_columns', None)
    filepath = r"../test_data/test_ohlc.csv"
    test_data = pd.read_csv(filepath)


    parameters = {'pd_series':test_data['close'],
                  'window': 14,
                  'with_wms': True}
    test_data = RSI(**parameters)

    print(test_data)
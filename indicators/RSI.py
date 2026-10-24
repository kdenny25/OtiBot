# Relative Strength Index
import pandas as pd

# Relative Strength Index (RSI)
def RSI(pd_series, window=14, with_wms=True):
    """
    Calculates the Relative Strength Index of a Pandas Series.

    :param
        pd_series (pandas.Series): Pandas series of closing prices

        window (int): Default 14. Number of periods used to average gains
                      and losses

        with_wms (bool): Default True. Uses Wilder's smoothing method (the
                         standard RSI). The first average is a simple mean of
                         the first `window` changes, every later value is
                         (previous_avg * (window - 1) + current) / window.
                         False uses a plain rolling mean (Cutler's RSI).
    :return:
        pandas.Series: RSI values between 0 and 100. The first `window`
                       values are NaN, and periods with no price movement at
                       all (no gains and no losses) are NaN.
    """

    delta = pd_series.diff(1)
    # clip keeps the leading NaN so the first average only uses real changes
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
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
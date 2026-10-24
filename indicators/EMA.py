# Exponential Moving Average
import pandas as pd

def EMA(pd_series, alpha=None, span=None, rounding=False):
    """
    Calculates exponential moving average of a Pandas Series

    :param:
        pd_series (pandas.Series): Pandas series of values to calculate SMA:

        alpha (float): smoothing factor between 0 and 1

        span (float): specify decay in terms of periods. Used instead of
                      alpha when given (alpha = 2 / (span + 1)). One of
                      alpha or span is required.

        rounding (bool): Default False. Crypto shouldn't use rounding while
                         stocks will round to 2
    :return:
        pandas.Series: values are a series of exponential moving averages
    """

    if span is None and alpha is None:
        raise ValueError('EMA requires either alpha or span')

    # pandas does not allow alpha and span together
    if span is None:
        EMA = pd_series.ewm(alpha=alpha, adjust=False).mean()
    else:
        EMA = pd_series.ewm(span=span, adjust=False).mean()

    if rounding == True:
        EMA = round(EMA, 2)

    return EMA

if __name__ == '__main__':
    arr = [1, 2, 3, 7, 9]
    window_size = 3

    numbers_series = pd.Series(arr)
    parameters = {'pd_series':numbers_series, 'alpha': .5}

    print(EMA(**parameters).tail(20))
# Moving Average Convergence/Divergence
import pandas as pd

def MACD(pd_series, slow, fast, smooth):
    """
    Creates Pandas Dataframe containing MACD columns.

    :param:
        pd_series (pd.series): Panda series of closing prices

        slow (int): Common value 26. Must be higher than fast

        fast (int): Common value 12. Must be lower than slow

        smooth (int): Common value 9.

    :return:
        pandas dataframe: 3 columns; macd, macd_signal, macd_hist
    """
    #todo: min_periods adds nan values rather than 0's this will have an impact
    # on results. Double check results.

    # calculate fast EMA of closing price
    fast_ema = pd_series.ewm(span=fast, adjust=False, min_periods=fast).mean()

    # calculate slow EMA of closing price
    slow_ema = pd_series.ewm(span=slow, adjust=False, min_periods=slow).mean()

    macd = fast_ema - slow_ema

    # get EMA of the MACD for the Trigger line
    macd_signal = macd.ewm(span=smooth, adjust=False, min_periods=9).mean()

    # Calculate difference between MACD and Signal for convergence/divergence value
    macd_hist = macd - macd_signal

    # create pandas dataframe with MACD, MACD_SIGNAL and MACD_HIST
    data = {'macd': macd,
            'macd_signal': macd_signal,
            'macd_hist': macd_hist}

    df = pd.concat(data, axis=1)
    return df

if __name__ == '__main__':
    pd.set_option('display.max_columns', None)
    filepath = r"../test_data/test_ohlc.csv"
    test_data = pd.read_csv(filepath)


    parameters = {'pd_series':test_data['close'],
                  'slow': 26,
                  'fast': 12,
                  'smooth': 9}
    test_data = MACD(**parameters)

    print(test_data)
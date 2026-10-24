# Dividend and price metrics calculated from price and dividend history.
# Everything here works on pandas series so it can be tested without
# calling a data provider.
import numpy as np
import pandas as pd


def annual_dividends(dividends: pd.Series, as_of=None) -> pd.Series:
    """
    Sums dividends per calendar year, keeping only complete years.

    :param:
        dividends (pandas.Series): dividend per share indexed by pay date

        as_of (datetime): Default today. The year containing this date is
                          not complete and is dropped.
    :return:
        pandas.Series: total dividend per share indexed by year
    """
    if dividends is None or dividends.empty:
        return pd.Series(dtype=float)
    as_of = pd.Timestamp.now() if as_of is None else pd.Timestamp(as_of)
    yearly = dividends.groupby(dividends.index.year).sum()
    return yearly[yearly.index < as_of.year]


def dividend_cagr(dividends: pd.Series, years: int = 5, as_of=None) -> float:
    """
    Compound annual growth rate of the yearly dividend over the last
    `years` complete years.

    :return:
        float: growth as a fraction, NaN when there isn't enough history or
               the starting dividend is 0
    """
    yearly = annual_dividends(dividends, as_of)
    if len(yearly) < years + 1:
        return np.nan
    start, end = yearly.iloc[-(years + 1)], yearly.iloc[-1]
    if start <= 0 or end <= 0:
        return np.nan
    return (end / start) ** (1 / years) - 1


def consecutive_increase_years(dividends: pd.Series, as_of=None) -> int:
    """
    Number of complete years in a row the yearly dividend went up, counting
    back from the most recent complete year.
    """
    yearly = annual_dividends(dividends, as_of)
    count = 0
    for i in range(len(yearly) - 1, 0, -1):
        if yearly.iloc[i] > yearly.iloc[i - 1]:
            count += 1
        else:
            break
    return count


def payout_frequency(dividends: pd.Series, as_of=None) -> str:
    """
    Monthly, Quarterly, Semi-Annual or Annual based on the number of payments
    in the last complete year.
    """
    if dividends is None or dividends.empty:
        return 'None'
    as_of = pd.Timestamp.now() if as_of is None else pd.Timestamp(as_of)
    last_year = dividends[dividends.index.year == as_of.year - 1]
    count = len(last_year)
    if count >= 11:
        return 'Monthly'
    if count >= 4:
        return 'Quarterly'
    if count >= 2:
        return 'Semi-Annual'
    if count == 1:
        return 'Annual'
    return 'None'


def annualized_return(prices: pd.Series, years: float) -> float:
    """
    Annualized growth of a price series over the last `years` years. Use
    adjusted close prices for total return (price plus reinvested
    dividends) or plain close prices for price growth only.

    :return:
        float: annualized return as a fraction, NaN without enough history
    """
    prices = prices.dropna()
    if prices.empty:
        return np.nan
    start_date = prices.index[-1] - pd.DateOffset(years=years)
    # allow a few days of slack for weekends and holidays
    if prices.index[0] > start_date + pd.Timedelta(days=7):
        return np.nan
    start = prices[prices.index >= start_date].iloc[0]
    return (prices.iloc[-1] / start) ** (1 / years) - 1


def annualized_volatility(prices: pd.Series, periods_per_year: int = 252) -> float:
    """ Annualized standard deviation of daily returns. """
    returns = prices.dropna().pct_change().dropna()
    if len(returns) < 2:
        return np.nan
    return returns.std() * np.sqrt(periods_per_year)


def max_drawdown(prices: pd.Series) -> float:
    """ Largest drop from a running peak, as a negative fraction. """
    prices = prices.dropna()
    if prices.empty:
        return np.nan
    return (prices / prices.cummax() - 1).min()

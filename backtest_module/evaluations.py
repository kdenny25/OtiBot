# backtest result scoring and evaluations.
import numpy as np
import pandas as pd


def total_return(equity: pd.Series) -> float:
    """
    Percent return from the first to last value of the equity curve.

    :param:
        equity (pandas.Series): account value at each period
    :return:
        float: return as a fraction, 0.1 is 10%
    """
    return equity.iloc[-1] / equity.iloc[0] - 1


def max_drawdown(equity: pd.Series) -> float:
    """
    Largest drop from a running peak of the equity curve.

    :param:
        equity (pandas.Series): account value at each period
    :return:
        float: drawdown as a negative fraction, -0.25 is a 25% drop
    """
    running_peak = equity.cummax()
    return (equity / running_peak - 1).min()


def sharpe_ratio(equity: pd.Series, periods_per_year: int = 365 * 96) -> float:
    """
    Annualized Sharpe ratio of period returns, assuming a 0% risk free rate.

    :param:
        equity (pandas.Series): account value at each period

        periods_per_year (int): Default is 15 minute candles traded 24/7
    :return:
        float: Sharpe ratio, NaN if returns never change
    """
    returns = equity.pct_change().dropna()
    std = returns.std()
    if len(returns) < 2 or std == 0:
        return np.nan
    return returns.mean() / std * np.sqrt(periods_per_year)


def trade_stats(trades: pd.DataFrame) -> dict:
    """
    Scores closed trades.

    :param:
        trades (pandas.DataFrame): one row per round trip with a pnl column
    :return:
        dict: num_trades, win_rate, profit_factor, avg_pnl
    """
    if trades.empty:
        return {'num_trades': 0, 'win_rate': np.nan,
                'profit_factor': np.nan, 'avg_pnl': np.nan}

    wins = trades.loc[trades['pnl'] > 0, 'pnl']
    losses = trades.loc[trades['pnl'] < 0, 'pnl']
    profit_factor = wins.sum() / -losses.sum() if not losses.empty else np.inf
    return {'num_trades': len(trades),
            'win_rate': len(wins) / len(trades),
            'profit_factor': profit_factor,
            'avg_pnl': trades['pnl'].mean()}


def evaluate(equity: pd.Series, trades: pd.DataFrame, periods_per_year: int = 365 * 96) -> dict:
    """
    Combines all scores for a backtest run.

    :return:
        dict: final_equity, total_return, max_drawdown, sharpe and trade stats
    """
    stats = {'final_equity': equity.iloc[-1],
             'total_return': total_return(equity),
             'max_drawdown': max_drawdown(equity),
             'sharpe': sharpe_ratio(equity, periods_per_year)}
    stats.update(trade_stats(trades))
    return stats

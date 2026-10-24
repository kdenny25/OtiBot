import numpy as np
import pandas as pd
import pytest

from backtest_module import backtest, evaluations


def candles(prices):
    prices = np.asarray(prices, dtype=float)
    return pd.DataFrame({'open': prices, 'high': prices, 'low': prices,
                         'close': prices, 'volume': 1.0})


def signal_at(buy_idx, sell_idx):
    def strategy(df):
        buy = pd.Series(False, index=df.index)
        sell = pd.Series(False, index=df.index)
        buy.iloc[list(buy_idx)] = True
        sell.iloc[list(sell_idx)] = True
        return buy, sell
    return strategy


def test_fills_at_next_open_and_charges_fees():
    data = candles([10, 10, 20, 20, 40])
    data.loc[2, 'open'] = 12   # signal on candle 1 fills at candle 2's open
    data.loc[4, 'open'] = 30   # signal on candle 3 fills at candle 4's open

    bt = backtest(capital=1000)
    bt.set_fees(0.01)
    bt.set_data(data)
    bt.set_strategy(signal_at([1], [3]))
    result = bt.run()

    units = 1000 * 0.99 / 12
    final = units * 30 * 0.99
    trade = result['trades'].iloc[0]
    assert trade['entry_price'] == 12 and trade['exit_price'] == 30
    assert trade['pnl'] == pytest.approx(final - 1000)
    assert result['stats']['final_equity'] == pytest.approx(final)
    assert result['stats']['num_trades'] == 1
    assert result['equity'].iloc[:2].tolist() == [1000, 1000]


def test_open_position_closed_at_end():
    bt = backtest(capital=100)
    bt.set_data(candles([1, 1, 2, 4]))
    bt.set_strategy(signal_at([0], []))
    result = bt.run()
    assert result['stats']['final_equity'] == pytest.approx(400)
    assert len(result['trades']) == 1


def test_no_signals_keeps_capital():
    bt = backtest(capital=500)
    bt.set_data(candles([1, 2, 3]))
    bt.set_strategy(signal_at([], []))
    result = bt.run()
    assert result['equity'].eq(500).all()
    assert result['stats']['num_trades'] == 0


def test_run_requires_strategy():
    bt = backtest()
    bt.set_data(candles([1, 2]))
    with pytest.raises(ValueError):
        bt.run()


def test_split_window(ohlc):
    from indicators import SMA

    def sma_cross(df):
        fast, slow = SMA(df['close'], 5), SMA(df['close'], 20)
        return fast > slow, fast < slow

    bt = backtest()
    bt.set_fees(0.0026)
    bt.set_data(ohlc)
    bt.set_strategy(sma_cross)
    windows = bt.run_split_window(3)
    assert len(windows) == 3
    assert windows['start_index'].tolist() == [0, 499, 998]
    assert windows['end_index'].iloc[-1] == len(ohlc) - 1


def test_evaluations():
    equity = pd.Series([100, 120, 90, 135])
    assert evaluations.total_return(equity) == pytest.approx(0.35)
    assert evaluations.max_drawdown(equity) == pytest.approx(-0.25)
    assert np.isnan(evaluations.sharpe_ratio(pd.Series([1.0, 1.0, 1.0])))

    trades = pd.DataFrame({'pnl': [10.0, -5.0, 15.0]})
    stats = evaluations.trade_stats(trades)
    assert stats['win_rate'] == pytest.approx(2 / 3)
    assert stats['profit_factor'] == pytest.approx(5)
    assert evaluations.trade_stats(pd.DataFrame({'pnl': []}))['num_trades'] == 0

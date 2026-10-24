# Compares each indicator against a plain python reference implementation
# of the textbook formula.
import math

import numpy as np
import pandas as pd
import pytest

from indicators import SMA, EMA, MACD, RSI, BBANDS


def ref_ema(values, alpha):
    out = []
    for v in values:
        out.append(v if not out else alpha * v + (1 - alpha) * out[-1])
    return out


def ref_wilder_rsi(values, window):
    changes = [values[i] - values[i - 1] for i in range(1, len(values))]
    gains = [max(c, 0) for c in changes]
    losses = [max(-c, 0) for c in changes]
    rsi = [math.nan] * len(values)
    avg_gain = sum(gains[:window]) / window
    avg_loss = sum(losses[:window]) / window
    for i in range(window, len(values)):
        if i > window:
            avg_gain = (avg_gain * (window - 1) + gains[i - 1]) / window
            avg_loss = (avg_loss * (window - 1) + losses[i - 1]) / window
        if avg_loss == 0:
            rsi[i] = math.nan if avg_gain == 0 else 100.0
        else:
            rsi[i] = 100 - 100 / (1 + avg_gain / avg_loss)
    return rsi


def test_sma_matches_manual_mean(close):
    result = SMA(close, 3)
    assert result.iloc[:2].isna().all()
    for i in range(2, len(close)):
        assert result.iloc[i] == pytest.approx(close.iloc[i - 2:i + 1].mean())


def test_ema_alpha_matches_reference(close):
    result = EMA(close, alpha=0.5)
    np.testing.assert_allclose(result, ref_ema(close.tolist(), 0.5))


def test_ema_span_uses_span_only(close):
    # passing span used to raise because alpha was also passed to pandas
    result = EMA(close, span=9)
    np.testing.assert_allclose(result, ref_ema(close.tolist(), 2 / 10))


def test_ema_rounding():
    result = EMA(pd.Series([1.0, 2.0, 3.0]), alpha=1 / 3, rounding=True)
    assert result.tolist() == [1.0, 1.33, 1.89]


def test_ema_requires_alpha_or_span(close):
    with pytest.raises(ValueError):
        EMA(close)


@pytest.mark.parametrize('with_wms', [True, False])
def test_rsi_warmup_is_nan(with_wms):
    # the first value has no price change, so the first full window ends at 14
    prices = pd.Series([10.0, 11.0, 10.5, 12.0, 11.0] * 6)
    result = RSI(prices, window=14, with_wms=with_wms)
    assert result.iloc[:14].isna().all()
    assert result.iloc[14:].notna().all()


def test_rsi_wilder_matches_reference(close):
    result = RSI(close, window=14, with_wms=True)
    expected = ref_wilder_rsi(close.tolist(), 14)
    np.testing.assert_allclose(result, expected, equal_nan=True)


def test_rsi_simple_matches_rolling_reference(close):
    window = 14
    values = close.tolist()
    result = RSI(close, window=window, with_wms=False)
    for i in range(window, len(values), 97):
        changes = [values[j] - values[j - 1] for j in range(i - window + 1, i + 1)]
        gain = sum(c for c in changes if c > 0) / window
        loss = sum(-c for c in changes if c < 0) / window
        if loss == 0:
            continue
        assert result.iloc[i] == pytest.approx(100 - 100 / (1 + gain / loss))


def test_rsi_bounds(close):
    result = RSI(close).dropna()
    assert ((result >= 0) & (result <= 100)).all()


def test_rsi_extremes():
    up = pd.Series(np.arange(1.0, 31.0))
    down = pd.Series(np.arange(30.0, 0.0, -1))
    assert RSI(up).dropna().eq(100).all()
    assert RSI(down).dropna().eq(0).all()


def test_macd_matches_reference(close):
    slow, fast, smooth = 26, 12, 9
    result = MACD(close, slow, fast, smooth)
    values = close.tolist()
    macd = np.array(ref_ema(values, 2 / (fast + 1))) - np.array(ref_ema(values, 2 / (slow + 1)))
    # signal starts once macd is valid
    signal = [math.nan] * (slow - 1) + ref_ema(macd[slow - 1:].tolist(), 2 / (smooth + 1))
    signal = np.array(signal)

    assert result['macd'].iloc[:slow - 1].isna().all()
    np.testing.assert_allclose(result['macd'].iloc[slow - 1:], macd[slow - 1:])

    first_signal = slow + smooth - 2
    assert result['macd_signal'].iloc[:first_signal].isna().all()
    np.testing.assert_allclose(result['macd_signal'].iloc[first_signal:], signal[first_signal:])
    np.testing.assert_allclose(result['macd_hist'].iloc[first_signal:],
                               macd[first_signal:] - signal[first_signal:])


def test_macd_signal_warmup_follows_smooth(close):
    result = MACD(close, 26, 12, 5)
    first_signal = 26 + 5 - 2
    assert result['macd_signal'].iloc[:first_signal].isna().all()
    assert result['macd_signal'].iloc[first_signal:].notna().all()


def test_bbands(ohlc):
    data = ohlc.rename(columns=str.capitalize)
    upper, lower = BBANDS(data, 20, 2)
    hlc3 = (data.High + data.Low + data.Close) / 3
    i = 500
    window = hlc3.iloc[i - 19:i + 1]
    assert upper.iloc[i] == pytest.approx(window.mean() + 2 * window.std())
    assert lower.iloc[i] == pytest.approx(window.mean() - 2 * window.std())
    assert (upper.dropna() >= lower.dropna()).all()

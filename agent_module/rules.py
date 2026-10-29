# Entry and exit rules shared by the live agents and the agent backtest, so a
# backtest tests exactly what the agents trade.
import numpy as np
import pandas as pd

PASS, RED, LATE, FADED = 'pass', 'red', 'late', 'faded'


def spike_signals(candles, config):
    """
    Scores every candle as a possible entry, using only candles up to it.

    :param:
        candles (pandas.DataFrame): closed candles with open, close and volume
    :return:
        pandas.DataFrame: spike (volume / median of the lookback before the
                          spike candle), move (spike candle gain) and signal:
                          None, PASS, RED (spike closed down), LATE (already
                          up more than max_entry_move) or FADED (the candle
                          after the spike gave back half of it)
    """
    volume = candles['volume'].astype(float)
    baseline = volume.shift(1).rolling(config.spike_lookback).median()
    spike = (volume / baseline.where(baseline > 0)).fillna(0.0)

    # with confirm_spike the spike is the candle before the last one
    lag = 1 if config.confirm_spike else 0
    spike = spike.shift(lag, fill_value=0.0)
    s_open = candles['open'].shift(lag)
    s_close = candles['close'].shift(lag)
    move = s_close / s_open - 1

    signal = np.full(len(candles), None, dtype=object)
    hot = (spike >= config.min_spike).to_numpy()
    signal[hot] = PASS
    if config.confirm_spike:
        faded = (candles['close'] < (s_open + s_close) / 2).to_numpy()
        signal[hot & faded] = FADED
    if config.max_entry_move:
        signal[hot & (move > config.max_entry_move).to_numpy()] = LATE
    signal[hot & (s_close <= s_open).to_numpy()] = RED
    return pd.DataFrame({'spike': spike.to_numpy(), 'move': move.to_numpy(), 'signal': signal},
                        index=candles.index)


def describe(row, config):
    """ The reason logged for a scored candle. """
    spike = f'spike {row["spike"]:.1f}x'
    return {PASS: spike + (' and held' if config.confirm_spike else ''),
            RED: f'{spike} on a red candle',
            LATE: f'{spike} but already up {row["move"]:.1%}, too late',
            FADED: f'{spike} then gave half of it back'}[row['signal']]


def market_ok(btc_price, btc_day_open):
    """ True when BTC is at or above today's open, or when either is unknown. """
    return not btc_price or not btc_day_open or btc_price >= btc_day_open


def round_trip_cost(config, entry_fee):
    """ Fees and slippage of getting in at entry_fee and out with a market order. """
    return entry_fee + config.taker_fee + config.slippage


def trail_level(pos, config):
    """
    :return:
        float: price where the trailing stop closes the trade, or None while it is off
    """
    entry, peak = pos['entry_price'], pos['peak']
    if peak / entry - 1 < config.trail_trigger:
        return None
    level = peak * (1 - config.trail_pct)
    if config.trail_covers_costs and \
            level < entry * (1 + round_trip_cost(config, pos.get('fee_rate', config.taker_fee))):
        return None
    return level


def exit_reason(pos, bid, now_ts, config):
    """
    :param:
        pos (dict): entry_price, entry_ts, peak (highest bid since entry) and
                    fee_rate (fee paid to get in)
    :return:
        str: why to close at this bid, or None to hold
    """
    change = bid / pos['entry_price'] - 1
    if change <= -config.stop_loss:
        return 'stop loss'
    if change >= config.take_profit:
        return 'take profit'
    level = trail_level(pos, config)
    if level is not None and bid <= level:
        return 'trailing stop'
    held = now_ts - pos['entry_ts']
    if config.stale_minutes and held >= config.stale_minutes * 60 and change < config.stale_move:
        return 'went nowhere'
    if held >= config.max_hold_minutes * 60:
        return 'time limit'
    return None

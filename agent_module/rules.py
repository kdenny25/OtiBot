# Entry and exit rules shared by the live agents and the agent backtest, so a
# backtest tests exactly what the agents trade. Positions have a side: 1 is
# long (bought, profits when price rises), -1 is short (sold first, profits
# when price falls).
import numpy as np
import pandas as pd

PASS, SHORT, RED, LATE, FADED = 'pass', 'short', 'red', 'late', 'faded'
SIDES = {PASS: 1, SHORT: -1}


def spike_signals(candles, config):
    """
    Scores every candle as a possible entry, using only candles up to it.

    :param:
        candles (pandas.DataFrame): closed candles with open, close and volume
    :return:
        pandas.DataFrame: spike (volume / median of the lookback before the
                          spike candle), move (spike candle change) and signal:
                          None, PASS (buy a green spike), SHORT (short a red
                          spike, with short_spikes on), RED (red spike with
                          shorts off), LATE (already moved more than
                          max_entry_move) or FADED (the candle after the spike
                          gave back half of it)
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

    hot = (spike >= config.min_spike).to_numpy()
    green = (s_close > s_open).to_numpy()
    red = (s_close < s_open).to_numpy()
    signal = np.full(len(candles), None, dtype=object)
    signal[hot] = RED
    signal[hot & green] = PASS
    if config.short_spikes:
        signal[hot & red] = SHORT
    trade = hot & (green | (red & config.short_spikes))
    if config.confirm_spike:
        mid = ((s_open + s_close) / 2).to_numpy()
        close = candles['close'].to_numpy()
        signal[trade & np.where(green, close < mid, close > mid)] = FADED
    if config.max_entry_move:
        signal[trade & (move.abs() > config.max_entry_move).to_numpy()] = LATE
    return pd.DataFrame({'spike': spike.to_numpy(), 'move': move.to_numpy(), 'signal': signal},
                        index=candles.index)


def describe(row, config):
    """ The reason logged for a scored candle. """
    spike = f'spike {row["spike"]:.1f}x'
    held = ' and held' if config.confirm_spike else ''
    direction = 'up' if row['move'] > 0 else 'down'
    return {PASS: spike + held,
            SHORT: f'{spike} on a red candle{held}, short',
            RED: f'{spike} on a red candle',
            LATE: f'{spike} but already {direction} {abs(row["move"]):.1%}, too late',
            FADED: f'{spike} then gave half of it back'}[row['signal']]


def market_ok(btc_price, btc_day_open, side=1):
    """
    With the market filter on, longs need BTC at or above today's open and
    shorts need it below. True when either price is unknown.
    """
    if not btc_price or not btc_day_open:
        return True
    return btc_price >= btc_day_open if side == 1 else btc_price < btc_day_open


def round_trip_cost(config, entry_fee, side=1):
    """ Fees and slippage of getting in at entry_fee and out with a market order. """
    cost = entry_fee + config.taker_fee + config.slippage
    return cost + 2 * config.margin_fee if side == -1 else cost


def trail_level(pos, config):
    """
    :param:
        pos (dict): peak is the best price since entry, the highest for a
                    long and the lowest for a short
    :return:
        float: price where the trailing stop closes the trade, or None while it is off
    """
    side = pos.get('side', 1)
    entry, peak = pos['entry_price'], pos['peak']
    if side * (peak / entry - 1) < config.trail_trigger:
        return None
    level = peak * (1 - side * config.trail_pct)
    if config.trail_covers_costs:
        cost = round_trip_cost(config, pos.get('fee_rate', config.taker_fee), side)
        if side * (level / entry - 1) < cost:
            return None
    return level


def exit_reason(pos, price, now_ts, config):
    """
    :param:
        pos (dict): entry_price, entry_ts, side, peak (best price since
                    entry) and fee_rate (fee paid to get in)
        price (float): what closing would trade at: the bid for a long,
                       the ask for a short
    :return:
        str: why to close at this price, or None to hold
    """
    side = pos.get('side', 1)
    change = side * (price / pos['entry_price'] - 1)
    if change <= -config.stop_loss:
        return 'stop loss'
    if change >= config.take_profit:
        return 'take profit'
    level = trail_level(pos, config)
    if level is not None and side * (price - level) <= 0:
        return 'trailing stop'
    held = now_ts - pos['entry_ts']
    if config.stale_minutes and held >= config.stale_minutes * 60 and change < config.stale_move:
        return 'went nowhere'
    if held >= config.max_hold_minutes * 60:
        return 'time limit'
    return None


def margin_cost(config, value, held_seconds):
    """ Kraken margin fees on a short: one to open, then one per 4 hours open. """
    return value * config.margin_fee * (1 + int(max(held_seconds, 0) // (4 * 3600)))

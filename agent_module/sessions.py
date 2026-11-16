# US stock market hours. The NYSE and Nasdaq trade 9:30 to 4:00 New York
# time on weekdays, except the holidays below, and close at 1:00 on a few
# days around Thanksgiving, July 4th and Christmas. Crypto never closes.
#
# Times elsewhere in the agents are UTC; this converts to New York time so
# daylight saving is handled. Add each new year's dates from
# https://www.nyse.com/markets/hours-calendars
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

NEW_YORK = ZoneInfo('America/New_York')
OPEN, CLOSE, EARLY_CLOSE = time(9, 30), time(16, 0), time(13, 0)

HOLIDAYS = {
    # 2025
    date(2025, 1, 1), date(2025, 1, 9), date(2025, 1, 20), date(2025, 2, 17), date(2025, 4, 18),
    date(2025, 5, 26), date(2025, 6, 19), date(2025, 7, 4), date(2025, 9, 1), date(2025, 11, 27),
    date(2025, 12, 25),
    # 2026
    date(2026, 1, 1), date(2026, 1, 19), date(2026, 2, 16), date(2026, 4, 3), date(2026, 5, 25),
    date(2026, 6, 19), date(2026, 7, 3), date(2026, 9, 7), date(2026, 11, 26), date(2026, 12, 25),
    # 2027
    date(2027, 1, 1), date(2027, 1, 18), date(2027, 2, 15), date(2027, 3, 26), date(2027, 5, 31),
    date(2027, 6, 18), date(2027, 7, 5), date(2027, 9, 6), date(2027, 11, 25), date(2027, 12, 24),
}
EARLY_CLOSES = {date(2025, 7, 3), date(2025, 11, 28), date(2025, 12, 24),
                date(2026, 11, 27), date(2026, 12, 24), date(2027, 11, 26)}


def _utc(ts):
    """ Epoch seconds, or a naive (UTC) or aware datetime, as an aware UTC datetime. """
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(ts, timezone.utc)
    if isinstance(ts, pd.Timestamp):
        ts = ts.to_pydatetime()
    return ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts.astimezone(timezone.utc)


def session(day):
    """
    :param:
        day (date): a New York calendar day
    :return:
        (datetime, datetime): that day's open and close in UTC, or None when closed
    """
    if day.weekday() >= 5 or day in HOLIDAYS:
        return None
    close = EARLY_CLOSE if day in EARLY_CLOSES else CLOSE
    return (datetime.combine(day, OPEN, NEW_YORK).astimezone(timezone.utc),
            datetime.combine(day, close, NEW_YORK).astimezone(timezone.utc))


def status(ts):
    """
    :return:
        dict: open (bool), minutes_open (since the bell, None while closed),
              minutes_left (until the close, None while closed) and
              next_open (UTC datetime of the next opening bell)
    """
    now = _utc(ts)
    day = now.astimezone(NEW_YORK).date()
    today = session(day)
    if today and today[0] <= now < today[1]:
        return {'open': True, 'minutes_open': (now - today[0]).total_seconds() / 60,
                'minutes_left': (today[1] - now).total_seconds() / 60, 'next_open': None}
    nxt = day if today and now < today[0] else day + timedelta(days=1)
    while session(nxt) is None:
        nxt += timedelta(days=1)
    return {'open': False, 'minutes_open': None, 'minutes_left': None, 'next_open': session(nxt)[0]}


def describe_next_open(next_open):
    """ 'Mon 9:30 AM ET' """
    local = next_open.astimezone(NEW_YORK)
    return local.strftime('%a %-I:%M %p ET')


def candle_flags(times, interval, skip_open_minutes=0):
    """
    Session flags for every candle in a backtest, from its start time.

    :param:
        times (pandas.DatetimeIndex): naive UTC candle start times
        interval (int): candle size in minutes
    :return:
        dict of numpy arrays:
            in_session: the candle trades during regular hours
            can_enter: in session, past skip_open_minutes and not the day's last candle
            last: the last candle of its session, where flat_at_close closes trades
            day: the New York trading day, for "today's open"
    """
    local = times.tz_localize('UTC').tz_convert(NEW_YORK)
    days = local.normalize().tz_localize(None).date
    opens, closes = {}, {}
    for d in set(days):
        s = session(d)
        if s:
            opens[d], closes[d] = pd.Timestamp(s[0]).tz_localize(None), pd.Timestamp(s[1]).tz_localize(None)
    open_t = pd.DatetimeIndex([opens.get(d, pd.NaT) for d in days])
    close_t = pd.DatetimeIndex([closes.get(d, pd.NaT) for d in days])
    step = pd.Timedelta(minutes=interval)
    in_session = np.asarray((times >= open_t) & (times < close_t))
    # an hour candle from 3:30 is the last one even though it runs past 4:00
    last = np.asarray(in_session & (times + step >= close_t))
    # a gap before the close (a candle with no data) still ends the day on the last candle there is
    idx = np.arange(len(times))
    latest = pd.Series(np.where(in_session, idx, -1)).groupby(np.asarray(days)).transform('max').to_numpy()
    last = last | (in_session & (idx == latest))
    minutes_in = np.asarray((times - open_t) / pd.Timedelta(minutes=1))
    can_enter = in_session & ~last & (np.nan_to_num(minutes_in, nan=-1) >= skip_open_minutes)
    return {'in_session': in_session, 'can_enter': can_enter, 'last': last, 'day': np.asarray(days)}

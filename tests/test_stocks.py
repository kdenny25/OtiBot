import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest
from flask import Flask
from flask_socketio import SocketIO

from agent_module import AgentConfig, Pipeline, sessions, stock_history
from agent_module.config import VENUES
from agent_module.rules import order_fee
from agent_module.simulate import simulate
from agent_module.stock_market import YahooStockMarket
from agent_module.store import Store


def ts(text):
    """ epoch seconds of a UTC time """
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc).timestamp()


# market hours

def test_session_hours_follow_new_york_time():
    # Monday 16 Nov 2026 is standard time, the open is 14:30 UTC
    assert sessions.status(ts('2026-11-16T14:29:00'))['open'] is False
    s = sessions.status(ts('2026-11-16T14:45:00'))
    assert s['open'] and s['minutes_open'] == 15 and s['minutes_left'] == 375
    # summer time, the open is 13:30 UTC
    assert sessions.status(ts('2026-07-15T13:35:00'))['open'] is True
    assert sessions.status(ts('2026-07-15T20:00:00'))['open'] is False


def test_weekends_holidays_and_early_closes():
    saturday = sessions.status(ts('2026-11-14T15:00:00'))
    assert not saturday['open'] and saturday['next_open'].isoformat() == '2026-11-16T14:30:00+00:00'
    assert sessions.describe_next_open(saturday['next_open']) == 'Mon 9:30 AM ET'
    # Thanksgiving, then the 1 PM close the day after
    assert not sessions.status(ts('2026-11-26T16:00:00'))['open']
    assert sessions.status(ts('2026-11-27T17:50:00'))['minutes_left'] == 10
    assert not sessions.status(ts('2026-11-27T18:30:00'))['open']


def stock_day(day='2026-11-16', price=100.0, volume=1e6):
    """ one regular session of 5 minute candles in UTC, 9:30 to 3:55 New York time """
    times = pd.date_range(f'{day} 14:30', f'{day} 20:55', freq='5min')
    n = len(times)
    return pd.DataFrame({'time': times, 'open': [price] * n, 'high': [price * 1.001] * n,
                         'low': [price * 0.999] * n, 'close': [price] * n, 'volume': [volume] * n})


def test_candle_flags():
    df = pd.concat([stock_day('2026-11-13'), stock_day('2026-11-16')])
    f = sessions.candle_flags(pd.DatetimeIndex(df['time']), 5, skip_open_minutes=15)
    assert f['in_session'].all()
    assert list(df['time'][f['last']].astype(str)) == ['2026-11-13 20:55:00', '2026-11-16 20:55:00']
    enter = df['time'][f['can_enter']]
    assert str(enter.iloc[0]) == '2026-11-13 14:45:00' and str(enter.iloc[-1]) == '2026-11-16 20:50:00'


# fees

def test_stock_fees():
    pro = AgentConfig.for_market('stocks', venue='ibkr_pro')
    # 100 shares of a $10 stock: $0.50 at $0.005 a share, so the $1 minimum
    assert order_fee(pro, 1000, 0.0, units=100) == pytest.approx(1.0)
    # 1000 shares of a $1 stock: $5, capped at 1% of $1000 = $10, so $5
    assert order_fee(pro, 1000, 0.0, units=1000) == pytest.approx(5.0)
    # 5000 shares at $0.10: $25, capped at 1% = $5
    assert order_fee(pro, 500, 0.0, units=5000) == pytest.approx(5.0)
    alpaca = AgentConfig.for_market('stocks')
    assert order_fee(alpaca, 10000, 0.0, units=100) == 0.0
    # selling pays the SEC fee on value and FINRA's per share fee
    assert order_fee(alpaca, 10000, 0.0, units=100, sell=True) == pytest.approx(10000 * 0.0000206 + 100 * 0.000166)
    # FINRA's fee stops at $8.30 an order
    assert order_fee(alpaca, 0, 0.0, units=1e6, sell=True) == pytest.approx(8.30)


def test_crypto_fees_are_unchanged():
    c = AgentConfig()
    assert order_fee(c, 100, c.taker_fee, units=1, sell=True) == pytest.approx(0.4)


def test_venues_belong_to_one_market():
    stocks = AgentConfig.for_market('stocks')
    assert stocks.venue == 'alpaca_stocks' and stocks.taker_fee == 0 and stocks.flat_at_close
    with pytest.raises(ValueError):
        stocks.update({'venue': 'kraken'})
    with pytest.raises(ValueError):
        AgentConfig().update({'venue': 'schwab'})
    # the market itself can't be switched by a settings form
    assert stocks.update({'market': 'crypto'}) == {}
    assert all(v['market'] in ('crypto', 'stocks') for v in VENUES.values())


# backtest

def spike(df, at, move=0.004, volume=8e6):
    """ a green volume spike on candle at, then a slow drift up that never reaches take profit """
    df = df.reset_index(drop=True).copy()
    base = df['open'][at]
    k = np.arange(len(df)) - at
    close = np.where(k < 0, base, base * (1 + move + 0.0002 * np.maximum(k, 0)))
    df['close'] = close
    df['open'] = np.where(k <= 0, base, np.roll(close, 1))
    df['high'] = np.maximum(df['open'], df['close']) * 1.0005
    df['low'] = np.minimum(df['open'], df['close']) * 0.9995
    df.loc[at, 'volume'] = volume
    return df


def test_stock_trades_close_before_the_bell():
    df = spike(stock_day(), 60)
    config = AgentConfig.for_market('stocks', take_profit=0.5, stop_loss=0.2, trail_trigger=0.5,
                                    max_hold_minutes=10000, max_position_pct=0.5)
    r = simulate({'NVDA': df}, config, spread=0.0004)
    assert r['stats']['trades'] == 1
    trade = r['trades'][0]
    assert trade['reason'] == 'market close' and trade['exit_time'] == '2026-11-16T20:55:00'
    held = simulate({'NVDA': df}, AgentConfig.for_market('stocks', take_profit=0.5, stop_loss=0.2, trail_trigger=0.5,
                                                         max_hold_minutes=10000, flat_at_close=False), spread=0.0004)
    assert held['trades'][0]['reason'] == 'end of test'


def test_stock_entries_skip_the_opening_bell():
    # the day before gives the volume baseline, then a spike on the 9:35 candle
    df = spike(pd.concat([stock_day('2026-11-13'), stock_day()]), 79)
    config = AgentConfig.for_market('stocks', take_profit=0.5)
    assert simulate({'NVDA': df}, config)['stats']['trades'] == 0
    assert simulate({'NVDA': df}, AgentConfig.for_market('stocks', take_profit=0.5,
                                                         skip_open_minutes=0))['stats']['trades'] == 1


def test_stock_market_filter_follows_spy():
    df = spike(stock_day(), 60)
    spy = stock_day(price=500.0)
    spy['close'] = np.linspace(500, 490, len(spy))      # SPY falls all day
    config = AgentConfig.for_market('stocks', market_filter=True)
    assert simulate({'NVDA': df, 'SPY': spy}, config)['stats']['trades'] == 0
    spy['close'] = np.linspace(500, 510, len(spy))
    assert simulate({'NVDA': df, 'SPY': spy}, config)['stats']['trades'] == 1


# live stock agents

class FakeStocks:
    def __init__(self):
        self.prices = {'SPY': 500.0, 'NVDA': 100.0}
        self.spiking = set()
        self.calls = 0

    def usd_pairs(self):
        return {s: s for s in self.prices}

    def tickers(self, pairs):
        self.calls += 1
        return {p: {'bid': self.prices[p] * 0.9998, 'ask': self.prices[p] * 1.0002, 'last': self.prices[p],
                    'open': self.prices[p], 'quote_volume': 5e9} for p in pairs}

    def candles(self, pair, interval):
        df = stock_day().iloc[:40].reset_index(drop=True)
        if pair in self.spiking:
            df.loc[39, ['close', 'volume']] = [101.0, 9e6]
        return df


@pytest.fixture
def stock_pipeline():
    return Pipeline(FakeStocks(), Store(':memory:'), AgentConfig.for_market('stocks'))


def test_closed_market_waits_without_scanning(stock_pipeline):
    p = stock_pipeline
    p.run_cycle(now='2026-11-14T15:00:00Z', now_ts=ts('2026-11-14T15:00:00'))
    p.run_cycle(now='2026-11-14T15:01:00Z', now_ts=ts('2026-11-14T15:01:00'))
    assert p.market.calls == 0
    waits = [e for e in p.store.recent_events(10) if e['action'] == 'WAIT']
    assert len(waits) == 1 and 'opens Mon 9:30 AM ET' in waits[0]['detail']


def test_stock_agents_trade_and_close_at_the_bell(stock_pipeline):
    p = stock_pipeline
    p.market.spiking = {'NVDA'}
    # 9:35, still inside the 15 opening minutes
    p.run_cycle(now='a', now_ts=ts('2026-11-16T14:35:00'))
    assert not p.broker.positions
    p.run_cycle(now='b', now_ts=ts('2026-11-16T17:00:00'))
    assert 'NVDA' in p.broker.positions
    p.market.spiking = set()
    # 3:57, the last candle: everything closes
    p.run_cycle(now='c', now_ts=ts('2026-11-16T20:57:00'))
    assert not p.broker.positions
    assert p.store.trades()[0]['reason'] == 'market close'
    state = p.state()
    assert state['market'] == 'stocks' and 'session' in state


def test_yahoo_market_uses_last_trade_and_drops_forming_candle():
    now = pd.Timestamp.now(tz='UTC').tz_localize(None).floor('5min')
    times = pd.date_range(end=now, periods=30, freq='5min')
    df = pd.DataFrame({'time': times, 'open': 100.0, 'high': 101.0, 'low': 99.0, 'close': 100.0, 'volume': 1000.0})
    market = YahooStockMarket(['AAPL'], fetch=lambda symbols, interval: {'AAPL': df})
    t = market.tickers(['AAPL'])['AAPL']
    assert t['last'] == 100 and t['bid'] < 100 < t['ask']
    assert t['quote_volume'] == pytest.approx(100 * 1000 * 30)
    # the candle starting now is still forming
    assert len(market.candles('AAPL', 5)) == 29


def test_stock_history_download(tmp_path):
    def fetch(symbols, interval, period):
        assert period == '60d'
        return {s: stock_day() for s in symbols if s != 'NOPE'}
    info = stock_history.download(90, ['AAPL', 'NOPE'], path=str(tmp_path), fetch=fetch)
    assert info['pairs'] == ['SPY', 'AAPL'] and info['missing'] == ['NOPE'] and info['days'] == 60
    assert set(stock_history.load(str(tmp_path))) == {'SPY', 'AAPL'}
    assert stock_history.info(str(tmp_path))['days'] == 60


# pages and API

def test_stock_routes(monkeypatch):
    from agent_module.routes import init_agents
    from agent_module import history
    crypto = Pipeline(FakeStocks(), Store(':memory:'), AgentConfig())
    stocks = Pipeline(FakeStocks(), Store(':memory:'), AgentConfig.for_market('stocks'))
    app = Flask(__name__, template_folder='../templates')
    init_agents(app, SocketIO(app), pipeline_factory=lambda: crypto, stock_pipeline_factory=lambda: stocks)
    client = app.test_client()
    for path in ['/stocks/agents', '/stocks/agents/tune']:
        page = client.get(path)
        assert page.status_code == 200 and b'/api/stocks/agents' in page.data
    assert b'name="flat_at_close"' in client.get('/stocks/agents/tune').data
    assert b'name="flat_at_close"' not in client.get('/agents/tune').data

    settings = client.get('/api/stocks/agents/settings').get_json()
    assert set(settings['venues']) == {'alpaca_stocks', 'schwab', 'ibkr_lite', 'ibkr_pro'}
    assert settings['live']['flat_at_close'] is True
    assert set(client.get('/api/agents/settings').get_json()['venues']) == {
        k for k, v in VENUES.items() if v['market'] == 'crypto'}

    r = client.post('/api/stocks/agents/settings', json={'skip_open_minutes': 30, 'venue': 'kraken'})
    assert r.status_code == 400
    r = client.post('/api/stocks/agents/settings', json={'skip_open_minutes': 30})
    assert r.get_json()['changed'] == {'skip_open_minutes': 30} and crypto.config.skip_open_minutes == 0

    # each market reads its own history
    monkeypatch.setattr(history, 'load', lambda: {})
    monkeypatch.setattr(stock_history, 'load', lambda: {'NVDA': spike(stock_day(), 60)})
    assert client.post('/api/agents/simulate', json={}).status_code == 400
    r = client.post('/api/stocks/agents/simulate', json={'settings': {'take_profit': 0.5}}).get_json()
    assert r['pairs'] == 1 and r['test']['trades'][0]['reason'] == 'market close'
    rows = client.post('/api/stocks/agents/venues', json={}).get_json()['rows']
    assert len(rows) == 4
    impact = client.post('/api/stocks/agents/impact', json={}).get_json()['rows']
    assert 'flat_at_close' in {row['setting'] for row in impact}
    assert client.get('/api/stocks/agents/state').get_json()['market'] == 'stocks'


def test_app_has_both_sections():
    from app import app
    client = app.test_client()
    page = client.get('/stocks/backtest')
    assert page.status_code == 200
    for link in [b'href="/stocks/agents"', b'href="/stocks/agents/tune"', b'href="/stocks/backtest"',
                 b'href="/agents"', b'href="/backtest"', b'>Crypto<', b'>Stocks<']:
        assert link in page.data
    assert b'value="SPY"' in page.data and b'Yahoo Finance' in page.data
    assert b'/api/stocks/agents/state' in client.get('/').data


def test_stock_backtest_counts_market_hours():
    from backtest_module.routes import periods_per_year
    assert periods_per_year('stocks', 5) == 252 * 78
    assert periods_per_year('stocks', 1440) == 252
    assert periods_per_year('crypto', 1440) == 365


def test_quiet_candle_after_a_spike_scores_none():
    # pandas 3 used to turn the quiet candle's None into NaN once a spike was in the window
    from agent_module.rules import spike_signals
    df = stock_day().iloc[:40].reset_index(drop=True)
    df.loc[30, ['close', 'volume']] = [101.0, 9e6]
    signals = spike_signals(df, AgentConfig())['signal']
    assert signals.iloc[30] == 'pass' and signals.iloc[-1] is None

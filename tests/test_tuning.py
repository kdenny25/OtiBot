import numpy as np
import pandas as pd
import pytest
from flask import Flask
from flask_socketio import SocketIO

from agent_module import AgentConfig, Pipeline
from agent_module import history
from agent_module.config import BASELINE, RECOMMENDED
from agent_module.rules import FADED, LATE, PASS, RED, exit_reason, spike_signals
from agent_module.simulate import simulate
from agent_module.store import Store
from tests.test_agents import FakeMarket, make_candles


def candles(rows):
    """ rows of (open, close, volume), 5 minutes apart """
    df = pd.DataFrame(rows, columns=['open', 'close', 'volume'])
    df['high'] = df[['open', 'close']].max(axis=1) * 1.001
    df['low'] = df[['open', 'close']].min(axis=1) * 0.999
    df['time'] = pd.date_range('2026-01-01', periods=len(df), freq='5min')
    return df[['time', 'open', 'high', 'low', 'close', 'volume']]


QUIET = [(100, 100, 10)] * 24


def last_signal(rows, **settings):
    return spike_signals(candles(rows), AgentConfig(**settings))['signal'].iloc[-1]


def test_spike_signals():
    assert last_signal(QUIET + [(100, 101, 80)]) == PASS
    assert last_signal(QUIET + [(100, 99, 80)]) == RED
    assert last_signal(QUIET + [(100, 100.5, 20)]) is None
    assert last_signal(QUIET + [(100, 105, 80)]) == PASS
    assert last_signal(QUIET + [(100, 105, 80)], max_entry_move=0.03) == LATE


def test_confirm_spike_waits_for_the_next_candle():
    assert last_signal(QUIET + [(100, 102, 80)], confirm_spike=True) is None
    assert last_signal(QUIET + [(100, 102, 80), (102, 102.5, 30)], confirm_spike=True) == PASS
    assert last_signal(QUIET + [(100, 102, 80), (102, 100.5, 30)], confirm_spike=True) == FADED


def position(entry=100.0, peak=100.0, fee_rate=0.004):
    return {'entry_price': entry, 'entry_ts': 0, 'peak': peak, 'fee_rate': fee_rate}


def test_trailing_stop_waits_until_it_covers_costs():
    # up 2%, trail 1.5% would close at 100.47, below the ~0.9% round trip cost
    pos = position(peak=102.0)
    assert exit_reason(pos, 100.4, 60, AgentConfig()) == 'trailing stop'
    assert exit_reason(pos, 100.4, 60, AgentConfig(trail_covers_costs=True)) is None
    pos['peak'] = 103.0
    assert exit_reason(pos, 101.4, 60, AgentConfig(trail_covers_costs=True)) == 'trailing stop'


def test_flat_trades_close_early():
    config = AgentConfig(stale_minutes=90, stale_move=0.005)
    assert exit_reason(position(), 100.2, 89 * 60, config) is None
    assert exit_reason(position(), 100.2, 90 * 60, config) == 'went nowhere'
    assert exit_reason(position(), 101.0, 90 * 60, config) is None
    assert exit_reason(position(), 100.2, 90 * 60, AgentConfig()) is None


@pytest.fixture
def limit_pipeline():
    config = AgentConfig(start_balance=1000, limit_orders=True)
    return Pipeline(FakeMarket(), Store(':memory:'), config)


def test_limit_buy_fills_at_its_price_with_maker_fee(limit_pipeline):
    p, market = limit_pipeline, limit_pipeline.market
    market.spiking = {'XETHZUSD'}
    p.run_cycle(now_ts=1000)
    assert p.broker.positions == {} and 'XETHZUSD' in p.broker.orders
    limit = p.broker.orders['XETHZUSD']['price']
    assert p.broker.free_cash() == pytest.approx(1000 - 100 * 1.0025)

    market.spiking = set()
    market.prices['XETHZUSD'] = 99.0
    p.run_cycle(now_ts=1060)
    pos = p.broker.positions['XETHZUSD']
    assert pos['entry_price'] == limit and pos['fee_rate'] == 0.0025
    assert p.broker.cash == pytest.approx(1000 - 100 * 1.0025)
    actions = [(e['agent'], e['action']) for e in p.store.recent_events(50)]
    assert ('EXECUTE', 'WAIT') in actions and ('EXECUTE', 'ENTER') in actions


def test_limit_buy_is_cancelled_when_price_runs_away(limit_pipeline):
    p, market = limit_pipeline, limit_pipeline.market
    market.spiking = {'XETHZUSD'}
    p.run_cycle(now_ts=1000)
    market.spiking = set()
    market.prices['XETHZUSD'] = 101.0
    p.run_cycle(now_ts=1000 + 5 * 60)
    assert p.broker.orders == {} and p.broker.positions == {}
    assert p.broker.free_cash() == pytest.approx(1000)
    assert 'cancelled' in p.store.recent_events(50, agent='EXECUTE')[0]['detail']


def test_take_profit_fills_as_a_limit_sell(limit_pipeline):
    p, market = limit_pipeline, limit_pipeline.market
    market.spiking = {'XETHZUSD'}
    p.run_cycle(now_ts=1000)
    market.spiking = set()
    market.prices['XETHZUSD'] = 99.0
    p.run_cycle(now_ts=1060)
    entry = p.broker.positions['XETHZUSD']['entry_price']
    market.prices['XETHZUSD'] = 110.0
    p.run_cycle(now_ts=1120)
    trade = p.store.trades()[0]
    assert trade['reason'] == 'take profit'
    assert trade['exit_price'] == pytest.approx(entry * 1.04)


def test_market_filter_blocks_buys_when_btc_is_down():
    market = FakeMarket()
    market.pairs['XXBTZUSD'] = 'XBT/USD'
    market.prices['XXBTZUSD'] = 60000.0
    market.volume['XXBTZUSD'] = 1e9
    base = market.tickers
    market.tickers = lambda pairs: {p: {**t, 'open': 61000.0 if p == 'XXBTZUSD' else None}
                                    for p, t in base(pairs).items()}
    market.spiking = {'XETHZUSD'}
    p = Pipeline(market, Store(':memory:'), AgentConfig(market_filter=True))
    p.run_cycle()
    assert p.broker.positions == {}
    assert 'no new buys' in p.store.recent_events(50, agent='RISK CHECK')[0]['detail']

    market.prices['XXBTZUSD'] = 62000.0
    p.run_cycle()
    assert 'XETHZUSD' in p.broker.positions


def test_settings_survive_restart_and_reset(tmp_path):
    path = str(tmp_path / 'agents.db')
    first = Pipeline(FakeMarket(), Store(path))
    changed = first.apply_settings({'limit_orders': True, 'take_profit': '0.05'})
    assert changed == {'limit_orders': True, 'take_profit': 0.05}
    second = Pipeline(FakeMarket(), Store(path))
    assert second.config.limit_orders is True and second.config.take_profit == 0.05
    second.reset()
    assert Pipeline(FakeMarket(), Store(path)).config.limit_orders is True


def trend(n, start=100.0, step=0.0, spike_at=(), jump=0.01):
    rows, price = [], start
    for i in range(n):
        move = jump if i in spike_at else step
        rows.append((price, price * (1 + move), 80.0 if i in spike_at else 10.0))
        price *= 1 + move
    return candles(rows)


def test_simulate_trades_a_spike_to_take_profit():
    pair = trend(80, step=0.004, spike_at={30})
    result = simulate({'ETH/USD': pair}, AgentConfig(min_quote_volume=0))
    trade = result['trades'][-1]
    assert trade['reason'] == 'take profit' and trade['pnl'] > 0
    assert result['stats']['trades'] == 1
    assert result['stats']['final_equity'] == pytest.approx(1000 + trade['pnl'])
    assert result['exits'] == [{'reason': 'take profit', 'count': 1, 'pnl': trade['pnl']}]


def test_simulate_stop_and_costs():
    pair = trend(80, step=-0.004, spike_at={30})
    result = simulate({'ETH/USD': pair}, AgentConfig(min_quote_volume=0))
    assert result['trades'][-1]['reason'] == 'stop loss'
    stats = result['stats']
    assert stats['fees'] > 0 and stats['pnl_before_fees'] > stats['final_equity'] - 1000


def test_simulate_limit_buy_needs_price_to_come_back():
    # price only rises after the spike with no dips, so a limit just under the spike close never fills
    pair = trend(80, step=0.004, spike_at={30})
    pair['low'] = pair[['open', 'close']].min(axis=1)
    config = AgentConfig(min_quote_volume=0, limit_orders=True)
    assert simulate({'ETH/USD': pair}, config)['stats']['trades'] == 0
    # one dip through the limit fills it at the limit price with the maker fee
    pair.loc[31, 'low'] = pair.loc[30, 'close'] * 0.99
    trade = simulate({'ETH/USD': pair}, config)['trades'][-1]
    assert trade['entry_price'] == pytest.approx(pair.loc[30, 'close'] * 0.9995)


def test_simulate_market_filter_uses_btc():
    pair = trend(80, step=0.004, spike_at={30})
    btc = trend(80, start=60000, step=-0.001)
    config = AgentConfig(min_quote_volume=0, market_filter=True)
    assert simulate({'ETH/USD': pair, 'BTC/USD': btc}, config)['stats']['trades'] == 0
    config.market_filter = False
    assert simulate({'ETH/USD': pair, 'BTC/USD': btc}, config)['stats']['trades'] == 1


def test_simulate_respects_max_positions():
    pairs = {f'P{i}/USD': trend(80, step=0.001, spike_at={30}) for i in range(4)}
    config = AgentConfig(min_quote_volume=0, max_open_positions=2, max_hold_minutes=60)
    result = simulate(pairs, config)
    assert result['stats']['trades'] == 2


class FakeResponse:
    def __init__(self, status, data=None):
        self.status_code, self.data = status, data

    def json(self):
        return self.data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class FakeCoinbase:
    def __init__(self):
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append(url)
        if 'NOPE' in url:
            return FakeResponse(404, {'message': 'NotFound'})
        end = int(pd.Timestamp(params['end']).timestamp())
        start = int(pd.Timestamp(params['start']).timestamp())
        # newest first, like Coinbase: [time, low, high, open, close, volume]
        return FakeResponse(200, [[t, 1, 3, 2, 2.5, 10] for t in range(end - 300, start - 1, -300)])


def test_history_download_and_load(tmp_path):
    session = FakeCoinbase()
    info = history.download(days=3, pairs=['ETH/USD', 'NOPE/USD'], path=str(tmp_path),
                            session=session, progress=lambda *a: None)
    assert info['pairs'] == ['BTC/USD', 'ETH/USD'] and info['missing'] == ['NOPE/USD']
    assert any('BTC-USD' in c for c in session.calls)
    loaded = history.load(str(tmp_path))
    assert set(loaded) == {'BTC/USD', 'ETH/USD'}
    df = loaded['ETH/USD']
    assert len(df) == 3 * 288 and df['time'].is_monotonic_increasing
    assert history.info(str(tmp_path))['days'] == 3


def test_product_ids():
    assert history.product_id('XBT/USD') == 'BTC-USD'
    assert history.product_id('XDG/USD') == 'DOGE-USD'
    assert history.product_id('SOL/USD') == 'SOL-USD'


def test_tune_routes(monkeypatch):
    from agent_module.routes import init_agents
    pipeline = Pipeline(FakeMarket(), Store(':memory:'), AgentConfig())
    app = Flask(__name__, template_folder='../templates')
    init_agents(app, SocketIO(app), pipeline_factory=lambda: pipeline)
    client = app.test_client()
    assert client.get('/agents/tune').status_code == 200

    settings = client.get('/api/agents/settings').get_json()
    assert settings['live']['limit_orders'] is False
    assert all(settings['recommended'][k] == v for k, v in RECOMMENDED.items())
    assert all(settings['baseline'][k] == v for k, v in BASELINE.items())

    r = client.post('/api/agents/settings', json={'limit_orders': True, 'start_balance': 5})
    assert r.get_json()['changed'] == {'limit_orders': True}
    assert pipeline.config.limit_orders is True and pipeline.config.start_balance == 1000

    monkeypatch.setattr(history, 'load', lambda: {})
    assert client.post('/api/agents/simulate', json={}).status_code == 400

    pair = trend(80, step=0.004, spike_at={30})
    pair['volume'] *= 1e5
    monkeypatch.setattr(history, 'load', lambda: {'ETH/USD': pair})
    r = client.post('/api/agents/simulate', json={'settings': {'limit_orders': False}}).get_json()
    assert r['test']['stats']['trades'] == 1 and r['baseline']['stats']['trades'] == 1
    assert r['pairs'] == 1 and len(r['test']['equity']) <= 601

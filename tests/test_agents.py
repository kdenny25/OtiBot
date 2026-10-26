import pandas as pd
import pytest
from flask import Flask
from flask_socketio import SocketIO

from agent_module import AgentConfig, Pipeline
from agent_module.agents import volume_spike
from agent_module.market import KrakenMarket
from agent_module.store import Store


def make_candles(volumes, last_open=100.0, last_close=101.0):
    n = len(volumes)
    df = pd.DataFrame({'time': pd.date_range('2026-01-01', periods=n, freq='5min'),
                       'open': [100.0] * n, 'high': [102.0] * n,
                       'low': [99.0] * n, 'close': [100.0] * n,
                       'volume': volumes})
    df.loc[n - 1, ['open', 'close']] = [last_open, last_close]
    return df


class FakeMarket:
    def __init__(self):
        self.pairs = {'XETHZUSD': 'ETH/USD', 'SOLUSD': 'SOL/USD', 'THINUSD': 'THIN/USD'}
        self.prices = {'XETHZUSD': 100.0, 'SOLUSD': 50.0, 'THINUSD': 1.0}
        self.volume = {'XETHZUSD': 5e7, 'SOLUSD': 2e7, 'THINUSD': 1000}
        self.spiking = set()

    def usd_pairs(self):
        return dict(self.pairs)

    def tickers(self, pairs):
        return {p: {'bid': self.prices[p] * 0.9995, 'ask': self.prices[p] * 1.0005,
                    'last': self.prices[p], 'quote_volume': self.volume[p]} for p in pairs}

    def candles(self, pair, interval):
        volumes = [10.0] * 30
        if pair in self.spiking:
            volumes[-1] = 80.0
        return make_candles(volumes)


@pytest.fixture
def pipeline():
    return Pipeline(FakeMarket(), Store(':memory:'), AgentConfig(start_balance=1000))


def test_volume_spike():
    assert volume_spike(make_candles([10.0] * 24 + [50.0]), 24) == pytest.approx(5.0)
    assert volume_spike(make_candles([10.0] * 5), 24) == 0.0


def test_quiet_market_makes_no_trades(pipeline):
    pipeline.run_cycle()
    state = pipeline.state()
    assert state['positions'] == []
    assert state['balance'] == pytest.approx(1000)
    agents = {e['agent'] for e in state['calls']}
    assert {'SCAN', 'VOLUME', 'LOG'} <= agents


def test_spike_enters_sized_position(pipeline):
    pipeline.market.spiking = {'XETHZUSD'}
    pipeline.run_cycle()
    pos = pipeline.broker.positions['XETHZUSD']
    # 1% risk / 2% stop is 50%, capped at 10% of equity
    assert pos['cost'] == pytest.approx(100)
    assert pos['entry_price'] > 100.0
    assert pipeline.broker.cash == pytest.approx(1000 - 100 * 1.004)
    actions = [(e['agent'], e['action']) for e in pipeline.store.recent_events(50)]
    assert ('EXECUTE', 'ENTER') in actions


def test_thin_pair_fails_risk_check(pipeline):
    pipeline.market.spiking = {'THINUSD'}
    pipeline.run_cycle()
    assert 'THINUSD' not in pipeline.broker.positions
    skip = pipeline.store.recent_events(50, agent='RISK CHECK')[0]
    assert skip['action'] == 'SKIP' and skip['symbol'] == 'THIN/USD'


def test_take_profit_and_stop_loss(pipeline):
    market = pipeline.market
    market.spiking = {'XETHZUSD', 'SOLUSD'}
    pipeline.run_cycle()
    market.spiking = set()
    market.prices['XETHZUSD'] = 106.0
    market.prices['SOLUSD'] = 48.0
    pipeline.run_cycle()

    trades = {t['symbol']: t for t in pipeline.store.trades()}
    assert trades['ETH/USD']['reason'] == 'take profit' and trades['ETH/USD']['pnl'] > 0
    assert trades['SOL/USD']['reason'] == 'stop loss' and trades['SOL/USD']['pnl'] < 0
    stats = pipeline.state()['stats']
    assert (stats['wins'], stats['losses'], stats['win_rate']) == (1, 1, 0.5)
    assert stats['total_pnl'] == pytest.approx(pipeline.broker.cash - 1000)


def test_trailing_stop(pipeline):
    market = pipeline.market
    market.spiking = {'XETHZUSD'}
    pipeline.run_cycle()
    market.spiking = set()
    market.prices['XETHZUSD'] = 103.0
    pipeline.run_cycle()
    assert 'XETHZUSD' in pipeline.broker.positions
    market.prices['XETHZUSD'] = 101.0
    pipeline.run_cycle()
    assert pipeline.store.trades()[0]['reason'] == 'trailing stop'


def test_time_limit_exit(pipeline):
    pipeline.market.spiking = {'XETHZUSD'}
    pipeline.run_cycle()
    pipeline.market.spiking = set()
    later = pipeline.broker.positions['XETHZUSD']['entry_ts'] + 241 * 60
    pipeline.run_cycle(now_ts=later)
    assert pipeline.store.trades()[0]['reason'] == 'time limit'


def test_no_new_entries_past_max_positions():
    market = FakeMarket()
    config = AgentConfig(start_balance=1000, max_open_positions=1)
    pipeline = Pipeline(market, Store(':memory:'), config)
    market.spiking = {'XETHZUSD', 'SOLUSD'}
    pipeline.run_cycle()
    assert len(pipeline.broker.positions) == 1
    assert pipeline.store.recent_events(50, agent='SIZE')[0]['action'] == 'SKIP'


def test_positions_survive_restart(tmp_path):
    path = str(tmp_path / 'agents.db')
    market = FakeMarket()
    market.spiking = {'XETHZUSD'}
    first = Pipeline(market, Store(path))
    first.run_cycle()
    second = Pipeline(market, Store(path))
    assert 'XETHZUSD' in second.broker.positions
    assert second.broker.cash == pytest.approx(first.broker.cash)


def test_new_listing_is_logged(pipeline):
    pipeline.run_cycle()
    pipeline.market.pairs['NEWUSD'] = 'NEW/USD'
    pipeline.market.prices['NEWUSD'] = 2.0
    pipeline.market.volume['NEWUSD'] = 1e6
    pipeline.scan.pairs_loaded = 0
    pipeline.run_cycle()
    events = pipeline.store.recent_events(50, agent='SCAN')
    assert any(e['symbol'] == 'NEW/USD' and e['detail'] == 'new listing' for e in events)


def test_kraken_market_parses_responses():
    class Resp:
        def __init__(self, data):
            self.data = data

        def raise_for_status(self):
            pass

        def json(self):
            return self.data

    class Session:
        def get(self, url, params=None, timeout=None):
            if url.endswith('AssetPairs'):
                return Resp({'error': [], 'result': {
                    'XETHZUSD': {'wsname': 'ETH/USD', 'status': 'online'},
                    'USDTZUSD': {'wsname': 'USDT/USD', 'status': 'online'},
                    'XETHXXBT': {'wsname': 'ETH/XBT', 'status': 'online'}}})
            if url.endswith('Ticker'):
                return Resp({'error': [], 'result': {'XETHZUSD': {
                    'a': ['101', '1', '1'], 'b': ['99', '1', '1'], 'c': ['100', '1'],
                    'v': ['10', '1000'], 'p': ['100', '100']}}})
            rows = [[1700000000 + i * 300, '1', '2', '0.5', '1.5', '1.2', '10', 5] for i in range(3)]
            return Resp({'error': [], 'result': {'XETHZUSD': rows, 'last': 1700000600}})

    market = KrakenMarket(session=Session())
    assert market.usd_pairs() == {'XETHZUSD': 'ETH/USD'}
    t = market.tickers(['XETHZUSD'])['XETHZUSD']
    assert (t['bid'], t['ask'], t['quote_volume']) == (99.0, 101.0, 100000.0)
    candles = market.candles('XETHZUSD', 5)
    assert len(candles) == 2 and candles['close'].iloc[0] == 1.5


def test_routes(pipeline):
    from agent_module.routes import init_agents, runner
    app = Flask(__name__, template_folder='../templates')
    init_agents(app, SocketIO(app), pipeline_factory=lambda: pipeline)
    client = app.test_client()
    assert client.get('/agents').status_code == 200
    state = client.get('/api/agents/state').get_json()
    assert state['mode'] == 'paper' and state['running'] is False
    assert [p['name'] for p in state['pipeline']][0] == 'SCAN'
    assert client.post('/api/agents/reset').status_code == 200
    runner.running = True
    assert client.post('/api/agents/reset').status_code == 409
    runner.running = False

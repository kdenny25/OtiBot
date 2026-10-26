import pytest

import app as web
from backtest_module import routes as bt_routes
from backtest_module.strategies import STRATEGIES, build, catalog


@pytest.fixture
def client():
    web.app.config['TESTING'] = True
    return web.app.test_client()


@pytest.mark.parametrize('path', ['/', '/agents', '/backtest', '/dividends'])
def test_pages_render_with_nav(client, path):
    resp = client.get(path)
    assert resp.status_code == 200
    for link in [b'href="/agents"', b'href="/backtest"', b'href="/dividends"']:
        assert link in resp.data
    assert b'class="active"' in resp.data


@pytest.mark.parametrize('key', list(STRATEGIES))
def test_every_strategy_runs_on_sample_data(key):
    result = bt_routes.run_backtest({'strategy': key, 'source': 'sample', 'windows': 2})
    assert result['candles'] > 900
    assert len(result['equity']) <= bt_routes.MAX_POINTS + 1
    assert result['equity'][0]['v'] == pytest.approx(10000, rel=0.01)
    assert result['stats']['buy_hold_return'] is not None
    assert len(result['windows']) == 2


def test_strategy_params_are_clamped(ohlc):
    # a slow SMA of 10000 would never warm up, the clamp keeps it at 400
    buy, sell = build('sma_cross', {'fast': 10, 'slow': 10000})(ohlc.copy())
    assert buy.any()


def test_catalog_has_no_functions():
    assert all('fn' not in s for s in catalog())


def test_run_api(client):
    resp = client.post('/api/backtest/run', json={'strategy': 'sma_cross', 'source': 'sample',
                                                  'params': {'fast': 5, 'slow': 20}, 'fee': 0.001})
    data = resp.get_json()
    assert resp.status_code == 200
    assert data['strategy'] == 'Moving average crossover'
    assert data['trades'] and data['trades'][0]['side'] == 'long'
    last = client.get('/api/backtest/last').get_json()
    assert last['strategy'] == 'Moving average crossover'


def test_run_api_reports_bad_input(client):
    resp = client.post('/api/backtest/run', json={'strategy': 'nope', 'source': 'sample'})
    assert resp.status_code == 400
    assert 'Unknown strategy' in resp.get_json()['error']
    resp = client.post('/api/backtest/run', json={'source': 'database', 'pair': 'ETHUSD'})
    assert resp.status_code == 400
    assert 'date' in resp.get_json()['error']


def test_strategies_api(client):
    data = client.get('/api/backtest/strategies').get_json()
    assert {s['key'] for s in data} == set(STRATEGIES)


def test_market_api(client, monkeypatch):
    class Market:
        def tickers(self, pairs):
            return {'XXBTZUSD': {'last': 110.0, 'open': 100.0}, 'XETHZUSD': {'last': 9.0, 'open': 10.0}}

    monkeypatch.setitem(web._market_cache, 'data', None)
    data = web.market_snapshot(Market())
    assert [d['symbol'] for d in data] == ['BTC', 'ETH']
    assert data[0]['change'] == pytest.approx(0.1)
    # cached for the next call
    assert web.market_snapshot() is data


def test_market_api_error(client, monkeypatch):
    def fail():
        raise RuntimeError('blocked')
    monkeypatch.setattr(web, 'market_snapshot', fail)
    resp = client.get('/api/market')
    assert resp.status_code == 502

import os
import threading
import time

from flask import Flask, jsonify, render_template
from flask_socketio import SocketIO

from agent_module.routes import init_agents
from backtest_module.routes import backtest_bp
from dividend_module.routes import dividends_bp

# Set this variable to "threading", "eventlet" or "gevent" to test the
# different async modes, or leave it set to None for the application to choose
# the best option based on installed packages.
async_mode = None

base_dir = '.'

app = Flask(__name__,
            static_folder=os.path.join(base_dir, 'static'),
            template_folder=os.path.join(base_dir, 'templates'),)

app.register_blueprint(dividends_bp)
app.register_blueprint(backtest_bp)

socketio = SocketIO(app, async_mode=async_mode)
init_agents(app, socketio)

# prices shown on the home page, cached so page loads don't hammer Kraken
MARKET_PAIRS = {'XXBTZUSD': 'BTC', 'XETHZUSD': 'ETH', 'SOLUSD': 'SOL', 'XXRPZUSD': 'XRP'}
MARKET_TTL = 30
_market_cache = {'time': 0, 'data': None}
_market_lock = threading.Lock()


def market_snapshot(market=None):
    with _market_lock:
        if _market_cache['data'] is not None and time.time() - _market_cache['time'] < MARKET_TTL:
            return _market_cache['data']
        if market is None:
            from agent_module.market import KrakenMarket
            market = KrakenMarket()
        tickers = market.tickers(list(MARKET_PAIRS))
        data = [{'symbol': MARKET_PAIRS[pair], 'price': t['last'],
                 'change': t['last'] / t['open'] - 1 if t.get('open') else None}
                for pair, t in tickers.items() if pair in MARKET_PAIRS]
        data.sort(key=lambda d: list(MARKET_PAIRS.values()).index(d['symbol']))
        _market_cache.update(time=time.time(), data=data)
        return data


@app.route('/')
def index():
    return render_template('home.html')


@app.route('/favicon.ico')
def favicon():
    # browsers ask for /favicon.ico directly, before reading the page's <link> tags
    return app.send_static_file('img/favicon.ico')


@app.route('/healthz')
def healthz():
    return jsonify({'ok': True})


@app.route('/api/market')
def market_api():
    try:
        return jsonify(market_snapshot())
    except Exception as e:
        return jsonify({'error': str(e)}), 502


if __name__ == '__main__':
    socketio.run(app, debug=True)

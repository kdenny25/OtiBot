# Flask pages and the background loops for the agent dashboards. Crypto and
# stocks each get the same pages and API from make_blueprint, with their own
# paper account, settings and candle history.
import os
import threading
import time

from flask import Blueprint, jsonify, render_template, request

from agent_module.config import AgentConfig, CANDLE_SIZES, VENUES, presets
from agent_module.markets import CRYPTO, STOCKS


class Runner:
    """ Runs pipeline cycles in a socketio background task and pushes state to the page. """

    def __init__(self, make_pipeline, event='agent_'):
        self.make_pipeline = make_pipeline
        self.event = event
        self._pipeline = None
        self.socketio = None
        self.lock = threading.Lock()
        self.running = False
        self.cycling = False
        self.last_cycle = None
        self.error = None

    @property
    def pipeline(self):
        if self._pipeline is None:
            self._pipeline = self.make_pipeline()
        return self._pipeline

    def state(self):
        state = self.pipeline.state()
        state['running'] = self.running
        state['cycling'] = self.cycling
        # epoch seconds, so the page can count down to the next scan
        state['last_cycle'] = self.last_cycle
        state['cycle_seconds'] = self.pipeline.config.cycle_seconds
        state['error'] = self.error
        return state

    def start(self):
        with self.lock:
            if self.running:
                return
            self.running = True
        self.socketio.start_background_task(self._loop)

    def stop(self):
        self.running = False

    def _loop(self):
        while self.running:
            self.cycling = True
            self.socketio.emit(self.event + 'cycle', {'cycling': True})
            try:
                self.pipeline.run_cycle()
                self.error = None
            except Exception as e:
                self.error = str(e)
            self.cycling = False
            self.last_cycle = time.time()
            self.socketio.emit(self.event + 'state', self.state())
            # sleep in steps so stop takes effect quickly
            for _ in range(self.pipeline.config.cycle_seconds):
                if not self.running:
                    break
                self.socketio.sleep(1)


def _default_pipeline():
    from agent_module.market import KrakenMarket
    from agent_module.pipeline import Pipeline
    from agent_module.store import Store
    return Pipeline(KrakenMarket(), Store(CRYPTO.db))


def _default_stock_pipeline():
    from agent_module.pipeline import Pipeline
    from agent_module.stock_market import YahooStockMarket
    from agent_module.store import Store
    return Pipeline(YahooStockMarket(), Store(STOCKS.db), AgentConfig.for_market('stocks'))


runner = Runner(_default_pipeline, CRYPTO.event)
stock_runner = Runner(_default_stock_pipeline, STOCKS.event)
MAX_POINTS = 600


def init_agents(app, socketio, pipeline_factory=None, stock_pipeline_factory=None):
    for r, factory, market in [(runner, pipeline_factory, CRYPTO), (stock_runner, stock_pipeline_factory, STOCKS)]:
        if factory:
            r.make_pipeline = factory
            r._pipeline = None
        r.socketio = socketio
        if _blueprint_name(market) not in app.blueprints:
            app.register_blueprint(make_blueprint(market, r))
    # e.g. in Docker, so a restart picks paper trading back up without a click
    if os.getenv('AGENTS_AUTOSTART', '').lower() in ('1', 'true', 'yes'):
        runner.start()
    if os.getenv('STOCK_AGENTS_AUTOSTART', '').lower() in ('1', 'true', 'yes'):
        stock_runner.start()


def _downsample(points):
    step = max(1, -(-len(points) // MAX_POINTS))
    return points[::step] + ([points[-1]] if (len(points) - 1) % step else [])


def _blueprint_name(market):
    # crypto keeps the original name so its endpoints (agents.agents_page) don't change
    return 'agents' if market is CRYPTO else 'stock_agents'


def make_blueprint(market, runner):
    """ The dashboard, tuning page and API for one market, run by runner. """
    bp = Blueprint(_blueprint_name(market), __name__)
    baseline, recommended, impact, tunable = presets(market.key)
    venues = {k: v for k, v in VENUES.items() if v['market'] == market.key}
    history_lock = threading.Lock()
    history_state = {'running': False, 'error': None, 'done': 0, 'total': 0, 'pair': None}
    page, api = market.page, market.api

    def settings_of(config):
        return {k: getattr(config, k) for k in tunable}

    def make_config(values):
        config = AgentConfig.for_market(market.key)
        config.update(values)
        if config.candle_interval not in CANDLE_SIZES:
            raise ValueError(f'candle size must be one of {CANDLE_SIZES} minutes')
        return config

    def sim_request():
        """ :return: (candles, settings, spread) from the request, or raises ValueError """
        candles = market.history.load()
        if not candles:
            raise ValueError('Download candle history first')
        body = request.get_json(force=True) or {}
        settings = {k: v for k, v in (body.get('settings') or {}).items() if k in tunable}
        try:
            make_config(settings)
        except (TypeError, ValueError) as e:
            raise ValueError(f'Invalid setting: {e}')
        return candles, settings, float(body.get('spread', market.spread))

    @bp.route(page)
    def agents_page():
        return render_template('agents.html', m=market.template())

    @bp.route(page + '/tune')
    def tune_page():
        return render_template('agents_tune.html', m=market.template())

    @bp.route(api + '/state')
    def agents_state():
        return jsonify(runner.state())

    @bp.route(api + '/start', methods=['POST'])
    def agents_start():
        runner.start()
        return jsonify({'running': True})

    @bp.route(api + '/stop', methods=['POST'])
    def agents_stop():
        runner.stop()
        return jsonify({'running': False})

    @bp.route(api + '/reset', methods=['POST'])
    def agents_reset():
        if runner.running:
            return jsonify({'error': 'Stop the agents before resetting'}), 409
        runner.pipeline.reset()
        return jsonify(runner.state())

    # agent backtest: settings, candle history and runs

    @bp.route(api + '/settings')
    def agents_settings():
        return jsonify({'live': settings_of(runner.pipeline.config),
                        'baseline': {**settings_of(AgentConfig.for_market(market.key)), **baseline},
                        'recommended': {**settings_of(runner.pipeline.config), **recommended},
                        'venues': venues})

    @bp.route(api + '/settings', methods=['POST'])
    def agents_apply_settings():
        values = {k: v for k, v in (request.get_json(force=True) or {}).items() if k in tunable}
        try:
            changed = runner.pipeline.apply_settings(values)
        except (TypeError, ValueError) as e:
            return jsonify({'error': f'Invalid setting: {e}'}), 400
        return jsonify({'live': settings_of(runner.pipeline.config), 'changed': changed})

    def progress(done, total, pair):
        history_state.update(done=done, total=total, pair=pair)

    def run_history(days):
        try:
            market.history.download(days, progress=progress)
            history_state['error'] = None
        except Exception as e:
            history_state['error'] = str(e)
        finally:
            history_state['running'] = False

    @bp.route(api + '/history')
    def agents_history():
        return jsonify({'info': market.history.info(), **history_state})

    @bp.route(api + '/history', methods=['POST'])
    def agents_history_refresh():
        """ Downloads 5 minute candles in the background. Takes a few minutes. """
        days = min(max(int((request.get_json(silent=True) or {}).get('days', 30)), 3), max(market.days))
        with history_lock:
            if not history_state['running']:
                history_state.update(running=True, error=None, done=0, total=0, pair=None)
                threading.Thread(target=run_history, args=(days,), daemon=True).start()
        return jsonify({'running': True})

    @bp.route(api + '/simulate', methods=['POST'])
    def agents_simulate():
        """ Runs the original rules and the given settings over the saved history. """
        from agent_module.simulate import simulate
        try:
            candles, settings, spread = sim_request()
        except ValueError as e:
            return jsonify({'error': str(e)}), 400

        results = {}
        for key, values in [('baseline', {**settings, **baseline}), ('test', settings)]:
            result = simulate(candles, make_config(values), spread=spread)
            result['equity'] = _downsample(result['equity'])
            result['trades'] = result['trades'][:100]
            results[key] = result
        first = min(df['time'].iloc[0] for df in candles.values())
        last = max(df['time'].iloc[-1] for df in candles.values())
        return jsonify({**results, 'pairs': len(candles), 'start': first.isoformat(), 'end': last.isoformat()})

    @bp.route(api + '/chart', methods=['POST'])
    def agents_chart():
        """
        One pair's candles with every trade the given settings made on it and
        the levels each exit rule watched. The whole test reruns so position
        limits across pairs match the results table.
        """
        from agent_module.chart import pair_chart, traded_pairs
        from agent_module.simulate import simulate
        try:
            candles, settings, spread = sim_request()
        except ValueError as e:
            return jsonify({'error': str(e)}), 400

        config = make_config(settings)
        trades = simulate(candles, config, spread=spread)['trades']
        pairs = traded_pairs(trades)
        pair = (request.get_json(force=True) or {}).get('pair') or (pairs[0][0] if pairs else next(iter(candles)))
        if pair not in candles:
            return jsonify({'error': f'No history for {pair}'}), 400
        chart = pair_chart(candles[pair], [t for t in trades if t['symbol'] == pair], config)
        return jsonify({**chart, 'pair': pair, 'pairs': [{'pair': p, 'trades': n} for p, n in pairs]})

    @bp.route(api + '/impact', methods=['POST'])
    def agents_impact():
        """
        Reruns the given settings with one change at a time: each rule switched
        the other way, and each other candle size. Shows what every rule adds
        and how it moves the reasons trades closed.
        """
        from agent_module.simulate import simulate
        try:
            candles, settings, spread = sim_request()
        except ValueError as e:
            return jsonify({'error': str(e)}), 400

        def summary(result):
            return {'return': result['stats']['total_return'], 'trades': result['stats']['trades'],
                    'win_rate': result['stats']['win_rate'], 'fees': result['stats']['fees'],
                    'exits': {e['reason']: {'count': e['count'], 'pnl': e['pnl']} for e in result['exits']}}

        test = make_config(settings)
        current = summary(simulate(candles, test, spread=spread))
        rows = []
        for key, on_value in impact.items():
            on = bool(getattr(test, key))
            other = baseline[key] if on else on_value
            rows.append({'setting': key, 'on': on,
                         'other': summary(simulate(candles, make_config({**settings, key: other}), spread=spread))})
        for size in CANDLE_SIZES:
            if size != test.candle_interval:
                rows.append({'setting': 'candle_interval', 'value': size, 'on': False,
                             'other': summary(simulate(candles, make_config({**settings, 'candle_interval': size}),
                                                       spread=spread))})
        return jsonify({'current': current, 'rows': rows})

    @bp.route(api + '/venues', methods=['POST'])
    def agents_venues():
        """ Reruns the given settings with each venue's fees, to show what the broker alone changes. """
        from agent_module.simulate import simulate
        try:
            candles, settings, spread = sim_request()
        except ValueError as e:
            return jsonify({'error': str(e)}), 400

        rows = []
        for key, venue in venues.items():
            config = make_config({**settings, 'venue': key})
            stats = simulate(candles, config, spread=spread)['stats']
            rows.append({'venue': key, 'label': venue['label'], 'note': venue['note'], 'shorts': venue['shorts'],
                         'taker_fee': venue['taker_fee'], 'maker_fee': venue['maker_fee'],
                         'per_share_fee': venue['per_share_fee'], 'min_fee': venue['min_fee'],
                         'trades': stats['trades'], 'win_rate': stats['win_rate'], 'return': stats['total_return'],
                         'before_fees': stats['pnl_before_fees'], 'fees': stats['fees'],
                         'pnl': stats['pnl_before_fees'] - stats['fees']})
        return jsonify({'rows': rows, 'current': make_config(settings).venue})

    return bp

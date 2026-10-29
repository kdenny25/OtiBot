# Flask pages and the background loop for the agent dashboard.
import os
import threading
import time

from flask import Blueprint, jsonify, render_template, request

from agent_module import history
from agent_module.config import AgentConfig, BASELINE, CANDLE_SIZES, IMPACT, RECOMMENDED, TUNABLE

agents_bp = Blueprint('agents', __name__)


class Runner:
    """ Runs pipeline cycles in a socketio background task and pushes state to the page. """

    def __init__(self, make_pipeline):
        self.make_pipeline = make_pipeline
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
            self.socketio.emit('agent_cycle', {'cycling': True})
            try:
                self.pipeline.run_cycle()
                self.error = None
            except Exception as e:
                self.error = str(e)
            self.cycling = False
            self.last_cycle = time.time()
            self.socketio.emit('agent_state', self.state())
            # sleep in steps so stop takes effect quickly
            for _ in range(self.pipeline.config.cycle_seconds):
                if not self.running:
                    break
                self.socketio.sleep(1)


def _default_pipeline():
    from agent_module.market import KrakenMarket
    from agent_module.pipeline import Pipeline
    return Pipeline(KrakenMarket())


runner = Runner(_default_pipeline)


def init_agents(app, socketio, pipeline_factory=None):
    if pipeline_factory:
        runner.make_pipeline = pipeline_factory
        runner._pipeline = None
    runner.socketio = socketio
    app.register_blueprint(agents_bp)
    # e.g. in Docker, so a restart picks paper trading back up without a click
    if os.getenv('AGENTS_AUTOSTART', '').lower() in ('1', 'true', 'yes'):
        runner.start()


@agents_bp.route('/agents')
def agents_page():
    return render_template('agents.html')


@agents_bp.route('/agents/tune')
def tune_page():
    return render_template('agents_tune.html')


@agents_bp.route('/api/agents/state')
def agents_state():
    return jsonify(runner.state())


@agents_bp.route('/api/agents/start', methods=['POST'])
def agents_start():
    runner.start()
    return jsonify({'running': True})


@agents_bp.route('/api/agents/stop', methods=['POST'])
def agents_stop():
    runner.stop()
    return jsonify({'running': False})


@agents_bp.route('/api/agents/reset', methods=['POST'])
def agents_reset():
    if runner.running:
        return jsonify({'error': 'Stop the agents before resetting'}), 409
    runner.pipeline.reset()
    return jsonify(runner.state())


# agent backtest: settings, candle history and runs

_history_lock = threading.Lock()
_history_state = {'running': False, 'error': None, 'done': 0, 'total': 0, 'pair': None}
MAX_POINTS = 600


def _settings(config):
    return {k: getattr(config, k) for k in TUNABLE}


@agents_bp.route('/api/agents/settings')
def agents_settings():
    return jsonify({'live': _settings(runner.pipeline.config),
                    'baseline': {**_settings(AgentConfig()), **BASELINE},
                    'recommended': {**_settings(runner.pipeline.config), **RECOMMENDED}})


@agents_bp.route('/api/agents/settings', methods=['POST'])
def agents_apply_settings():
    values = {k: v for k, v in (request.get_json(force=True) or {}).items() if k in TUNABLE}
    try:
        changed = runner.pipeline.apply_settings(values)
    except (TypeError, ValueError) as e:
        return jsonify({'error': f'Invalid setting: {e}'}), 400
    return jsonify({'live': _settings(runner.pipeline.config), 'changed': changed})


def _history_progress(done, total, pair):
    _history_state.update(done=done, total=total, pair=pair)


def _run_history(days):
    try:
        history.download(days, progress=_history_progress)
        _history_state['error'] = None
    except Exception as e:
        _history_state['error'] = str(e)
    finally:
        _history_state['running'] = False


@agents_bp.route('/api/agents/history')
def agents_history():
    return jsonify({'info': history.info(), **_history_state})


@agents_bp.route('/api/agents/history', methods=['POST'])
def agents_history_refresh():
    """ Downloads 5 minute candles in the background. Takes a few minutes. """
    days = min(max(int((request.get_json(silent=True) or {}).get('days', 30)), 3), 180)
    with _history_lock:
        if not _history_state['running']:
            _history_state.update(running=True, error=None, done=0, total=0, pair=None)
            threading.Thread(target=_run_history, args=(days,), daemon=True).start()
    return jsonify({'running': True})


def _downsample(points):
    step = max(1, -(-len(points) // MAX_POINTS))
    return points[::step] + ([points[-1]] if (len(points) - 1) % step else [])


def _config(values):
    config = AgentConfig()
    config.update(values)
    if config.candle_interval not in CANDLE_SIZES:
        raise ValueError(f'candle size must be one of {CANDLE_SIZES} minutes')
    return config


def _sim_request():
    """ :return: (candles, settings, spread) from the request, or raises ValueError """
    candles = history.load()
    if not candles:
        raise ValueError('Download candle history first')
    body = request.get_json(force=True) or {}
    settings = {k: v for k, v in (body.get('settings') or {}).items() if k in TUNABLE}
    try:
        _config(settings)
    except (TypeError, ValueError) as e:
        raise ValueError(f'Invalid setting: {e}')
    return candles, settings, float(body.get('spread', 0.001))


@agents_bp.route('/api/agents/simulate', methods=['POST'])
def agents_simulate():
    """ Runs the original rules and the given settings over the saved history. """
    from agent_module.simulate import simulate
    try:
        candles, settings, spread = _sim_request()
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    results = {}
    for key, values in [('baseline', {**settings, **BASELINE}), ('test', settings)]:
        result = simulate(candles, _config(values), spread=spread)
        result['equity'] = _downsample(result['equity'])
        result['trades'] = result['trades'][:100]
        results[key] = result
    first = min(df['time'].iloc[0] for df in candles.values())
    last = max(df['time'].iloc[-1] for df in candles.values())
    return jsonify({**results, 'pairs': len(candles), 'start': first.isoformat(), 'end': last.isoformat()})


@agents_bp.route('/api/agents/impact', methods=['POST'])
def agents_impact():
    """
    Reruns the given settings with one change at a time: each rule switched
    the other way, and each other candle size. Shows what every rule adds
    and how it moves the reasons trades closed.
    """
    from agent_module.simulate import simulate
    try:
        candles, settings, spread = _sim_request()
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    def summary(result):
        return {'return': result['stats']['total_return'], 'trades': result['stats']['trades'],
                'win_rate': result['stats']['win_rate'], 'fees': result['stats']['fees'],
                'exits': {e['reason']: {'count': e['count'], 'pnl': e['pnl']} for e in result['exits']}}

    test = _config(settings)
    current = summary(simulate(candles, test, spread=spread))
    rows = []
    for key, on_value in IMPACT.items():
        on = bool(getattr(test, key))
        other = BASELINE[key] if on else on_value
        rows.append({'setting': key, 'on': on,
                     'other': summary(simulate(candles, _config({**settings, key: other}), spread=spread))})
    for size in CANDLE_SIZES:
        if size != test.candle_interval:
            rows.append({'setting': 'candle_interval', 'value': size, 'on': False,
                         'other': summary(simulate(candles, _config({**settings, 'candle_interval': size}),
                                                   spread=spread))})
    return jsonify({'current': current, 'rows': rows})

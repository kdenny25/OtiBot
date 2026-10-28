# Flask pages and the background loop for the agent dashboard.
import os
import threading
import time

from flask import Blueprint, jsonify, render_template

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

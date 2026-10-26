# SQLite storage for the agent pipeline: every agent call, trades, open
# positions and the equity curve. Kept out of the Postgres candle database so
# paper trading runs with no setup.
import json
import os
import sqlite3
import threading

DEFAULT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'agents.db')

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    time TEXT NOT NULL,
    agent TEXT NOT NULL,
    action TEXT NOT NULL,
    symbol TEXT,
    detail TEXT
);
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    entry_time TEXT NOT NULL,
    exit_time TEXT NOT NULL,
    entry_price REAL NOT NULL,
    exit_price REAL NOT NULL,
    units REAL NOT NULL,
    fees REAL NOT NULL,
    slippage REAL NOT NULL,
    pnl REAL NOT NULL,
    reason TEXT
);
CREATE TABLE IF NOT EXISTS positions (
    pair TEXT PRIMARY KEY,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS equity (
    time TEXT PRIMARY KEY,
    value REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class Store:
    def __init__(self, path=DEFAULT_PATH):
        if path != ':memory:':
            os.makedirs(os.path.dirname(path), exist_ok=True)
        self.lock = threading.Lock()
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def _write(self, query, params=()):
        with self.lock:
            self.conn.execute(query, params)
            self.conn.commit()

    def _read(self, query, params=()):
        with self.lock:
            return [dict(r) for r in self.conn.execute(query, params).fetchall()]

    # events
    def log(self, time, agent, action, symbol=None, detail=''):
        self._write('INSERT INTO events (time, agent, action, symbol, detail) VALUES (?, ?, ?, ?, ?)',
                    (time, agent, action, symbol, detail))

    def recent_events(self, limit=40, agent=None):
        if agent:
            return self._read('SELECT * FROM events WHERE agent = ? ORDER BY id DESC LIMIT ?',
                              (agent, limit))
        return self._read('SELECT * FROM events ORDER BY id DESC LIMIT ?', (limit,))

    def last_event(self, agent):
        rows = self._read('SELECT * FROM events WHERE agent = ? ORDER BY id DESC LIMIT 1', (agent,))
        return rows[0] if rows else None

    def event_count(self):
        return self._read('SELECT COUNT(*) AS n FROM events')[0]['n']

    # trades
    def add_trade(self, trade):
        cols = ['symbol', 'entry_time', 'exit_time', 'entry_price', 'exit_price',
                'units', 'fees', 'slippage', 'pnl', 'reason']
        self._write(f'INSERT INTO trades ({", ".join(cols)}) VALUES ({", ".join("?" * len(cols))})',
                    tuple(trade[c] for c in cols))

    def trades(self, limit=None):
        query = 'SELECT * FROM trades ORDER BY id DESC'
        if limit:
            return self._read(query + ' LIMIT ?', (limit,))
        return self._read(query)

    # open positions
    def save_position(self, pair, position):
        self._write('INSERT OR REPLACE INTO positions (pair, data) VALUES (?, ?)',
                    (pair, json.dumps(position)))

    def remove_position(self, pair):
        self._write('DELETE FROM positions WHERE pair = ?', (pair,))

    def positions(self):
        return {r['pair']: json.loads(r['data']) for r in self._read('SELECT * FROM positions')}

    # equity curve
    def add_equity(self, time, value):
        self._write('INSERT OR REPLACE INTO equity (time, value) VALUES (?, ?)', (time, value))

    def equity_curve(self):
        return self._read('SELECT time, value FROM equity ORDER BY time')

    # key value settings, e.g. paper cash balance
    def get(self, key, default=None):
        rows = self._read('SELECT value FROM state WHERE key = ?', (key,))
        return json.loads(rows[0]['value']) if rows else default

    def set(self, key, value):
        self._write('INSERT OR REPLACE INTO state (key, value) VALUES (?, ?)', (key, json.dumps(value)))

    def reset(self):
        with self.lock:
            for table in ['events', 'trades', 'positions', 'equity', 'state']:
                self.conn.execute(f'DELETE FROM {table}')
            self.conn.commit()

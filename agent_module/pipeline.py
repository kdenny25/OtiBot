# Runs the six agents once per cycle and builds the dashboard state.
import time as _time
from datetime import datetime, timezone

import pandas as pd

from backtest_module.evaluations import max_drawdown, trade_stats
from agent_module.agents import (ScanAgent, VolumeAgent, RiskAgent, SizeAgent,
                                 ExecuteAgent, LogAgent)
from agent_module.broker import PaperBroker
from agent_module.config import AgentConfig
from agent_module.store import Store

AGENTS = [('SCAN', 'new pairs'), ('VOLUME', 'volume spikes'), ('RISK CHECK', 'filters thin pairs'),
          ('SIZE', 'sizes position'), ('EXECUTE', 'places orders'), ('LOG', 'every decision')]


def now_iso():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


class Pipeline:
    def __init__(self, market, store=None, config=None):
        self.config = config or AgentConfig()
        self.market = market
        self.store = store or Store()
        self.broker = PaperBroker(self.config, self.store)
        self.scan = ScanAgent(self.config, market, self.store)
        self.volume = VolumeAgent(self.config, market, self.store)
        self.risk = RiskAgent(self.config, self.store)
        self.size = SizeAgent(self.config, self.store)
        self.execute = ExecuteAgent(self.config, self.store, self.broker)
        self.log = LogAgent(self.store)
        if self.store.get('started') is None:
            self.store.set('started', now_iso())
            self.store.add_equity(self.store.get('started'), self.config.start_balance)

    def run_cycle(self, now=None, now_ts=None):
        now = now or now_iso()
        now_ts = now_ts or _time.time()
        try:
            watched, tickers = self.scan.run(now)
            # exits first so freed cash and slots are available to new setups
            self.execute.manage(now, now_ts, tickers)

            names = self.scan.pairs
            candidates = [p for p in watched if p not in self.broker.positions]
            for pair in self.volume.run(now, candidates, names):
                if not self.risk.run(now, pair, tickers[pair], names[pair]):
                    continue
                value = self.size.run(now, names[pair], self.broker, self.broker.equity(tickers))
                if value:
                    self.execute.enter(now, now_ts, pair, names[pair], tickers[pair], value)

            self.log.run(now, self.broker.equity(tickers), len(self.broker.positions))
        except Exception as e:
            self.store.log(now, 'LOG', 'ERROR', None, str(e)[:300])
            raise

    def reset(self):
        self.store.reset()
        self.broker.cash = self.config.start_balance
        self.broker.positions = {}
        self.store.set('started', now_iso())
        self.store.add_equity(self.store.get('started'), self.config.start_balance)

    def state(self):
        """ Everything the dashboard shows, as plain JSON types. """
        trades = self.store.trades()
        trades_df = pd.DataFrame(trades, columns=['pnl'] if not trades else None)
        stats = trade_stats(trades_df)
        wins = trades_df.loc[trades_df['pnl'] > 0, 'pnl']
        losses = trades_df.loc[trades_df['pnl'] < 0, 'pnl']
        curve = self.store.equity_curve()
        equity = self.broker.equity()
        drawdown = max_drawdown(pd.Series([p['value'] for p in curve])) if curve else 0.0

        def clean(x):
            return None if x is None or pd.isna(x) or x in (float('inf'), float('-inf')) else float(x)

        pipeline = []
        for name, label in AGENTS:
            last = self.store.last_event(name) or {}
            pipeline.append({'name': name, 'label': label,
                             'symbol': last.get('symbol'),
                             'action': last.get('action'),
                             'detail': last.get('detail')})

        return {'mode': 'paper',
                'started': self.store.get('started'),
                'start_balance': self.config.start_balance,
                'balance': equity,
                'cash': self.broker.cash,
                'stats': {'closes': stats['num_trades'],
                          'wins': int(len(wins)),
                          'losses': int(len(losses)),
                          'win_rate': clean(stats['win_rate']),
                          'profit_factor': clean(stats['profit_factor']),
                          'avg_win': clean(wins.mean()) if len(wins) else None,
                          'avg_loss': clean(losses.mean()) if len(losses) else None,
                          'total_pnl': float(trades_df['pnl'].sum()) if trades else 0.0,
                          'max_drawdown': clean(drawdown)},
                'equity_curve': curve,
                'pipeline': pipeline,
                'positions': [dict(pair=k, **v) for k, v in self.broker.positions.items()],
                'calls': self.store.recent_events(40),
                'trades': trades[:20],
                'events_logged': self.store.event_count(),
                'config': self.config.to_dict()}

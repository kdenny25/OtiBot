# Runs the six agents once per cycle and builds the dashboard state.
import time as _time
from datetime import datetime, timezone

import pandas as pd

from backtest_module.evaluations import max_drawdown, trade_stats
from agent_module.agents import (ScanAgent, VolumeAgent, RiskAgent, SizeAgent,
                                 ExecuteAgent, LogAgent)
from agent_module.broker import PaperBroker
from agent_module.config import AgentConfig
from agent_module.rules import market_ok
from agent_module.store import Store

AGENTS = [('SCAN', 'new pairs'), ('VOLUME', 'volume spikes'), ('RISK CHECK', 'filters thin pairs'),
          ('SIZE', 'sizes position'), ('EXECUTE', 'places orders'), ('LOG', 'every decision')]


def now_iso():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


class Pipeline:
    def __init__(self, market, store=None, config=None):
        self.market = market
        self.store = store or Store()
        self.config = config or AgentConfig()
        # settings chosen on the backtest page and applied to the live agents
        self.config.update(self.store.get('config', {}))
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
            sides = self.allowed_sides(now, tickers, names)
            if not sides:
                self.log.run(now, self.broker.equity(tickers), len(self.broker.positions))
                return
            candidates = [p for p in watched if p not in self.broker.positions and p not in self.broker.orders]
            for pair, side in self.volume.run(now, candidates, names):
                if side not in sides or not self.risk.run(now, pair, tickers[pair], names[pair]):
                    continue
                value = self.size.run(now, names[pair], self.broker, self.broker.equity(tickers))
                if value:
                    self.execute.enter(now, now_ts, pair, names[pair], tickers[pair], value, side)

            self.log.run(now, self.broker.equity(tickers), len(self.broker.positions))
        except Exception as e:
            self.store.log(now, 'LOG', 'ERROR', None, str(e)[:300])
            raise

    def allowed_sides(self, now, tickers, names):
        """
        Sides new trades may take: 1 to buy, -1 to short. With market_filter
        on, buys only while BTC is at or above today's open and shorts only
        while it is below.
        """
        sides = {1, -1} if self.config.short_spikes else {1}
        if not self.config.market_filter:
            return sides
        btc = next((tickers[p] for p, n in names.items() if n in ('XBT/USD', 'BTC/USD') and p in tickers), None)
        if btc is None:
            return sides
        allowed = {s for s in sides if market_ok(btc['last'], btc.get('open'), s)}
        if allowed != sides and btc.get('open'):
            change = btc['last'] / btc['open'] - 1
            self.store.log(now, 'RISK CHECK', 'WAIT', 'XBT/USD',
                           f'BTC {change:+.1%} today, ' + ('shorts only' if allowed else 'no new buys')
                           if change < 0 else f'BTC {change:+.1%} today, buys only')
        return allowed

    def apply_settings(self, values):
        """ Changes the live settings and keeps them across restarts. Returns what changed. """
        changed = self.config.update(values)
        saved = self.store.get('config', {})
        saved.update({k: getattr(self.config, k) for k in values if hasattr(self.config, k)})
        self.store.set('config', saved)
        return changed

    def reset(self):
        settings = self.store.get('config')
        self.store.reset()
        if settings:
            self.store.set('config', settings)
        self.broker.cash = self.config.start_balance
        self.broker.positions = {}
        self.broker.orders = {}
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
                             'event_id': last.get('id'),
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
                'orders': [dict(pair=k, **v) for k, v in self.broker.orders.items()],
                'calls': self.store.recent_events(40),
                'trades': trades[:20],
                'events_logged': self.store.event_count(),
                'config': self.config.to_dict()}

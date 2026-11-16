# The two sections of the app. Crypto and stocks run the same six agents,
# backtest and tuning page; this is everything that differs between them.
import os
from dataclasses import dataclass, field

from agent_module import history, stock_history

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')


@dataclass(frozen=True)
class Market:
    key: str                  # 'crypto' or 'stocks', AgentConfig.market
    label: str                # section name in the menu
    title: str                # page titles: 'Crypto agents', 'Stock agents'
    page: str                 # agents dashboard URL, the tuning page is page + '/tune'
    api: str                  # API prefix
    event: str                # socket event prefix
    db: str                   # SQLite file for paper trades and the event log
    history: object           # module with download, info, load
    source: str               # where the history comes from
    noun: str                 # 'pair' or 'stock'
    benchmark: str            # what the market filter follows
    spread: float             # assumed spread for backtests, history has no quotes
    days: tuple               # history lengths the page offers
    hours: str                # when it trades
    words: dict = field(default_factory=dict)

    def template(self):
        """ What the pages need, as plain values. """
        return {'key': self.key, 'label': self.label, 'title': self.title, 'page': self.page, 'api': self.api,
                'event': self.event, 'noun': self.noun, 'nouns': self.noun + 's', 'source': self.source,
                'benchmark': self.benchmark, 'bench': self.benchmark.split('/')[0],
                'spread': self.spread, 'days': list(self.days), 'hours': self.hours, **self.words}


CRYPTO = Market(key='crypto', label='Crypto', title='Crypto', page='/agents', api='/api/agents', event='agent_',
                db=os.path.join(DATA_DIR, 'agents.db'), history=history, source='Coinbase',
                noun='pair', benchmark='BTC/USD', spread=0.001, days=(14, 30, 60, 90),
                hours='24/7',
                words={'scan': 'Six agents scan Kraken USD pairs every minute and paper trade volume spikes.',
                       'day_open': 'midnight UTC'})

STOCKS = Market(key='stocks', label='Stocks', title='Stock', page='/stocks/agents', api='/api/stocks/agents',
                event='stocks_agent_', db=os.path.join(DATA_DIR, 'agents_stocks.db'), history=stock_history,
                source='Yahoo Finance', noun='stock', benchmark='SPY', spread=0.0004, days=(14, 30, 60),
                hours='9:30 AM to 4:00 PM ET on market days',
                words={'scan': 'Six agents scan the most traded US stocks and ETFs every minute during '
                               'market hours and paper trade volume spikes.',
                       'day_open': 'the 9:30 AM open'})

MARKETS = {m.key: m for m in (CRYPTO, STOCKS)}

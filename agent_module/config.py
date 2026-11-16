# Settings for the agent pipeline. Paper trading only for now.
#
# The same agents trade crypto and US stocks. AgentConfig() is the crypto
# setup, AgentConfig.for_market('stocks') starts from the stock defaults below.
from dataclasses import dataclass, asdict, fields

MARKETS = ('crypto', 'stocks')


@dataclass
class AgentConfig:
    market: str = 'crypto'            # 'crypto' trades 24/7, 'stocks' only in NYSE hours

    # paper account
    start_balance: float = 1000.0
    venue: str = 'kraken'             # key in VENUES, sets the fee fields below
    taker_fee: float = 0.004          # Kraken Pro starter tier taker fee
    maker_fee: float = 0.0025         # and maker fee, paid by resting limit orders
    min_fee: float = 0.0              # smallest fee per order in USD, 0 is none
    fee_cap: float = 0.0              # the minimum fee is never more than this share of the order, 0 is no cap
    slippage: float = 0.001           # extra 0.1% on top of crossing the spread
    margin_fee: float = 0.0002        # Kraken margin: 0.02% to open a short and every 4 hours it stays open
    per_share_fee: float = 0.0        # stocks: commission per share, e.g. IBKR Pro's $0.005
    sell_fee: float = 0.0             # stocks: SEC fee on every sale, as a share of its value
    sell_fee_per_share: float = 0.0   # stocks: FINRA trading activity fee per share sold, capped per order

    # market hours, stocks only
    flat_at_close: bool = False       # close every trade on the session's last candle, nothing held overnight
    skip_open_minutes: int = 0        # no new trades this long after the opening bell

    # scan
    candle_interval: int = 5          # minutes
    max_pairs: int = 25               # most traded USD pairs to watch each cycle

    # volume spike
    spike_lookback: int = 24          # candles in the volume baseline
    min_spike: float = 3.0            # last candle volume / baseline median
    max_entry_move: float = 0.0       # skip a spike candle that already rose more than this, 0 is off
    confirm_spike: bool = False       # wait for the candle after the spike to hold half its gain
    short_spikes: bool = False        # paper short red volume spikes instead of skipping them

    # risk check, stands in for the rug check until DEX pairs are added
    min_quote_volume: float = 250000  # USD traded in the last 24 hours
    max_spread: float = 0.005         # 0.5% between bid and ask
    market_filter: bool = False       # buy only while BTC is above today's open, short only while below

    # size
    risk_per_trade: float = 0.01      # lose at most 1% of equity if the stop hits
    max_position_pct: float = 0.10    # never more than 10% of equity in one pair
    max_open_positions: int = 5

    # orders
    limit_orders: bool = False        # buy with a limit at the bid and take profit with a resting limit
    limit_wait_minutes: int = 5       # cancel an unfilled limit buy after this long

    # exits
    take_profit: float = 0.04
    stop_loss: float = 0.02
    trail_trigger: float = 0.015      # trailing stop turns on once up this much
    trail_pct: float = 0.015          # and closes on this drop from the high
    trail_covers_costs: bool = False  # only trail once the stop would lock in a profit after fees
    stale_minutes: int = 0            # close a trade still within stale_move after this long, 0 is off
    stale_move: float = 0.005
    max_hold_minutes: int = 240

    # loop
    cycle_seconds: int = 60

    @classmethod
    def for_market(cls, market='crypto', **values):
        if market not in MARKETS:
            raise ValueError(f'unknown market {market}')
        config = cls(**{**(STOCK_DEFAULTS if market == 'stocks' else {}), **values})
        if config.venue not in VENUES or VENUES[config.venue]['market'] != market:
            raise ValueError(f'unknown {market} venue {config.venue}')
        # the venue sets its fees, unless they were given too
        for name in VENUE_FEES:
            if name not in values:
                setattr(config, name, VENUES[config.venue][name])
        return config

    def to_dict(self):
        return asdict(self)

    def update(self, values):
        """ Sets known fields from a dict, cast to each field's type. Returns what changed. """
        changed = {}
        for f in fields(self):
            if f.name not in values or values[f.name] is None:
                continue
            value = values[f.name]
            if f.type in (str, 'str'):
                value = str(value)
                if f.name == 'market':
                    continue
                if f.name == 'venue' and VENUES.get(value, {}).get('market') != self.market:
                    raise ValueError(f'unknown {self.market} venue {value}')
            elif f.type in (bool, 'bool'):
                value = value if isinstance(value, bool) else str(value).lower() in ('1', 'true', 'yes', 'on')
            elif f.type in (int, 'int'):
                value = int(float(value))
            else:
                value = float(value)
            if getattr(self, f.name) != value:
                changed[f.name] = value
                setattr(self, f.name, value)
        if 'venue' in changed:
            for name in VENUE_FEES:
                setattr(self, name, VENUES[self.venue][name])
        return changed


SEC_FEE = 0.0000206       # Section 31 fee, $20.60 per $1M sold, from April 4 2026
FINRA_TAF = 0.000166      # per share sold, capped at TAF_CAP in rules.order_fee

# Lowest volume tier fees at each venue, read from their fee pages in November
# 2026. shorts is whether the venue lets a small US account short crypto.
VENUE_FEES = ('taker_fee', 'maker_fee', 'min_fee', 'fee_cap', 'per_share_fee', 'sell_fee', 'sell_fee_per_share')
VENUES = {
    'kraken': {'label': 'Kraken Pro, old rates', 'taker_fee': 0.004, 'maker_fee': 0.0025,
               'min_fee': 0.0, 'fee_cap': 0.0, 'shorts': True, 'market': 'crypto',
               'note': 'What the paper agents have used so far.'},
    'kraken_2026': {'label': 'Kraken Pro, reported since July 2026', 'taker_fee': 0.008, 'maker_fee': 0.004,
                    'min_fee': 0.0, 'fee_cap': 0.0, 'shorts': True, 'market': 'crypto',
                    'note': 'Reported for under $2,500 traded in 30 days. Not confirmed on Kraken\'s own page.'},
    'binance_us': {'label': 'Binance.US', 'taker_fee': 0.00019, 'maker_fee': 0.0,
                   'min_fee': 0.0, 'fee_cap': 0.0, 'shorts': False, 'market': 'crypto',
                   'note': 'All spot pairs since April 2026. Not available in every state.'},
    'alpaca': {'label': 'Alpaca', 'taker_fee': 0.0025, 'maker_fee': 0.0015,
               'min_fee': 0.0, 'fee_cap': 0.0, 'shorts': False, 'market': 'crypto',
               'note': '56 crypto pairs, and a free paper trading account.'},
    'ibkr': {'label': 'Interactive Brokers', 'taker_fee': 0.0018, 'maker_fee': 0.0018,
             'min_fee': 1.75, 'fee_cap': 0.01, 'shorts': False, 'market': 'crypto',
             'note': 'At least $1.75 an order, capped at 1% of the order, so small orders pay about 1%.'},

    # US stocks. Every broker passes on the SEC fee ($20.60 per million sold since April 2026)
    # and FINRA's trading activity fee ($0.000166 a share sold, at most $8.30 an order).
    # Shorting needs a margin account; easy to borrow stocks cost well under 1% a year,
    # charged only on shorts held overnight, so it is left out.
    'alpaca_stocks': {'label': 'Alpaca', 'taker_fee': 0.0, 'maker_fee': 0.0, 'min_fee': 0.0, 'fee_cap': 0.0,
                      'per_share_fee': 0.0, 'sell_fee': SEC_FEE, 'sell_fee_per_share': FINRA_TAF,
                      'shorts': True, 'market': 'stocks',
                      'note': 'No commission. Free paper trading account and market data API.'},
    'schwab': {'label': 'Charles Schwab', 'taker_fee': 0.0, 'maker_fee': 0.0, 'min_fee': 0.0, 'fee_cap': 0.0,
               'per_share_fee': 0.0, 'sell_fee': SEC_FEE, 'sell_fee_per_share': FINRA_TAF,
               'shorts': True, 'market': 'stocks',
               'note': 'No commission on online stock and ETF trades.'},
    'ibkr_lite': {'label': 'Interactive Brokers Lite', 'taker_fee': 0.0, 'maker_fee': 0.0, 'min_fee': 0.0,
                  'fee_cap': 0.0, 'per_share_fee': 0.0, 'sell_fee': SEC_FEE, 'sell_fee_per_share': FINRA_TAF,
                  'shorts': True, 'market': 'stocks',
                  'note': 'No commission, but orders are routed for payment, so fills can be a little worse.'},
    'ibkr_pro': {'label': 'Interactive Brokers Pro', 'taker_fee': 0.0, 'maker_fee': 0.0, 'min_fee': 1.0,
                 'fee_cap': 0.01, 'per_share_fee': 0.005, 'sell_fee': SEC_FEE, 'sell_fee_per_share': FINRA_TAF,
                 'shorts': True, 'market': 'stocks',
                 'note': '$0.005 a share, at least $1 and at most 1% of the order. Small orders pay the $1.'},
}
for _v in VENUES.values():
    for _k in VENUE_FEES:
        _v.setdefault(_k, 0.0)


# the original rules, before the changes below
BASELINE = {'limit_orders': False, 'trail_covers_costs': False, 'max_entry_move': 0.0,
            'confirm_spike': False, 'market_filter': False, 'stale_minutes': 0, 'short_spikes': False}

# fixes for fees eating every trade, buying the top of a spike and buying into a falling market,
# plus shorting so a falling market can pay too
RECOMMENDED = {'limit_orders': True, 'trail_covers_costs': True, 'max_entry_move': 0.03,
               'confirm_spike': True, 'market_filter': True, 'stale_minutes': 90, 'short_spikes': True}

# rules the page measures one at a time, with the value that turns each one on
IMPACT = {'limit_orders': True, 'trail_covers_costs': True, 'confirm_spike': True, 'market_filter': True,
          'max_entry_move': 0.03, 'stale_minutes': 90, 'short_spikes': True}

CANDLE_SIZES = [5, 15, 60]

# where the stock agents start: zero commission, exits sized for stocks, which move
# a fraction of what coins do in 5 minutes, and the opening bell's volume ignored
STOCK_DEFAULTS = {'market': 'stocks', 'venue': 'alpaca_stocks', 'taker_fee': 0.0, 'maker_fee': 0.0,
                  'min_fee': 0.0, 'fee_cap': 0.0, 'per_share_fee': 0.0, 'sell_fee': SEC_FEE,
                  'sell_fee_per_share': FINRA_TAF, 'margin_fee': 0.0, 'slippage': 0.0005,
                  'max_pairs': 25, 'min_quote_volume': 20_000_000, 'max_spread': 0.002,
                  'take_profit': 0.015, 'stop_loss': 0.0075, 'trail_trigger': 0.0075, 'trail_pct': 0.005,
                  'stale_move': 0.0025, 'max_hold_minutes': 240, 'risk_per_trade': 0.01,
                  'flat_at_close': True, 'skip_open_minutes': 15}

# a big stock candle is a much smaller move than a big coin candle
STOCK_RECOMMENDED = {**RECOMMENDED, 'max_entry_move': 0.015}
STOCK_IMPACT = {**IMPACT, 'max_entry_move': 0.015, 'flat_at_close': True}
STOCK_BASELINE = {**BASELINE, 'flat_at_close': False}

# settings the page can change, the rest stay fixed
TUNABLE = ['venue', 'limit_orders', 'trail_covers_costs', 'max_entry_move', 'confirm_spike', 'market_filter',
           'short_spikes', 'candle_interval',
           'stale_minutes', 'stale_move', 'min_spike', 'take_profit', 'stop_loss', 'trail_trigger',
           'trail_pct', 'max_hold_minutes', 'max_open_positions', 'max_position_pct']
STOCK_TUNABLE = TUNABLE + ['flat_at_close', 'skip_open_minutes']


def presets(market):
    """ :return: (baseline, recommended, impact, tunable) for 'crypto' or 'stocks' """
    if market == 'stocks':
        return STOCK_BASELINE, STOCK_RECOMMENDED, STOCK_IMPACT, STOCK_TUNABLE
    return BASELINE, RECOMMENDED, IMPACT, TUNABLE

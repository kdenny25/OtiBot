# Settings for the agent pipeline. Paper trading only for now.
from dataclasses import dataclass, asdict, fields


@dataclass
class AgentConfig:
    # paper account
    start_balance: float = 1000.0
    taker_fee: float = 0.004          # Kraken Pro starter tier taker fee
    maker_fee: float = 0.0025         # and maker fee, paid by resting limit orders
    slippage: float = 0.001           # extra 0.1% on top of crossing the spread
    margin_fee: float = 0.0002        # Kraken margin: 0.02% to open a short and every 4 hours it stays open

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

    def to_dict(self):
        return asdict(self)

    def update(self, values):
        """ Sets known fields from a dict, cast to each field's type. Returns what changed. """
        changed = {}
        for f in fields(self):
            if f.name not in values or values[f.name] is None:
                continue
            value = values[f.name]
            if f.type in (bool, 'bool'):
                value = value if isinstance(value, bool) else str(value).lower() in ('1', 'true', 'yes', 'on')
            elif f.type in (int, 'int'):
                value = int(float(value))
            else:
                value = float(value)
            if getattr(self, f.name) != value:
                changed[f.name] = value
                setattr(self, f.name, value)
        return changed


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

# settings the page can change, the rest stay fixed
TUNABLE = ['limit_orders', 'trail_covers_costs', 'max_entry_move', 'confirm_spike', 'market_filter',
           'short_spikes', 'candle_interval',
           'stale_minutes', 'stale_move', 'min_spike', 'take_profit', 'stop_loss', 'trail_trigger',
           'trail_pct', 'max_hold_minutes', 'max_open_positions', 'max_position_pct']

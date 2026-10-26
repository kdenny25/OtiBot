# Settings for the agent pipeline. Paper trading only for now.
from dataclasses import dataclass, asdict


@dataclass
class AgentConfig:
    # paper account
    start_balance: float = 1000.0
    taker_fee: float = 0.004          # Kraken Pro starter tier taker fee
    slippage: float = 0.001           # extra 0.1% on top of crossing the spread

    # scan
    candle_interval: int = 5          # minutes
    max_pairs: int = 25               # most traded USD pairs to watch each cycle

    # volume spike
    spike_lookback: int = 24          # candles in the volume baseline
    min_spike: float = 3.0            # last candle volume / baseline median

    # risk check, stands in for the rug check until DEX pairs are added
    min_quote_volume: float = 250000  # USD traded in the last 24 hours
    max_spread: float = 0.005         # 0.5% between bid and ask

    # size
    risk_per_trade: float = 0.01      # lose at most 1% of equity if the stop hits
    max_position_pct: float = 0.10    # never more than 10% of equity in one pair
    max_open_positions: int = 5

    # exits
    take_profit: float = 0.04
    stop_loss: float = 0.02
    trail_trigger: float = 0.015      # trailing stop turns on once up this much
    trail_pct: float = 0.015          # and closes on this drop from the high
    max_hold_minutes: int = 240

    # loop
    cycle_seconds: int = 60

    def to_dict(self):
        return asdict(self)

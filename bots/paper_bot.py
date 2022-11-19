import numpy as np
import pandas as pd
from exch_apis.coinbase.cb_stream_data import CB_Stream_Data
from strategies.grid_rules import Grid_Rules

class Grid_Paper_Bot:
    def __init__(self):
        self.initial_balance = 0.0  # initial balance of account
        self.cont_balance = 0.0   # initial balance plus any additional contributions.
        self.equity = 0.0 # current equity in account
        self.last_equity = 0.0 # prior days equity changes at 12:00 AM est
        self.trade_pair = ['ETH-USD']

    # checks profit or loss from the previous days balance.
    def current_profit_loss(self):
        """ Calculates profit/loss from prior days balance.

        Returns:
            float: balance change
        """
        balance_change = self.equity - self.last_equity
        print(f'Today\'s portfolio balance change: ${balance_change}')

    def main(self):
        s = CB_Stream_Data()

        bars = s.stream_data()
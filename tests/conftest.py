import os
import sys

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


@pytest.fixture
def ohlc():
    """15 minute ETHUSD candles from test_data/test_ohlc.csv"""
    return pd.read_csv(os.path.join(ROOT, 'test_data', 'test_ohlc.csv'))


@pytest.fixture
def close(ohlc):
    return ohlc['close']

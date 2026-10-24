# Default tickers for the dividend screener. Edit these lists or pass your
# own symbols to dividend_data.refresh().

DIVIDEND_ETFS = [
    'SCHD', 'VYM', 'VIG', 'DGRO', 'HDV', 'NOBL', 'SDY', 'DVY', 'SPYD',
    'SPHD', 'FDVV', 'DGRW', 'DIVO', 'JEPI', 'JEPQ', 'QYLD', 'VYMI', 'VIGI',
    'IDV', 'VNQ', 'SCHY', 'DHS', 'RDVY', 'COWZ',
]

DIVIDEND_STOCKS = [
    'KO', 'PEP', 'JNJ', 'PG', 'MMM', 'ABBV', 'XOM', 'CVX', 'T', 'VZ', 'O',
    'MO', 'PM', 'MCD', 'HD', 'LOW', 'TXN', 'AVGO', 'MSFT', 'AAPL', 'JPM',
    'PFE', 'IBM', 'ABT', 'CAT', 'WMT', 'COST', 'TGT', 'NEE', 'UNP', 'LMT',
    'MRK', 'KMB', 'CL', 'ED', 'SO', 'DUK', 'ADP', 'ITW', 'BLK', 'ENB',
    'MAIN', 'ARCC', 'EPD', 'BMY', 'CSCO', 'HSY', 'SBUX', 'V', 'UNH',
]

DEFAULT_UNIVERSE = DIVIDEND_ETFS + DIVIDEND_STOCKS

# Otibot

The objective is to create a crypto bot using the GRID strategy. 
The app should be developed with the intention of adding additional
strategies in the future.

Deploy this app on Digital Ocean cloud services
https://www.digitalocean.com/products/managed-databases-postgresql

GRID Trading Resources:
https://phemex.com/academy/what-is-grid-trading
https://medium.com/@chris_42047/how-to-implement-a-grid-trading-strategy-python-tutorial-338b38fc5e84

Web interface using Streamlit
https://streamlit.io/

The web interface changed. We are now using Flask for the interface along
with Flask-socketio for asynchronous page updates to display realtime data.

https://flask-socketio.readthedocs.io/en/latest/getting_started.html

Binance connector library:
https://github.com/binance/binance-connector-python

# Phase 1 - Exchange Communication:

Establish a scalable way to interact with exchange data.

I need a class that generates data based on the exchange selected.

This needs to be a tiered system. A master class will contain all required
commands the app will use. The master class will have child classes that
manage communications with each exchange. Every child class will have the
same functions.

The master class will mostly represent the structure of the child classes.

Master Class Functions:
get_crypto_pairs()
get_candle_sticks()
get_current_price()


# Setup

Install dependencies with `pip install -r requirements.txt`, then copy
`.env.example` to `.env` and fill in the database password and exchange
settings. `.env` is ignored by git.

Run the tests from the project root with `python -m pytest`.

# Backtesting

`backtest_module.backtest` runs a strategy over candle data. A strategy is
a function that takes the candle dataframe and returns `(buy, sell)` boolean
series, like `strategies/sample_strategy.py`. A buy goes long, a sell exits
the long and, with `allow_short=True`, goes short.

    bt = backtest(capital=10000, allow_short=True)
    bt.set_fees(0.0026)
    bt.set_slippage(0.0005)    # fills 0.05% worse than the open
    bt.get_historical_data(15, '7/1/2023', '11/5/2023')  # or bt.set_data(df)
    bt.set_strategy(my_strategy)
    bt.run()['stats']          # return, drawdown, sharpe, win rate...
    bt.run_split_window(4)     # same strategy across 4 back to back periods

# Dividend screener

Compares dividend stocks and ETFs at `/dividends` in the Flask app. Pick a
goal (income, growing dividends, stock growth, balanced, low cost or a
custom mix), then filter by yield, dividend growth, years of increases,
payout ratio, payout frequency, price growth, total return, volatility,
ETF expense ratio, size and sector. Enter an amount to invest or a yearly
income target to see projected dividend income.

Data comes from Yahoo Finance through `yfinance` and is cached in
`dividend_module/data/dividend_data.json`. Build or update it with the
Refresh data button or `python -m dividend_module.dividend_data`. The
tickers are listed in `dividend_module/universe.py`.

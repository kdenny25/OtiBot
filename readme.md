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

# Agent pipeline (paper trading)

A live dashboard at `/agents` runs six agents once a minute on Kraken USD
pairs. Each setup runs left to right:

1. **Scan** watches the 25 most traded USD pairs and logs new listings.
2. **Volume** passes pairs whose last closed 5 minute candle traded at
   least 3x the median of the 24 before it and closed green.
3. **Risk check** skips pairs with under $250k traded in 24 hours or a
   spread over 0.5%. This stands in for a rug check until DEX pairs are added.
4. **Size** risks 1% of the balance against a 2% stop, capped at 10% of the
   balance per pair and 5 open positions.
5. **Execute** paper fills buys at the ask and sells at the bid, plus 0.1%
   slippage and a 0.4% fee each way. It exits on +4% take profit, -2% stop
   loss, a 1.5% trailing stop once up 1.5%, or after 4 hours.
6. **Log** records the balance for the equity curve. Every agent call, including
   skips, is stored with its reason.

Press Start on the page to begin. Nothing is sent to an exchange. Settings
are in `agent_module/config.py`. Trades, positions and the event log are
kept in `agent_module/data/agents.db`, so a restart picks up where it left
off. Reset clears them.

The dashboard shows average win, average loss, profit factor and drawdown
next to the win rate, because win rate alone says nothing about whether the
system makes money.

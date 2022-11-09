# Otibot

The objective is to create a crypto bot using the GRID strategy. 
The app should be developed with the intention of adding additional
strategies in the future.

Deploy this app on Digital Ocean cloud services
https://www.digitalocean.com/products/managed-databases-postgresql

GRID Trading Resources:
https://phemex.com/academy/what-is-grid-trading

Web interface using Streamlit
https://streamlit.io/

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


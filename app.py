from dash import Dash, dcc, html, Input, Output
import plotly.graph_objects as go
import pandas as pd
import cbpro
import requests


app = Dash(__name__)

app.layout = html.Div([
    html.H4('Eth stock candlestick chart'),
    dcc.Checklist(
        id='toggle-rangeslider',
        options=[{'label': 'Include Rangeslider',
                  'value': 'slider'}],
        value=['slider']
    ),
    dcc.Graph(id="graph"),
])

c = cbpro.PublicClient()

# generate dataframe containing data.
# TODO: change this chart so it will continuously update at specified intervals
#df = pd.DataFrame(c.get_product_historic_rates(product_id='ETH-USD'))
url = "https://api.exchange.coinbase.com/products/ETH-USD/candles?granularity=60&start=1662814380"
data = requests.get(url)
df = pd.DataFrame(data.json())
df.columns = ['Date', 'Low', 'High', 'Open', 'Close', 'Volume']
df['Date'] = pd.to_datetime(df['Date'], unit='s')

#df.set_index('Date', inplace=True)
#df.sort_values(by='Date', ascending=True, inplace=True)

@app.callback(
    Output("graph", "figure"),
    Input("toggle-rangeslider", "value"))
def display_candlestick(value):

    fig = go.Figure(go.Candlestick(
        x=df['Date'],
        open=df['Open'],
        high=df['High'],
        low=df['Low'],
        close=df['Close']
    ))

    fig.update_layout(
        xaxis_rangeslider_visible='slider' in value
    )

    return fig


app.run_server(debug=True)
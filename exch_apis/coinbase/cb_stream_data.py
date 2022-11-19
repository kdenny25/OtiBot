from cb_config import cb_settings
from websocket import create_connection
import asyncio
import simplejson as json


class CB_Stream_Data:
    def __init__(self) -> None:
        # url to websocket data stream
        self.url = 'wss://ws-feed.exchange.coinbase.com'
        # default products to list
        self.product_ids = ["ETH-USD"]

    def stream_data(self):
        # establish a connection to websock server
        ws = create_connection(self.url)
        # message to be sent to server
        subscription = {
                        "type": "subscribe",
                        "product_ids": self.product_ids,
                        "channels": ["ticker"]
                        }
        # send message
        ws.send(json.dumps(subscription))
        # stream the data
        while True:
            data = json.loads(ws.recv())
            yield data

    def bar_data(self):
        """Generates candlestick data from the ticker stream
        What is needed for candle stick data:
        - Date time
        - Open
        - High
        - Low
        - Close
        """


s = CB_Stream_Data()
s.product_ids = ['ETH-USD']
data = s.stream_data()
for value in data:
    print(value)
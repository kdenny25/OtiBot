from cb_config import cb_settings
from websocket import create_connection
import asyncio
import simplejson as json


class CB_Stream_Data:
    def __init__(self) -> None:

        self.url = 'wss://ws-feed.exchange.coinbase.com'

    def bar_data(self):
        ws = create_connection(self.url)

        subscription = {
                        "type": "subscribe",
                        "product_ids": [
                            "ETH-USD",
                            "BTC-USD"
                        ],
                        "channels": ["ticker"]
                        }

        ws.send(json.dumps(subscription))

        while True:
            data = json.loads(ws.recv())
            yield data


s = CB_Stream_Data()
data = s.bar_data()
for value in data:
    print(value)
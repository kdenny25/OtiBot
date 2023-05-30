import plotly.graph_objects as go
import pandas as pd
import requests
from threading import Lock
from flask import Flask, render_template, session
from flask_socketio import SocketIO, emit
import requests
import os

# Set this variable to "threading", "eventlet" or "gevent" to test the
# different async modes, or leave it set to None for the application to choose
# the best option based on installed packages.
async_mode = None

base_dir = '.'

app = Flask(__name__,
            static_folder=os.path.join(base_dir, 'static'),
            template_folder=os.path.join(base_dir, 'templates'),)

socketio = SocketIO(app, async_mode=async_mode)
thread = None
thread_lock = Lock()

# generate dataframe containing data.
# TODO: change this chart so it will continuously update at specified intervals
#df = pd.DataFrame(c.get_product_historic_rates(product_id='ETH-USD'))
url = "https://api.exchange.coinbase.com/products/ETH-USD/candles?granularity=60&start=1662814380"
data = requests.get(url)
df = pd.DataFrame(data.json())
df.columns = ['Date', 'Low', 'High', 'Open', 'Close', 'Volume']
df['Date'] = pd.to_datetime(df['Date'], unit='s')

url_cb = 'https://api.coinbase.com/v2/prices/btc-usd/spot'

def background_thread():
    """Example of how to send server generated events to clients."""
    count = 0
    while True:
        socketio.sleep(3)
        count += 1
        print(requests.get(url_cb).json())
        price = (requests.get(url_cb).json())['data']['amount']
        socketio.emit('my_response',
                      {'data': price, 'count': count})


@app.route('/')
def index():
    return render_template('index.html', async_mode=socketio.async_mode)

@socketio.event
def my_event(message):
    session['receive_count'] = session.get('receive_count', 0) + 1
    emit('my_response',
         {'data': message['data'], 'count': session['receive_count']})

# receive the test request from client and send back a test response
@socketio.on('test_message')
def handle_message(data):
    print('received message: ' + str(data))
    emit('test_resposne', {'data': 'Test response sent'})

# broadcast a message to all clients
@socketio.on('broadcast_mssage')
def handle_broadcast(data):
    print('received: ' + str(data))
    emit('broadcast_response', {'data': 'Broadcast sent'}, broadcast=True)

@socketio.event
def connect():
    global thread
    with thread_lock:
        if thread is None:
            thread = socketio.start_background_task(background_thread)

    emit('my_response', {'data': 'Connected', 'count': 0})

if __name__ == '__main__':
    socketio.run(app)
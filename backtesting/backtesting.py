
#Example of Simple Moving Average strategy
def strategy(df):
    buy = df['SMA'] > df['SMA'].shift(1)
    buy &= df['RSI'] < 30
    sell = df['SMA'] < df['SMA'].shift(1)
    sell |= df['RSI'] > 70

# Calculate technical indicators
def calculate_indicators(df):
    # simple moving average (SMA)
    sma = df['close'].rolling(window=50).mean()
    df['SMA'] = sma

    # Relative Strength Index (RSI)
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(window=14).mean()
    avg_loss = loss.rolling(window=14).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    df['RSI'] = rsi
#Example of Simple Moving Average strategy
def strategy(df):
    buy = df['SMA'] > df['SMA'].shift(1)
    buy &= df['RSI'] < 30
    sell = df['SMA'] < df['SMA'].shift(1)
    sell |= df['RSI'] > 70
    return buy, sell

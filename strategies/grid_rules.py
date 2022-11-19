class Grid_Rules:

    def __init__(self, current_price) -> None:
        self.grid_size = 5
        self.grid_interval = 100
        self.current_price = current_price
        self.risk_percent = 0.1
        self.strategy = {'Against-the-Trend': 1, 'With-the-Trend': 0}

    def calculate_grid_lines(self):
        """ Calculates the grid lines for the Grid Strategy

        :return:
            float: sell_stop_loss - sell all holdings position to prevent large loss
            float: buy_stop_loss - sell all holdings position to take all profits
            list(floats): buy_lines - grid positions to buy
            list(floats): sell_lines - grid positions to sell
        """
        line_count = self.grid_size
        grid_space = self.grid_interval
        price = self.current_price
        strategy = self.strategy

        sell_stop_loss = price - ((line_count +1) * grid_space) # sell all holdings at lowest
        buy_stop_loss = price + ((line_count +1) * grid_space) # sell all holdings at highest
        buy_lines = []
        sell_lines = []

        if strategy['Against-the-Trend'] == 1:
            # buy and sell lines for Against-the-Trend Strategy
            for i in range(line_count):
                buy_lines.append(price - ((i * grid_space)))
                sell_lines.append(price + ((i * grid_space)))
        else:
            # buy and sell lines for With-the-Trend Strategy
            for j in range(line_count):
                buy_lines.append(price + ((j * grid_space)))
                sell_lines.append(price - ((j * grid_space)))

        return sell_stop_loss, buy_stop_loss, buy_lines, sell_lines

    # risk no more than 10 percent of our account
    # when the stoploss is triggered only 10 percent is lost
    def calculate_position_size(self, account_size, ticker_value):
        """ Calculates the position size of the crypto we are trading.
        This will be how much of a crypto to trade.

        :param
            account_size: total balance of the account
            ticker_value: current value of crypto to trade
        :return
            float:
        """
        line_count = self.grid_size
        grid_space = self.grid_interval

        risk = account_size * self.risk_percent
        tick_value = ticker_value # value of the crypto
        ticks_at_risk = (line_count + 1) * grid_space
        position_size = risk / (ticks_at_risk * tick_value)
        position_size = round(position_size, 2)
        return position_size
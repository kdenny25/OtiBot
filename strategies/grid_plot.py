import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd

def plot_grid_chart(i, product_id, df, current_price, buy_grid, sell_grid,
                    buy_stop_loss, sell_stop_loss):
    """ Generates a plotly chart for the grid strategy.

    :param i: Name of cryptocurrency
    :param product_id: ID of cryptocurrent i.e. 'ETH-USD'
    :param df:
    :param current_price:
    :param buy_grid:
    :param sell_grid:
    :param take_profit:
    :param stop_loss:
    :return:
    """
    light_palette = {
        'bg_color' : '#ffffff',
        'plot_bg_color' : '#ffffff',
        'grid_color': '#e6e6e6',
        'text_color': '#2e2e2e',
        'dark_candle': 'black',
        'light_candle': 'steelblue',
        'volume_color': '#c74e96',
        'border_color': '#2e2e2e',
        'color_1': '#5c285b',
        'color_2': '#802c62',
        'color_3': '#a33262',
        'color_4': '#c43d5c',
        'color_5': '#de4f51',
        'color_6': '#f26841',
        'color_7': '#fd862b',
        'color_8': '#ffa600',
        'color_9': '#3366d6'
    }

    palette = light_palette
    #  Array of colors for support/resistance lines
    buy_grid_colors = ["#e28743", "#e28743", "#e28743", "#e28743", "#e28743"]
    sell_grid_colors = ["#2596be", "#2596be", "#2596be", "#2596be", "#2596be"]

    # create sub plots
    fig = make_subplots(rows=1, cols=1, subplot_titles=[f"{i} {product_id} Chart"],
                        specs=[[{"secondary_y": False}]],
                        vertical_spacing=0.04, shared_xaxes=True)

    # Plot close price
    # x is the datetime
    # y is closing price
    fig.add_trace(
        go.Scatter(x=df.index,
                   y=df['Close'],
                   line=dict(color='blue', width=1),
                   name=f"Close"),
        row=1, col=1
    )

    # current price
    fig.add_hline(y=current_price,
                  line_width=0.6,
                  line_dash='solid',
                  line_color='blue',
                  row=1, col=1
                  )

    # add buy and sell grids
    for idx, level in enumerate(buy_grid):
        line_color = buy_grid_colors[idx] if idx < len(buy_grid_colors) else buy_grid_colors[0]

        fig.add_hline(y=level,
                      line_width=0.6,
                      line_dash='dash',
                      line_color=line_color,
                      row=1, col=1)

    #stop loss
    fig.add_hline(y=buy_stop_loss,
                  line_width=0.6,
                  line_dash='solid',
                  line_color='red',
                  row=1, col=1)

    for idx, level in enumerate(sell_grid):
        line_color = sell_grid_colors[idx] if idx < len(sell_grid_colors) else sell_grid_colors[0]

        fig.add_hline(y=level,
                      line_width=1,
                      line_dash='dash',
                      line_color=line_color,
                      row=1, col=1)

    # stop loss
    fig.add_hline(y=sell_stop_loss, line_width=1, line_dash='solid', line_color='red', row=1, col=1)

    fig.update_layout(
        title={'text': '', 'x': 0.5},
        font=dict(family="Verdana", size=12, color=palette['text_color']),
        autosize=True,
        width=1280,
        height=720,
        xaxis={'rangeslider': {'visible': False}},
        plot_bgcolor=palette["plot_bg_color"],
        paper_bgcolor=palette['bg_color']
    )

    fig.update_yaxes(visible=False, secondary_y=True)

    # Change grid color
    fig.update_xaxes(showline=True,
                     linewidth=1,
                     linecolor=palette['grid_color'],
                     gridcolor=palette['grid_color'])

    fig.update_yaxes(showline=True,
                     linewidth=1,
                     linecolor=palette['grid_color'],
                     gridcolor=palette['grid_color'])

    file_name = f'{i}_{product_id}_grid_trading_1.png'
    fig.write_image(file_name, format='png')

    return fig
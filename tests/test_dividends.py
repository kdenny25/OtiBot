import json

import numpy as np
import pandas as pd
import pytest
from flask import Flask

from dividend_module import metrics, dividend_data, screener

AS_OF = pd.Timestamp('2026-06-30')


def quarterly(start_year, end_year, first, growth):
    """ Quarterly dividends growing by `growth` per year. """
    dates, values = [], []
    for year in range(start_year, end_year + 1):
        for month in (3, 6, 9, 12):
            date = pd.Timestamp(year, month, 15)
            if date <= AS_OF:
                dates.append(date)
                values.append(first * (1 + growth) ** (year - start_year) / 4)
    return pd.Series(values, index=pd.DatetimeIndex(dates))


def daily_prices(years, start, yearly_growth):
    index = pd.bdate_range(end=AS_OF, periods=int(252 * years))
    t = (index - index[0]).days.to_numpy() / 365.25
    return pd.Series(start * (1 + yearly_growth) ** t, index=index)


# metrics

def test_annual_dividends_drops_current_year():
    yearly = metrics.annual_dividends(quarterly(2020, 2026, 1.0, 0.1), AS_OF)
    assert yearly.index.tolist() == [2020, 2021, 2022, 2023, 2024, 2025]
    assert yearly.loc[2020] == pytest.approx(1.0)


def test_dividend_cagr_and_streak():
    divs = quarterly(2014, 2026, 1.0, 0.07)
    assert metrics.dividend_cagr(divs, 5, AS_OF) == pytest.approx(0.07)
    assert metrics.dividend_cagr(divs, 10, AS_OF) == pytest.approx(0.07)
    assert metrics.consecutive_increase_years(divs, AS_OF) == 11
    assert np.isnan(metrics.dividend_cagr(quarterly(2023, 2026, 1, .1), 5, AS_OF))


def test_streak_resets_after_a_cut():
    divs = quarterly(2015, 2026, 1.0, 0.05)
    divs[divs.index.year == 2021] *= 0.5
    assert metrics.consecutive_increase_years(divs, AS_OF) == 4


def test_payout_frequency():
    monthly = pd.Series(1.0, index=pd.date_range('2025-01-15', periods=12, freq='MS'))
    assert metrics.payout_frequency(monthly, AS_OF) == 'Monthly'
    assert metrics.payout_frequency(quarterly(2024, 2026, 1, 0), AS_OF) == 'Quarterly'
    assert metrics.payout_frequency(pd.Series(dtype=float), AS_OF) == 'None'


def test_price_metrics():
    prices = daily_prices(6, 100, 0.10)
    assert metrics.annualized_return(prices, 5) == pytest.approx(0.10, abs=0.002)
    assert np.isnan(metrics.annualized_return(prices, 10))
    assert metrics.max_drawdown(pd.Series([100, 120, 90, 130])) == pytest.approx(-0.25)


# provider data -> record

def test_build_record_etf():
    info = {'quoteType': 'ETF', 'longName': 'Test Dividend ETF', 'category': 'Large Value',
            'regularMarketPrice': 50.0, 'netExpenseRatio': 0.06, 'totalAssets': 6e10}
    divs = quarterly(2014, 2026, 1.6, 0.08)
    prices = daily_prices(11, 30, 0.05)
    rec = dividend_data.build_record('TST', info, divs, prices, prices * 1.2, AS_OF)

    ttm = divs[divs.index > AS_OF - pd.DateOffset(years=1)].sum()
    assert rec['type'] == 'ETF'
    assert rec['dividend_yield'] == pytest.approx(ttm / 50)
    assert rec['expense_ratio'] == pytest.approx(0.0006)
    assert rec['payout_ratio'] is None
    assert rec['dividend_growth_5y'] == pytest.approx(0.08)
    assert rec['payout_frequency'] == 'Quarterly'
    assert rec['size'] == 6e10
    json.dumps(rec)   # must be JSON safe


def test_build_record_stock_without_history():
    info = {'quoteType': 'EQUITY', 'shortName': 'New Co', 'sector': 'Technology',
            'currentPrice': 10.0, 'payoutRatio': 0.4, 'exDividendDate': 1767225600}
    rec = dividend_data.build_record('NEW', info, pd.Series(dtype=float),
                                     daily_prices(.5, 10, 0), daily_prices(.5, 10, 0), AS_OF)
    assert rec['type'] == 'Stock'
    assert rec['dividend_yield'] == 0
    assert rec['dividend_growth_5y'] is None
    assert rec['expense_ratio'] is None
    assert rec['ex_dividend_date'] == '2026-01-01'
    json.dumps(rec)


# screener

def record(symbol, kind='Stock', **values):
    base = {'symbol': symbol, 'name': symbol + ' Inc', 'type': kind, 'sector': 'Utilities',
            'dividend_yield': .03, 'dividend_growth_5y': .05, 'years_of_increases': 10,
            'payout_ratio': .5 if kind == 'Stock' else None,
            'expense_ratio': .001 if kind == 'ETF' else None,
            'price_growth_5y': .05, 'total_return_5y': .08, 'volatility': .2,
            'payout_frequency': 'Quarterly', 'size': 5e10}
    base.update(values)
    return base


RECORDS = [
    record('HIGHYLD', dividend_yield=.08, price_growth_5y=-.02, total_return_5y=.05, payout_ratio=.95),
    record('GROWER', dividend_yield=.01, dividend_growth_5y=.15, price_growth_5y=.20, total_return_5y=.22),
    record('STEADY', dividend_yield=.035, dividend_growth_5y=.06, years_of_increases=50, payout_ratio=.45),
    record('CHEAPETF', 'ETF', dividend_yield=.035, expense_ratio=.0006, sector='Large Value'),
    record('PRICYETF', 'ETF', dividend_yield=.09, expense_ratio=.0065, payout_frequency='Monthly',
           sector='Derivative Income'),
]


def symbols(results):
    return [r['symbol'] for r in results]


def test_goals_change_the_top_pick():
    assert symbols(screener.screen(RECORDS, goal='growth'))[0] == 'GROWER'
    assert symbols(screener.screen(RECORDS, goal='income'))[0] in ('HIGHYLD', 'PRICYETF')
    assert symbols(screener.screen(RECORDS, goal='custom', dividend_weight=0))[0] == 'GROWER'
    top_income = symbols(screener.screen(RECORDS, goal='custom', dividend_weight=1))[0]
    assert top_income != 'GROWER'


def test_scores_are_0_to_100_and_sorted():
    results = screener.screen(RECORDS, goal='balanced')
    scores = [r['score'] for r in results]
    assert scores == sorted(scores, reverse=True)
    assert all(0 <= s <= 100 for s in scores)


def test_filters():
    def run(**filters):
        return set(symbols(screener.screen(RECORDS, filters)))

    assert run(type='ETF') == {'CHEAPETF', 'PRICYETF'}
    assert run(min_yield=.03, max_yield=.05) == {'STEADY', 'CHEAPETF'}
    assert run(max_expense_ratio=.001) == {'HIGHYLD', 'GROWER', 'STEADY', 'CHEAPETF'}
    assert run(max_payout_ratio=.6) == {'GROWER', 'STEADY', 'CHEAPETF', 'PRICYETF'}
    assert run(min_years_of_increases=20) == {'STEADY'}
    assert run(min_price_growth=.1) == {'GROWER'}
    assert run(frequencies=['Monthly']) == {'PRICYETF'}
    assert run(sectors=['Large Value', 'Derivative Income']) == {'CHEAPETF', 'PRICYETF'}
    assert run(search='grow') == {'GROWER'}


def test_missing_values_fail_range_filters_but_still_score():
    records = RECORDS + [record('NOHIST', dividend_growth_5y=None)]
    assert 'NOHIST' not in symbols(screener.screen(records, {'min_dividend_growth': 0}))
    assert 'NOHIST' in symbols(screener.screen(records))


def test_income_targets():
    results = screener.screen(RECORDS, {'search': 'steady'}, invest_amount=10000, target_income=700)
    r = results[0]
    assert r['annual_income'] == pytest.approx(350)
    assert r['income_10y'] == pytest.approx(350 * 1.06 ** 10)
    assert r['amount_needed'] == pytest.approx(20000)


def test_empty_inputs():
    assert screener.screen([]) == []
    assert screener.screen(RECORDS, {'min_yield': 1}) == []


# flask routes

@pytest.fixture
def client(tmp_path, monkeypatch):
    from dividend_module.routes import dividends_bp
    import os

    path = tmp_path / 'cache.json'
    path.write_text(json.dumps({'updated': '2026-06-30 12:00 UTC', 'records': RECORDS, 'errors': {}}))
    monkeypatch.setattr(dividend_data, 'CACHE_PATH', str(path))
    monkeypatch.setattr(dividend_data.load, '__defaults__', (str(path),))

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    app = Flask(__name__, template_folder=os.path.join(root, 'templates'))
    app.register_blueprint(dividends_bp)
    return app.test_client()


def test_page_renders(client):
    resp = client.get('/dividends')
    assert resp.status_code == 200
    assert b'Dividend screener' in resp.data
    assert b'Growing dividends' in resp.data


def test_api_filters_and_goal(client):
    data = client.get('/api/dividends?type=ETF&max_expense_ratio=0.001&goal=income').get_json()
    assert data['total'] == 5
    assert symbols(data['results']) == ['CHEAPETF']
    assert 'Large Value' in data['sectors']

    data = client.get('/api/dividends?frequency=Monthly&frequency=Quarterly&min_yield=bad').get_json()
    assert len(data['results']) == 5

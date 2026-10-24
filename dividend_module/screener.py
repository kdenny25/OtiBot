# Filters and ranks dividend stocks and ETFs by an investment goal.
import numpy as np
import pandas as pd

# factor weights for each goal. Factors are scored 0 to 1 by percentile rank
# within the filtered results, so scores compare what's on screen.
GOALS = {
    'income': {'label': 'Maximize income',
               'weights': {'yield': .50, 'safety': .25, 'dividend_growth': .10,
                           'cost': .10, 'low_volatility': .05}},
    'dividend_growth': {'label': 'Growing dividends',
                        'weights': {'dividend_growth': .40, 'safety': .25, 'yield': .15,
                                    'price_growth': .10, 'cost': .10}},
    'growth': {'label': 'Stock growth',
               'weights': {'price_growth': .40, 'total_return': .30,
                           'dividend_growth': .20, 'cost': .10}},
    'balanced': {'label': 'Balanced income and growth',
                 'weights': {'yield': .25, 'dividend_growth': .20, 'total_return': .25,
                             'safety': .15, 'cost': .10, 'low_volatility': .05}},
    'low_cost': {'label': 'Low cost',
                 'weights': {'cost': .40, 'total_return': .30, 'yield': .20,
                             'low_volatility': .10}},
}

# filter name -> (column, comparison)
RANGE_FILTERS = {
    'min_yield': ('dividend_yield', '>='),
    'max_yield': ('dividend_yield', '<='),
    'min_dividend_growth': ('dividend_growth_5y', '>='),
    'min_years_of_increases': ('years_of_increases', '>='),
    'min_price_growth': ('price_growth_5y', '>='),
    'min_total_return': ('total_return_5y', '>='),
    'max_volatility': ('volatility', '<='),
    'min_size': ('size', '>='),
}


def custom_weights(dividend_weight):
    """
    Weights for a slider between dividends (1.0) and stock growth (0.0).
    """
    w = min(max(float(dividend_weight), 0.0), 1.0)
    return {'yield': .55 * w, 'safety': .20 * w, 'dividend_growth': .25 * w,
            'total_return': .55 * (1 - w), 'price_growth': .45 * (1 - w)}


def _rank(series, ascending=True):
    """ Percentile rank 0-1, missing values get a neutral 0.5. """
    if series.notna().sum() < 2:
        return pd.Series(0.5, index=series.index)
    ranked = series.rank(pct=True, ascending=ascending)
    return ranked.fillna(0.5)


def factor_scores(df):
    """
    :return:
        pandas.DataFrame: 0-1 score per factor, higher is better
    """
    safety = (_rank(df['years_of_increases'])
              + _rank(df['payout_ratio'], ascending=False)) / 2
    # stocks have no fund fee, so they count as 0 for cost
    cost = df['expense_ratio'].where(df['type'] == 'ETF', 0.0)
    return pd.DataFrame({
        'yield': _rank(df['dividend_yield']),
        'dividend_growth': _rank(df['dividend_growth_5y']),
        'price_growth': _rank(df['price_growth_5y']),
        'total_return': _rank(df['total_return_5y']),
        'safety': safety,
        'cost': _rank(cost, ascending=False),
        'low_volatility': _rank(df['volatility'], ascending=False),
    }, index=df.index)


def apply_filters(df, filters):
    """
    :param:
        df (pandas.DataFrame): screener rows

        filters (dict): any of type ('Stock' or 'ETF'), the RANGE_FILTERS
                        keys, max_expense_ratio (ETFs only), max_payout_ratio
                        (stocks only), frequencies (list), sectors (list),
                        search (text in symbol or name)
    :return:
        pandas.DataFrame: rows that pass every filter. A row missing the
                          value a range filter needs is dropped.
    """
    mask = pd.Series(True, index=df.index)

    kind = filters.get('type')
    if kind in ('Stock', 'ETF'):
        mask &= df['type'] == kind

    for name, (column, op) in RANGE_FILTERS.items():
        value = filters.get(name)
        if value is None:
            continue
        mask &= df[column] >= value if op == '>=' else df[column] <= value

    # fees only apply to ETFs and payout ratios only to stocks
    if filters.get('max_expense_ratio') is not None:
        mask &= (df['type'] != 'ETF') | (df['expense_ratio'] <= filters['max_expense_ratio'])
    if filters.get('max_payout_ratio') is not None:
        mask &= (df['type'] != 'Stock') | (df['payout_ratio'] <= filters['max_payout_ratio'])

    if filters.get('frequencies'):
        mask &= df['payout_frequency'].isin(filters['frequencies'])
    if filters.get('sectors'):
        mask &= df['sector'].isin(filters['sectors'])

    search = (filters.get('search') or '').strip().lower()
    if search:
        mask &= (df['symbol'].str.lower().str.contains(search, regex=False)
                 | df['name'].str.lower().str.contains(search, regex=False))

    return df[mask]


def screen(records, filters=None, goal='balanced', dividend_weight=None,
           invest_amount=None, target_income=None):
    """
    Filters records and sorts them by how well they match the goal.

    :param:
        records (list of dict): rows from dividend_data

        filters (dict): see apply_filters

        goal (str): a GOALS key, or 'custom' to use dividend_weight

        dividend_weight (float): 0 (all stock growth) to 1 (all dividends),
                                 only used when goal is 'custom'

        invest_amount (float): adds annual_income and income_10y (income in
                               10 years if the dividend keeps its 5 year
                               growth rate) for this amount invested

        target_income (float): adds amount_needed, the investment needed
                               for this yearly dividend income
    :return:
        list of dict: matching records with score (0-100) and factor scores,
                      best match first
    """
    if not records:
        return []
    df = apply_filters(pd.DataFrame(records), filters or {})
    if df.empty:
        return []

    weights = custom_weights(dividend_weight if dividend_weight is not None else .5) \
        if goal == 'custom' else GOALS.get(goal, GOALS['balanced'])['weights']

    factors = factor_scores(df)
    score = sum(factors[name] * weight for name, weight in weights.items())
    df = df.assign(score=(score / sum(weights.values()) * 100).round(1))
    for name in factors:
        df[f'score_{name}'] = factors[name].round(3)

    yield_ = df['dividend_yield']
    if invest_amount:
        df['annual_income'] = invest_amount * yield_
        growth = df['dividend_growth_5y'].fillna(0).clip(lower=-.5)
        df['income_10y'] = df['annual_income'] * (1 + growth) ** 10
    if target_income:
        df['amount_needed'] = (target_income / yield_).where(yield_ > 0)

    df = df.sort_values('score', ascending=False)
    df = df.replace([np.inf, -np.inf], np.nan).astype(object).where(df.notna(), None)
    return df.to_dict(orient='records')

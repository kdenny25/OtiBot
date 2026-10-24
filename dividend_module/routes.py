# Flask pages for the dividend screener.
import threading

from flask import Blueprint, jsonify, render_template, request

from dividend_module import dividend_data
from dividend_module.screener import GOALS, screen

dividends_bp = Blueprint('dividends', __name__)

_refresh_lock = threading.Lock()
_refresh_state = {'running': False, 'error': None}

FLOAT_ARGS = ['min_yield', 'max_yield', 'min_dividend_growth', 'min_price_growth',
              'min_total_return', 'max_volatility', 'min_size', 'max_expense_ratio',
              'max_payout_ratio']


def _float_arg(name):
    value = request.args.get(name, '').strip()
    try:
        return float(value) if value else None
    except ValueError:
        return None


@dividends_bp.route('/dividends')
def dividends_page():
    return render_template('dividends.html', goals=GOALS)


@dividends_bp.route('/api/dividends')
def dividends_api():
    cache = dividend_data.load()
    filters = {name: _float_arg(name) for name in FLOAT_ARGS}
    filters['min_years_of_increases'] = _float_arg('min_years_of_increases')
    filters['type'] = request.args.get('type')
    filters['frequencies'] = request.args.getlist('frequency')
    filters['sectors'] = request.args.getlist('sector')
    filters['search'] = request.args.get('search')

    results = screen(cache['records'], filters,
                     goal=request.args.get('goal', 'balanced'),
                     dividend_weight=_float_arg('dividend_weight'),
                     invest_amount=_float_arg('invest_amount'),
                     target_income=_float_arg('target_income'))

    sectors = sorted({r['sector'] for r in cache['records'] if r.get('sector')})
    return jsonify({'updated': cache['updated'],
                    'total': len(cache['records']),
                    'sectors': sectors,
                    'refreshing': _refresh_state['running'],
                    'refresh_error': _refresh_state['error'],
                    'results': results})


def _run_refresh():
    try:
        dividend_data.refresh()
        _refresh_state['error'] = None
    except Exception as e:
        _refresh_state['error'] = str(e)
    finally:
        _refresh_state['running'] = False


@dividends_bp.route('/api/dividends/refresh', methods=['POST'])
def dividends_refresh():
    """ Downloads fresh data in the background. Takes a few minutes. """
    with _refresh_lock:
        if not _refresh_state['running']:
            _refresh_state['running'] = True
            threading.Thread(target=_run_refresh, daemon=True).start()
    return jsonify({'refreshing': True})

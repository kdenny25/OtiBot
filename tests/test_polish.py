import os
import subprocess
import sys

from dividend_module import dividend_data, routes as div_routes

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_yfinance_inplace_warning_is_silenced():
    # pytest installs its own warning filters, so check in a fresh interpreter
    script = (
        "import warnings\n"
        "import dividend_module.dividend_data\n"
        "msg = 'The inplace keyword in DataFrame.sort_index is deprecated'\n"
        "warnings.warn_explicit(msg, FutureWarning, 'utils.py', 606, module='yfinance.utils')\n"
        "warnings.warn_explicit(msg, FutureWarning, 'mine.py', 1, module='otibot.mine')\n")
    result = subprocess.run([sys.executable, '-c', script], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    # ours still shows, yfinance's doesn't
    assert 'mine.py:1' in result.stderr
    assert 'utils.py' not in result.stderr


def test_refresh_reports_progress(tmp_path, monkeypatch):
    monkeypatch.setattr(dividend_data, 'fetch_record', lambda s: {'symbol': s})
    seen = []
    dividend_data.refresh(['AAA', 'BBB'], path=str(tmp_path / 'c.json'),
                          progress=lambda done, total, symbol: seen.append((done, total, symbol)))
    assert seen == [(0, 2, 'AAA'), (1, 2, 'BBB')]


def test_refresh_progress_reaches_the_api(monkeypatch):
    div_routes._progress(40, 74, 'LOW')
    assert {k: div_routes._refresh_state[k] for k in ('done', 'total', 'symbol')} == \
        {'done': 40, 'total': 74, 'symbol': 'LOW'}


def test_failed_refresh_keeps_existing_data(tmp_path, monkeypatch):
    import json
    import pytest
    path = tmp_path / 'c.json'
    path.write_text(json.dumps({'updated': 'before', 'records': [{'symbol': 'KO'}], 'errors': {}}))

    def fail(symbol):
        raise ConnectionError('blocked')
    monkeypatch.setattr(dividend_data, 'fetch_record', fail)
    with pytest.raises(RuntimeError, match='kept the existing data'):
        dividend_data.refresh(['AAA'], path=str(path))
    assert json.loads(path.read_text())['updated'] == 'before'

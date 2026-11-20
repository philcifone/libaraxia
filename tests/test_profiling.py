"""Dev-only request timing (utils/profiling.py, ROADMAP 16.0g step 1)."""
from conftest import login


def test_off_by_default(client, db, people):
    login(client, 'alice')
    assert 'Server-Timing' not in client.get('/books/').headers


def test_on_it_times_and_counts_statements(monkeypatch, db, people):
    from app import create_app
    from utils.rate_limiting import limiter
    monkeypatch.setenv('PROFILE_REQUESTS', '1')
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    limiter.enabled = False
    client = app.test_client()
    login(client, 'alice')
    timing = client.get('/books/').headers['Server-Timing']
    assert timing.startswith('app;dur=') and 'statements' in timing
    assert int(timing.split('"')[1].split()[0]) > 0

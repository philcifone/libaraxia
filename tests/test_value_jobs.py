"""Bulk Fetch values (ROADMAP 16.0a, migration 039): a cover_jobs row of
kind 'value', run by the same worker. The fetch itself is faked."""
import pytest

from conftest import add_book, login, scalar
from utils import valuation


@pytest.fixture
def fake_values(monkeypatch):
    """eBay 'set up'; every item is worth 1000 cents plus its id, except
    the ids in `misses` (no value) and `busy` (busy once)."""
    monkeypatch.setenv('EBAY_CLIENT_ID', 'x')
    monkeypatch.setenv('EBAY_CLIENT_SECRET', 'y')
    monkeypatch.delenv('DISCOGS_TOKEN', raising=False)
    from utils import cover_jobs
    monkeypatch.setattr(cover_jobs, 'BUSY_WAIT', 0)
    state = {'asked': [], 'misses': set(), 'busy': set()}

    def fetch(row):
        state['asked'].append(row['id'])
        if row['id'] in state['busy']:
            state['busy'].discard(row['id'])
            return valuation.Result('ebay', busy=True, message='busy')
        if row['id'] in state['misses']:
            return valuation.Result('ebay', message='Only 1 listing')
        return valuation.Result('ebay', cents=1000 + row['id'], note='eBay: median asking price of 5 listings')
    monkeypatch.setattr(valuation, 'fetch', fetch)
    return state


def item(db, owner, isbn='9780316066525', **cols):
    b = add_book(db, owner)
    db.execute('UPDATE books SET isbn = ? WHERE id = ?', (isbn, b))
    for k, v in cols.items():
        db.execute(f'UPDATE books SET {k} = ? WHERE id = ?', (v, b))
    db.commit()
    return b


def run(app):
    from utils import cover_jobs
    with app.app_context():
        cover_jobs.run_pending(worker='t', pause=0)


def start(client, **form):
    return client.post('/values/start', data=form, headers={'X-Requested-With': 'XMLHttpRequest'})


def test_value_job_values_your_shelf_and_skips_the_rest(app, client, db, people, fake_values):
    mine = item(db, people['alice'])
    typed = item(db, people['alice'], value_cents=500, value_source='manual')
    recent = item(db, people['alice'], value_cents=700, value_source='ebay',
                  value_checked_at=scalar(db, "SELECT datetime('now', '-3 days')"))
    old = item(db, people['alice'], value_cents=700, value_source='ebay', value_checked_at='2020-01-01')
    no_code = item(db, people['alice'], isbn=None)
    removed = item(db, people['alice'], removed_at='2026-01-01')
    bobs = item(db, people['bob'])
    login(client, 'alice')
    job = start(client).get_json()['job']
    assert job['kind'] == 'value' and job['total'] == 2
    run(app)
    assert sorted(fake_values['asked']) == sorted([mine, old])
    assert scalar(db, 'SELECT value_cents FROM books WHERE id = ?', mine) == 1000 + mine
    assert scalar(db, 'SELECT value_source FROM books WHERE id = ?', old) == 'ebay'
    assert scalar(db, 'SELECT value_cents FROM books WHERE id = ?', typed) == 500
    for untouched in (recent, no_code, removed, bobs):
        assert untouched not in fake_values['asked']
    row = db.execute('SELECT status, checked, found FROM cover_jobs WHERE id = ?', (job['id'],)).fetchone()
    assert tuple(row) == ('done', 2, 2)


def test_value_job_never_overwrites_a_value_typed_meanwhile(app, client, db, people, fake_values, monkeypatch):
    mine = item(db, people['alice'])
    login(client, 'alice')
    start(client)
    # Typed by hand after the job started, before the worker reaches it
    db.execute("UPDATE books SET value_cents = 42, value_source = 'manual' WHERE id = ?", (mine,))
    db.commit()
    run(app)
    assert scalar(db, 'SELECT value_cents FROM books WHERE id = ?', mine) == 42


def test_value_job_sections_skip_choice_and_busy_retry(app, client, db, people, fake_values):
    book = item(db, people['alice'], value_cents=1, value_source='ebay',
                value_checked_at=scalar(db, "SELECT datetime('now', '-1 day')"))
    video = db.execute("INSERT INTO books (title, author, added_by, media_type, format, barcode) "
                       "VALUES ('Jaws', 'S', ?, 'video', 'VHS', '0012345678905')", (people['alice'],)).lastrowid
    db.commit()
    fake_values['busy'].add(book)
    login(client, 'alice')
    # Books only, and refetch recent values too
    job = start(client, media_type='book', skip_recent='0').get_json()['job']
    assert job['total'] == 1
    run(app)
    assert fake_values['asked'] == [book, book]          # busy once, then asked again
    assert video not in fake_values['asked']
    assert scalar(db, 'SELECT value_cents FROM books WHERE id = ?', book) == 1000 + book


def test_everyone_scope_is_admin_only(client, db, people, fake_values):
    item(db, people['bob'])
    login(client, 'bob')
    assert start(client, scope='all').status_code == 403
    client.get('/auth/logout')
    login(client, 'alice')
    assert start(client, scope='all').get_json()['job']['total'] == 1


def test_nothing_to_value(client, db, people, fake_values):
    login(client, 'alice')
    data = start(client).get_json()
    assert data['job'] is None and 'Nothing to value' in data['message']


def test_settings_shows_fetch_values_only_with_a_source(client, db, people, monkeypatch):
    login(client, 'bob')
    monkeypatch.delenv('EBAY_CLIENT_ID', raising=False)
    monkeypatch.delenv('DISCOGS_TOKEN', raising=False)
    assert 'id="fetch-values"' not in client.get('/user/settings').get_data(as_text=True)
    monkeypatch.setenv('DISCOGS_TOKEN', 't')
    assert 'id="fetch-values"' in client.get('/user/settings').get_data(as_text=True)

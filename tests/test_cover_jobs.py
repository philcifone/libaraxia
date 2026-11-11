"""Background cover fetching (utils/cover_jobs.py, blueprints/covers.py).

In tests kick() never starts a thread; run_pending() is called directly, with
the network lookup faked."""
import pytest

from conftest import add_book, login, scalar


@pytest.fixture
def fake_lookup(monkeypatch):
    """Covers are 'found' for every ISBN except those in `misses`."""
    import utils.book_utils as bu
    state = {'looked_up': [], 'misses': set()}

    def details(isbn):
        state['looked_up'].append(isbn)
        return None if isbn in state['misses'] else {'local_cover_url': f'uploads/{isbn}.jpg'}
    monkeypatch.setattr(bu, 'fetch_book_details_from_isbn', details)
    return state


def book_with_isbn(db, owner, isbn):
    b = add_book(db, owner, f'Book {isbn}', 'X')
    db.execute('UPDATE books SET isbn = ? WHERE id = ?', (isbn, b))
    db.commit()
    return b


def run_worker(app, worker='test-worker'):
    from utils import cover_jobs
    with app.app_context():
        cover_jobs.run_pending(worker=worker, pause=0)


def start(client, scope='own'):
    return client.post('/covers/start', data={'scope': scope},
                       headers={'X-Requested-With': 'XMLHttpRequest'})


def test_own_job_only_touches_your_books(app, client, db, people, fake_lookup):
    mine = book_with_isbn(db, people['alice'], '9780000000019')
    bobs = book_with_isbn(db, people['bob'], '9780000000026')
    login(client, 'alice')
    job = start(client).get_json()['job']
    assert (job['status'], job['total']) == ('running', 1)

    run_worker(app)
    assert fake_lookup['looked_up'] == ['9780000000019']
    assert scalar(db, 'SELECT cover_image_url FROM books WHERE id = ?', mine) == 'uploads/9780000000019.jpg'
    assert scalar(db, 'SELECT cover_image_url FROM books WHERE id = ?', bobs) is None
    status = client.get('/covers/status').get_json()['job']
    assert (status['status'], status['checked'], status['found']) == ('done', 1, 1)


def test_books_without_a_cover_online_are_tried_once_and_the_job_ends(app, client, db, people, fake_lookup):
    for isbn in ('9780000000019', '9780000000026', '9780000000033'):
        book_with_isbn(db, people['alice'], isbn)
    fake_lookup['misses'] = {'9780000000026'}
    login(client, 'alice')
    start(client)
    run_worker(app)
    assert len(fake_lookup['looked_up']) == 3
    job = client.get('/covers/status').get_json()['job']
    assert (job['status'], job['checked'], job['found']) == ('done', 3, 2)


def test_all_scope_is_admin_only(app, client, db, people, fake_lookup):
    book_with_isbn(db, people['alice'], '9780000000019')
    book_with_isbn(db, people['bob'], '9780000000026')
    login(client, 'bob')
    assert start(client, 'all').status_code == 403
    client.post('/auth/logout')
    login(client, 'alice')  # admin
    assert start(client, 'all').get_json()['job']['total'] == 2
    run_worker(app)
    assert scalar(db, "SELECT COUNT(*) FROM books WHERE cover_image_url LIKE 'uploads/%'") == 2


def test_starting_twice_returns_the_running_job(client, db, people, fake_lookup):
    book_with_isbn(db, people['alice'], '9780000000019')
    login(client, 'alice')
    first = start(client).get_json()['job']
    second = start(client).get_json()['job']
    assert first['id'] == second['id']
    assert scalar(db, 'SELECT COUNT(*) FROM cover_jobs') == 1


def test_nothing_to_do(client, db, people):
    login(client, 'alice')
    data = start(client).get_json()
    assert data['job'] is None and 'already has a cover' in data['message']


def test_stop_and_dismiss(app, client, db, people, fake_lookup):
    book_with_isbn(db, people['alice'], '9780000000019')
    login(client, 'alice')
    job = start(client).get_json()['job']
    assert client.post(f"/covers/{job['id']}/stop").get_json()['job']['status'] == 'cancelled'
    run_worker(app)
    assert fake_lookup['looked_up'] == []          # a stopped job isn't picked up
    client.post(f"/covers/{job['id']}/dismiss")
    assert client.get('/covers/status').get_json()['job'] is None


def test_other_users_cannot_stop_your_job(client, db, people, fake_lookup):
    book_with_isbn(db, people['alice'], '9780000000019')
    login(client, 'alice')
    job = start(client).get_json()['job']
    client.post('/auth/logout')
    login(client, 'bob')
    client.post(f"/covers/{job['id']}/stop")
    assert scalar(db, 'SELECT status FROM cover_jobs WHERE id = ?', job['id']) == 'running'


def test_live_worker_keeps_its_job_and_a_dead_one_is_taken_over(app, client, db, people, fake_lookup):
    book_with_isbn(db, people['alice'], '9780000000019')
    login(client, 'alice')
    job = start(client).get_json()['job']
    # another process is working on it, heartbeat fresh: leave it alone
    db.execute("UPDATE cover_jobs SET worker = 'other', heartbeat_at = CURRENT_TIMESTAMP WHERE id = ?", (job['id'],))
    db.commit()
    run_worker(app)
    assert fake_lookup['looked_up'] == []
    # that process died (e.g. a deploy restart): its heartbeat goes stale
    db.execute("UPDATE cover_jobs SET heartbeat_at = datetime('now', '-1 hour') WHERE id = ?", (job['id'],))
    db.commit()
    run_worker(app)
    assert fake_lookup['looked_up'] == ['9780000000019']
    assert scalar(db, 'SELECT status FROM cover_jobs WHERE id = ?', job['id']) == 'done'


def test_resume_carries_on_from_the_cursor(app, client, db, people, fake_lookup):
    first = book_with_isbn(db, people['alice'], '9780000000019')
    book_with_isbn(db, people['alice'], '9780000000026')
    fake_lookup['misses'] = {'9780000000019'}
    login(client, 'alice')
    job = start(client).get_json()['job']
    # as if a worker checked the first book (no cover found) and then died
    db.execute("UPDATE cover_jobs SET checked = 1, last_book_id = ?, worker = 'dead', "
               "heartbeat_at = datetime('now', '-1 hour') WHERE id = ?", (first, job['id']))
    db.commit()
    run_worker(app)
    assert fake_lookup['looked_up'] == ['9780000000026']   # the first one isn't retried


def test_panel_renders_only_with_a_job(client, db, people, fake_lookup):
    login(client, 'alice')
    page = client.get('/base/index').get_data(as_text=True)
    assert "data-job='null'" in page
    book_with_isbn(db, people['alice'], '9780000000019')
    start(client)
    page = client.get('/base/index').get_data(as_text=True)
    assert '"status": "running"' in page or '"status":"running"' in page


def test_profile_button_starts_a_job_and_redirects(client, db, people, fake_lookup):
    book_with_isbn(db, people['alice'], '9780000000019')
    login(client, 'alice')
    r = client.post('/covers/start', data={'scope': 'own', 'next': '/user/alice'})
    assert r.status_code == 302 and r.headers['Location'].endswith('/user/alice')
    r = client.post('/covers/start', data={'scope': 'own', 'next': '//evil.example'})
    assert r.headers['Location'].endswith('/base/index') or r.headers['Location'].endswith('/base/')


def test_a_cover_whose_file_is_gone_is_fetched_again(app, client, db, people, fake_lookup, static_root):
    """A stored link to a deleted file shows as no cover on the grid, so the
    fetcher counts it as missing and replaces it; a cover whose file is
    there is left alone."""
    uploads = static_root / 'uploads'
    uploads.mkdir()
    (uploads / 'here.jpg').write_bytes(b'x')
    gone = book_with_isbn(db, people['alice'], '9780000000019')
    kept = book_with_isbn(db, people['alice'], '9780000000026')
    db.execute("UPDATE books SET cover_image_url = 'uploads/gone.jpg' WHERE id = ?", (gone,))
    db.execute("UPDATE books SET cover_image_url = 'uploads/here.jpg' WHERE id = ?", (kept,))
    db.commit()
    login(client, 'alice')
    assert start(client).get_json()['job']['total'] == 1
    run_worker(app)
    assert fake_lookup['looked_up'] == ['9780000000019']
    assert scalar(db, 'SELECT cover_image_url FROM books WHERE id = ?', gone) == 'uploads/9780000000019.jpg'
    assert scalar(db, 'SELECT cover_image_url FROM books WHERE id = ?', kept) == 'uploads/here.jpg'


def test_an_empty_or_absent_uploads_folder_marks_nothing_missing(db, people, static_root):
    """An unmounted or moved uploads folder must not make every cover look
    lost (the fetcher would overwrite the whole catalog's links)."""
    from utils.book_utils import missing_cover_sql
    b = book_with_isbn(db, people['alice'], '9780000000019')
    db.execute("UPDATE books SET cover_image_url = 'uploads/gone.jpg' WHERE id = ?", (b,))
    db.commit()
    count = 'SELECT COUNT(*) ' + missing_cover_sql()
    assert scalar(db, count) == 0                  # no uploads folder
    (static_root / 'uploads').mkdir()
    assert scalar(db, count) == 0                  # an empty one
    (static_root / 'uploads' / 'other.jpg').write_bytes(b'x')
    assert scalar(db, count) == 1

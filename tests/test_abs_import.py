"""The Audiobookshelf import: sync, staging, the plan's boxes and choices
(ROADMAP 16.0e step 4, docs/AUDIOBOOKSHELF-SPEC.md section 8). The client
is stubbed: what ABS would answer is set per test."""
import json
import re
from types import SimpleNamespace

import pytest

from conftest import add_book, login
from test_layout import unbalanced_tags
from utils import abs_import
from utils import audiobookshelf as abs_

SECRET = 'test-secret-key'
MS = 1700000000000          # 2023-11-14, a time ABS reports in milliseconds


def item(title, author='An Author', audio=1, ebook='', **meta):
    return {'id': meta.pop('id', 'li_' + title.lower().replace(' ', '_')), 'library_id': 'lib_a',
            'title': title, 'subtitle': '', 'author': author, 'narrator': meta.get('narrator', 'Ray Porter'),
            'series': '', 'publisher': '', 'year': '2021', 'genres': [], 'isbn': meta.get('isbn', ''),
            'asin': '', 'description': '', 'duration': 36000, 'audio_files': audio,
            'ebook_format': ebook, 'missing': meta.get('missing', False)}


def progress(item_id, value=0.5, finished=False, ebook=None):
    return {'libraryItemId': item_id, 'progress': 1 if finished else value, 'isFinished': finished,
            'startedAt': MS, 'finishedAt': MS + 86400000 * 30 if finished else None,
            'currentTime': 36000 if finished else round(36000 * value), 'duration': 36000,
            'lastUpdate': MS, 'ebookProgress': ebook}


@pytest.fixture
def abs_server(monkeypatch):
    """serve(items, progress_rows) sets what the stubbed client returns."""
    monkeypatch.setenv('AUDIOBOOKSHELF_URL', 'http://192.168.1.171:13378')

    def serve(items, rows):
        monkeypatch.setattr(abs_, 'me', lambda token, timeout=None: {
            'abs_user_id': 'usr_1', 'username': 'phil', 'books': rows})
        monkeypatch.setattr(abs_, 'library_items', lambda token: {i['id']: i for i in items})
    return serve


def who(user_id):
    return SimpleNamespace(id=user_id, is_admin=False)


def boxes(plan):
    return {r.title: r.box for r in plan.rows}


# --- sync --------------------------------------------------------------------

def test_sync_stages_only_what_you_started(db, people, abs_server):
    abs_server(
        [item('Finished'), item('Halfway'), item('Untouched'), item('Zero'), item('Gone', missing=True),
         item('Ebook Only', audio=0, ebook='epub'), item('Both', audio=3, ebook='epub'),
         item('Broken', audio=0)],
        [progress('li_finished', finished=True), progress('li_halfway', 0.4), progress('li_zero', 0),
         progress('li_gone', 0.2), progress('li_ebook_only', 0, ebook=0.3), progress('li_both', 0.1)])
    alice = who(people['alice'])
    assert abs_import.sync(db, alice, 'key') == 4
    staged = {r['abs_item_id']: json.loads(r['data']) for r in db.execute('SELECT * FROM abs_staging')}
    assert set(staged) == {'li_finished', 'li_halfway', 'li_ebook_only', 'li_both'}
    assert staged['li_ebook_only']['format'] == 'Ebook' and staged['li_ebook_only']['progress'] == 0.3
    assert staged['li_both']['format'] == 'Audiobook'          # audio wins
    assert staged['li_finished']['finished'] and staged['li_finished']['finished_on'] == '2023-12-14'

    # The option brings in the rest, flagged, never the broken or missing
    assert abs_import.sync(db, alice, 'key', include_unstarted=True) == 6
    assert {r['abs_item_id'] for r in db.execute('SELECT * FROM abs_staging')} >= {'li_untouched', 'li_zero'}


# --- the plan's boxes --------------------------------------------------------

def test_boxes(db, people, abs_server):
    alice, bob, carol = people['alice'], people['bob'], people['carol']
    add_book(db, alice, 'Mine', 'An Author')
    add_book(db, bob, 'Household', 'An Author')                 # bob shares alice's household
    add_book(db, carol, 'Friends', 'An Author')                 # carol is only a friend
    wished = add_book(db, alice, 'Wished', 'An Author')
    db.execute('INSERT INTO wishlist (user_id, book_id) VALUES (?, ?)', (alice, wished))
    linked = add_book(db, alice, 'Linked', 'An Author')
    again = add_book(db, alice, 'Done Since', 'An Author')
    db.executemany("INSERT INTO abs_links (user_id, abs_item_id, book_id, outcome, finished_at) VALUES (?, ?, ?, ?, ?)",
                   [(alice, 'li_linked', linked, 'created', None),
                    (alice, 'li_done_since', again, 'created', None),
                    (alice, 'li_skipped', None, 'skipped', None)])
    db.commit()
    titles = ['New Finished', 'New Progress', 'Mine', 'Household', 'Friends', 'Wished', 'Linked',
              'Done Since', 'Skipped', 'Never']
    abs_server([item(t) for t in titles],
               [progress('li_new_finished', finished=True), progress('li_new_progress'),
                progress('li_mine', finished=True), progress('li_household'), progress('li_friends'),
                progress('li_wished', finished=True), progress('li_linked'),
                progress('li_done_since', finished=True), progress('li_skipped')])
    abs_import.sync(db, who(alice), 'key', include_unstarted=True)
    plan = abs_import.plan(db, who(alice))
    assert boxes(plan) == {
        'New Finished': 'finished_new', 'New Progress': 'progress_new',
        'Mine': 'match', 'Household': 'match',
        'Friends': 'progress_new',              # a friend's copy never matches
        'Wished': 'finished_new',               # a wish isn't a copy
        'Linked': 'imported', 'Done Since': 'finished_since', 'Skipped': 'skipped_before',
        'Never': 'not_started',
    }
    by = {r.title: r for r in plan.rows}
    assert by['Household'].book['owner'] == 'bob'
    assert (by['New Finished'].choice, by['Mine'].choice, by['Never'].choice) == ('add', 'attach', 'skip')
    assert by['New Finished'].adds == ['a new unshelved audiobook', 'Read', 'listened 14 Nov to 14 Dec 2023']
    assert by['Mine'].adds == ['Read', 'listened 14 Nov to 14 Dec 2023']
    assert by['Done Since'].adds == ['Read', 'listened 14 Nov to 14 Dec 2023']    # no open session: a new one
    assert by['Never'].adds == [] and not by['Never'].writes


def test_attach_adds_only_whats_missing(db, people, abs_server):
    alice = people['alice']
    book = add_book(db, alice, 'Mine', 'An Author')
    db.execute("INSERT INTO collections (user_id, book_id, status) VALUES (?, ?, 'did not finish')", (alice, book))
    db.execute("INSERT INTO reading_sessions (user_id, book_id, date_started, date_completed)"
               " VALUES (?, ?, '2023-11-14', '2023-12-14')", (alice, book))
    db.commit()
    abs_server([item('Mine')], [progress('li_mine', finished=True)])
    abs_import.sync(db, who(alice), 'key')
    row = abs_import.plan(db, who(alice)).rows[0]
    assert row.box == 'match' and row.adds == [] and not row.writes     # your status and session stand


def test_choices_saved_and_checked(db, people, abs_server):
    alice = who(people['alice'])
    abs_server([item('One'), item('Two')], [progress('li_one', finished=True), progress('li_two')])
    abs_import.sync(db, alice, 'key')
    plan = abs_import.choose(db, alice, {'li_one': 'skip', 'li_two': 'attach', 'li_nope': 'add'})
    by = {r.title: r for r in plan.rows}
    assert by['One'].choice == 'skip' and by['Two'].choice == 'add'     # attach isn't a choice there
    assert db.execute("SELECT choice FROM abs_staging WHERE abs_item_id = 'li_one'").fetchone()[0] == 'skip'
    abs_import.choose(db, alice, {'li_one': 'add'})                      # back to the default: stored as NULL
    assert db.execute("SELECT choice FROM abs_staging WHERE abs_item_id = 'li_one'").fetchone()[0] is None


def test_plan_fingerprint_moves_with_your_data(db, people, abs_server):
    alice = people['alice']
    book = add_book(db, alice, 'Mine', 'An Author')
    abs_server([item('Mine')], [progress('li_mine')])
    abs_import.sync(db, who(alice), 'key')
    before = abs_import.plan(db, who(alice)).fingerprint
    db.execute("INSERT INTO collections (user_id, book_id, status) VALUES (?, ?, 'currently reading')", (alice, book))
    db.commit()
    assert abs_import.plan(db, who(alice)).fingerprint != before


# --- routes ------------------------------------------------------------------

def connect(db, user_id):
    db.execute("INSERT INTO abs_accounts (user_id, token_enc, abs_user_id, abs_username) VALUES (?, ?, 'usr_1', 'phil')",
               (user_id, abs_.seal('key', SECRET)))
    db.commit()


def test_sync_route_to_review(client, db, people, abs_server):
    connect(db, people['alice'])
    abs_server([item('Project Hail Mary', 'Andy Weir')], [progress('li_project_hail_mary', finished=True)])
    login(client, 'alice')
    r = client.post('/abs/sync', data={})
    assert r.status_code == 302 and r.headers['Location'].endswith('/abs/review')
    page = client.get('/abs/review').get_data(as_text=True)
    assert 'data-abs-review' in page and 'Project Hail Mary' in page and 'read by Ray Porter' in page
    assert unbalanced_tags(page) == []                          # test_every_page_loads can't reach it
    assert 'data-box="finished_new"' in page and 'name="choice_li_project_hail_mary"' in page
    assert '/audiobookshelf/item/li_project_hail_mary' in page

    client.post('/abs/choose', data={'box_finished_new': 'skip'})
    assert db.execute('SELECT choice FROM abs_staging').fetchone()[0] == 'skip'
    assert 'data-abs-review-link' in client.get('/user/settings').get_data(as_text=True)

    client.post('/abs/discard')
    assert db.execute('SELECT COUNT(*) FROM abs_staging').fetchone()[0] == 0
    assert client.get('/abs/review').status_code == 302


def test_sync_needs_a_connection(client, db, people, abs_server):
    abs_server([], [])
    login(client, 'bob')
    r = client.post('/abs/sync', follow_redirects=True)
    assert 'Connect to Audiobookshelf first.' in r.get_data(as_text=True)


def test_review_is_yours_alone(client, db, people, abs_server):
    connect(db, people['alice'])
    abs_server([item('Secret Listen')], [progress('li_secret_listen')])
    abs_import.sync(db, who(people['alice']), 'key')
    login(client, 'bob')
    assert 'Secret Listen' not in client.get('/abs/review', follow_redirects=True).get_data(as_text=True)


# --- apply, undo, covers (step 5) ---------------------------------------------

def book_row(db, title):
    return db.execute('SELECT * FROM books WHERE title = ?', (title,)).fetchone()


def status_of(db, user_id, book_id):
    row = db.execute('SELECT status FROM collections WHERE user_id = ? AND book_id = ?', (user_id, book_id)).fetchone()
    return row and row[0]


def sessions_of(db, user_id, book_id):
    return [tuple(r) for r in db.execute('SELECT date_started, date_completed FROM reading_sessions '
                                         'WHERE user_id = ? AND book_id = ? ORDER BY session_id', (user_id, book_id))]


def run(db, user_id, choices=None):
    u = who(user_id)
    if choices:
        abs_import.choose(db, u, choices)
    return abs_import.apply(db, u, abs_import.plan(db, u).fingerprint)


def test_apply_creates_unowned_books(app, db, people, abs_server):
    alice = people['alice']
    abs_server([item('Heard', narrator='Ray Porter'), item('Going'), item('Screen', audio=0, ebook='epub')],
               [progress('li_heard', finished=True), progress('li_going', 0.3),
                progress('li_screen', 0, ebook=0.5)])
    abs_import.sync(db, who(alice), 'key')
    result = run(db, alice)
    assert result['counts']['created'] == 3 and result['edit_id']

    heard = book_row(db, 'Heard')
    assert (heard['format'], heard['owned'], heard['narrator'], heard['runtime_minutes'], heard['added_by']) == \
        ('Audiobook', 0, 'Ray Porter', 600, alice)
    assert heard['created_at'].startswith('2023-11-14')                  # dated when you started
    assert status_of(db, alice, heard['id']) == 'read'
    assert sessions_of(db, alice, heard['id']) == [('2023-11-14', '2023-12-14')]
    quiet = db.execute('SELECT quiet FROM collections WHERE book_id = ?', (heard['id'],)).fetchone()[0]
    assert quiet == 1                                                     # not in friends' feed

    going = book_row(db, 'Going')
    assert status_of(db, alice, going['id']) == 'currently reading'
    assert sessions_of(db, alice, going['id']) == [('2023-11-14', None)]
    screen = book_row(db, 'Screen')
    assert (screen['format'], screen['owned'], screen['narrator'], screen['runtime_minutes']) == ('Ebook', 0, None, None)
    links = {r['abs_item_id']: r['outcome'] for r in db.execute('SELECT * FROM abs_links')}
    assert links == {'li_heard': 'created', 'li_going': 'created', 'li_screen': 'created'}
    assert db.execute('SELECT COUNT(*) FROM abs_staging').fetchone()[0] == 0

    # A second sync and import creates nothing
    abs_import.sync(db, who(alice), 'key')
    assert {r.box for r in abs_import.plan(db, who(alice)).rows} == {'imported'}
    assert run(db, alice)['edit_id'] is None
    assert db.execute("SELECT COUNT(*) FROM books WHERE title IN ('Heard', 'Going', 'Screen')").fetchone()[0] == 3


def test_ownership_never_written(app, db, people, abs_server):
    """Phil's rule: nothing from ABS is owned unless the catalogue says so."""
    alice = people['alice']
    paper = add_book(db, alice, 'Paper', 'An Author')                       # owned, a printed book
    heard = add_book(db, alice, 'Heard Before', 'An Author')
    db.execute("UPDATE books SET owned = 0, format = 'Audiobook', runtime_minutes = 99 WHERE id = ?", (heard,))
    db.execute("INSERT INTO collections (user_id, book_id, status) VALUES (?, ?, 'want to read')", (alice, heard))
    db.commit()
    abs_server([item('Paper'), item('Heard Before'), item('Fresh'), item('Never')],
               [progress('li_paper', finished=True), progress('li_heard_before', finished=True),
                progress('li_fresh')])
    abs_import.sync(db, who(alice), 'key', include_unstarted=True)
    run(db, alice, {'li_never': 'want'})

    p = book_row(db, 'Paper')
    assert (p['owned'], p['format'], p['narrator'], p['runtime_minutes']) == (1, None, None, None)
    assert status_of(db, alice, paper) == 'read'
    h = book_row(db, 'Heard Before')
    assert (h['owned'], h['narrator'], h['runtime_minutes']) == (0, 'Ray Porter', 99)   # filled where empty only
    assert status_of(db, alice, heard) == 'read'                                       # Want to Read moved on
    assert book_row(db, 'Fresh')['owned'] == 0 and book_row(db, 'Never')['owned'] == 0
    assert status_of(db, alice, book_row(db, 'Never')['id']) == 'want to read'
    assert sessions_of(db, alice, book_row(db, 'Never')['id']) == []


def test_in_progress_then_finished_completes_the_session(app, db, people, abs_server, monkeypatch):
    alice = people['alice']
    abs_server([item('Long One')], [progress('li_long_one', 0.2)])
    abs_import.sync(db, who(alice), 'key')
    run(db, alice)
    book = book_row(db, 'Long One')['id']
    abs_server([item('Long One')], [progress('li_long_one', finished=True)])
    abs_import.sync(db, who(alice), 'key')
    row = abs_import.plan(db, who(alice)).rows[0]
    assert row.box == 'finished_since' and row.adds == ['Read', 'finished 14 Dec 2023']
    run(db, alice)
    assert status_of(db, alice, book) == 'read'
    assert sessions_of(db, alice, book) == [('2023-11-14', '2023-12-14')]   # the same session, completed
    abs_import.sync(db, who(alice), 'key')
    assert abs_import.plan(db, who(alice)).rows[0].box == 'imported'


def test_skip_is_remembered(app, db, people, abs_server):
    alice = people['alice']
    abs_server([item('Not For Me')], [progress('li_not_for_me', finished=True)])
    abs_import.sync(db, who(alice), 'key')
    run(db, alice, {'li_not_for_me': 'skip'})
    assert book_row(db, 'Not For Me') is None
    abs_import.sync(db, who(alice), 'key')
    row = abs_import.plan(db, who(alice)).rows[0]
    assert (row.box, row.choice, row.choices) == ('skipped_before', 'skip', ['skip', 'add'])
    run(db, alice, {'li_not_for_me': 'add'})
    assert book_row(db, 'Not For Me')['owned'] == 0


def test_stale_review_is_refused(app, db, people, abs_server):
    alice = people['alice']
    mine = add_book(db, alice, 'Mine', 'An Author')
    abs_server([item('Mine')], [progress('li_mine')])
    abs_import.sync(db, who(alice), 'key')
    seen = abs_import.plan(db, who(alice)).fingerprint
    db.execute("INSERT INTO collections (user_id, book_id, status) VALUES (?, ?, 'read')", (alice, mine))
    db.commit()
    with pytest.raises(abs_import.StalePlan):
        abs_import.apply(db, who(alice), seen)
    assert sessions_of(db, alice, mine) == []


def test_undo(app, db, people, abs_server):
    from utils import bulk
    alice, bob = people['alice'], people['bob']
    mine = add_book(db, alice, 'Mine', 'An Author')
    db.execute("INSERT INTO collections (user_id, book_id, status) VALUES (?, ?, 'want to read')", (alice, mine))
    db.commit()
    abs_server([item('Mine'), item('New One'), item('Reviewed')],
               [progress('li_mine', finished=True), progress('li_new_one'), progress('li_reviewed', finished=True)])
    abs_import.sync(db, who(alice), 'key')
    edit_id = run(db, alice)['edit_id']
    reviewed = book_row(db, 'Reviewed')['id']
    db.execute("INSERT INTO read_data (user_id, book_id, rating) VALUES (?, ?, 5)", (bob, reviewed))  # bob's data
    db.commit()

    result = bulk.undo(db, who(alice), edit_id)
    assert result.changed == 2 and result.skipped == 1
    assert book_row(db, 'New One') is None
    assert book_row(db, 'Reviewed') is not None                     # someone else has data on it: kept
    assert status_of(db, alice, mine) == 'want to read' and sessions_of(db, alice, mine) == []
    assert db.execute('SELECT COUNT(*) FROM abs_links').fetchone()[0] == 0
    # A fresh sync offers them again (Mine matches; Reviewed is still your book)
    abs_import.sync(db, who(alice), 'key')
    assert boxes(abs_import.plan(db, who(alice))) == {'Mine': 'match', 'New One': 'progress_new',
                                                      'Reviewed': 'match'}


def test_undo_reopens_a_completed_session(app, db, people, abs_server):
    from utils import bulk
    alice = people['alice']
    abs_server([item('Long One')], [progress('li_long_one', 0.2)])
    abs_import.sync(db, who(alice), 'key')
    run(db, alice)
    book = book_row(db, 'Long One')['id']
    abs_server([item('Long One')], [progress('li_long_one', finished=True)])
    abs_import.sync(db, who(alice), 'key')
    edit_id = run(db, alice)['edit_id']
    bulk.undo(db, who(alice), edit_id)
    assert status_of(db, alice, book) == 'currently reading'
    assert sessions_of(db, alice, book) == [('2023-11-14', None)]
    assert db.execute('SELECT finished_at FROM abs_links').fetchone()[0] is None


def test_covers_from_abs(app, db, people, abs_server, static_root, monkeypatch):
    from io import BytesIO
    from PIL import Image
    alice = people['alice']
    monkeypatch.setitem(app.config, 'UPLOAD_FOLDER', str(static_root / 'uploads'))
    picture = BytesIO()
    img = Image.new('RGB', (300, 300))        # square, like most audiobook covers; not a flat colour
    img.putdata([(x % 256, y % 256, (x + y) % 256) for y in range(300) for x in range(300)])
    img.save(picture, 'PNG')
    monkeypatch.setattr(abs_, 'cover', lambda token, item_id: picture.getvalue() if item_id == 'li_one' else b'junk')
    abs_server([item('One'), item('Two')], [progress('li_one'), progress('li_two')])
    abs_import.sync(db, who(alice), 'key')
    run(db, alice)
    with app.app_context():
        assert abs_import.fetch_covers(db, who(alice), 'key') == (1, 0)
    cover = book_row(db, 'One')['cover_image_url']
    assert cover.startswith('uploads/') and (static_root / cover).is_file()
    assert not book_row(db, 'Two')['cover_image_url']
    with app.app_context():
        assert abs_import.fetch_covers(db, who(alice), 'key', budget=-1) == (0, 1)   # out of time: next time


def test_apply_route_backs_up_first(client, db, people, abs_server, monkeypatch):
    from utils import personal_backups
    connect(db, people['alice'])
    monkeypatch.setattr(abs_, 'cover', lambda token, item_id: b'')
    abs_server([item('Project Hail Mary', 'Andy Weir')], [progress('li_project_hail_mary', finished=True)])
    login(client, 'alice')
    client.post('/abs/sync')
    fingerprint = abs_import.plan(db, who(people['alice'])).fingerprint
    page = client.post('/abs/apply', data={'fingerprint': fingerprint}, follow_redirects=True).get_data(as_text=True)
    assert 'Audiobookshelf import: 1 added.' in page and 'Undo it under Recent bulk edits.' in page
    assert book_row(db, 'Project Hail Mary')['owned'] == 0
    kinds = [b['kind'] for b in personal_backups.list_backups(people['alice'])]
    assert kinds == ['audiobookshelf']
    assert 'Audiobookshelf import' in client.get('/user/settings').get_data(as_text=True)


def test_apply_route_refuses_a_stale_review(client, db, people, abs_server):
    connect(db, people['alice'])
    abs_server([item('One')], [progress('li_one')])
    login(client, 'alice')
    client.post('/abs/sync')
    page = client.post('/abs/apply', data={'fingerprint': 'old'}, follow_redirects=True).get_data(as_text=True)
    assert 'Something changed since you looked' in page and book_row(db, 'One') is None


def test_backup_restore_brings_links_back(app, db, people, abs_server):
    from utils import personal_backups
    alice = people['alice']
    abs_server([item('Kept')], [progress('li_kept', finished=True)])
    abs_import.sync(db, who(alice), 'key')
    run(db, alice)
    with app.app_context():
        made = personal_backups.create(db, alice, 'alice')
        db.execute('DELETE FROM abs_links')
        db.commit()
        personal_backups.restore(db, alice, made['name'])
    assert db.execute('SELECT abs_item_id, outcome FROM abs_links').fetchall()[0][:] == ('li_kept', 'created')


# --- the item page: provenance and the live line (step 6) ---------------------

def test_progress_words():
    now = MS + 2 * 86400000
    line = abs_import.progress_line({'progress': 0.43, 'currentTime': 14122, 'duration': 32842,
                                     'lastUpdate': MS, 'isFinished': False}, 'Audiobook', None, now)
    assert line == {'text': 'Audiobookshelf: 43 %, 5 h 12 min left, last listened 2 days ago.', 'unsynced': False,
                    'progress': 0.43}
    sliver = abs_import.progress_line({'progress': 0.001, 'lastUpdate': MS}, 'Audiobook', None, MS + 60 * 86400000)
    assert sliver['text'] == 'Audiobookshelf: under 1 %, last listened on 14 Nov 2023.'
    ebook = abs_import.progress_line({'ebookProgress': 0.25, 'lastUpdate': now}, 'Ebook', None, now)
    assert ebook['text'] == 'Audiobookshelf: 25 %, last read today.'
    assert ebook['progress'] == 0.25                # the cover's ring
    done = abs_import.progress_line({'isFinished': True, 'finishedAt': MS}, 'Audiobook', {'finished_at': None}, now)
    assert done == {'text': 'Finished in Audiobookshelf on 14 Nov 2023.', 'unsynced': True}   # no ring
    assert 'progress' not in abs_import.progress_line(None, 'Audiobook', None, now)
    assert not abs_import.progress_line({'isFinished': True, 'finishedAt': MS}, 'Audiobook',
                                        {'finished_at': MS}, now)['unsynced']


def test_item_page_note_and_live_line(client, db, people, abs_server, monkeypatch):
    from blueprints import audiobookshelf as abs_bp
    alice = people['alice']
    connect(db, alice)
    abs_server([item('Heard')], [progress('li_heard', 0.5)])
    abs_import.sync(db, who(alice), 'key')
    run(db, alice)
    book = book_row(db, 'Heard')['id']
    abs_bp._PROGRESS_CACHE.clear()
    calls = []
    monkeypatch.setattr(abs_, 'progress', lambda token, item_id, timeout=None: calls.append(item_id) or
                        {'progress': 0.5, 'currentTime': 18000, 'duration': 36000, 'isFinished': False})

    login(client, 'alice')
    page = client.get(f'/books/book/{book}').get_data(as_text=True)
    assert 'data-abs-note' in page and 'From your Audiobookshelf import' in page
    assert f'data-url="/abs/progress/{book}"' in page
    answer = client.get(f'/abs/progress/{book}').get_json()
    assert answer['success'] and answer['text'] == 'Audiobookshelf: 50 %, 5 h 0 min left.'
    assert answer['link'].endswith('/audiobookshelf/item/li_heard') and 'key' not in json.dumps(answer)
    client.get(f'/abs/progress/{book}')
    assert calls == ['li_heard']                                   # the second answer is cached

    # bob (household) sees the book, never alice's link or progress
    login(client, 'bob')
    page = client.get(f'/books/book/{book}').get_data(as_text=True)
    assert 'data-abs-note' not in page and 'data-abs-progress' not in page
    assert client.get(f'/abs/progress/{book}').status_code == 404


def test_live_line_quiet_when_abs_is_down(client, db, people, abs_server, monkeypatch):
    from blueprints import audiobookshelf as abs_bp
    alice = people['alice']
    connect(db, alice)
    abs_server([item('Heard')], [progress('li_heard', 0.5)])
    abs_import.sync(db, who(alice), 'key')
    run(db, alice)
    abs_bp._PROGRESS_CACHE.clear()

    def down(*a, **k):
        raise abs_.AbsError()
    monkeypatch.setattr(abs_, 'progress', down)
    login(client, 'alice')
    r = client.get(f"/abs/progress/{book_row(db, 'Heard')['id']}")
    assert r.status_code == 502 and r.get_json() == {'success': False, 'error': "Audiobookshelf didn't answer."}


# --- the Books filter: From Audiobookshelf ------------------------------------

def grid_titles(client, url):
    r = client.get(url, headers={'X-Requested-With': 'XMLHttpRequest'})
    assert r.status_code == 200
    return sorted(b['title'] for b in r.get_json()['books'])


def test_from_audiobookshelf_filter(client, db, people, abs_server):
    alice = people['alice']
    mine = add_book(db, alice, 'Paper Copy', 'An Author')                  # owned: the listen attaches
    add_book(db, alice, 'Untouched', 'An Author')
    gr = db.execute("INSERT INTO goodreads_imports (user_id, filename, row_count) VALUES (?, 'x.csv', 1)",
                    (alice,)).lastrowid
    db.execute("INSERT INTO goodreads_rows (import_id, line, book_id, outcome) VALUES (?, 1, ?, 'matched')",
               (gr, add_book(db, alice, 'From Goodreads', 'An Author')))
    db.commit()
    abs_server([item('Paper Copy'), item('Heard')], [progress('li_paper_copy', finished=True),
                                                     progress('li_heard', finished=True)])
    abs_import.sync(db, who(alice), 'key')
    run(db, alice)

    login(client, 'alice')
    assert grid_titles(client, '/base/index?from=audiobookshelf') == ['Paper Copy']          # on the shelf
    assert grid_titles(client, '/base/index?from=audiobookshelf&show=all') == ['Heard', 'Paper Copy']
    assert grid_titles(client, '/base/index?from=audiobookshelf&from=goodreads&show=all') == \
        ['From Goodreads', 'Heard', 'Paper Copy']                                         # either source
    page = client.get('/base/index?from=audiobookshelf').get_data(as_text=True)
    assert re.search(r'id="from_audiobookshelf"[^>]*checked', page)

    # Always your own imports: bob shares alice's shelf but imported nothing
    login(client, 'bob')
    assert grid_titles(client, '/base/index?from=audiobookshelf&show=all') == []
    assert mine


def test_from_audiobookshelf_hidden_without_a_server(client, db, people):
    login(client, 'alice')
    page = client.get('/base/index').get_data(as_text=True)
    assert 'id="from_goodreads"' in page and 'id="from_audiobookshelf"' not in page


# --- listening again: Libaraxia keeps every listen ----------------------------

DAY = 86400000
FIRST_DONE = MS + 30 * DAY                        # progress()'s finish: 14 Dec 2023


def again(item_id, *, finished_at=None, position=0.25, updated=MS + 60 * DAY):
    """ABS after a replay: startedAt is still the first listen's (ABS never
    changes it), and `progress` can stay at 1 until you finish again."""
    return {'libraryItemId': item_id, 'progress': 1, 'isFinished': bool(finished_at),
            'startedAt': MS, 'finishedAt': finished_at, 'currentTime': 36000 * (1 if finished_at else position),
            'duration': 36000, 'lastUpdate': updated, 'ebookProgress': None}


@pytest.fixture
def sessions(monkeypatch):
    """ABS's listening sessions per item: {item id: [startedAt ms, ...]}."""
    starts = {}
    monkeypatch.setattr(abs_, 'listening_starts', lambda token, item_id, timeout=None: starts.get(item_id, []))
    return starts


def test_listening_again_then_finishing_again(app, db, people, abs_server, sessions):
    alice = people['alice']
    abs_server([item('Twice')], [progress('li_twice', finished=True)])
    abs_import.sync(db, who(alice), 'key')
    run(db, alice)
    book = book_row(db, 'Twice')['id']

    # Started again on 2 Feb 2024 (sessions before the first finish don't count)
    sessions['li_twice'] = [MS + 2 * DAY, FIRST_DONE - DAY, MS + 80 * DAY, MS + 90 * DAY]
    abs_server([item('Twice')], [again('li_twice', updated=MS + 95 * DAY)])
    abs_import.sync(db, who(alice), 'key')
    row = abs_import.plan(db, who(alice)).rows[0]
    assert (row.box, row.choice, row.choices) == ('listening_again', 'again', ['again', 'later'])
    assert row.data['progress'] == 0.25                    # from the position, not ABS's stale 1
    assert row.adds == ['Currently Reading', 'started again 2 Feb 2024']
    run(db, alice)
    assert status_of(db, alice, book) == 'currently reading'
    assert sessions_of(db, alice, book) == [('2023-11-14', '2023-12-14'), ('2024-02-02', None)]

    # Still going: nothing new
    abs_import.sync(db, who(alice), 'key')
    assert abs_import.plan(db, who(alice)).rows[0].box == 'imported'

    # Finished: the open session is completed, the first one untouched
    abs_server([item('Twice')], [again('li_twice', finished_at=MS + 100 * DAY)])
    abs_import.sync(db, who(alice), 'key')
    row = abs_import.plan(db, who(alice)).rows[0]
    assert row.box == 'finished_since' and row.adds == ['Read', 'finished 22 Feb 2024']
    run(db, alice)
    assert status_of(db, alice, book) == 'read'
    assert sessions_of(db, alice, book) == [('2023-11-14', '2023-12-14'), ('2024-02-02', '2024-02-22')]
    abs_import.sync(db, who(alice), 'key')
    assert abs_import.plan(db, who(alice)).rows[0].box == 'imported'


def test_finished_again_between_syncs(app, db, people, abs_server, sessions):
    alice = people['alice']
    abs_server([item('Twice')], [progress('li_twice', finished=True)])
    abs_import.sync(db, who(alice), 'key')
    run(db, alice)
    book = book_row(db, 'Twice')['id']

    sessions['li_twice'] = [MS + 80 * DAY, MS + 90 * DAY]
    abs_server([item('Twice')], [again('li_twice', finished_at=MS + 100 * DAY)])
    abs_import.sync(db, who(alice), 'key')
    row = abs_import.plan(db, who(alice)).rows[0]
    assert row.box == 'finished_again' and row.adds == ['listened again 2 Feb to 22 Feb 2024']
    result = run(db, alice)
    assert result['counts']['again'] == 1 and 'listened to again' in result['summary']
    assert sessions_of(db, alice, book) == [('2023-11-14', '2023-12-14'), ('2024-02-02', '2024-02-22')]
    assert status_of(db, alice, book) == 'read'
    abs_import.sync(db, who(alice), 'key')
    assert abs_import.plan(db, who(alice)).rows[0].box == 'imported'


def test_skip_and_not_now(app, db, people, abs_server, sessions):
    alice = people['alice']
    abs_server([item('Twice')], [progress('li_twice', finished=True)])
    abs_import.sync(db, who(alice), 'key')
    run(db, alice)
    book = book_row(db, 'Twice')['id']

    # Not now: nothing written, asked again next sync
    abs_server([item('Twice')], [again('li_twice')])
    abs_import.sync(db, who(alice), 'key')
    run(db, alice, {'li_twice': 'later'})
    assert len(sessions_of(db, alice, book)) == 1 and status_of(db, alice, book) == 'read'
    abs_import.sync(db, who(alice), 'key')
    assert abs_import.plan(db, who(alice)).rows[0].box == 'listening_again'

    # Skipping a finished re-listen is remembered
    abs_server([item('Twice')], [again('li_twice', finished_at=MS + 100 * DAY)])
    abs_import.sync(db, who(alice), 'key')
    run(db, alice, {'li_twice': 'skip'})
    assert len(sessions_of(db, alice, book)) == 1
    abs_import.sync(db, who(alice), 'key')
    assert abs_import.plan(db, who(alice)).rows[0].box == 'imported'


def test_undo_listening_again(app, db, people, abs_server, sessions):
    from utils import bulk
    alice = people['alice']
    abs_server([item('Twice')], [progress('li_twice', finished=True)])
    abs_import.sync(db, who(alice), 'key')
    run(db, alice)
    book = book_row(db, 'Twice')['id']
    abs_server([item('Twice')], [again('li_twice')])            # no sessions on ABS: start unknown
    abs_import.sync(db, who(alice), 'key')
    assert abs_import.plan(db, who(alice)).rows[0].adds == ['Currently Reading', 'a new session, start date unknown']
    edit_id = run(db, alice)['edit_id']
    assert sessions_of(db, alice, book)[-1] == (None, None)
    bulk.undo(db, who(alice), edit_id)
    assert status_of(db, alice, book) == 'read' and sessions_of(db, alice, book) == [('2023-11-14', '2023-12-14')]
    assert db.execute('SELECT finished_at FROM abs_links').fetchone()[0] == FIRST_DONE
    abs_import.sync(db, who(alice), 'key')
    assert abs_import.plan(db, who(alice)).rows[0].box == 'listening_again'


def test_item_page_says_a_newer_finish_is_unsynced():
    link = {'finished_at': FIRST_DONE}
    newer = abs_import.progress_line({'isFinished': True, 'finishedAt': MS + 100 * DAY}, 'Audiobook', link)
    assert newer['unsynced']
    same = abs_import.progress_line({'isFinished': True, 'finishedAt': FIRST_DONE}, 'Audiobook', link)
    assert not same['unsynced']


def test_review_page_shows_a_relisten(client, db, people, abs_server, sessions):
    alice = people['alice']
    connect(db, alice)
    abs_server([item('Twice')], [progress('li_twice', finished=True)])
    abs_import.sync(db, who(alice), 'key')
    run(db, alice)
    sessions['li_twice'] = [MS + 80 * DAY]
    abs_server([item('Twice')], [again('li_twice')])
    login(client, 'alice')
    client.post('/abs/sync')
    page = client.get('/abs/review').get_data(as_text=True)
    assert 'data-box="listening_again"' in page and '25 %, started again 2 Feb 2024' in page
    assert 'Not now (asked again next sync)' in page and unbalanced_tags(page) == []


# --- the progress ring on covers (Phil, 2026-11-19) ------------------------------

def stored(db, user_id, item_id):
    row = db.execute('SELECT progress FROM abs_links WHERE user_id = ? AND abs_item_id = ?',
                     (user_id, item_id)).fetchone()
    return row['progress'] if row else 'no link'


def test_progress_is_kept_for_the_ring(app, db, people, abs_server):
    alice = people['alice']
    abs_server([item('Halfway'), item('Done'), item('Ebook', audio=0, ebook='epub')],
               [progress('li_halfway', 0.4), progress('li_done', finished=True),
                progress('li_ebook', 0, ebook=0.25)])
    abs_import.sync(db, who(alice), 'key')
    run(db, alice)
    # The import writes it: in progress only, by position for audio
    assert stored(db, alice, 'li_halfway') == 0.4
    assert stored(db, alice, 'li_done') is None                  # finished: no ring
    assert stored(db, alice, 'li_ebook') == 0.25

    # Every later Sync refreshes it, whether or not the item is in that review
    abs_server([item('Halfway'), item('Done'), item('Ebook', audio=0, ebook='epub')],
               [progress('li_halfway', 0.75), progress('li_done', finished=True)])
    abs_import.sync(db, who(alice), 'key')
    assert stored(db, alice, 'li_halfway') == 0.75
    assert stored(db, alice, 'li_ebook') is None                 # ABS has no progress for it now

    # rings(): yours, by book id
    assert abs_import.rings(db, alice) == {book_row(db, 'Halfway')['id']: 0.75}
    assert abs_import.rings(db, people['bob']) == {}


def test_progress_is_dated_by_when_you_listened(db, people, abs_server):
    """16.0f: the ring shows the newer of ABS and manual progress, so each
    ABS value carries ABS's own lastUpdate (when you listened), or now when
    ABS gives none and the value moved."""
    alice = people['alice']
    abs_server([item('Halfway')], [progress('li_halfway', 0.4)])
    abs_import.sync(db, who(alice), 'key')
    run(db, alice)
    when = lambda: db.execute('SELECT progress_at FROM abs_links').fetchone()[0]
    assert when() == abs_import.stamp(MS) == '2023-11-14 22:13:20'
    # The live line: no lastUpdate and the same value keeps the time...
    abs_import.store_progress(db, alice, 'li_halfway', 0.4)
    assert when() == '2023-11-14 22:13:20'
    # ...a new value without one is dated now, and one with it by ABS
    abs_import.store_progress(db, alice, 'li_halfway', 0.5)
    assert when() > '2026-01-01'
    abs_import.store_progress(db, alice, 'li_halfway', 0.6, updated_ms=MS + 1000)
    assert when() == '2023-11-14 22:13:21'
    assert abs_import.dated_rings(db, alice) == {book_row(db, 'Halfway')['id']: (0.6, '2023-11-14 22:13:21')}


def test_ring_on_the_grid_and_lists_is_yours_alone(client, db, people, abs_server, monkeypatch):
    from blueprints import audiobookshelf as abs_bp
    alice = people['alice']
    connect(db, alice)
    abs_server([item('Heard')], [progress('li_heard', 0.5)])
    abs_import.sync(db, who(alice), 'key')
    run(db, alice)
    book = book_row(db, 'Heard')['id']

    login(client, 'alice')
    page = client.get('/base/index?show=all').get_data(as_text=True)
    assert 'data-abs-ring="50"' in page and 'stroke-dasharray="50 100"' in page
    r = client.get('/base/index?show=all', headers={'X-Requested-With': 'XMLHttpRequest'})
    assert [b['abs_progress'] for b in r.get_json()['books'] if b['id'] == book] == [0.5]
    page = client.get(f'/books/book/{book}').get_data(as_text=True)
    assert 'data-abs-ring="50"' in page                          # before the live line answers

    # The live line updates the stored value, so the grid follows it
    abs_bp._PROGRESS_CACHE.clear()
    monkeypatch.setattr(abs_, 'progress', lambda token, item_id, timeout=None:
                        {'progress': 0.9, 'currentTime': 32400, 'duration': 36000, 'isFinished': False})
    assert client.get(f'/abs/progress/{book}').get_json()['progress'] == 0.9
    assert 'data-abs-ring="90"' in client.get('/base/index?show=all').get_data(as_text=True)

    # A page typed on the paper copy afterwards is newer: the live answer's
    # `ring` says so, even from the cache, and so do the grids (16.0f)
    from utils import reading_progress
    reading_progress.set_progress(db, alice, book, percent='25')     # an audiobook: a percent
    db.execute("UPDATE reading_sessions SET progress_at = '2999-01-01 00:00:00' WHERE progress IS NOT NULL")
    db.commit()
    answer = client.get(f'/abs/progress/{book}').get_json()
    assert (answer['progress'], answer['ring']) == (0.9, 0.25)
    assert 'data-abs-ring="25"' in client.get('/base/index?show=all').get_data(as_text=True)
    db.execute('UPDATE reading_sessions SET progress = NULL')
    db.commit()

    # bob shares the shelf: the book, never alice's ring
    login(client, 'bob')
    shared = client.get('/base/shared-library?show=all').get_data(as_text=True)
    assert f'/books/book/{book}' in shared and 'data-abs-ring' not in shared
    r = client.get(f'/books/book/{book}').get_data(as_text=True)
    assert 'data-abs-ring' not in r

    # Finished on ABS: the ring goes
    login(client, 'alice')
    abs_bp._PROGRESS_CACHE.clear()
    monkeypatch.setattr(abs_, 'progress', lambda token, item_id, timeout=None:
                        {'progress': 1, 'isFinished': True, 'finishedAt': MS})
    assert 'progress' not in client.get(f'/abs/progress/{book}').get_json()
    assert 'data-abs-ring' not in client.get('/base/index?show=all').get_data(as_text=True)


def test_disconnect_clears_the_rings(client, db, people, abs_server):
    alice = people['alice']
    connect(db, alice)
    abs_server([item('Heard')], [progress('li_heard', 0.5)])
    abs_import.sync(db, who(alice), 'key')
    run(db, alice)
    login(client, 'alice')
    client.post('/abs/disconnect')
    assert stored(db, alice, 'li_heard') is None
    assert book_row(db, 'Heard') is not None                     # what you imported stays


def test_ring_markup_matches_its_js_twin(app):
    """_covers.html progress_ring and common.js progressRingHtml draw the
    same ring, and a sliver still shows."""
    import shutil
    import subprocess
    from pathlib import Path
    node = shutil.which('node')
    if not node:
        pytest.skip('node not installed')
    with app.test_request_context():
        macro = app.jinja_env.get_template('_covers.html').module.progress_ring
        server = {v: str(macro(v)).strip() for v in (0.5, 0.004, 1, 0.755)}
        assert str(macro(None)).strip() == '' and str(macro(0)).strip() == ''
    src = Path(app.root_path, 'static', 'common.js').read_text()
    fn = re.search(r'function progressRingHtml\(share\) \{.*?\n\}', src, re.S).group(0)
    out = subprocess.run([node, '-e', fn + '\nconsole.log(JSON.stringify([0.5, 0.004, 1, 0.755].map(progressRingHtml)))'],
                         capture_output=True, text=True, check=True).stdout
    assert dict(zip((0.5, 0.004, 1, 0.755), json.loads(out))) == server
    assert 'data-abs-ring="1"' in server[0.004] and 'data-abs-ring="76"' in server[0.755]


def test_a_dash_subtitle_matches_your_copy(db, people):
    """Phil, 2026-11-19: Audiobookshelf's "Blood in the Machine - The Origins
    of the Rebellion Against Big Tech" became its own audiobook instead of
    attaching to the paper copy, as the matcher only split at a colon. A
    spaced dash starts a subtitle too; a hyphen inside a word doesn't."""
    from utils.book_matching import BookIndex, wanted_title_forms
    alice = people['alice']
    paper = add_book(db, alice, 'Blood in the Machine', 'Brian Merchant')
    index = BookIndex(db, alice)
    for title in ('Blood in the Machine - The Origins of the Rebellion Against Big Tech',
                  'Blood in the Machine – The Origins', 'Blood in the Machine: The Origins'):
        assert index.match((), title, 'Brian Merchant')[0]['id'] == paper, title
    assert wanted_title_forms('Spider-Man') == ['Spider-Man']
    assert wanted_title_forms(' - Untitled') == [' - Untitled']

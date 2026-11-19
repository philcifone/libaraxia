"""The Audiobookshelf import: sync, staging, the plan's boxes and choices
(ROADMAP 16.0e step 4, docs/AUDIOBOOKSHELF-SPEC.md section 8). The client
is stubbed: what ABS would answer is set per test."""
import json
from types import SimpleNamespace

import pytest

from conftest import add_book, login
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
            'currentTime': 100, 'duration': 36000, 'lastUpdate': MS, 'ebookProgress': ebook}


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

"""ROADMAP 8B.3: owned or not, separate from removed.

`books.owned = 0` is something you read, watched or listened to but never
had. It stays yours (reviews, statuses, sessions hang on it) but no library
view, search or owned count shows it unless "Show: Unshelved" is chosen, and
then it's badged. These tests pin that down, since the whole point is that
the shelf never claims you own something you don't.
"""
import sqlite3

from conftest import add_book, add_review, add_user, login, scalar
from test_migrations import fresh_db, run_manage, wind_back_to_023

AJAX = {'X-Requested-With': 'XMLHttpRequest'}
BOOK_FORM = {
    'submit_book': '1', 'title': 'Piranesi', 'author': 'Susanna Clarke', 'publisher': 'Bloomsbury',
    'year': '2020', 'isbn': '9781635575637', 'page_count': '272', 'description': 'A house of halls.',
    'subtitle': '', 'genre': 'Fantasy',
}


def not_owned(db, owner, title, **kw):
    book = add_book(db, owner, title=title, **kw)
    db.execute('UPDATE books SET owned = 0 WHERE id = ?', (book,))
    db.commit()
    return book


def titles(client, url):
    return {b['title'] for b in client.get(url, headers=AJAX).get_json()['books']}


# --- what the shelf shows ------------------------------------------------------

def test_library_hides_not_owned_unless_asked(client, db, people):
    alice = people['alice']
    owned = add_book(db, alice, title='On the shelf')
    heard = not_owned(db, alice, 'Borrowed audiobook')
    gone = add_book(db, alice, title='Given away')
    db.execute('UPDATE books SET removed_at = CURRENT_TIMESTAMP WHERE id = ?', (gone,))
    db.commit()
    login(client, 'alice')

    assert titles(client, '/base/index') == {'On the shelf'}
    assert titles(client, '/base/index?show=not_owned') == {'Borrowed audiobook'}
    assert titles(client, '/base/index?show=removed') == {'Given away'}
    assert titles(client, '/base/index?show=all') == {'On the shelf', 'Borrowed audiobook', 'Given away'}
    # Old links: "include removed" means everything, "only" means removed
    assert titles(client, '/base/index?show_removed=only') == {'Given away'}
    assert 'Borrowed audiobook' in titles(client, '/base/index?show_removed=include')
    # A nonsense value falls back to the shelf, never to everything
    assert titles(client, '/base/index?show=bogus') == {'On the shelf'}

    rows = client.get('/base/index?show=all', headers=AJAX).get_json()['books']
    flags = {b['title']: (b['not_owned'], b['removed']) for b in rows}
    assert flags == {'On the shelf': (False, False), 'Borrowed audiobook': (True, False),
                     'Given away': (False, True)}
    assert owned and heard


def test_grid_badges_not_owned(client, db, people):
    not_owned(db, people['alice'], 'Borrowed audiobook')
    login(client, 'alice')
    page = client.get('/base/index?show=not_owned').get_data(as_text=True)
    assert 'Borrowed audiobook' in page and '>Unshelved</span>' in page
    # The Show choice is in the filter panel, set to what the URL asked
    assert '<option value="not_owned" selected>Unshelved</option>' in page


def test_search_shared_and_friends_skip_not_owned(client, db, people):
    """The bookstore case: searching your shelf never turns up a copy you don't have."""
    alice, bob, carol = people['alice'], people['bob'], people['carol']
    not_owned(db, alice, 'Dune Messiah')
    add_book(db, alice, title='Dune')
    login(client, 'bob')                       # alice's household
    assert titles(client, '/books/search?search_term=dune') == {'Dune'}
    assert titles(client, '/base/shared-library') == {'Dune'}
    login(client, 'carol')                     # alice's friend
    page = client.get('/base/library/alice').get_data(as_text=True)
    assert 'Dune' in page and 'Dune Messiah' not in page
    assert bob and carol


def test_movie_and_music_grids_hide_not_owned(client, db, people):
    alice = people['alice']
    for title, kind in (('Heat', 'video'), ('On TV', 'video'), ('Blue', 'record'), ('Streamed', 'record')):
        db.execute('INSERT INTO books (title, author, added_by, media_type, owned) VALUES (?, ?, ?, ?, ?)',
                   (title, 'x', alice, kind, 0 if title in ('On TV', 'Streamed') else 1))
    db.commit()
    login(client, 'alice')
    videos = client.get('/videos/').get_data(as_text=True)
    assert 'Heat' in videos and 'On TV' not in videos
    assert 'On TV' in client.get('/videos/?show=not_owned').get_data(as_text=True)
    music = client.get('/records/').get_data(as_text=True)
    assert 'Blue' in music and 'Streamed' not in music


# --- counts and stats ---------------------------------------------------------------

def test_owned_counts_skip_not_owned_but_reading_counts(app, db, people):
    from utils.stats import type_stats
    alice = people['alice']
    add_book(db, alice, title='Mine')
    heard = not_owned(db, alice, 'Library audiobook')
    add_review(db, alice, heard)                # read it, rated it
    tv = db.execute("INSERT INTO books (title, author, added_by, media_type, owned, runtime_minutes)"
                    " VALUES ('On TV', 'x', ?, 'video', 0, 120)", (alice,)).lastrowid
    db.execute("INSERT INTO collections (user_id, book_id, status) VALUES (?, ?, 'watched')", (alice, tv))
    db.commit()
    with app.app_context():
        from utils.database import get_db
        conn = get_db()
        books = type_stats(conn, alice, 'book')
        movies = type_stats(conn, alice, 'video')
    assert books['owned'] == 1 and books['not_owned'] == 1
    # Watched counts (and its hours); owned doesn't
    assert (movies['owned'], movies['size_owned']) == (0, 0)
    assert (movies['done'], movies['size_done']) == (1, 2.0)
    assert movies['not_owned'] == 1
    # The review and the 'read' status still count as reading
    assert scalar(db, "SELECT COUNT(*) FROM collections WHERE user_id = ? AND status = 'read'", alice) == 1


# --- adding and changing ownership ------------------------------------------------

def test_add_book_not_owned_goes_to_its_page(client, db, people):
    login(client, 'bob')
    r = client.post('/books/add', data={**BOOK_FORM, 'not_owned': '1'})
    book = scalar(db, "SELECT id FROM books WHERE title = 'Piranesi'")
    assert scalar(db, 'SELECT owned FROM books WHERE id = ?', book) == 0
    assert r.headers['Location'].endswith(f'/books/book/{book}')
    page = client.get(f'/books/book/{book}').get_data(as_text=True)
    assert 'Unshelved.' in page and 'I Own It Now' in page


def test_add_book_owned_by_default(client, db, people):
    login(client, 'bob')
    client.post('/books/add', data=BOOK_FORM)
    assert scalar(db, "SELECT owned FROM books WHERE title = 'Piranesi'") == 1


def test_add_album_not_owned(client, db, people):
    login(client, 'alice')
    client.post('/records/add', data={'title': 'Blue', 'author': 'Joni Mitchell', 'format': 'CD',
                                      'not_owned': '1'})
    assert scalar(db, "SELECT owned FROM books WHERE title = 'Blue'") == 0


def test_add_page_offers_not_owned_but_wishlist_does_not(client, people):
    login(client, 'alice')
    assert 'name="not_owned"' in client.get('/books/add').get_data(as_text=True)
    assert 'name="not_owned"' in client.get('/videos/add').get_data(as_text=True)
    assert 'name="not_owned"' not in client.get('/wishlist/add?type=book').get_data(as_text=True)


def test_i_own_it_now_and_back(client, db, people):
    alice = people['alice']
    book = not_owned(db, alice, 'Bought it later')
    db.execute("UPDATE books SET removed_at = CURRENT_TIMESTAMP WHERE id = ?", (book,))
    db.commit()
    login(client, 'alice')
    client.post(f'/books/ownership/{book}', data={'owned': '1'})
    row = db.execute('SELECT owned, removed_at FROM books WHERE id = ?', (book,)).fetchone()
    assert (row['owned'], row['removed_at']) == (1, None)
    assert 'Bought it later' in titles(client, '/base/index')

    client.post(f'/books/ownership/{book}', data={'owned': '0'})
    assert scalar(db, 'SELECT owned FROM books WHERE id = ?', book) == 0
    assert 'Bought it later' not in titles(client, '/base/index')


def test_only_owner_or_admin_changes_ownership(client, db, people):
    book = not_owned(db, people['alice'], 'Hers')
    login(client, 'bob')
    client.post(f'/books/ownership/{book}', data={'owned': '1'})
    assert scalar(db, 'SELECT owned FROM books WHERE id = ?', book) == 0
    add_user(db, 'dave', admin=True)
    login(client, 'dave')
    client.post(f'/books/ownership/{book}', data={'owned': '1'})
    assert scalar(db, 'SELECT owned FROM books WHERE id = ?', book) == 1


def test_duplicate_check_says_not_owned(client, db, people):
    not_owned(db, people['alice'], 'Piranesi', author='Susanna Clarke')
    login(client, 'alice')
    r = client.post('/books/check_duplicates', json={'title': 'Piranesi', 'author': 'Susanna Clarke'})
    (d,) = r.get_json()['duplicates']
    assert d['not_owned'] is True and d['removed'] is False


# --- migration 025 ------------------------------------------------------------------

def test_025_turns_wishlist_not_owned_rows_into_not_owned(template_db, tmp_path):
    """Before 025, "removed from wishlist; not owned" was stored as removed.
    Those rows become owned = 0 and not removed; a real removal stays removed."""
    path = tmp_path / 'at-023.db'
    conn = fresh_db(path)
    wind_back_to_023(conn)
    conn.executescript("""
        INSERT INTO users (id, username, email, password) VALUES (1, 'phil', 'p@example.test', 'x');
        INSERT INTO books (id, title, author, added_by, removed_at, removed_note)
            VALUES (1, 'Read, never bought', 'A', 1, '2026-01-01', 'Removed from wishlist; not owned');
        INSERT INTO books (id, title, author, added_by, removed_at, removed_note)
            VALUES (2, 'Gave it away', 'A', 1, '2026-01-01', 'Little Free Library');
        INSERT INTO books (id, title, author, added_by) VALUES (3, 'On the shelf', 'A', 1);
    """)
    conn.close()
    run_manage('--db', str(path), 'migrate', '-y')
    conn = sqlite3.connect(path)
    rows = conn.execute('SELECT id, owned, removed_at, removed_note FROM books ORDER BY id').fetchall()
    conn.close()
    assert rows == [(1, 0, None, None),
                    (2, 1, '2026-01-01', 'Little Free Library'),
                    (3, 1, None, None)]


# --- audiobooks (8B.2) ---------------------------------------------------------------

def test_book_form_saves_audiobook_format(client, db, people):
    login(client, 'bob')
    client.post('/books/add', data={**BOOK_FORM, 'format': 'Audiobook', 'not_owned': '1'})
    row = db.execute("SELECT id, format, owned FROM books WHERE title = 'Piranesi'").fetchone()
    assert (row['format'], row['owned']) == ('Audiobook', 0)
    # Editing back to Book stores no format, like every plain book
    client.post(f"/books/edit/{row['id']}", data={**BOOK_FORM, 'format': 'Book'})
    assert scalar(db, 'SELECT format FROM books WHERE id = ?', row['id']) is None
    # Anything else is a plain book too
    client.post(f"/books/edit/{row['id']}", data={**BOOK_FORM, 'format': 'Scroll'})
    assert scalar(db, 'SELECT format FROM books WHERE id = ?', row['id']) is None


def test_audiobooks_never_count_pages(app, db, people):
    from utils.stats import type_stats
    alice = people['alice']
    paper = add_book(db, alice, title='Paper')
    audio = add_book(db, alice, title='Owned audio files')        # owned, say
    db.execute('UPDATE books SET page_count = 300 WHERE id = ?', (paper,))
    db.execute("UPDATE books SET page_count = 900, format = 'Audiobook' WHERE id = ?", (audio,))
    db.commit()
    add_review(db, alice, paper)
    add_review(db, alice, audio)
    with app.app_context():
        from utils.database import get_db
        conn = get_db()
        s = type_stats(conn, alice, 'book')
    assert s['owned'] == 2                                   # owned audiobooks are owned
    assert s['size_owned'] == 300 and s['longest']['title'] == 'Paper'
    assert s['done'] == 2 and s['size_done'] == 300


def test_grid_badges_audiobooks_and_format_filter(client, db, people):
    alice = people['alice']
    add_book(db, alice, title='Paper')
    audio = add_book(db, alice, title='Spoken')
    login(client, 'alice')
    # No Format filter while there's nothing to tell apart
    assert 'name="format"' not in client.get('/base/index').get_data(as_text=True)
    db.execute("UPDATE books SET format = 'Audiobook' WHERE id = ?", (audio,))
    db.commit()
    page = client.get('/base/index').get_data(as_text=True)
    assert 'name="format"' in page
    assert 'title="Audiobook"' not in page                   # no grid badge (2026-11-11)
    assert 'title="Audiobook"' in client.get(f'/books/book/{audio}').get_data(as_text=True)
    assert titles(client, '/base/index?format=Audiobook') == {'Spoken'}
    assert titles(client, '/base/index?format=Book') == {'Paper'}
    assert client.get('/base/index', headers=AJAX).get_json()['books'][1]['format'] == 'Audiobook'


# --- the search hint (8B.3) ---------------------------------------------------------

def test_search_hints_at_matches_not_on_the_shelf(client, db, people):
    alice = people['alice']
    owned = add_book(db, alice, title='Dune')
    read = add_book(db, alice, title='Dune Messiah')
    db.execute('UPDATE books SET owned = 0 WHERE id = ?', (read,))
    db.execute("INSERT INTO collections (user_id, book_id, status) VALUES (?, ?, 'read')", (alice, read))
    db.commit()
    login(client, 'alice')
    page = client.get('/books/search?search_term=dune').get_data(as_text=True)
    hint = page[page.index('Not on your shelf:'):]
    hint = hint[:hint.index('</p>')]
    assert f'/books/book/{read}' in hint and '(read, unshelved)' in hint
    assert f'/books/book/{owned}"' not in hint                     # it's in the results instead
    assert 'show=all' in hint and 'Show it' in hint
    # The results themselves still hold only the owned copy
    grid = page[page.index('id="book-container"'):]
    assert 'Dune Messiah' not in grid
    # No hint once Show asks for them, or without a search, or with nothing hidden
    assert 'Not on your shelf' not in client.get('/books/search?search_term=dune&show=all').get_data(as_text=True)
    assert 'Not on your shelf' not in client.get('/books/search?search_term=zzz').get_data(as_text=True)


def test_section_search_hint_names_household_owner_and_skips_friends(client, db, people):
    from test_videos import add_video
    heat = add_video(db, people['bob'], title='Heat')              # bob shares alice's household
    db.execute("UPDATE books SET removed_at = '2026-01-01' WHERE id = ?", (heat,))
    db.commit()
    login(client, 'alice')
    page = client.get('/videos/shared?search_term=heat').get_data(as_text=True)
    assert 'Not on the shelf:' in page and '(bob&#39;s, removed)' in page
    assert 'Not on' not in client.get('/videos/?search_term=heat').get_data(as_text=True)   # not alice's

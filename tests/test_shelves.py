"""Collections per section (ROADMAP 8C) and the profile's shelf rows (8C/8D)."""
import sqlite3

from conftest import add_book, login, scalar
from test_migrations import fresh_db, run_manage
from test_records import add_record
from test_videos import add_video


def set_status(db, user_id, book_id, status):
    db.execute('INSERT INTO collections (user_id, book_id, status) VALUES (?, ?, ?)',
               (user_id, book_id, status))
    db.commit()


def shelf(db, user_id, name, media_type='book', items=()):
    cid = db.execute('INSERT INTO user_collections (user_id, name, media_type) VALUES (?, ?, ?)',
                     (user_id, name, media_type)).lastrowid
    for book_id in items:
        db.execute('INSERT INTO collection_books (collection_id, book_id) VALUES (?, ?)', (cid, book_id))
    db.commit()
    return cid


def test_collections_page_has_a_tab_per_section(client, db, people):
    alice = people['alice']
    book, movie = add_book(db, alice, title='Dune'), add_video(db, alice, title='Heat')
    set_status(db, alice, book, 'read')
    set_status(db, alice, movie, 'want to watch')
    shelf(db, alice, 'Noir', 'video', [movie])
    login(client, 'alice')

    page = client.get('/collections/collections').get_data(as_text=True)      # Books by default
    assert 'Reading Shelves' in page and 'Did Not Finish' in page and 'Want to Watch' not in page
    assert 'Books <span class="text-sm opacity-75">(1)' in page
    assert 'Movies <span class="text-sm opacity-75">(2)' in page                # a status and a shelf entry
    assert 'Noir' not in page

    page = client.get('/collections/collections?type=video').get_data(as_text=True)
    assert 'Watching Shelves' in page and 'Want to Watch' in page and 'Did Not Finish' not in page
    assert 'Noir' in page
    # Anything else is the Books tab
    assert 'Reading Shelves' in client.get('/collections/collections?type=x').get_data(as_text=True)


def test_create_shelf_in_a_section(client, db, people):
    login(client, 'alice')
    r = client.post('/collections/collections/create', data={'name': 'Favourites', 'media_type': 'record'})
    assert r.headers['Location'].endswith('/collections/collections?type=record')
    # The same name in another section is fine; twice in one isn't
    client.post('/collections/collections/create', data={'name': 'Favourites', 'media_type': 'book'})
    r = client.post('/collections/collections/create', data={'name': 'Favourites', 'media_type': 'book'},
                    follow_redirects=True)
    assert 'already have a shelf called' in r.get_data(as_text=True)
    rows = db.execute("SELECT media_type FROM user_collections WHERE user_id = ? ORDER BY media_type",
                      (people['alice'],)).fetchall()
    assert [r[0] for r in rows] == ['book', 'record']
    # An unknown type is a book shelf
    client.post('/collections/collections/create', data={'name': 'Odd', 'media_type': 'scroll'})
    assert scalar(db, "SELECT media_type FROM user_collections WHERE name = 'Odd'") == 'book'


def test_item_page_offers_its_sections_shelves(client, db, people):
    alice = people['alice']
    movie = add_video(db, alice, title='Heat')
    shelf(db, alice, 'Noir', 'video')
    shelf(db, alice, 'Sci-fi', 'book')
    login(client, 'alice')
    page = client.get(f'/videos/{movie}').get_data(as_text=True)
    assert 'Noir (0)' in page and 'Sci-fi' not in page
    assert '<input type="hidden" name="media_type" value="video"/>' in page


def test_status_shelf_page_is_one_type(client, db, people):
    alice = people['alice']
    book, record = add_book(db, alice, title='Dune'), add_record(db, alice, title='Blue')
    set_status(db, alice, book, 'read')
    set_status(db, alice, record, 'listened')
    login(client, 'alice')
    page = client.get('/collections/collections/status/listened').get_data(as_text=True)
    assert 'Blue' in page and 'Dune' not in page
    assert '/collections/collections?type=record" class="crumb-link">Collections' in page
    assert 'Not owned' not in page                                  # owned items, no badge
    assert client.get('/collections/collections/status/nonsense').status_code == 404


def test_profile_rows_per_section(client, db, people):
    alice, carol = people['alice'], people['carol']                 # friends
    book, movie = add_book(db, alice, title='Dune'), add_video(db, alice, title='Heat')
    set_status(db, alice, book, 'currently reading')
    set_status(db, alice, movie, 'watched')
    wish = add_record(db, alice, title='Hejira')
    db.execute('INSERT INTO wishlist (user_id, book_id) VALUES (?, ?)', (alice, wish))
    db.commit()

    login(client, 'carol')
    page = client.get('/user/alice').get_data(as_text=True)
    # Shelves: only statuses in use, Books then Movies, links carry the username
    assert 'Currently Reading' in page and 'Watched' in page and 'Did Not Finish' not in page
    assert '/collections/collections/status/watched?username=alice' in page
    assert page.index('Currently Reading') < page.index('>Watched<')
    # Wishlist: a Music row only (no books or movies wished for), linked to her wishlist
    section = page[page.index("alice's Wishlist"):]
    assert '>Music<' in section and '>Books<' not in section[:2000]
    assert 'shelf-row' in page and 'flex gap-2 mt-2 truncate' not in page

    login(client, 'alice')
    page = client.get('/user/alice').get_data(as_text=True)
    assert '/wishlist/view?show=music' in page


def test_027_types_existing_shelves(template_db, tmp_path):
    """Shelves of only movies (or only albums) become that section's; empty
    and mixed shelves are Books shelves. Ids and contents are kept."""
    path = tmp_path / 'at-026.db'
    conn = fresh_db(path)
    conn.executescript("""
        PRAGMA foreign_keys = OFF;
        DROP TABLE user_collections;
        CREATE TABLE user_collections (
            collection_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            UNIQUE (user_id, name)
        );
        DELETE FROM schema_migrations WHERE name = '027_shelf_types.sql';
        INSERT INTO users (id, username, email, password) VALUES (1, 'phil', 'p@example.test', 'x');
        INSERT INTO books (id, title, author, added_by, media_type) VALUES
            (1, 'Dune', 'A', 1, 'book'), (2, 'Heat', 'B', 1, 'video'), (3, 'Blue', 'C', 1, 'record');
        INSERT INTO user_collections (collection_id, user_id, name) VALUES
            (1, 1, 'Sci-fi'), (2, 1, 'Noir'), (3, 1, 'Folk'), (4, 1, 'Mixed'), (5, 1, 'Empty');
        INSERT INTO collection_books (collection_id, book_id) VALUES
            (1, 1), (2, 2), (3, 3), (4, 1), (4, 2);
    """)
    conn.close()
    run_manage('--db', str(path), 'migrate', '-y')
    conn = sqlite3.connect(path)
    rows = conn.execute('SELECT collection_id, name, media_type FROM user_collections ORDER BY 1').fetchall()
    entries = conn.execute('SELECT COUNT(*) FROM collection_books').fetchone()[0]
    violations = conn.execute('PRAGMA foreign_key_check').fetchall()
    conn.close()
    assert rows == [(1, 'Sci-fi', 'book'), (2, 'Noir', 'video'), (3, 'Folk', 'record'),
                    (4, 'Mixed', 'book'), (5, 'Empty', 'book')]
    assert entries == 5 and violations == []

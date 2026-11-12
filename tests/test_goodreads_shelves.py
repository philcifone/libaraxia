"""The Goodreads shelves card on Collections (ROADMAP 14c): custom shelves
from goodreads_rows, made into or added to a collection through the bulk
journal, and the grid filtered to one shelf."""
from conftest import add_book, add_user, login, scalar


def imported(db, user_id, rows, undone=False):
    """An import of `rows`: [(book_id or None, 'shelf,shelf')]."""
    imp = db.execute('INSERT INTO goodreads_imports (user_id, row_count, undone_at) VALUES (?, ?, ?)',
                     (user_id, len(rows), '2026-01-01' if undone else None)).lastrowid
    for line, (book_id, shelves) in enumerate(rows, start=2):
        db.execute("INSERT INTO goodreads_rows (import_id, line, book_id, outcome, shelves) VALUES (?, ?, ?, 'new', ?)",
                   (imp, line, book_id, shelves))
    db.commit()
    return imp


def setup_shelves(db, people):
    alice = people['alice']
    a, b, c = (add_book(db, alice, t) for t in ('Dune', 'Emma', 'Heidi'))
    imported(db, alice, [
        (a, 'read,audiobook,re-read'),
        (b, 'to-read,audiobook'),
        (c, 'currently-reading,picture_book'),
        (None, 'audiobook'),                    # never reached a book
    ])
    return a, b, c


def test_shelves_are_custom_only_counted_and_sorted(db, people):
    from utils import goodreads
    setup_shelves(db, people)
    imported(db, people['alice'], [(add_book(db, people['alice'], 'Gone'), 'undone-shelf')], undone=True)
    imported(db, people['bob'], [(add_book(db, people['bob'], 'Bobs'), 'bobs-shelf')])
    assert goodreads.custom_shelves(db, people['alice']) == [
        {'name': 'audiobook', 'count': 2}, {'name': 'picture_book', 'count': 1}, {'name': 're-read', 'count': 1}]


def test_card_shows_on_books_tab_only(client, db, people):
    setup_shelves(db, people)
    login(client, 'alice')
    html = client.get('/collections/collections?type=book').get_data(as_text=True)
    assert 'Goodreads Shelves' in html and 'audiobook' in html
    assert '/base/index?gr_shelf=audiobook&amp;show=all' in html
    assert 'Goodreads Shelves' not in client.get('/collections/collections?type=video').get_data(as_text=True)


def test_make_a_collection_is_journalled_and_undoable(client, db, people):
    a, b, _ = setup_shelves(db, people)
    login(client, 'alice')
    r = client.post('/collections/goodreads_shelf', data={'shelf': 'audiobook', 'mode': 'new', 'name': 'Audiobooks'})
    shelf_id = scalar(db, "SELECT collection_id FROM user_collections WHERE name = 'Audiobooks'")
    assert r.headers['Location'].endswith(f'/collections/collections/{shelf_id}/view')
    assert {row[0] for row in db.execute('SELECT book_id FROM collection_books WHERE collection_id = ?',
                                         (shelf_id,))} == {a, b}
    edit = scalar(db, "SELECT id FROM bulk_edits WHERE action = 'shelf_add'")
    # The collection page carries the Undo banner
    assert 'data-click="bulkUndo"' in client.get(r.headers['Location']).get_data(as_text=True)
    client.post(f'/bulk/{edit}/undo', json={})
    assert scalar(db, 'SELECT COUNT(*) FROM user_collections WHERE collection_id = ?', shelf_id) == 0


def test_add_to_a_collection_skips_books_already_in_it(client, db, people):
    a, b, _ = setup_shelves(db, people)
    shelf_id = db.execute("INSERT INTO user_collections (user_id, name, media_type) VALUES (?, 'Listen', 'book')",
                          (people['alice'],)).lastrowid
    db.execute('INSERT INTO collection_books (collection_id, book_id) VALUES (?, ?)', (shelf_id, a))
    db.commit()
    login(client, 'alice')
    client.post('/collections/goodreads_shelf', data={'shelf': 'audiobook', 'mode': 'add', 'collection_id': shelf_id})
    assert scalar(db, 'SELECT COUNT(*) FROM collection_books WHERE collection_id = ?', shelf_id) == 2
    assert scalar(db, "SELECT item_count FROM bulk_edits WHERE action = 'shelf_add'") == 1
    # Again: nothing to add, no journal entry
    client.post('/collections/goodreads_shelf', data={'shelf': 'audiobook', 'mode': 'add', 'collection_id': shelf_id})
    assert scalar(db, "SELECT COUNT(*) FROM bulk_edits") == 1


def test_cannot_add_to_someone_elses_collection(client, db, people):
    setup_shelves(db, people)
    theirs = db.execute("INSERT INTO user_collections (user_id, name, media_type) VALUES (?, 'Bobs', 'book')",
                        (people['bob'],)).lastrowid
    db.commit()
    login(client, 'alice')
    client.post('/collections/goodreads_shelf', data={'shelf': 'audiobook', 'mode': 'add', 'collection_id': theirs})
    assert scalar(db, 'SELECT COUNT(*) FROM collection_books WHERE collection_id = ?', theirs) == 0


def test_unknown_or_status_shelf_does_nothing(client, db, people):
    setup_shelves(db, people)
    login(client, 'alice')
    for shelf in ('nope', 'read', 'to-read'):
        client.post('/collections/goodreads_shelf', data={'shelf': shelf, 'mode': 'new'})
    assert scalar(db, 'SELECT COUNT(*) FROM user_collections') == 0


def test_grid_filters_to_one_shelf(client, db, people):
    a, b, c = setup_shelves(db, people)
    db.execute('UPDATE books SET owned = 0 WHERE id = ?', (b,))     # an unshelved audiobook
    db.commit()
    from utils import grid_query
    from werkzeug.datastructures import MultiDict
    alice = type('U', (), {'id': people['alice']})()
    assert set(grid_query.view_ids(db, alice, 'book:mine', 'gr_shelf=audiobook&show=all')) == {a, b}
    assert set(grid_query.view_ids(db, alice, 'book:mine', 'gr_shelf=audiobook')) == {a}
    # An underscore is a character, not a LIKE wildcard
    assert grid_query.view_ids(db, alice, 'book:mine', 'gr_shelf=picture_book&show=all') == [c]
    assert grid_query.view_ids(db, alice, 'book:mine', 'gr_shelf=picture-book&show=all') == []
    login(client, 'alice')
    html = client.get('/base/index?gr_shelf=audiobook&show=all').get_data(as_text=True)
    assert 'On the Goodreads shelf "audiobook"' in html

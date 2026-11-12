"""utils/bulk.py, ROADMAP 14a step 5: format, owned, remove, restore, status,
shelves and tags. Genre is in test_bulk.py. Headless, like that file."""
import json

import pytest

from conftest import add_book, add_user
from test_bulk import User, conn, who, genre_of            # noqa: F401  (fixtures)
from test_grid_query import put
from utils import bulk, media


def run(conn, user, action, params, ids, excluded=()):
    """plan, then apply what was planned."""
    p = bulk.plan(conn, user, action, params, ids)
    return bulk.apply(conn, user, action, params, ids, p.fingerprint, excluded)


def col(conn, book_id, column):
    return conn.execute(f'SELECT {column} FROM books WHERE id = ?', (book_id,)).fetchone()[0]


def rows(conn, sql, *args):
    return [tuple(r) for r in conn.execute(sql, args)]


def mine(conn, people, n=1, kind='book', **cols):
    ids = [put(conn, people['alice'], f'{kind} {i}', kind, **cols) for i in range(n)]
    conn.commit()
    return ids


# --- format ------------------------------------------------------------------

def test_format_for_books_stores_null_for_a_plain_book(conn, people, who):
    plain, audio = mine(conn, people, 1, format=None) + mine(conn, people, 1, format='Audiobook')
    p = bulk.plan(conn, who['alice'], 'format', {'format': 'Audiobook'}, [plain, audio])
    assert (p.changes, p.same) == (1, 1)
    assert p.notes == ["Audiobooks don't count toward pages read."]
    assert p.groups[0].label == 'Book \u2192 Audiobook'            # a plain book reads as "Book"
    run(conn, who['alice'], 'format', {'format': 'Audiobook'}, [plain, audio])
    assert col(conn, plain, 'format') == 'Audiobook'
    r = run(conn, who['alice'], 'format', {'format': 'Book'}, [plain, audio])
    assert r.changed == 2 and col(conn, plain, 'format') is None and col(conn, audio, 'format') is None
    # "Book" on a book that already stores NULL is already set, not a change
    assert bulk.plan(conn, who['alice'], 'format', {'format': 'Book'}, [plain]).same == 1


def test_format_is_checked_against_each_items_own_type(conn, people, who):
    book = mine(conn, people)[0]
    movie = mine(conn, people, 1, 'video', format='VHS')[0]
    music = mine(conn, people, 1, 'record', format='LP')[0]
    p = bulk.plan(conn, who['alice'], 'format', {'format': 'DVD'}, [book, movie, music])
    assert p.skipped == {'Not a format for Books': [book], 'Not a format for Music': [music]}
    assert p.groups[0].label == '→'.join(['Cartridge ', ' DVD'])
    assert bulk.ACTIONS['format'].describe({'format': 'VHS'}) == 'Set format to Cartridge'
    audiobook_on_a_movie = bulk.plan(conn, who['alice'], 'format', {'format': 'Audiobook'}, [movie])
    assert audiobook_on_a_movie.skipped == {'Not a format for Movies': [movie]}
    for bad in ('Betamax', '', None):
        with pytest.raises(bulk.BulkError):
            bulk.plan(conn, who['alice'], 'format', {'format': bad}, [movie])


def test_format_undo(conn, people, who):
    movie = mine(conn, people, 1, 'video', format='VHS')[0]
    r = run(conn, who['alice'], 'format', {'format': 'DVD'}, [movie])
    assert col(conn, movie, 'format') == 'DVD'
    bulk.undo(conn, who['alice'], r.edit_id)
    assert col(conn, movie, 'format') == 'VHS'


# --- owned -------------------------------------------------------------------

def test_owned_and_the_notes(conn, people, who):
    a, b = mine(conn, people, 2)
    conn.execute('UPDATE books SET owned = 0 WHERE id = ?', (b,))
    p = bulk.plan(conn, who['alice'], 'owned', {'owned': 0}, [a, b])
    assert (p.changes, p.same) == (1, 1)
    assert p.notes == ['Unshelved items leave your shelf. Reviews, ratings and history stay.']
    r = run(conn, who['alice'], 'owned', {'owned': 0}, [a, b])
    assert (col(conn, a, 'owned'), r.summary) == (0, 'Marked unshelved on 1 item')
    run(conn, who['alice'], 'owned', {'owned': 1}, [a, b])
    assert (col(conn, a, 'owned'), col(conn, b, 'owned')) == (1, 1)
    assert bulk.ACTIONS['owned'].describe({'owned': 1}) == 'Mark as owned'
    for bad in (None, 'yes', 2, {}):
        with pytest.raises(bulk.BulkError):
            bulk.plan(conn, who['alice'], 'owned', {'owned': bad}, [a])


def test_owned_does_not_touch_removal(conn, people, who):
    """The single-item route also un-removes; a bulk edit writes only what it
    says it does (spec section 8), and says so in the review."""
    book = mine(conn, people, 1, owned=0, removed_at='2024-05-01 00:00:00', removed_note='gone')[0]
    p = bulk.plan(conn, who['alice'], 'owned', {'owned': 1}, [book])
    assert 'Items that were removed from the library stay removed.' in p.notes
    run(conn, who['alice'], 'owned', {'owned': 1}, [book])
    assert (col(conn, book, 'owned'), col(conn, book, 'removed_at'), col(conn, book, 'removed_note')) == (
        1, '2024-05-01 00:00:00', 'gone')


def test_owned_undo_and_permission(conn, people, who):
    book = mine(conn, people)[0]
    assert bulk.plan(conn, who['bob'], 'owned', {'owned': 0}, [book]).skipped == {'Not yours': [book]}
    r = run(conn, who['alice'], 'owned', {'owned': 0}, [book])
    bulk.undo(conn, who['alice'], r.edit_id)
    assert col(conn, book, 'owned') == 1


# --- remove and restore ------------------------------------------------------

def test_remove_then_restore_round_trip(conn, people, who):
    alice = who['alice']
    a, b = mine(conn, people, 2)
    conn.execute("INSERT INTO read_data (user_id, book_id, rating) VALUES (?, ?, 5)", (people['alice'], a))
    conn.execute("INSERT INTO collections (user_id, book_id, status) VALUES (?, ?, 'read')", (people['alice'], a))
    conn.commit()
    r = run(conn, alice, 'remove', {'note': '  Little Free Library  '}, [a, b])
    assert r.summary == 'Removed 2 items from the library'
    assert col(conn, a, 'removed_at') and col(conn, a, 'removed_note') == 'Little Free Library'
    # Reviews and statuses stay
    assert rows(conn, 'SELECT rating FROM read_data WHERE book_id = ?', a) == [(5,)]
    assert rows(conn, 'SELECT status FROM collections WHERE book_id = ?', a) == [('read',)]
    # Already removed items are skipped, not rewritten
    again = bulk.plan(conn, alice, 'remove', {'note': 'x'}, [a, b])
    assert again.skipped == {'Already removed': [a, b]} and again.changes == 0

    back = run(conn, alice, 'restore', {}, [a, b])
    assert back.summary == 'Put 2 items back on the shelf'
    assert col(conn, a, 'removed_at') is None and col(conn, a, 'removed_note') is None
    # Restoring what is on the shelf is "already set"
    assert bulk.plan(conn, alice, 'restore', {}, [a]).same == 1


def test_remove_undo_puts_the_old_values_back_unless_changed_since(conn, people, who):
    alice = who['alice']
    a, b = mine(conn, people, 2)
    r = run(conn, alice, 'remove', {'note': 'sold'}, [a, b])
    conn.execute("UPDATE books SET removed_note = 'sold on eBay' WHERE id = ?", (b,))     # edited by hand since
    conn.commit()
    undone = bulk.undo(conn, alice, r.edit_id)
    assert (undone.changed, undone.skipped) == (1, 1)
    assert col(conn, a, 'removed_at') is None
    assert col(conn, b, 'removed_note') == 'sold on eBay'


def test_restore_undo_removes_again_with_the_original_time(conn, people, who):
    book = mine(conn, people, 1, removed_at='2024-05-01 12:00:00', removed_note='lent')[0]
    r = run(conn, who['alice'], 'restore', {}, [book])
    assert col(conn, book, 'removed_at') is None
    bulk.undo(conn, who['alice'], r.edit_id)
    assert (col(conn, book, 'removed_at'), col(conn, book, 'removed_note')) == ('2024-05-01 12:00:00', 'lent')


def test_remove_note_is_capped_and_blank_is_none(conn, people, who):
    a, b = mine(conn, people, 2)
    assert bulk.plan(conn, who['alice'], 'remove', {'note': 'x' * 300}, [a]).params['note'] == 'x' * 200
    run(conn, who['alice'], 'remove', {'note': '   '}, [b])
    assert col(conn, b, 'removed_note') is None


def test_only_the_owner_or_an_admin_removes(conn, people, who):
    book = mine(conn, people)[0]
    for name in ('bob', 'carol'):
        assert bulk.plan(conn, who[name], 'remove', {}, [book]).skipped == {'Not yours': [book]}
        assert bulk.plan(conn, who[name], 'restore', {}, [book]).skipped == {'Not yours': [book]}
    bobs = put(conn, people['bob'], 'Bob book', 'book')
    conn.commit()
    assert run(conn, who['alice'], 'remove', {}, [bobs]).changed == 1        # alice is an admin


def test_no_action_reaches_hard_delete(conn, people, who):
    assert not [k for k in bulk.ACTIONS if 'delete' in k]
    ids = mine(conn, people, 3)
    before = rows(conn, 'SELECT id FROM books ORDER BY id')
    run(conn, who['alice'], 'remove', {}, ids)
    run(conn, who['alice'], 'restore', {}, ids)
    assert rows(conn, 'SELECT id FROM books ORDER BY id') == before


# --- status ------------------------------------------------------------------

def test_status_types_and_untracked(conn, people, who):
    alice = who['alice']
    book = mine(conn, people)[0]
    movie = mine(conn, people, 1, 'video')[0]
    p = bulk.plan(conn, alice, 'status', {'status': 'watched'}, [book, movie])
    assert p.skipped == {'Not a status for Books': [book]} and p.changes == 1
    assert bulk.plan(conn, alice, 'status', {'status': 'listened'}, [movie]).skipped == {
        'Not a status for Movies': [movie]}
    assert bulk.plan(conn, alice, 'status', {'status': 'untracked'}, [book]).same == 1      # nothing to clear
    for bad in ('', None, 'finished', 'READ'):
        with pytest.raises(bulk.BulkError):
            bulk.plan(conn, alice, 'status', {'status': bad}, [book])


def test_new_status_rows_are_quiet_and_updates_keep_quiet(conn, people, who):
    alice = who['alice']
    new, old = mine(conn, people, 2)
    conn.execute("INSERT INTO collections (user_id, book_id, status, created_at, quiet) "
                 "VALUES (?, ?, 'want to read', '2023-01-01 00:00:00', 0)", (people['alice'], old))
    conn.commit()
    r = run(conn, alice, 'status', {'status': 'currently reading'}, [new, old])
    assert r.summary == 'Status set to Currently Reading on 2 items'
    got = {b: rows(conn, 'SELECT status, quiet, created_at FROM collections WHERE book_id = ?', b)[0]
           for b in (new, old)}
    assert got[new][:2] == ('currently reading', 1)                  # a new row: kept out of the feed
    assert got[old] == ('currently reading', 0, '2023-01-01 00:00:00')   # an update: quiet and created_at stay


def test_status_adds_no_reading_data(conn, people, who):
    book = mine(conn, people)[0]
    p = bulk.plan(conn, who['alice'], 'status', {'status': 'read'}, [book])
    assert 'No reading dates are added, and no reviews.' in p.notes
    run(conn, who['alice'], 'status', {'status': 'read'}, [book])
    assert rows(conn, 'SELECT COUNT(*) FROM reading_sessions') == [(0,)]
    assert rows(conn, 'SELECT COUNT(*) FROM read_data') == [(0,)]


def test_status_undo_restores_a_deleted_row_exactly(conn, people, who):
    alice = who['alice']
    a, b = mine(conn, people, 2)
    conn.execute("INSERT INTO collections (user_id, book_id, status, created_at, updated_at, quiet) "
                 "VALUES (?, ?, 'read', '2022-02-02 02:02:02', '2022-03-03 03:03:03', 0)", (people['alice'], a))
    conn.commit()
    r = run(conn, alice, 'status', {'status': 'untracked'}, [a, b])           # b has none: same
    assert r.changed == 1 and rows(conn, 'SELECT * FROM collections') == []
    bulk.undo(conn, alice, r.edit_id)
    assert rows(conn, 'SELECT status, created_at, updated_at, quiet FROM collections WHERE book_id = ?', a) == [
        ('read', '2022-02-02 02:02:02', '2022-03-03 03:03:03', 0)]


def test_status_undo_removes_rows_it_created_and_restores_updated_ones(conn, people, who):
    alice = who['alice']
    new, old = mine(conn, people, 2)
    conn.execute("INSERT INTO collections (user_id, book_id, status, created_at, updated_at, quiet) "
                 "VALUES (?, ?, 'want to read', '2022-02-02 02:02:02', '2022-02-02 02:02:02', 0)",
                 (people['alice'], old))
    conn.commit()
    r = run(conn, alice, 'status', {'status': 'read'}, [new, old])
    undone = bulk.undo(conn, alice, r.edit_id)
    assert undone.changed == 2
    assert rows(conn, 'SELECT book_id FROM collections') == [(old,)]
    assert rows(conn, 'SELECT status, updated_at, quiet FROM collections') == [
        ('want to read', '2022-02-02 02:02:02', 0)]


def test_status_undo_leaves_what_you_changed_since(conn, people, who):
    alice = who['alice']
    a, b = mine(conn, people, 2)
    r = run(conn, alice, 'status', {'status': 'want to read'}, [a, b])
    # You mark b as read by hand afterwards (the single-item route)
    conn.execute("UPDATE collections SET status = 'read', quiet = 0, updated_at = '2030-01-01 00:00:00' "
                 "WHERE book_id = ?", (b,))
    conn.commit()
    undone = bulk.undo(conn, alice, r.edit_id)
    assert (undone.changed, undone.skipped) == (1, 1)
    assert rows(conn, 'SELECT book_id, status FROM collections') == [(b, 'read')]


def test_marks_follow_the_circle_not_ownership(conn, people, who):
    alices = mine(conn, people, 1)[0]
    stranger = add_user(conn, 'dave')
    secret = put(conn, stranger, 'Dave book', 'book')
    conn.commit()
    # bob (same household) and carol (alice's friend) may mark alice's book
    for name in ('bob', 'carol'):
        run(conn, who[name], 'status', {'status': 'want to read'}, [alices])
    assert rows(conn, 'SELECT user_id, status FROM collections WHERE book_id = ? ORDER BY user_id', alices) == [
        (people['bob'], 'want to read'), (people['carol'], 'want to read')]
    # ...but not a stranger's
    p = bulk.plan(conn, who['carol'], 'status', {'status': 'want to read'}, [secret])
    assert p.skipped == {'Not found': [secret]} and p.rows[0].title == ''


# --- shelves -----------------------------------------------------------------

def shelf_of(conn, people, name, kind='book', user='alice'):
    cid = conn.execute('INSERT INTO user_collections (user_id, name, media_type) VALUES (?, ?, ?)',
                       (people[user], name, kind)).lastrowid
    conn.commit()
    return cid


def on_shelf(conn, shelf_id):
    return [r[0] for r in conn.execute('SELECT book_id FROM collection_books WHERE collection_id = ? '
                                       'ORDER BY book_id', (shelf_id,))]


def test_shelf_add_and_remove_with_undo_that_only_touches_its_own_rows(conn, people, who):
    alice = who['alice']
    a, b, c = mine(conn, people, 3)
    jazz = shelf_of(conn, people, 'Jazz')
    conn.execute('INSERT INTO collection_books (collection_id, book_id, added_at) VALUES (?, ?, ?)',
                 (jazz, b, '2020-01-01 00:00:00'))                # already on it
    conn.commit()
    params = {'shelf_id': jazz, 'media_type': 'book'}
    p = bulk.plan(conn, alice, 'shelf_add', params, [a, b, c])
    assert (p.changes, p.same, p.same_text) == (2, 1, 'Already in “Jazz”')
    r = run(conn, alice, 'shelf_add', params, [a, b, c])
    assert r.summary == 'Added 2 items to Jazz' and on_shelf(conn, jazz) == [a, b, c]
    bulk.undo(conn, alice, r.edit_id)
    assert on_shelf(conn, jazz) == [b]                               # b was already there: untouched
    assert rows(conn, 'SELECT added_at FROM collection_books WHERE book_id = ?', b) == [('2020-01-01 00:00:00',)]

    out = run(conn, alice, 'shelf_remove', params, [a, b])           # a isn't on it: same
    assert (out.changed, out.summary) == (1, 'Removed 1 item from Jazz')
    assert on_shelf(conn, jazz) == []
    bulk.undo(conn, alice, out.edit_id)
    assert rows(conn, 'SELECT added_at FROM collection_books WHERE book_id = ?', b) == [('2020-01-01 00:00:00',)]


def test_a_shelf_is_for_one_section(conn, people, who):
    book = mine(conn, people)[0]
    movie = mine(conn, people, 1, 'video')[0]
    films = shelf_of(conn, people, 'Noir', 'video')
    p = bulk.plan(conn, who['alice'], 'shelf_add', {'shelf_id': films, 'media_type': 'video'}, [book, movie])
    assert p.skipped == {'Collection is for Movies': [book]} and p.changes == 1
    # The shelf's own section wins over what the request claims
    again = bulk.plan(conn, who['alice'], 'shelf_add', {'shelf_id': films, 'media_type': 'book'}, [book, movie])
    assert again.skipped == {'Collection is for Movies': [book]}


def test_shelf_must_be_yours(conn, people, who):
    book = mine(conn, people)[0]
    theirs = shelf_of(conn, people, 'Bob only', user='bob')
    for params in ({'shelf_id': theirs, 'media_type': 'book'}, {'shelf_id': 9999, 'media_type': 'book'},
                   {'media_type': 'book'}, {'shelf_id': theirs}, {}):
        for action in ('shelf_add', 'shelf_remove'):
            with pytest.raises(bulk.BulkError):
                bulk.plan(conn, who['alice'], action, params, [book])


def test_new_shelf_is_created_on_apply_and_goes_with_an_undo(conn, people, who):
    alice = who['alice']
    a, b = mine(conn, people, 2)
    params = {'new_shelf': '  Road   trip ', 'media_type': 'book'}
    p = bulk.plan(conn, alice, 'shelf_add', params, [a, b])
    assert p.notes == ['A new collection “Road trip” will be created.']
    assert rows(conn, 'SELECT name FROM user_collections') == []         # planning creates nothing
    r = run(conn, alice, 'shelf_add', params, [a, b])
    shelf = rows(conn, 'SELECT collection_id, name, media_type FROM user_collections')
    assert [s[1:] for s in shelf] == [('Road trip', 'book')] and on_shelf(conn, shelf[0][0]) == [a, b]
    bulk.undo(conn, alice, r.edit_id)
    assert rows(conn, 'SELECT name FROM user_collections') == []         # empty again, so it goes too


def test_undo_keeps_a_new_shelf_that_has_something_else_on_it(conn, people, who):
    alice = who['alice']
    a, other = mine(conn, people, 2)
    r = run(conn, alice, 'shelf_add', {'new_shelf': 'Keepers', 'media_type': 'book'}, [a])
    shelf = rows(conn, 'SELECT collection_id FROM user_collections')[0][0]
    conn.execute('INSERT INTO collection_books (collection_id, book_id) VALUES (?, ?)', (shelf, other))
    conn.commit()
    bulk.undo(conn, alice, r.edit_id)
    assert on_shelf(conn, shelf) == [other]


def test_new_shelf_name_rules(conn, people, who):
    book = mine(conn, people)[0]
    shelf_of(conn, people, 'Jazz')
    for name in ('', '   ', 'x' * 61, 'Jazz', 'Jazz  '):      # blank, too long, already there
        with pytest.raises(bulk.BulkError):
            bulk.plan(conn, who['alice'], 'shelf_add', {'new_shelf': name, 'media_type': 'book'}, [book])
    # The same name in another section is fine
    assert bulk.plan(conn, who['alice'], 'shelf_add', {'new_shelf': 'Jazz', 'media_type': 'record'},
                     [book]).skipped == {'Collection is for Music': [book]}
    with pytest.raises(bulk.BulkError):                           # remove can't create one
        bulk.plan(conn, who['alice'], 'shelf_remove', {'new_shelf': 'x', 'media_type': 'book'}, [book])


def test_a_new_shelf_is_not_left_behind_when_nothing_was_written(conn, people, who):
    book = mine(conn, people)[0]
    conn.execute("""CREATE TRIGGER refuse BEFORE INSERT ON collection_books
                    BEGIN SELECT RAISE(ABORT, 'no'); END""")
    r = run(conn, who['alice'], 'shelf_add', {'new_shelf': 'Ghost', 'media_type': 'book'}, [book])
    assert (r.edit_id, r.failed) == (None, 1)
    assert rows(conn, 'SELECT name FROM user_collections') == []
    assert rows(conn, 'SELECT COUNT(*) FROM bulk_edits') == [(0,)]


def test_household_member_shelves_a_book_they_dont_own(conn, people, who):
    alices = mine(conn, people)[0]
    mine_shelf = shelf_of(conn, people, 'Bob reads', user='bob')
    r = run(conn, who['bob'], 'shelf_add', {'shelf_id': mine_shelf, 'media_type': 'book'}, [alices])
    assert r.changed == 1 and on_shelf(conn, mine_shelf) == [alices]


# --- tags --------------------------------------------------------------------

def tags_of(conn, user_id, book_id):
    return [r[0] for r in conn.execute('SELECT tag_name FROM book_tags WHERE user_id = ? AND book_id = ? '
                                       'ORDER BY tag_name', (user_id, book_id))]


def test_tags_are_cleaned_like_the_tags_route(conn, people, who):
    book = mine(conn, people)[0]
    p = bulk.plan(conn, who['alice'], 'tag_add', {'tag': '  Gifted By Mum '}, [book])
    assert p.params == {'tag': 'gifted by mum'}
    for bad in ('', '   ', None, 'x' * 51, 'a\x00b'):
        with pytest.raises(bulk.BulkError):
            bulk.plan(conn, who['alice'], 'tag_add', {'tag': bad}, [book])


def test_tag_add_remove_and_undo(conn, people, who):
    alice = who['alice']
    a, b = mine(conn, people, 2)
    conn.execute("INSERT INTO book_tags (user_id, book_id, tag_name, created_at) VALUES (?, ?, 'kitchen', "
                 "'2021-01-01 00:00:00')", (people['alice'], b))
    conn.commit()
    p = bulk.plan(conn, alice, 'tag_add', {'tag': 'Kitchen'}, [a, b])
    assert (p.changes, p.same, p.same_text) == (1, 1, 'Already tagged “kitchen”')
    r = run(conn, alice, 'tag_add', {'tag': 'Kitchen'}, [a, b])
    assert r.summary == 'Tag “kitchen” added to 1 item' and tags_of(conn, people['alice'], a) == ['kitchen']
    bulk.undo(conn, alice, r.edit_id)
    assert tags_of(conn, people['alice'], a) == [] and tags_of(conn, people['alice'], b) == ['kitchen']

    out = run(conn, alice, 'tag_remove', {'tag': 'kitchen'}, [a, b])
    assert out.changed == 1 and tags_of(conn, people['alice'], b) == []
    bulk.undo(conn, alice, out.edit_id)
    assert rows(conn, 'SELECT created_at FROM book_tags WHERE book_id = ?', b) == [('2021-01-01 00:00:00',)]


def test_tags_belong_to_the_person_who_set_them(conn, people, who):
    alices = mine(conn, people)[0]
    run(conn, who['bob'], 'tag_add', {'tag': 'borrowed'}, [alices])
    assert tags_of(conn, people['bob'], alices) == ['borrowed'] and tags_of(conn, people['alice'], alices) == []
    # carol has none to remove
    assert bulk.plan(conn, who['carol'], 'tag_remove', {'tag': 'borrowed'}, [alices]).same == 1


# --- the pickers -------------------------------------------------------------

def test_options_for_each_section(conn, people, who):
    alice = who['alice']
    shelf_of(conn, people, 'Jazz')
    shelf_of(conn, people, 'Noir', 'video')
    book = mine(conn, people)[0]
    conn.execute("INSERT INTO book_tags (user_id, book_id, tag_name) VALUES (?, ?, 'kitchen')", (people['alice'], book))
    conn.commit()
    books = bulk.options(conn, alice, 'book')
    assert [s['value'] for s in books['statuses']] == [*media.STATUSES['book'], 'untracked']
    assert books['statuses'][-1]['label'] == 'Unread'
    assert [f['value'] for f in books['formats']] == ['Book', 'Audiobook']
    assert [s['name'] for s in books['shelves']] == ['Jazz'] and books['tags'] == [{'value': 'kitchen', 'count': 1}]
    movies = bulk.options(conn, alice, 'video')
    assert movies['statuses'][-1]['label'] == 'Unwatched'
    assert [(f['value'], f['label']) for f in movies['formats']] == [('VHS', 'Cartridge'), ('DVD', 'DVD')]
    assert [s['name'] for s in movies['shelves']] == ['Noir']
    assert bulk.options(conn, alice, 'bogus')['media_type'] == 'book'
    assert bulk.options(conn, who['bob'], 'book')['shelves'] == []


# --- the journal, for every action -------------------------------------------

@pytest.mark.parametrize('action, params', [
    ('format', {'format': 'Audiobook'}), ('owned', {'owned': 0}), ('remove', {'note': 'x'}),
    ('status', {'status': 'read'}), ('tag_add', {'tag': 'x'}),
])
def test_every_action_journals_and_undoes_once(conn, people, who, action, params):
    ids = mine(conn, people, 3)
    r = run(conn, who['alice'], action, params, ids)
    assert r.changed == 3
    journal = rows(conn, 'SELECT book_id FROM bulk_edit_items WHERE edit_id = ? ORDER BY book_id', r.edit_id)
    assert journal == [(i,) for i in ids]
    row = conn.execute('SELECT action, params FROM bulk_edits WHERE id = ?', (r.edit_id,)).fetchone()
    assert row['action'] == action and json.loads(row['params'])
    assert bulk.undo(conn, who['alice'], r.edit_id).changed == 3
    with pytest.raises(bulk.BulkError):
        bulk.undo(conn, who['alice'], r.edit_id)


def test_remove_and_restore_write_nothing_else(conn, people, who):
    """Only removed_at and removed_note: ownership, genre and the rest stay."""
    book = mine(conn, people, 1, owned=0, genre='Cooking', format='Audiobook')[0]
    snapshot = rows(conn, 'SELECT owned, genre, format, title FROM books WHERE id = ?', book)
    run(conn, who['alice'], 'remove', {'note': 'x'}, [book])
    run(conn, who['alice'], 'restore', {}, [book])
    assert rows(conn, 'SELECT owned, genre, format, title FROM books WHERE id = ?', book) == snapshot


def test_clearing_a_status_keeps_reviews_and_says_so(conn, people, who):
    alice = who['alice']
    (book,) = mine(conn, people, 1)
    conn.execute("INSERT INTO collections (user_id, book_id, status) VALUES (?, ?, 'read')", (people['alice'], book))
    conn.execute('INSERT INTO read_data (user_id, book_id, rating, comment) VALUES (?, ?, 4, ?)',
                 (people['alice'], book, 'Good'))
    conn.commit()
    p = bulk.plan(conn, alice, 'status', {'status': 'untracked'}, [book])
    assert p.notes == ["Reviews, ratings and reading dates are kept. Delete those on the item's page."]
    run(conn, alice, 'status', {'status': 'untracked'}, [book])
    assert rows(conn, 'SELECT rating, comment FROM read_data WHERE book_id = ?', book) == [(4, 'Good')]

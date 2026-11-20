"""Merge two records into one (ROADMAP 16.0f part B, docs/PROGRESS-MERGE-SPEC.md):
utils/merge.py.

People (conftest): alice (admin) and bob share a household; carol is
alice's friend. alice is an admin, so the user rule is tested with bob.
"""
import os
from types import SimpleNamespace

import pytest

from conftest import add_book, add_review, fk_violations, scalar
from utils import bulk, image_utils, merge
from utils.merge import MergeError


def who(db, user_id):
    row = db.execute('SELECT id, username, is_admin FROM users WHERE id = ?', (user_id,)).fetchone()
    return SimpleNamespace(id=row['id'], username=row['username'], is_admin=bool(row['is_admin']))


def unowned(db, title='Dune', **fields):
    book_id = add_book(db, None, title)
    for k, v in fields.items():
        db.execute(f'UPDATE books SET {k} = ? WHERE id = ?', (v, book_id))
    db.commit()
    return book_id


def rows(db, table, book_id, column='book_id'):
    return db.execute(f'SELECT COUNT(*) FROM {table} WHERE {column} = ?', (book_id,)).fetchone()[0]


def exists(db, book_id):
    return db.execute('SELECT 1 FROM books WHERE id = ?', (book_id,)).fetchone() is not None


def test_every_table_pointing_at_books_is_handled(db):
    """A new table with a foreign key to books must be added to MOVERS, or a
    merge would cascade-delete its rows (or set them NULL) with the folded
    record."""
    found = {(r['name'], r['from']) for r in db.execute(
        "SELECT m.name, p.\"from\" FROM sqlite_master m JOIN pragma_foreign_key_list(m.name) p "
        "WHERE m.type = 'table' AND p.\"table\" = 'books'")}
    assert found == {(table, spec[0]) for table, spec in merge.MOVERS.items()}


def test_a_pre_ownership_record_folds_into_your_copy(db, people):
    alice = people['alice']
    old = unowned(db, 'Dune', page_count=412, description='Spice.')
    mine = add_book(db, alice, 'Dune')
    add_review(db, alice, old, rating=5, comment='Loved it')      # review, Read, a dated session
    db.execute("INSERT INTO book_tags (user_id, book_id, tag_name) VALUES (?, ?, 'scifi'), (?, ?, 'classic'), (?, ?, 'scifi')",
               (alice, old, alice, old, alice, mine))
    db.execute("INSERT INTO notifications (user_id, type, message, related_book_id) VALUES (?, 'like', 'x', ?)",
               (people['carol'], old))
    db.commit()

    p = merge.plan(db, mine, old)
    assert p['clashes'] == []
    assert [f['field'] for f in p['fills']] == ['page_count', 'description']
    assert ('tags both records had', 1) in p['drops'] and p['people'] == ['alice']

    merge.apply(db, who(db, alice), mine, old, {}, ['page_count', 'description'])
    assert not exists(db, old)
    assert scalar(db, 'SELECT rating FROM read_data WHERE book_id = ?', mine) == 5
    assert scalar(db, 'SELECT status FROM collections WHERE book_id = ?', mine) == 'read'
    assert rows(db, 'reading_sessions', mine) == 1
    assert sorted(r[0] for r in db.execute('SELECT tag_name FROM book_tags WHERE book_id = ?', (mine,))) == \
        ['classic', 'scifi']
    assert rows(db, 'notifications', mine, 'related_book_id') == 1
    assert scalar(db, 'SELECT page_count FROM books WHERE id = ?', mine) == 412
    assert fk_violations(db) == []


def test_a_clash_needs_a_choice_and_the_choice_wins(db, people):
    alice = people['alice']
    old, mine = unowned(db), add_book(db, alice, 'Dune')
    add_review(db, alice, old, rating=5, comment='First read, loved it')
    db.execute("INSERT INTO read_data (user_id, book_id, rating, comment) VALUES (?, ?, 4, 'Second read')", (alice, mine))
    db.execute("INSERT INTO collections (user_id, book_id, status) VALUES (?, ?, 'currently reading')", (alice, mine))
    db.commit()
    ids = sorted(c['id'] for c in merge.plan(db, mine, old)['clashes'])
    assert ids == [f'collections:{alice}', f'read_data:{alice}:comment', f'read_data:{alice}:rating']

    with pytest.raises(MergeError, match='every item'):
        merge.apply(db, who(db, alice), mine, old, {f'read_data:{alice}:rating': 'keep'}, [])
    assert exists(db, old)                                   # nothing written

    merge.apply(db, who(db, alice), mine, old, {f'read_data:{alice}:rating': 'fold',
                                                f'read_data:{alice}:comment': 'keep',
                                                f'collections:{alice}': 'fold'}, [])
    review = db.execute('SELECT rating, comment FROM read_data WHERE book_id = ?', (mine,)).fetchall()
    assert [tuple(r) for r in review] == [(5, 'Second read')]    # a rating from one, the review from the other
    assert [r[0] for r in db.execute('SELECT status FROM collections WHERE book_id = ?', (mine,))] == ['read']
    assert fk_violations(db) == []


def test_wishlist_notes_can_be_joined(db, people):
    alice = people['alice']
    old, mine = unowned(db), add_book(db, alice, 'Dune')
    db.execute("INSERT INTO wishlist (user_id, book_id, notes) VALUES (?, ?, 'hardback'), (?, ?, 'signed if possible')",
               (alice, old, alice, mine))
    db.commit()
    merge.apply(db, who(db, alice), mine, old, {f'wishlist:{alice}': 'join'}, [])
    assert scalar(db, 'SELECT notes FROM wishlist WHERE book_id = ?', mine) == 'signed if possible\n\nhardback'


def test_photos_keep_their_files_and_the_loser_joins_the_gallery(db, people):
    alice = people['alice']
    old, mine = unowned(db), add_book(db, alice, 'Dune')
    path = f'uploads/photos/{old}/back.jpg'
    full = os.path.join(image_utils.STATIC_ROOT, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    open(full, 'wb').write(b'jpeg')
    db.execute("INSERT INTO item_photos (book_id, kind, path) VALUES (?, 'back', ?), (?, 'gallery', 'g.jpg'), "
               "(?, 'back', 'mine.jpg')", (old, path, old, mine))
    db.commit()
    merge.apply(db, who(db, alice), mine, old, {'item_photos:back': 'keep'}, [])
    kinds = sorted(tuple(r) for r in db.execute('SELECT kind, path FROM item_photos WHERE book_id = ?', (mine,)))
    assert kinds == [('back', 'mine.jpg'), ('gallery', 'g.jpg'), ('gallery', path)]
    assert os.path.exists(full)                               # the folded record's folder survives


def test_undo_puts_everything_back(db, people):
    alice = people['alice']
    old = unowned(db, 'Dune', page_count=412)
    mine = add_book(db, alice, 'Dune')
    add_review(db, alice, old, rating=5, comment='First read')
    db.execute("INSERT INTO read_data (user_id, book_id, rating, comment) VALUES (?, ?, NULL, 'Second read')", (alice, mine))
    db.execute("INSERT INTO collections (user_id, book_id, status) VALUES (?, ?, 'currently reading')", (alice, mine))
    db.execute("INSERT INTO item_photos (book_id, kind, path) VALUES (?, 'back', 'a.jpg'), (?, 'back', 'b.jpg')", (old, mine))
    db.commit()
    before = {t: sorted(tuple(r) for r in db.execute(f'SELECT * FROM {t} ORDER BY rowid'))
              for t in ('books', 'read_data', 'collections', 'reading_sessions', 'item_photos')}

    edit_id = merge.apply(db, who(db, alice), mine, old,
                          {f'read_data:{alice}:comment': 'fold', f'collections:{alice}': 'fold',
                           'item_photos:back': 'fold'}, ['page_count'])
    assert not exists(db, old)
    result = bulk.undo(db, who(db, alice), edit_id)
    assert (result.changed, result.skipped) == (1, 0)
    after = {t: sorted(tuple(r) for r in db.execute(f'SELECT * FROM {t} ORDER BY rowid')) for t in before}
    assert after == before
    assert fk_violations(db) == []


def test_who_may_merge(db, people):
    alice, bob = who(db, people['alice']), who(db, people['bob'])
    old, bobs = unowned(db), add_book(db, people['bob'], 'Dune')
    film = add_book(db, people['bob'], 'Alien')
    db.execute("UPDATE books SET media_type = 'video' WHERE id = ?", (film,))
    book = lambda i: db.execute('SELECT * FROM books WHERE id = ?', (i,)).fetchone()

    assert merge.may_merge(db, bob, book(bobs), book(old)) is None             # yours and unowned
    assert 'same kind' in merge.may_merge(db, bob, book(bobs), book(film))
    assert 'different' in merge.may_merge(db, bob, book(bobs), book(bobs))
    alices = add_book(db, people['alice'], 'Dune')
    assert 'yours' in merge.may_merge(db, bob, book(bobs), book(alices))      # alice's record
    add_review(db, people['alice'], old)                                        # alice has data on it
    assert 'ask an admin' in merge.may_merge(db, bob, book(bobs), book(old))
    assert merge.may_merge(db, alice, book(bobs), book(old)) is None           # an admin may
    with pytest.raises(MergeError, match='ask an admin'):
        merge.apply(db, bob, bobs, old, {}, [])
    assert exists(db, old)

"""utils/bulk.py (ROADMAP 14a step 3): plan, apply, undo, genre only.

Driven directly, on its own connection and with no app context: the module
takes a connection and a user, nothing from Flask.
"""
import json
from collections import namedtuple

import pytest

from conftest import add_book, add_user
from utils import bulk
from utils.database import get_db_connection

User = namedtuple('User', 'id is_admin')


@pytest.fixture
def conn(db_path):
    """The module's own connection (fold() registered, foreign keys on)."""
    c = get_db_connection()
    yield c
    c.close()


@pytest.fixture
def who(people):
    return {name: User(uid, name == 'alice') for name, uid in people.items()}


def genre_of(conn, book_id):
    return conn.execute('SELECT genre FROM books WHERE id = ?', (book_id,)).fetchone()[0]


def shelf(conn, owner, genre_counts):
    """Books for `owner`: {genre: how many}; None means no genre."""
    ids = {}
    for genre, n in genre_counts.items():
        ids[genre] = []
        for i in range(n):
            bid = add_book(conn, owner, title=f'{genre or "Blank"} {i}')
            conn.execute('UPDATE books SET genre = ? WHERE id = ?', (genre, bid))
            ids[genre].append(bid)
    conn.commit()
    return ids


def everything(ids):
    return [i for group in ids.values() for i in group]


def cookbooks(conn, people):
    """The spec's cookbook case, scaled down. alice is admin, so her own
    shelf is the one to edit; bob's household copies are 'Not yours' for him
    and checked in the permission tests."""
    return shelf(conn, people['alice'], {'Cooking': 4, 'Cookbook': 3, 'Cookery': 2, 'Reference': 2,
                                         None: 2, 'Cookbooks': 1})


# --- plan --------------------------------------------------------------------

def test_plan_groups_changes_by_before_value(conn, people, who):
    ids = cookbooks(conn, people)
    p = bulk.plan(conn, who['alice'], 'genre', {'genre': 'Cookbooks'}, everything(ids))
    assert [(g.key, g.count) for g in p.groups] == [
        ('Cooking', 4), ('Cookbook', 3), ('Cookery', 2), ('Reference', 2), (None, 2)]
    assert all(g.label.endswith('\u2192 Cookbooks') for g in p.groups)
    assert p.groups[0].label == 'Cooking \u2192 Cookbooks' and p.groups[-1].label == '(no genre) \u2192 Cookbooks'
    assert p.changes == 13 and p.same == 1 and p.skipped == {}
    assert sorted(p.groups[0].ids) == sorted(ids['Cooking'])


def test_plan_writes_nothing(conn, people, who):
    ids = cookbooks(conn, people)
    before = conn.total_changes
    bulk.plan(conn, who['alice'], 'genre', {'genre': 'Cookbooks'}, everything(ids))
    assert conn.total_changes == before
    assert genre_of(conn, ids['Cooking'][0]) == 'Cooking'


def test_a_different_spelling_is_a_change_and_blank_counts_as_none(conn, people, who):
    a = shelf(conn, people['alice'], {'cooking': 1, '': 1, None: 1})
    p = bulk.plan(conn, who['alice'], 'genre', {'genre': 'Cooking'}, everything(a))
    assert p.changes == 3 and p.same == 0
    cleared = bulk.plan(conn, who['alice'], 'genre', {'genre': None}, everything(a))
    assert (cleared.changes, cleared.same) == (1, 2)     # '' and NULL are already "no genre"


def test_plan_fingerprint_follows_the_data_and_the_value(conn, people, who):
    ids = everything(cookbooks(conn, people))
    alice = who['alice']
    one = bulk.plan(conn, alice, 'genre', {'genre': 'Cookbooks'}, ids)
    assert one.fingerprint == bulk.plan(conn, alice, 'genre', {'genre': 'Cookbooks'}, ids).fingerprint
    assert one.fingerprint != bulk.plan(conn, alice, 'genre', {'genre': 'Food'}, ids).fingerprint
    conn.execute('UPDATE books SET genre = ? WHERE id = ?', ('Elsewhere', ids[0]))
    assert one.fingerprint != bulk.plan(conn, alice, 'genre', {'genre': 'Cookbooks'}, ids).fingerprint


def test_params_are_checked(conn, people, who):
    ids = everything(shelf(conn, people['alice'], {'A': 1}))
    alice = who['alice']
    for params in ({}, None, {'genre': ''}, {'genre': '   '}, {'genre': 'x' * 81}, {'genre': 'a\x00b'}):
        with pytest.raises(bulk.BulkError):
            bulk.plan(conn, alice, 'genre', params, ids)
    with pytest.raises(bulk.BulkError):
        bulk.plan(conn, alice, 'title', {'title': 'x'}, ids)         # not on the whitelist
    with pytest.raises(bulk.BulkError):
        bulk.plan(conn, alice, 'genre', {'genre': 'x'}, [])
    with pytest.raises(bulk.BulkError):
        bulk.plan(conn, alice, 'genre', {'genre': 'x'}, ['abc'])


def test_clean_genre():
    assert bulk.clean_genre('  Sci-Fi \n Fantasy ') == 'Sci-Fi Fantasy'
    assert bulk.clean_genre('Sci-Fi') == 'Sci-Fi'           # no title-casing
    assert bulk.clean_genre('x' * 80) == 'x' * 80


def test_cap_of_500(conn, people, who):
    with pytest.raises(bulk.TooMany):
        bulk.plan(conn, who['alice'], 'genre', {'genre': 'x'}, list(range(1, 502)))
    # Repeats don't count twice
    book = add_book(conn, people['alice'])
    assert bulk.plan(conn, who['alice'], 'genre', {'genre': 'x'}, [book] * 600).changes == 1


# --- permission --------------------------------------------------------------

def test_household_member_sees_but_cannot_edit(conn, people, who):
    mine = shelf(conn, people['alice'], {'Fiction': 2})['Fiction']
    p = bulk.plan(conn, who['bob'], 'genre', {'genre': 'Cookbooks'}, mine)
    assert p.skipped == {'Not yours': mine} and p.changes == 0
    assert [r.title for r in p.rows] == ['Fiction 0', 'Fiction 1']        # visible, so named
    with pytest.raises(bulk.BulkError):
        bulk.apply(conn, who['bob'], 'genre', {'genre': 'Cookbooks'}, mine, p.fingerprint)
    assert genre_of(conn, mine[0]) == 'Fiction'


def test_forged_ids_are_not_found_and_leak_nothing(conn, people, who):
    stranger = add_user(conn, 'dave')
    secret = add_book(conn, stranger, title='Dave Diary', author='Dave')
    p = bulk.plan(conn, who['carol'], 'genre', {'genre': 'X'}, [secret, 99999])
    assert p.skipped == {'Not found': [secret, 99999]}
    for row in p.rows:
        assert (row.title, row.creator, row.cover, row.before) == ('', '', None, None)
    with pytest.raises(bulk.BulkError):
        bulk.apply(conn, who['carol'], 'genre', {'genre': 'X'}, [secret], p.fingerprint)
    assert genre_of(conn, secret) is None


def test_a_friend_can_see_but_not_edit(conn, people, who):
    book = shelf(conn, people['alice'], {'Fiction': 1})['Fiction'][0]
    p = bulk.plan(conn, who['carol'], 'genre', {'genre': 'X'}, [book])      # carol is alice's friend
    assert p.skipped == {'Not yours': [book]}


def test_admin_edits_anyones_item(conn, people, who):
    bobs = shelf(conn, people['bob'], {'Fiction': 1})['Fiction']
    p = bulk.plan(conn, who['alice'], 'genre', {'genre': 'Novels'}, bobs)
    assert p.changes == 1
    bulk.apply(conn, who['alice'], 'genre', {'genre': 'Novels'}, bobs, p.fingerprint)
    assert genre_of(conn, bobs[0]) == 'Novels'


# --- apply -------------------------------------------------------------------

def test_the_cookbook_case_from_plan_to_undo(conn, people, who):
    """Spec section 5: set Cookbooks, leave a group out, then undo with one
    item changed since."""
    ids = cookbooks(conn, people)
    alice, selection = who['alice'], everything(ids)
    params = {'genre': 'Cookbooks'}

    p = bulk.plan(conn, alice, 'genre', params, selection)
    excluded = ids['Reference']                      # he unticks the Reference group
    result = bulk.apply(conn, alice, 'genre', params, selection, p.fingerprint, excluded)

    assert (result.changed, result.failed) == (11, 0)
    assert result.summary == 'Genre set to Cookbooks on 11 items'
    for genre in ('Cooking', 'Cookbook', 'Cookery', None, 'Cookbooks'):
        assert {genre_of(conn, i) for i in ids[genre]} == {'Cookbooks'}
    assert {genre_of(conn, i) for i in ids['Reference']} == {'Reference'}

    # The journal has exactly the changed items (not the "same" one, not the excluded)
    edit = conn.execute('SELECT * FROM bulk_edits WHERE id = ?', (result.edit_id,)).fetchone()
    assert (edit['action'], edit['item_count'], edit['undone_at']) == ('genre', 11, None)
    assert json.loads(edit['params']) == params
    items = conn.execute('SELECT * FROM bulk_edit_items WHERE edit_id = ?', (result.edit_id,)).fetchall()
    assert len(items) == 11
    assert {i['book_id'] for i in items} == set(ids['Cooking'] + ids['Cookbook'] + ids['Cookery'] + ids[None])
    one = next(i for i in items if i['book_id'] == ids['Cooking'][0])
    assert json.loads(one['before']) == {'genre': 'Cooking'} and json.loads(one['after']) == {'genre': 'Cookbooks'}

    # Someone edits one of them by hand; undo leaves that one alone
    conn.execute("UPDATE books SET genre = 'Food' WHERE id = ?", (ids['Cookery'][0],))
    conn.commit()
    undone = bulk.undo(conn, alice, result.edit_id)
    assert (undone.changed, undone.skipped) == (10, 1)
    assert undone.summary == 'Undone: 10 restored, 1 changed since and left alone.'
    assert [genre_of(conn, i) for i in ids['Cooking']] == ['Cooking'] * 4
    assert [genre_of(conn, i) for i in ids[None]] == [None, None]
    assert genre_of(conn, ids['Cookery'][0]) == 'Food'
    assert genre_of(conn, ids['Cookery'][1]) == 'Cookery'
    assert genre_of(conn, ids['Cookbooks'][0]) == 'Cookbooks'     # was already Cookbooks, never journalled

    with pytest.raises(bulk.BulkError, match='Already undone'):
        bulk.undo(conn, alice, result.edit_id)


def test_clearing_a_genre_round_trips(conn, people, who):
    ids = everything(shelf(conn, people['alice'], {'Cooking': 2}))
    alice = who['alice']
    p = bulk.plan(conn, alice, 'genre', {'genre': None}, ids)
    r = bulk.apply(conn, alice, 'genre', {'genre': None}, ids, p.fingerprint)
    assert r.summary == 'Genre cleared on 2 items' and genre_of(conn, ids[0]) is None
    bulk.undo(conn, alice, r.edit_id)
    assert genre_of(conn, ids[0]) == 'Cooking'


def test_stale_plan_raises_with_the_new_plan_and_writes_nothing(conn, people, who):
    ids = everything(cookbooks(conn, people))
    alice = who['alice']
    p = bulk.plan(conn, alice, 'genre', {'genre': 'Cookbooks'}, ids)
    conn.execute("UPDATE books SET genre = 'Cookbooks' WHERE id = ?", (ids[0],))   # another tab
    conn.commit()
    with pytest.raises(bulk.StalePlan) as stale:
        bulk.apply(conn, alice, 'genre', {'genre': 'Cookbooks'}, ids, p.fingerprint)
    assert stale.value.plan.fingerprint != p.fingerprint
    assert stale.value.plan.same == p.same + 1
    assert conn.execute('SELECT COUNT(*) FROM bulk_edits').fetchone()[0] == 0
    assert genre_of(conn, ids[1]) == 'Cooking'
    # Applying the fresh plan works
    bulk.apply(conn, alice, 'genre', {'genre': 'Cookbooks'}, ids, stale.value.plan.fingerprint)
    assert genre_of(conn, ids[1]) == 'Cookbooks'


def test_nothing_to_change_is_refused(conn, people, who):
    ids = everything(shelf(conn, people['alice'], {'Cooking': 2}))
    alice = who['alice']
    p = bulk.plan(conn, alice, 'genre', {'genre': 'Cooking'}, ids)           # all the same
    with pytest.raises(bulk.BulkError):
        bulk.apply(conn, alice, 'genre', {'genre': 'Cooking'}, ids, p.fingerprint)
    p = bulk.plan(conn, alice, 'genre', {'genre': 'Food'}, ids)
    with pytest.raises(bulk.BulkError):
        bulk.apply(conn, alice, 'genre', {'genre': 'Food'}, ids, p.fingerprint, excluded_ids=ids)
    assert conn.execute('SELECT COUNT(*) FROM bulk_edits').fetchone()[0] == 0


def test_one_failing_item_leaves_the_rest_applied_and_is_reported(conn, people, who):
    ids = everything(shelf(conn, people['alice'], {'Cooking': 3}))
    alice = who['alice']
    # A trigger that refuses one item's update stands in for a constraint
    conn.execute(f"""CREATE TRIGGER refuse BEFORE UPDATE OF genre ON books WHEN NEW.id = {ids[1]}
                     BEGIN SELECT RAISE(ABORT, 'no'); END""")
    p = bulk.plan(conn, alice, 'genre', {'genre': 'Food'}, ids)
    r = bulk.apply(conn, alice, 'genre', {'genre': 'Food'}, ids, p.fingerprint)
    assert (r.changed, r.failed) == (2, 1)
    assert r.summary == 'Genre set to Food on 2 items. 1 could not be changed'
    assert [genre_of(conn, i) for i in ids] == ['Food', 'Cooking', 'Food']
    journalled = [row[0] for row in conn.execute('SELECT book_id FROM bulk_edit_items ORDER BY book_id')]
    assert journalled == [ids[0], ids[2]]                    # the journal matches the data


def test_a_change_between_plan_and_write_is_skipped_not_overwritten(conn, people, who, monkeypatch):
    """The write repeats the value the plan saw, so a race can't clobber."""
    ids = everything(shelf(conn, people['alice'], {'Cooking': 2}))
    alice = who['alice']
    p = bulk.plan(conn, alice, 'genre', {'genre': 'Food'}, ids)
    real_plan = bulk.plan

    def plan_then_race(*args, **kwargs):
        result = real_plan(*args, **kwargs)
        conn.execute("UPDATE books SET genre = 'Race' WHERE id = ?", (ids[0],))   # after the re-plan
        return result
    monkeypatch.setattr(bulk, 'plan', plan_then_race)
    r = bulk.apply(conn, alice, 'genre', {'genre': 'Food'}, ids, p.fingerprint)
    assert (r.changed, r.failed) == (1, 1)
    assert [genre_of(conn, i) for i in ids] == ['Race', 'Food']


def test_apply_commits_and_a_second_connection_sees_it(conn, people, who, db_path):
    ids = everything(shelf(conn, people['alice'], {'Cooking': 2}))
    p = bulk.plan(conn, who['alice'], 'genre', {'genre': 'Food'}, ids)
    bulk.apply(conn, who['alice'], 'genre', {'genre': 'Food'}, ids, p.fingerprint)
    other = get_db_connection()
    try:
        assert genre_of(other, ids[0]) == 'Food'
        assert other.execute('SELECT COUNT(*) FROM bulk_edit_items').fetchone()[0] == 2
    finally:
        other.close()


def test_no_reading_data_is_touched(conn, people, who):
    """Genre edits write only books.genre."""
    ids = everything(shelf(conn, people['alice'], {'Cooking': 1}))
    tables = ('collections', 'read_data', 'reading_sessions', 'book_tags', 'wishlist')
    counts = lambda: [conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] for t in tables]
    before = counts()
    p = bulk.plan(conn, who['alice'], 'genre', {'genre': 'Food'}, ids)
    bulk.apply(conn, who['alice'], 'genre', {'genre': 'Food'}, ids, p.fingerprint)
    assert counts() == before


# --- undo --------------------------------------------------------------------

def applied(conn, user, ids, genre='Food'):
    p = bulk.plan(conn, user, 'genre', {'genre': genre}, ids)
    return bulk.apply(conn, user, 'genre', {'genre': genre}, ids, p.fingerprint)


def test_undo_is_only_for_the_edits_owner(conn, people, who):
    ids = everything(shelf(conn, people['alice'], {'Cooking': 1}))
    r = applied(conn, who['alice'], ids)
    for name in ('bob', 'carol'):
        with pytest.raises(bulk.BulkError):
            bulk.undo(conn, who[name], r.edit_id)
    with pytest.raises(bulk.BulkError):
        bulk.undo(conn, who['alice'], 99999)
    assert genre_of(conn, ids[0]) == 'Food'


def test_undo_rechecks_permission_now(conn, people, who):
    """bob edits his own books, then one is given to someone else. Undo
    must not touch what is no longer his."""
    bob = who['bob']
    ids = everything(shelf(conn, people['bob'], {'Cooking': 2}))
    r = applied(conn, bob, ids)
    stranger = add_user(conn, 'dave')
    conn.execute('UPDATE books SET added_by = ? WHERE id = ?', (stranger, ids[0]))   # given away
    conn.commit()
    undone = bulk.undo(conn, bob, r.edit_id)
    assert (undone.changed, undone.skipped) == (1, 1)
    assert genre_of(conn, ids[0]) == 'Food'                  # not his any more: left alone
    assert genre_of(conn, ids[1]) == 'Cooking'


def test_undo_of_a_deleted_book_is_skipped(conn, people, who):
    ids = everything(shelf(conn, people['alice'], {'Cooking': 2}))
    r = applied(conn, who['alice'], ids)
    conn.execute('DELETE FROM books WHERE id = ?', (ids[0],))       # journal row goes by cascade
    conn.commit()
    undone = bulk.undo(conn, who['alice'], r.edit_id)
    assert undone.changed == 1 and genre_of(conn, ids[1]) == 'Cooking'


# --- history, sweep, genres --------------------------------------------------

def test_history_lists_recent_edits_newest_first_within_30_days(conn, people, who):
    alice = who['alice']
    ids = everything(shelf(conn, people['alice'], {'A': 1}))
    first = applied(conn, alice, ids, 'B')
    second = applied(conn, alice, ids, 'C')
    assert [h['id'] for h in bulk.history(conn, alice)] == [second.edit_id, first.edit_id]
    assert bulk.history(conn, who['bob']) == []
    conn.execute("UPDATE bulk_edits SET created_at = datetime('now', '-31 days') WHERE id = ?", (first.edit_id,))
    assert [h['id'] for h in bulk.history(conn, alice)] == [second.edit_id]
    assert len(bulk.history(conn, alice, limit=0)) == 0


def test_apply_sweeps_journals_older_than_30_days(conn, people, who):
    alice = who['alice']
    ids = everything(shelf(conn, people['alice'], {'A': 1}))
    old = applied(conn, alice, ids, 'B')
    young = applied(conn, alice, ids, 'C')
    conn.execute("UPDATE bulk_edits SET created_at = datetime('now', '-31 days') WHERE id = ?", (old.edit_id,))
    conn.commit()
    new = applied(conn, alice, ids, 'D')
    assert [r[0] for r in conn.execute('SELECT id FROM bulk_edits ORDER BY id')] == [young.edit_id, new.edit_id]
    assert conn.execute('SELECT COUNT(*) FROM bulk_edit_items WHERE edit_id = ?',
                        (old.edit_id,)).fetchone()[0] == 0           # by cascade
    with pytest.raises(bulk.BulkError):
        bulk.undo(conn, alice, old.edit_id)


def test_genres_group_by_fold_and_show_the_most_used_spelling(conn, people, who):
    alice = people['alice']
    shelf(conn, alice, {'Cookbooks': 3, 'cookbooks': 1, 'Cook-books': 1, 'Fiction': 5, 'Sci-Fi': 1, None: 2, '': 1})
    shelf(conn, people['bob'], {'Poetry': 4})            # not alice's to edit, so not offered
    video = add_book(conn, alice, title='A film')
    conn.execute("UPDATE books SET genre = 'Documentary', media_type = 'video' WHERE id = ?", (video,))
    conn.commit()
    got = bulk.genres(conn, who['alice'])
    assert got[0]['count'] == 5 and got[-1]['count'] == 1      # most used first
    by_value = {g['value']: g['count'] for g in got}
    assert by_value == {'Cookbooks': 5, 'Fiction': 5, 'Sci-Fi': 1, 'Documentary': 1}
    assert [g['value'] for g in bulk.genres(conn, who['alice'], 'video')] == ['Documentary']
    assert 'Documentary' not in {g['value'] for g in bulk.genres(conn, who['alice'], 'book')}
    assert bulk.genres(conn, User(999, False)) == []


def test_an_undo_that_restores_nothing_says_why(conn, people, who):
    alice = who['alice']
    ids = [add_book(conn, people['alice'], title=f'B{i}') for i in range(2)]
    p = bulk.plan(conn, alice, 'genre', {'genre': 'SF'}, ids)
    r = bulk.apply(conn, alice, 'genre', {'genre': 'SF'}, ids, p.fingerprint)
    conn.execute("UPDATE books SET genre = 'Other'")
    conn.commit()
    assert bulk.undo(conn, alice, r.edit_id).summary == 'Nothing to undo: 2 items changed since, and keep the later change.'

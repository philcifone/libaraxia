"""The granular Goodreads import, headless (utils/goodreads_plan.py,
ROADMAP 14b, docs/GOODREADS-IMPORT-SPEC.md sections 6, 8, 9 and 13)."""
import json
from types import SimpleNamespace

import pytest

from conftest import add_book, add_user, scalar
from test_goodreads import csv_text, row

from utils import goodreads_plan as gp


def who(user_id, admin=False):
    return SimpleNamespace(id=user_id, is_admin=admin)


def staged(db, user_id, *rows):
    """Stage a file and return its plan."""
    gp.stage(db, who(user_id), csv_text(*rows), 'goodreads_library_export.csv')
    return gp.plan(db, who(user_id))


def by_title(plan, title):
    return next(r for r in plan.rows if r.data['title'] == title)


def with_isbn(db, book_id, isbn):
    db.execute('UPDATE books SET isbn = ? WHERE id = ?', (isbn, book_id))
    db.commit()


def give(db, user_id, book_id, status=None, rating=None, comment=None, sessions=()):
    """Your own data on a book."""
    if status:
        db.execute('INSERT INTO collections (user_id, book_id, status) VALUES (?, ?, ?)',
                   (user_id, book_id, status))
    if rating or comment:
        db.execute('INSERT INTO read_data (user_id, book_id, rating, comment) VALUES (?, ?, ?, ?)',
                   (user_id, book_id, rating, comment))
    for date in sessions:
        db.execute('INSERT INTO reading_sessions (user_id, book_id, date_completed) VALUES (?, ?, ?)',
                   (user_id, book_id, date))
    db.commit()


def wish(db, user_id, title):
    book = add_book(db, user_id, title, 'Some Author')
    db.execute('INSERT INTO wishlist (user_id, book_id) VALUES (?, ?)', (user_id, book))
    db.commit()
    return book


# --- stage ---------------------------------------------------------------------

def test_stage_replaces_the_previous_upload_and_writes_nothing_else(db, people):
    alice = people['alice']
    before = {t: scalar(db, f'SELECT COUNT(*) FROM {t}') for t in ('books', 'collections', 'read_data')}
    assert gp.stage(db, who(alice), csv_text(row('One'), row('Two')), 'a.csv') == 2
    assert gp.stage(db, who(alice), csv_text(row('Three')), 'b.csv') == 1
    staged_rows = db.execute('SELECT line, data, filename FROM goodreads_staging WHERE user_id = ?',
                             (alice,)).fetchall()
    assert [(r['line'], json.loads(r['data'])['title'], r['filename']) for r in staged_rows] == [(2, 'Three', 'b.csv')]
    assert before == {t: scalar(db, f'SELECT COUNT(*) FROM {t}') for t in before}


def test_stage_refuses_a_file_that_is_not_an_export_or_too_big(db, people, monkeypatch):
    from utils.goodreads import ImportFileError
    with pytest.raises(ImportFileError, match='missing column'):
        gp.stage(db, who(people['alice']), 'a,b\n1,2\n', 'x.csv')
    with pytest.raises(ImportFileError, match='no books'):
        gp.stage(db, who(people['alice']), csv_text(), 'x.csv')
    monkeypatch.setattr(gp, 'MAX_ROWS', 2)
    with pytest.raises(ImportFileError, match='has 3 rows; the import takes up to 2'):
        gp.stage(db, who(people['alice']), csv_text(row('a'), row('b'), row('c')), 'x.csv')
    assert scalar(db, 'SELECT COUNT(*) FROM goodreads_staging') == 0


def test_stage_sweeps_old_uploads_and_plan_ignores_them(db, people):
    alice, bob = people['alice'], people['bob']
    gp.stage(db, who(bob), csv_text(row('Old')), 'old.csv')
    db.execute("UPDATE goodreads_staging SET created_at = datetime('now', '-25 hours')")
    db.commit()
    assert gp.plan(db, who(bob)) is None and not gp.has_staging(db, who(bob))
    gp.stage(db, who(alice), csv_text(row('New')), 'new.csv')
    assert scalar(db, 'SELECT COUNT(*) FROM goodreads_staging WHERE user_id = ?', bob) == 0


def test_plan_without_staging_is_none_and_discard_clears_it(db, people):
    alice = people['alice']
    assert gp.plan(db, who(alice)) is None
    staged(db, alice, row('One'))
    gp.discard(db, who(alice))
    assert gp.plan(db, who(alice)) is None


# --- classification: one test per box --------------------------------------------

def test_read_not_in_your_library_defaults_to_not_owned(db, people):
    p = staged(db, people['alice'], row('Piranesi', my_rating='5', date_read='2022/01/09'),
               row('Quit', 'dnf'))
    for title in ('Piranesi', 'Quit'):
        r = by_title(p, title)
        assert (r.box, r.kind, r.default, r.choice) == ('read_new', 'none', 'not_owned', 'not_owned')
        assert r.choices == ['not_owned', 'library', 'skip']
        assert r.writes
    assert by_title(p, 'Piranesi').adds == ['new book, not owned', 'status Read', 'rating ★5',
                                            'a reading session (2022-01-09)']
    assert by_title(p, 'Quit').adds == ['new book, not owned', 'status Did Not Finish']


def test_currently_reading_needs_a_decision_when_new_or_no_status_here(db, people):
    alice = people['alice']
    mine = add_book(db, alice, 'On My Shelf', 'Some Author')
    has_status = add_book(db, alice, 'Already Read Here', 'Some Author')
    give(db, alice, has_status, status='read', sessions=['2024-01-01'])
    p = staged(db, alice, row('Normal People', 'currently-reading'),
               row('On My Shelf', 'currently-reading'),
               row('Already Read Here', 'currently-reading'))
    new, shelf = by_title(p, 'Normal People'), by_title(p, 'On My Shelf')
    assert (new.box, new.kind, new.default, new.choice) == ('decide_reading', 'none', 'ask', 'ask')
    assert new.choices == ['still_reading', 'finished', 'dnf', 'skip']
    assert not new.writes and new.adds == []
    assert (shelf.box, shelf.kind) == ('decide_reading', 'shelf')
    # Your status here wins: not asked, and nothing to add
    here = by_title(p, 'Already Read Here')
    assert here.box == 'nothing' and 'status: yours Read, Goodreads Currently Reading' in here.differs
    assert p.undecided == 2


def test_read_on_goodreads_and_on_your_wishlist_needs_a_decision(db, people):
    alice = people['alice']
    wish(db, alice, 'The Overstory')
    wish(db, alice, 'Reading It')
    p = staged(db, alice, row('The Overstory', my_rating='5', date_read='2023/04/02'),
               row('Reading It', 'currently-reading'))
    r = by_title(p, 'The Overstory')
    assert (r.box, r.kind, r.choice) == ('decide_wishlist', 'wishlist', 'ask')
    assert r.choices == ['keep_wished', 'drop_wish', 'bought', 'skip']
    # Currently reading but on your wishlist: the wishlist decision, not the reading one
    assert by_title(p, 'Reading It').box == 'decide_wishlist'


@pytest.mark.parametrize('how', ['shelf', 'not_owned', 'removed', 'household'])
def test_read_row_matching_a_book_you_have_fills_what_is_missing(db, people, how):
    alice, bob = people['alice'], people['bob']
    book = add_book(db, bob if how == 'household' else alice, 'Beloved', 'Some Author')
    if how == 'not_owned':
        db.execute('UPDATE books SET owned = 0 WHERE id = ?', (book,))
    if how == 'removed':
        db.execute("UPDATE books SET removed_at = '2025-01-01' WHERE id = ?", (book,))
    db.commit()
    p = staged(db, alice, row('Beloved', my_rating='4', my_review='Haunting'))
    r = by_title(p, 'Beloved')
    assert (r.box, r.kind, r.default, r.choices) == ('fill', how, 'fill', ['fill', 'skip'])
    assert r.book['id'] == book
    assert r.book['owner'] == ('bob' if how == 'household' else None)
    assert r.adds == ['status Read', 'rating ★4', 'review', 'a reading session']


def test_want_to_read_not_in_libaraxia_goes_to_the_wishlist(db, people):
    p = staged(db, people['alice'], row('Wanted', 'to-read', private_notes='a gift idea'))
    r = by_title(p, 'Wanted')
    assert (r.box, r.default, r.choices) == ('want_new', 'wishlist', ['wishlist', 'skip'])
    assert r.adds == ['new wishlist entry']


@pytest.mark.parametrize('how, reason', [('shelf', 'you own it now'), ('household', 'you own it now'),
                                         ('wishlist', 'already on your wishlist'),
                                         ('not_owned', 'you read it here'), ('removed', 'you let it go')])
def test_want_to_read_you_already_have_is_nothing_to_do(db, people, how, reason):
    # No Want to Read status any more for a to-read book you own (decision 3)
    alice, bob = people['alice'], people['bob']
    if how == 'wishlist':
        wish(db, alice, 'Wanted')
    else:
        book = add_book(db, bob if how == 'household' else alice, 'Wanted', 'Some Author')
        if how == 'not_owned':
            db.execute('UPDATE books SET owned = 0 WHERE id = ?', (book,))
        if how == 'removed':
            db.execute("UPDATE books SET removed_at = '2025-01-01' WHERE id = ?", (book,))
        db.commit()
    r = by_title(staged(db, alice, row('Wanted', 'to-read')), 'Wanted')
    assert (r.box, r.kind, r.reason, r.choices, r.writes) == ('want_nothing', how, reason, [], False)


def test_unknown_shelf_is_not_sure_and_skipped_by_default(db, people):
    alice = people['alice']
    add_book(db, alice, 'Have It', 'Some Author')
    p = staged(db, alice, row('Kindle Deal', 'kindle-deals', read_count='0'),
               row('Have It', 'kindle-deals', read_count='0'))
    r = by_title(p, 'Kindle Deal')
    assert (r.box, r.default, r.choices, r.writes) == ('unsure', 'skip', ['skip', 'not_owned', 'wishlist'], False)
    assert by_title(p, 'Have It').box == 'nothing'


def test_nothing_to_do_rows(db, people):
    alice = people['alice']
    book = add_book(db, alice, 'Complete', 'Some Author')
    give(db, alice, book, status='read', rating=3, comment='Mine', sessions=['2020-01-01'])
    p = staged(db, alice, row('Complete', my_rating='5', date_read='2020/01/01'), row(''),
               row('Twice'), row('Twice'))
    complete = by_title(p, 'Complete')
    assert complete.box == 'nothing' and complete.reason == 'in Libaraxia, nothing missing; yours kept'
    assert complete.differs == ['rating: yours ★3, Goodreads ★5']
    untitled = next(r for r in p.rows if r.data['title'] == '')
    assert (untitled.box, untitled.reason) == ('nothing', 'no title')
    second = p.rows[3]
    assert (second.box, second.same_as, second.reason) == ('nothing', 4, 'same book as line 4')
    assert not any(r.writes for r in (complete, untitled, second))


def test_same_book_twice_by_book_id_or_matched_book(db, people):
    alice = people['alice']
    add_book(db, alice, 'Mine', 'Some Author')
    p = staged(db, alice, row('Mine'), row('Mine (Deluxe)', author='Some Author'),
               row('One Title', book_id='77'), row('Other Title', book_id='77'))
    assert [r.same_as for r in p.rows] == [None, 2, None, 4]


# --- matching ---------------------------------------------------------------------

def test_book_id_memory_beats_a_changed_title(db, people):
    alice = people['alice']
    book = add_book(db, alice, 'Retitled Here', 'Someone Else')
    imp = db.execute("INSERT INTO goodreads_imports (user_id, row_count) VALUES (?, 1)", (alice,)).lastrowid
    db.execute("INSERT INTO goodreads_rows (import_id, line, goodreads_id, book_id, outcome) "
               "VALUES (?, 2, '42', ?, 'not_owned')", (imp, book))
    db.commit()
    r = by_title(staged(db, alice, row('Original Title', book_id='42')), 'Original Title')
    assert r.book['id'] == book and r.kind == 'shelf'

    # An undone import is forgotten
    db.execute("UPDATE goodreads_imports SET undone_at = CURRENT_TIMESTAMP WHERE id = ?", (imp,))
    db.commit()
    r = by_title(gp.plan(db, who(alice)), 'Original Title')
    assert r.kind == 'none'


def test_book_id_memory_never_points_outside_your_books(db, people):
    alice = people['alice']
    dave = add_user(db, 'dave')
    theirs = add_book(db, dave, 'Not Yours', 'X')
    imp = db.execute("INSERT INTO goodreads_imports (user_id, row_count) VALUES (?, 1)", (alice,)).lastrowid
    db.execute("INSERT INTO goodreads_rows (import_id, line, goodreads_id, book_id, outcome) "
               "VALUES (?, 2, '42', ?, 'filled')", (imp, theirs))
    db.commit()
    r = by_title(staged(db, alice, row('Not Yours', author='X', book_id='42')), 'Not Yours')
    assert r.kind == 'none' and r.book is None


def test_strangers_and_friends_books_are_never_matched(db, people):
    alice = people['alice']
    dave = add_user(db, 'dave')
    with_isbn(db, add_book(db, dave, 'Dune', 'Frank Herbert'), '9780441172719')
    add_book(db, people['carol'], 'Emma', 'Jane Austen')
    p = staged(db, alice, row('Dune', author='Frank Herbert', isbn13='="9780441172719"'),
               row('Emma', author='Jane Austen'))
    assert [r.kind for r in p.rows] == ['none', 'none']


def test_own_copy_wins_over_the_households(db, people):
    alice, bob = people['alice'], people['bob']
    add_book(db, bob, 'Middlemarch', 'George Eliot')
    mine = add_book(db, alice, 'Middlemarch', 'George Eliot')
    r = by_title(staged(db, alice, row('Middlemarch', author='George Eliot')), 'Middlemarch')
    assert (r.book['id'], r.kind) == (mine, 'shelf')


def test_skipped_last_time_defaults_to_skip_and_keeps_its_choices(db, people):
    alice = people['alice']
    imp = db.execute("INSERT INTO goodreads_imports (user_id, row_count) VALUES (?, 2)", (alice,)).lastrowid
    db.execute("INSERT INTO goodreads_rows (import_id, line, goodreads_id, book_id, outcome) "
               "VALUES (?, 2, '9', NULL, 'skipped')", (imp,))
    db.execute("INSERT INTO goodreads_rows (import_id, line, goodreads_id, book_id, outcome) "
               "VALUES (?, 3, '10', NULL, 'skipped')", (imp,))
    db.commit()
    p = staged(db, alice, row('Passed On', book_id='9'), row('Still Unsure', 'currently-reading', book_id='10'))
    r = by_title(p, 'Passed On')
    assert (r.box, r.home_box, r.reason, r.default, r.choice) == ('nothing', 'read_new', 'skipped last time',
                                                                   'skip', 'skip')
    assert r.choices == ['skip', 'not_owned', 'library'] and not r.writes
    asked = by_title(p, 'Still Unsure')
    assert (asked.box, asked.home_box, asked.choice) == ('nothing', 'decide_reading', 'skip')
    # Undoing the skip: the home box's choices still work
    gp.choose(db, who(alice), [2], 'library')
    r = by_title(gp.plan(db, who(alice)), 'Passed On')
    assert r.choice == 'library' and r.writes and r.adds[0] == 'new book, in your library'


# --- fill ---------------------------------------------------------------------

def test_fill_adds_each_part_only_when_missing(db, people):
    alice = people['alice']
    book = add_book(db, alice, 'Partly', 'Some Author')
    give(db, alice, book, comment='My words')        # a review, no rating, no status
    r = by_title(staged(db, alice, row('Partly', my_rating='4', my_review='My words')), 'Partly')
    assert r.adds == ['status Read', 'rating ★4', 'a reading session']
    assert r.differs == []


def test_fill_keeps_your_status_and_rating_and_lists_the_differences(db, people):
    alice = people['alice']
    book = add_book(db, alice, 'Disagree', 'Some Author')
    give(db, alice, book, status='did not finish', rating=2)
    r = by_title(staged(db, alice, row('Disagree', my_rating='5', my_review='Great')), 'Disagree')
    # Sessions follow what Goodreads says (section 6): you have none, it says
    # read, so one is added even though your status here stays Did Not Finish
    assert r.box == 'fill' and r.adds == ['review', 'a reading session']
    assert r.differs == ['status: yours Did Not Finish, Goodreads Read', 'rating: yours ★2, Goodreads ★5']


def test_fill_appends_a_different_goodreads_review_below_yours(db, people):
    alice = people['alice']
    book = add_book(db, alice, 'Reread', 'Some Author')
    give(db, alice, book, status='read', rating=5, comment='Better the second time.\n',
         sessions=['2025-03-01'])
    r = by_title(staged(db, alice, row('Reread', my_rating='3', date_read='2011/05/02',
                                       my_review='Fine, I suppose.')), 'Reread')
    assert r.adds == ['Goodreads review below yours', 'a reading session (2011-05-02)']
    assert r.preview == ('Better the second time.\n\n----\nGoodreads review, read 2011-05-02, ★3:\n'
                         'Fine, I suppose.')


def test_review_label_uses_date_added_and_drops_missing_stars():
    d = {'date_read': None, 'date_added': '2010-02-03', 'rating': None, 'review': 'x'}
    assert gp.appended_review('Mine', d) == 'Mine\n\n----\nGoodreads review, added 2010-02-03:\nx'


def test_fill_does_not_append_a_review_already_in_yours(db, people):
    alice = people['alice']
    book = add_book(db, alice, 'Kept', 'Some Author')
    give(db, alice, book, status='read', sessions=[None],
         comment='Mine.\n\n----\nGoodreads review, read 2011-05-02:\nFINE,   I suppose.')
    r = by_title(staged(db, alice, row('Kept', my_review='Fine, I suppose.')), 'Kept')
    assert r.box == 'nothing'


def test_sessions_none_of_yours_adds_read_count_sessions(db, people):
    alice = people['alice']
    add_book(db, alice, 'Twice', 'Some Author')
    r = by_title(staged(db, alice, row('Twice', read_count='2', date_read='2024/03/08')), 'Twice')
    assert r.parts['sessions'] == [None, '2024-03-08']
    assert '2 reading sessions (last 2024-03-08)' in r.adds


def test_sessions_with_yours_add_one_dated_session_only_if_the_date_is_absent(db, people):
    alice = people['alice']
    has_date = add_book(db, alice, 'Has Date', 'Some Author')
    other_date = add_book(db, alice, 'Other Date', 'Some Author')
    undated = add_book(db, alice, 'Undated Gr', 'Some Author')
    for book in (has_date, other_date, undated):
        give(db, alice, book, status='read', sessions=['2019-03-11', None])
    p = staged(db, alice, row('Has Date', read_count='3', date_read='2019/03/11'),
               row('Other Date', read_count='3', date_read='2018/01/01'),
               row('Undated Gr', read_count='3'))
    assert by_title(p, 'Has Date').box == 'nothing'
    assert by_title(p, 'Other Date').parts == {'sessions': ['2018-01-01']}
    assert by_title(p, 'Undated Gr').box == 'nothing'


def test_dnf_and_currently_reading_add_no_sessions(db, people):
    alice = people['alice']
    add_book(db, alice, 'Quit Here', 'Some Author')
    r = by_title(staged(db, alice, row('Quit Here', 'dnf', read_count='1')), 'Quit Here')
    assert 'sessions' not in r.parts


# --- choices ---------------------------------------------------------------------

def test_choices_persist_and_the_default_is_stored_as_null(db, people):
    alice = people['alice']
    staged(db, alice, row('A'), row('B'), row('C', 'currently-reading'))
    result = gp.choose(db, who(alice), [2, 3], 'library')
    assert result['saved'] == [2, 3] and result['refused'] == []
    assert [by_title(result['plan'], t).choice for t in 'AB'] == ['library', 'library']
    gp.choose(db, who(alice), [3], 'not_owned')
    assert [r['choice'] for r in db.execute('SELECT choice FROM goodreads_staging ORDER BY line')] == \
           ['library', None, None]
    gp.choose(db, who(alice), ['4'], 'finished')
    p = gp.plan(db, who(alice))
    assert by_title(p, 'C').choice == 'finished' and p.undecided == 0


def test_a_choice_not_valid_for_the_box_is_refused_not_coerced(db, people):
    alice = people['alice']
    staged(db, alice, row('Read One'), row('Wanted', 'to-read'))
    result = gp.choose(db, who(alice), [2, 3], 'library')
    assert result['saved'] == [2]
    assert result['refused'] == [{'line': 3, 'error': '"Add to my library" is not a choice for this row.'}]
    assert by_title(gp.plan(db, who(alice)), 'Wanted').choice == 'wishlist'
    for bad in ('ask', 'drop table', None):
        with pytest.raises(gp.PlanError):
            gp.choose(db, who(alice), [2], bad)
    with pytest.raises(gp.PlanError):
        gp.choose(db, who(alice), [], 'skip')
    with pytest.raises(gp.PlanError):
        gp.choose(db, who(alice), ['x'], 'skip')


def test_decisions_word_what_they_would_add(db, people):
    alice = people['alice']
    wish(db, alice, 'Wished')
    staged(db, alice, row('New Reading', 'currently-reading', my_rating='4'),
           row('Wished', my_rating='5', date_read='2023/04/02'))
    gp.choose(db, who(alice), [2], 'finished')
    gp.choose(db, who(alice), [3], 'drop_wish')
    p = gp.plan(db, who(alice))
    assert by_title(p, 'New Reading').adds == ['new book, not owned', 'status Read', 'rating ★4',
                                               'a reading session']
    assert by_title(p, 'Wished').adds == ['off your wishlist, as read and not owned', 'status Read',
                                          'rating ★5', 'a reading session (2023-04-02)']
    gp.choose(db, who(alice), [2], 'dnf')
    assert by_title(gp.plan(db, who(alice)), 'New Reading').adds == ['new book, not owned',
                                                                      'status Did Not Finish', 'rating ★4']


def test_currently_reading_on_your_wishlist_counts_as_finished(db, people):
    alice = people['alice']
    wish(db, alice, 'Was Wished')
    staged(db, alice, row('Was Wished', 'currently-reading'))
    gp.choose(db, who(alice), [2], 'keep_wished')
    r = gp.plan(db, who(alice)).rows[0]
    assert r.parts == {'status': 'read', 'sessions': [None]}


def test_unsure_added_as_read_gets_one_undated_session(db, people):
    alice = people['alice']
    staged(db, alice, row('Maybe', 'kindle-deals', read_count='0'))
    gp.choose(db, who(alice), [2], 'not_owned')
    r = gp.plan(db, who(alice)).rows[0]
    assert r.parts['create'] == 'not_owned' and r.parts['status'] == 'read' and r.parts['sessions'] == [None]


def test_another_users_staging_and_choices_are_unreachable(db, people):
    alice, bob = people['alice'], people['bob']
    staged(db, alice, row('Alices'))
    assert gp.plan(db, who(bob)) is None
    with pytest.raises(gp.PlanError, match='Upload your export first'):
        gp.choose(db, who(bob), [2], 'skip')
    staged(db, bob, row('Bobs'))
    assert gp.choose(db, who(bob), [2], 'skip')['saved'] == [2]
    assert scalar(db, 'SELECT choice FROM goodreads_staging WHERE user_id = ?', alice) is None


# --- the plan as a whole ---------------------------------------------------------

def test_fingerprint_moves_when_your_data_or_a_choice_does(db, people):
    alice = people['alice']
    book = add_book(db, alice, 'Moving', 'Some Author')
    first = staged(db, alice, row('Moving', my_rating='4'), row('New')).fingerprint
    assert gp.plan(db, who(alice)).fingerprint == first
    give(db, alice, book, rating=3)
    second = gp.plan(db, who(alice)).fingerprint
    assert second != first
    gp.choose(db, who(alice), [3], 'library')
    assert gp.plan(db, who(alice)).fingerprint != second


def test_plan_writes_nothing_and_counts_the_import_button(db, people):
    alice = people['alice']
    wish(db, alice, 'Wished')
    p = staged(db, alice, row('New'), row('Wanted', 'to-read'), row('Reading', 'currently-reading'),
               row('Wished'), row(''))
    assert (len(p.rows), p.will_write, p.undecided) == (5, 2, 2)
    d = p.as_dict()
    assert d['total'] == 5 and [b['key'] for b in d['boxes']] == list(gp.BOXES)
    assert {b['key']: b['count'] for b in d['boxes']}['decide_reading'] == 1
    assert 'to-read' in d['shelves'] and d['rows'][0]['choice'] == 'not_owned'
    assert scalar(db, 'SELECT COUNT(*) FROM collections') == 0
    assert scalar(db, "SELECT COUNT(*) FROM books WHERE title != 'Wished'") == 0


def test_every_box_key_and_choice_is_consistent():
    for key, box in gp.BOXES.items():
        assert box['default'] in (None, 'ask') or box['default'] in gp.CHOICES, key
        assert all(c in gp.CHOICES and c != 'ask' for c in box['choices']), key

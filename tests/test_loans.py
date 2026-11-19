"""Loans (ROADMAP 16.0d, docs/LENDING-SPEC.md): utils/loans.py.

People (conftest): alice (admin) and bob share a household; carol is
alice's friend. Tests add dave (bob's friend only) and erin (a stranger).
alice is an admin, so permission checks use bob, carol and dave.
"""
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from tests.conftest import add_book, add_user, fk_violations, make_friends, scalar
from utils import loans
from utils.loans import LoanError


def who(db, user_id):
    row = db.execute('SELECT id, username, is_admin FROM users WHERE id = ?', (user_id,)).fetchone()
    return SimpleNamespace(id=row['id'], username=row['username'], is_admin=bool(row['is_admin']))


def book(db, book_id):
    return db.execute('SELECT * FROM books WHERE id = ?', (book_id,)).fetchone()


@pytest.fixture
def cast(db, people):
    """people plus dave (bob's friend, not alice's) and erin (nobody's)."""
    dave = add_user(db, 'dave')
    erin = add_user(db, 'erin')
    make_friends(db, people['bob'], dave)
    return {**people, 'dave': dave, 'erin': erin}


def notes(db, user_id):
    return [tuple(r) for r in db.execute(
        'SELECT type, message FROM notifications WHERE user_id = ? ORDER BY id', (user_id,))]


def test_lend_to_a_friend_and_household_marks_it_returned(db, cast):
    dune = add_book(db, cast['alice'], 'Dune')
    alice, bob = who(db, cast['alice']), who(db, cast['bob'])

    loan_id = loans.lend(db, alice, book(db, dune), borrower_id=cast['carol'], due_at='2099-01-01')
    db.commit()
    loan = loans.open_loan(db, dune)
    assert (loan['id'], loan['borrower'], loan['lender'], loan['lent_at']) == \
        (loan_id, 'carol', 'alice', date.today().isoformat())
    assert notes(db, cast['carol']) == [('loan', 'alice lent you Dune')]
    assert notes(db, cast['alice']) == []           # nobody hears of their own action

    loans.mark_returned(db, bob, loan_id)
    db.commit()
    assert loans.open_loan(db, dune) is None
    assert notes(db, cast['carol']) == [('loan', 'alice lent you Dune')]   # none on return
    assert notes(db, cast['alice']) == [('loan_owner', 'bob marked your Dune returned')]
    assert fk_violations(db) == []


def test_household_member_lends_the_owners_item_and_the_owner_hears(db, cast):
    dune = add_book(db, cast['alice'], 'Dune')
    loans.lend(db, who(db, cast['bob']), book(db, dune), borrower_id=cast['dave'])
    assert notes(db, cast['alice']) == [('loan_owner', 'bob lent your Dune to dave')]
    assert notes(db, cast['dave']) == [('loan', 'bob lent you Dune')]


def test_a_typed_name_needs_no_account(db, cast):
    dune = add_book(db, cast['bob'], 'Dune')
    loans.lend(db, who(db, cast['bob']), book(db, dune), borrower_name='  Uncle   Ray ')
    loan = loans.open_loan(db, dune)
    assert (loan['borrower_id'], loan['borrower']) == (None, 'Uncle Ray')
    with pytest.raises(LoanError):
        loans.lend(db, who(db, cast['bob']), book(db, add_book(db, cast['bob'])), borrower_name='   ')


def test_borrower_must_be_in_the_lenders_circle(db, cast):
    dune = add_book(db, cast['bob'], 'Dune')
    bob = who(db, cast['bob'])
    with pytest.raises(LoanError):
        loans.lend(db, bob, book(db, dune), borrower_id=cast['erin'])
    with pytest.raises(LoanError):
        loans.lend(db, bob, book(db, dune), borrower_id=cast['bob'])      # not to yourself
    with pytest.raises(LoanError):
        loans.lend(db, bob, book(db, dune), borrower_id='nonsense')
    db.execute('UPDATE users SET is_active = 0 WHERE id = ?', (cast['dave'],))
    with pytest.raises(LoanError):
        loans.lend(db, bob, book(db, dune), borrower_id=cast['dave'])
    assert scalar(db, 'SELECT COUNT(*) FROM loans') == 0


def test_borrower_choices_household_first(db, cast):
    choices = loans.borrower_choices(db, cast['bob'])
    assert [(c['username'], c['household']) for c in choices] == [('alice', True), ('dave', False)]


def test_only_the_shelfs_people_or_an_admin_lend(db, cast):
    dune = add_book(db, cast['alice'], 'Dune')
    for outsider in ('carol', 'dave', 'erin'):
        with pytest.raises(LoanError):
            loans.lend(db, who(db, cast[outsider]), book(db, dune), borrower_name='X')
    carols = add_book(db, cast['carol'], 'Carol owns this')
    loans.lend(db, who(db, cast['alice']), book(db, carols), borrower_name='X')   # admin
    assert scalar(db, 'SELECT COUNT(*) FROM loans') == 1


def test_only_an_item_on_the_shelf_can_be_lent(db, cast):
    bob = who(db, cast['bob'])
    removed = add_book(db, cast['bob'], 'Removed')
    unowned = add_book(db, cast['bob'], 'Audiobook')
    wished = add_book(db, cast['bob'], 'Wished')
    db.execute("UPDATE books SET removed_at = '2026-01-01' WHERE id = ?", (removed,))
    db.execute('UPDATE books SET owned = 0 WHERE id = ?', (unowned,))
    db.execute('INSERT INTO wishlist (user_id, book_id) VALUES (?, ?)', (cast['bob'], wished))
    for item in (removed, unowned, wished):
        with pytest.raises(LoanError):
            loans.lend(db, bob, book(db, item), borrower_name='X')


def test_one_open_loan_per_item(db, cast):
    dune = add_book(db, cast['bob'], 'Dune')
    bob = who(db, cast['bob'])
    first = loans.lend(db, bob, book(db, dune), borrower_name='Ray')
    with pytest.raises(LoanError, match='already lent to Ray'):
        loans.lend(db, bob, book(db, dune), borrower_name='Sue')
    # The index holds even if the check is skipped.
    with pytest.raises(Exception):
        db.execute("INSERT INTO loans (book_id, borrower_name, lent_at) VALUES (?, 'Sue', '2026-01-01')",
                   (dune,))
    loans.mark_returned(db, bob, first)
    loans.lend(db, bob, book(db, dune), borrower_name='Sue')
    assert scalar(db, 'SELECT COUNT(*) FROM loans WHERE book_id = ?', dune) == 2


def test_dates_are_checked(db, cast):
    bob = who(db, cast['bob'])
    dune = add_book(db, cast['bob'], 'Dune')
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    for kwargs in ({'lent_at': 'soon'}, {'lent_at': tomorrow},
                   {'lent_at': '2026-03-01', 'due_at': '2026-02-01'}):
        with pytest.raises(LoanError):
            loans.lend(db, bob, book(db, dune), borrower_name='Ray', **kwargs)
    loan_id = loans.lend(db, bob, book(db, dune), borrower_name='Ray', lent_at='2026-03-01')
    for when in ('2026-02-01', tomorrow):
        with pytest.raises(LoanError):
            loans.mark_returned(db, bob, loan_id, when)
    loans.mark_returned(db, bob, loan_id, '2026-03-01')
    with pytest.raises(LoanError, match='already returned'):
        loans.mark_returned(db, bob, loan_id)


def test_outsiders_cannot_return_or_delete(db, cast):
    dune = add_book(db, cast['bob'], 'Dune')
    loan_id = loans.lend(db, who(db, cast['bob']), book(db, dune), borrower_id=cast['dave'])
    for outsider in ('carol', 'dave', 'erin'):        # the borrower can't either
        with pytest.raises(LoanError, match='not found'):
            loans.mark_returned(db, who(db, cast[outsider]), loan_id)
        with pytest.raises(LoanError, match='not found'):
            loans.delete(db, who(db, cast[outsider]), loan_id)
    with pytest.raises(LoanError, match='not found'):
        loans.delete(db, who(db, cast['bob']), 9999)


def test_delete_removes_the_unread_notifications(db, cast):
    dune = add_book(db, cast['alice'], 'Dune')
    loan_id = loans.lend(db, who(db, cast['bob']), book(db, dune), borrower_id=cast['dave'])
    loans.delete(db, who(db, cast['bob']), loan_id)
    assert scalar(db, 'SELECT COUNT(*) FROM loans') == 0
    assert notes(db, cast['dave']) == [] and notes(db, cast['alice']) == []


def test_history_borrower_sees_only_their_own(db, cast):
    dune = add_book(db, cast['bob'], 'Dune')
    bob = who(db, cast['bob'])
    first = loans.lend(db, bob, book(db, dune), borrower_id=cast['dave'], lent_at='2026-01-01')
    loans.mark_returned(db, bob, first, '2026-02-01')
    loans.lend(db, bob, book(db, dune), borrower_name='Ray', lent_at='2026-03-01')
    assert [r['borrower'] for r in loans.history(db, who(db, cast['alice']), book(db, dune))] == ['Ray', 'dave']
    assert [r['borrower'] for r in loans.history(db, who(db, cast['dave']), book(db, dune))] == ['dave']
    assert loans.history(db, who(db, cast['erin']), book(db, dune)) == []


def test_lent_map_only_for_your_households_shelf(db, cast):
    alices = add_book(db, cast['alice'], 'Dune')
    carols = add_book(db, cast['carol'], 'Emma')
    loans.lend(db, who(db, cast['bob']), book(db, alices), borrower_name='Ray')
    loans.lend(db, who(db, cast['carol']), book(db, carols), borrower_name='Sue')
    assert loans.lent_map(db, cast['bob'], [alices, carols, None]) == {alices: 'Ray'}
    assert loans.lent_map(db, cast['carol'], [alices, carols]) == {carols: 'Sue'}
    assert loans.lent_map(db, cast['bob'], []) == {}


def test_borrowed_and_lent_out_lists(db, cast):
    dune = add_book(db, cast['alice'], 'Dune')
    loans.lend(db, who(db, cast['alice']), book(db, dune), borrower_id=cast['carol'])
    assert [(r['title'], r['owner']) for r in loans.borrowed_by(db, cast['carol'])] == [('Dune', 'alice')]
    assert [r['title'] for r in loans.lent_out(db, cast['bob'], 'book')] == ['Dune']
    assert loans.lent_out(db, cast['bob'], 'video') == []
    assert loans.lent_out(db, cast['carol']) == []


def test_loans_outlive_the_borrower_and_lender_accounts(db, cast):
    dune = add_book(db, cast['alice'], 'Dune')
    loans.lend(db, who(db, cast['bob']), book(db, dune), borrower_id=cast['dave'])
    db.commit()
    db.execute('DELETE FROM users WHERE id IN (?, ?)', (cast['dave'], cast['bob']))
    db.commit()
    loan = loans.open_loan(db, dune)
    assert (loan['borrower_id'], loan['borrower'], loan['lent_by'], loan['lender']) == (None, 'dave', None, None)
    db.execute('DELETE FROM books WHERE id = ?', (dune,))
    db.commit()
    assert scalar(db, 'SELECT COUNT(*) FROM loans') == 0
    assert fk_violations(db) == []

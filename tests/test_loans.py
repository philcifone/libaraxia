"""Loans (ROADMAP 16.0d, docs/LENDING-SPEC.md): utils/loans.py.

People (conftest): alice (admin) and bob share a household; carol is
alice's friend. Tests add dave (bob's friend only) and erin (a stranger).
alice is an admin, so permission checks use bob, carol and dave.
"""
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from conftest import add_book, add_user, fk_violations, login, make_friends, scalar
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


# --- routes and pages ------------------------------------------------------



def lend_form(**fields):
    return {'borrower': 'other', 'borrower_name': '', 'lent_at': '', 'due_at': '', 'note': '', **fields}


def test_lend_route_comes_back_to_the_loans_section(client, db, cast):
    dune = add_book(db, cast['alice'], 'Dune')
    login(client, 'bob')
    r = client.post(f'/loans/{dune}/lend', data=lend_form(borrower=str(cast['dave']), due_at='2099-01-01'))
    assert r.status_code == 302 and r.headers['Location'].endswith(f'/books/book/{dune}#loans')
    assert scalar(db, 'SELECT borrower_id FROM loans WHERE book_id = ?', dune) == cast['dave']

    page = client.get(f'/books/book/{dune}').get_data(as_text=True)
    assert 'data-loan-open' in page and 'Lent to dave' in page and 'data-loan-history' in page
    assert f'/loans/' in page and 'Mark returned' in page


def test_a_refused_lend_flashes_and_writes_nothing(client, db, cast):
    dune = add_book(db, cast['alice'], 'Dune')
    login(client, 'bob')
    r = client.post(f'/loans/{dune}/lend', data=lend_form(borrower=str(cast['carol'])), follow_redirects=True)
    assert r.status_code == 200 and 'household or friends' in r.get_data(as_text=True)
    assert scalar(db, 'SELECT COUNT(*) FROM loans') == 0


def test_loan_routes_are_post_only_and_404_for_strangers(client, db, cast):
    dune = add_book(db, cast['alice'], 'Dune')
    login(client, 'erin')
    assert client.get(f'/loans/{dune}/lend').status_code == 405
    assert client.post(f'/loans/{dune}/lend', data=lend_form(borrower_name='Ray')).status_code == 404
    assert client.post('/loans/9999/return').status_code == 404
    assert scalar(db, 'SELECT COUNT(*) FROM loans') == 0


def test_return_and_delete_routes(client, db, cast):
    dune = add_book(db, cast['alice'], 'Dune')
    loan_id = loans.lend(db, who(db, cast['alice']), book(db, dune), borrower_name='Ray', lent_at='2026-01-01')
    db.commit()
    login(client, 'bob')
    r = client.post(f'/loans/{loan_id}/return', data={'returned_at': '2026-02-01'})
    assert r.headers['Location'].endswith('#loans')
    assert scalar(db, 'SELECT returned_at FROM loans WHERE id = ?', loan_id) == '2026-02-01'
    client.post(f'/loans/{loan_id}/delete')
    assert scalar(db, 'SELECT COUNT(*) FROM loans') == 0


def test_a_friend_of_the_owner_sees_nothing_about_loans(client, db, cast):
    dune = add_book(db, cast['alice'], 'Dune')
    loans.lend(db, who(db, cast['alice']), book(db, dune), borrower_name='Ray')
    db.commit()
    login(client, 'carol')
    page = client.get(f'/books/book/{dune}').get_data(as_text=True)
    assert 'id="loans"' not in page and 'Ray' not in page


def test_a_borrower_outside_the_owners_circle_sees_the_item(client, db, cast):
    """bob lends alice's book to dave, his friend and not alice's."""
    dune = add_book(db, cast['alice'], 'Dune')
    login(client, 'dave')
    assert client.get(f'/books/book/{dune}').status_code == 404
    loans.lend(db, who(db, cast['bob']), book(db, dune), borrower_id=cast['dave'])
    db.commit()
    page = client.get(f'/books/book/{dune}').get_data(as_text=True)
    assert 'Borrowed from bob' in page and 'Mark returned' not in page and 'lend-panel' not in page

    notes_page = client.get('/friends/notifications_page').get_data(as_text=True)
    assert 'data-notification-item' in notes_page and f'/books/book/{dune}' in notes_page


def test_lend_panel_offers_the_circle_and_someone_else(client, db, cast):
    dune = add_book(db, cast['bob'], 'Dune')
    login(client, 'bob')
    page = client.get(f'/books/book/{dune}').get_data(as_text=True)
    assert 'id="lend-panel"' in page
    assert f'<option value="{cast["alice"]}">alice</option>' in page
    assert f'<option value="{cast["dave"]}">dave</option>' in page
    assert f'value="{cast["carol"]}"' not in page and '<option value="other">' in page


def test_a_video_comes_back_to_its_own_page(client, db, cast):
    tape = add_book(db, cast['bob'], 'Alien')
    db.execute("UPDATE books SET media_type = 'video', format = 'VHS' WHERE id = ?", (tape,))
    db.commit()
    login(client, 'bob')
    r = client.post(f'/loans/{tape}/lend', data=lend_form(borrower_name='Ray'))
    assert r.headers['Location'].endswith(f'/videos/{tape}#loans')


# --- grids, Collections, profile (step 3) ----------------------------------

def test_grid_badge_and_show_lent_on_your_households_grids(client, db, cast):
    dune = add_book(db, cast['alice'], 'Dune')
    add_book(db, cast['alice'], 'Emma')
    loans.lend(db, who(db, cast['bob']), book(db, dune), borrower_name='Ray')
    db.commit()
    login(client, 'alice')
    page = client.get('/base/index').get_data(as_text=True)
    assert page.count('data-lent') == 1 and 'title="Lent to Ray"' in page
    assert '<option value="lent"' in page
    lent_only = client.get('/base/index?show=lent').get_data(as_text=True)
    assert 'Dune' in lent_only and 'Emma' not in lent_only
    # Infinite scroll's JSON carries it too
    data = client.get('/base/index?show=lent', headers={'X-Requested-With': 'XMLHttpRequest'}).get_json()
    assert [(b['title'], b['lent_to']) for b in data['books']] == [('Dune', 'Ray')]


def test_a_lent_item_that_was_removed_is_still_lent_out(client, db, cast):
    dune = add_book(db, cast['alice'], 'Dune')
    loans.lend(db, who(db, cast['alice']), book(db, dune), borrower_name='Ray')
    db.execute("UPDATE books SET removed_at = '2026-11-01' WHERE id = ?", (dune,))
    db.commit()
    login(client, 'alice')
    assert 'Dune' in client.get('/base/index?show=lent').get_data(as_text=True)


def test_a_friends_grid_shows_no_badge_and_ignores_show_lent(client, db, cast):
    dune = add_book(db, cast['alice'], 'Dune')
    loans.lend(db, who(db, cast['alice']), book(db, dune), borrower_name='Ray')
    tape = add_book(db, cast['alice'], 'Alien')
    db.execute("UPDATE books SET media_type = 'video', format = 'VHS' WHERE id = ?", (tape,))
    loans.lend(db, who(db, cast['alice']), book(db, tape), borrower_name='Ray')
    db.commit()
    login(client, 'carol')
    for url in ('/base/library/alice', '/videos/user/alice'):
        r = client.get(url)
        page = r.get_data(as_text=True)
        assert r.status_code == 200 and 'data-lent' not in page and 'Ray' not in page, url
        assert '<option value="lent"' not in page, url
        assert client.get(url + '?show=lent').status_code == 200
    data = client.get('/base/library/alice?show=lent', headers={'X-Requested-With': 'XMLHttpRequest'}).get_json()
    assert [(b['title'], b['lent_to']) for b in data['books']] == [('Dune', None)]


def test_collections_has_a_lent_out_row_for_the_household(client, db, cast):
    dune = add_book(db, cast['alice'], 'Dune')
    login(client, 'bob')
    assert 'Lent out' not in client.get('/collections/collections').get_data(as_text=True)
    loans.lend(db, who(db, cast['alice']), book(db, dune), borrower_name='Ray')
    db.commit()
    page = client.get('/collections/collections').get_data(as_text=True)
    assert 'Lent out' in page and '/base/shared-library?show=lent' in page and 'Ray' in page
    assert 'Lent out' not in client.get('/collections/collections?type=video').get_data(as_text=True)


def test_borrowed_on_your_own_profile_only(client, db, cast):
    dune = add_book(db, cast['alice'], 'Dune')
    loans.lend(db, who(db, cast['alice']), book(db, dune), borrower_id=cast['carol'], due_at='2099-01-01')
    db.commit()
    login(client, 'carol')
    profile = client.get('/user/carol').get_data(as_text=True)
    assert 'data-borrowed' in profile and '/loans/borrowed' in profile
    page = client.get('/loans/borrowed').get_data(as_text=True)
    assert 'data-borrowed-item' in page and 'From alice since' in page and 'due 1 Jan 2099' in page
    login(client, 'alice')
    assert 'data-borrowed' not in client.get('/user/carol').get_data(as_text=True)
    assert 'data-borrowed-item' not in client.get('/loans/borrowed').get_data(as_text=True)


# --- Do I have this? and exports (step 4) ----------------------------------

def test_do_i_have_this_words_the_loan(client, db, cast):
    dune = add_book(db, cast['alice'], 'Dune')
    loans.lend(db, who(db, cast['alice']), book(db, dune), borrower_id=cast['carol'], lent_at='2026-03-03')
    db.commit()
    login(client, 'alice')
    assert 'On your shelf, lent to carol since Mar 2026' in client.get('/have/?q=Dune').get_data(as_text=True)
    login(client, 'bob')
    assert "On the shelf: alice&#39;s, lent to carol since Mar 2026" in \
        client.get('/have/?q=Dune').get_data(as_text=True)
    login(client, 'carol')
    page = client.get('/have/?q=Dune').get_data(as_text=True)
    assert 'You have it on loan' in page and 'Borrowed from alice since Mar 2026' in page


def test_do_i_have_this_keeps_loans_from_others(client, db, cast):
    """dave has data on carol's copy, which carol lent to Ray: dave sees the
    copy in the results, never the loan."""
    emma = add_book(db, cast['carol'], 'Emma')
    db.execute("INSERT INTO read_data (user_id, book_id, rating) VALUES (?, ?, 4)", (cast['dave'], emma))
    loans.lend(db, who(db, cast['carol']), book(db, emma), borrower_name='Ray')
    db.commit()
    login(client, 'dave')
    page = client.get('/have/?q=Emma').get_data(as_text=True)
    assert 'Emma' in page and 'Ray' not in page and 'lent to' not in page


def test_exports_carry_loans(app, db, cast):
    from utils.export import data_zip, library_csv
    import csv, io, zipfile
    dune = add_book(db, cast['alice'], 'Dune')
    first = loans.lend(db, who(db, cast['bob']), book(db, dune), borrower_id=cast['dave'], lent_at='2026-01-01')
    loans.mark_returned(db, who(db, cast['alice']), first, '2026-02-01')
    loans.lend(db, who(db, cast['alice']), book(db, dune), borrower_name='Ray', lent_at='2026-03-01',
               due_at='2026-04-01')
    db.commit()
    rows = list(csv.DictReader(io.StringIO(library_csv(db, cast['bob']))))
    dune_row = next(r for r in rows if r['Title'] == 'Dune')
    assert (dune_row['Section'], dune_row['Lent To'], dune_row['Lent On'], dune_row['Due Back']) == \
        ('Shared (alice)', 'Ray', '2026-03-01', '2026-04-01')

    def loans_csv(user_id):
        with zipfile.ZipFile(io.BytesIO(data_zip(db, user_id))) as z:
            return [(r['Direction'], r['Borrower'], r['Returned On'])
                    for r in csv.DictReader(io.StringIO(z.read('loans.csv').decode()))]
    assert loans_csv(cast['alice']) == [('Lent', 'dave', '2026-02-01'), ('Lent', 'Ray', '')]
    assert loans_csv(cast['bob']) == [('Lent', 'dave', '2026-02-01')]       # the one bob lent
    assert loans_csv(cast['dave']) == [('Borrowed', 'dave', '2026-02-01')]
    assert loans_csv(cast['carol']) == []

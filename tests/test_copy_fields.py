"""Condition, price paid and value on the add and edit forms and the item
page (ROADMAP 16.0a, docs/PHOTOS-VALUE-SPEC.md sections 4, 5 and 11)."""
import pytest

from conftest import add_book, add_user, login, scalar


def book_form(**extra):
    return {'title': 'Infinite Jest', 'author': 'David Foster Wallace', 'year': '1996',
            'page_count': '1079', 'isbn': '9780316066525', **extra}


def record_form(**extra):
    return {'title': 'Blue', 'author': 'Joni Mitchell', 'format': 'LP', **extra}


# --- money --------------------------------------------------------------------

@pytest.mark.parametrize('text, cents', [
    ('12.50', 1250), ('12.5', 1250), ('$12.50', 1250), ('12', 1200), ('1,250', 125000),
    ('', None), ('  ', None), ('0.05', 5),
])
def test_money_parse(text, cents):
    from utils import money
    assert money.parse(text) == cents


@pytest.mark.parametrize('text', ['abc', '12.345', '-3', '1e5', '12.50.1'])
def test_money_parse_refuses_nonsense(text):
    from utils import money
    with pytest.raises(ValueError):
        money.parse(text)


def test_money_show():
    from utils import money
    assert money.show(123456, 'USD') == '$1,234.56'
    assert money.show(500, 'SEK') == '5.00 SEK'
    assert money.show(None) == ''


def test_discogs_release_parse():
    from utils.copy_fields import parse_discogs_release as p
    assert p('1234567') == 1234567
    assert p('https://www.discogs.com/release/1234567-Joni-Mitchell-Blue') == 1234567
    assert p('[r1234567]') == 1234567
    assert p('') is None
    with pytest.raises(ValueError):
        p('https://www.discogs.com/master/12345-Blue')
    with pytest.raises(ValueError):
        p('Blue by Joni')


# --- forms --------------------------------------------------------------------

def test_edit_book_saves_condition_price_and_manual_value(client, db, people):
    book = add_book(db, people['bob'])
    login(client, 'bob')
    r = client.post(f'/books/edit/{book}', data=book_form(condition='near_fine', price_paid='12.50', value='$40'))
    assert r.status_code == 302
    row = db.execute('SELECT * FROM books WHERE id = ?', (book,)).fetchone()
    assert (row['condition'], row['price_paid_cents'], row['value_cents'], row['value_source']) == \
        ('near_fine', 1250, 4000, 'manual')
    assert row['value_checked_at'] is not None


def test_bad_amount_and_wrong_grade_are_refused(client, db, people):
    book = add_book(db, people['bob'])
    login(client, 'bob')
    r = client.post(f'/books/edit/{book}', data=book_form(price_paid='twelve', condition='NM'))
    assert r.status_code == 400
    html = r.get_data(as_text=True)
    assert 'isn&#39;t an amount' in html and 'not one of the grades' in html
    assert 'value="twelve"' in html              # what was typed is kept
    assert scalar(db, 'SELECT title FROM books WHERE id = ?', book) == 'A Book'   # nothing saved


def test_unchanged_value_keeps_its_source(client, db, people):
    book = add_book(db, people['bob'])
    db.execute("UPDATE books SET value_cents = 2300, value_source = 'ebay', "
               "value_note = 'eBay: median asking price of 9 listings', value_checked_at = '2026-01-02' "
               "WHERE id = ?", (book,))
    db.commit()
    login(client, 'bob')
    client.post(f'/books/edit/{book}', data=book_form(value='23.00'))
    row = db.execute('SELECT value_source, value_note, value_checked_at FROM books WHERE id = ?', (book,)).fetchone()
    assert tuple(row) == ('ebay', 'eBay: median asking price of 9 listings', '2026-01-02')
    # Typed over: manual
    client.post(f'/books/edit/{book}', data=book_form(value='25'))
    assert scalar(db, 'SELECT value_source FROM books WHERE id = ?', book) == 'manual'
    # Cleared: nothing left
    client.post(f'/books/edit/{book}', data=book_form(value=''))
    row = db.execute('SELECT value_cents, value_source, value_note FROM books WHERE id = ?', (book,)).fetchone()
    assert tuple(row) == (None, None, None)


def test_fetched_value_is_saved_with_its_source(client, db, people):
    book = add_book(db, people['bob'])
    login(client, 'bob')
    client.post(f'/books/edit/{book}', data=book_form(
        value='18.00', value_source='ebay', value_fetched_cents='1800',
        value_note='eBay: median asking price of 12 listings'))
    row = db.execute('SELECT value_cents, value_source, value_note FROM books WHERE id = ?', (book,)).fetchone()
    assert tuple(row) == (1800, 'ebay', 'eBay: median asking price of 12 listings')


def test_add_record_with_two_grades_and_release(client, db, people):
    login(client, 'bob')
    r = client.post('/records/add', data=record_form(
        condition='VG+', sleeve_condition='Generic', price_paid='8',
        discogs_release='https://www.discogs.com/release/1531111-Joni-Mitchell-Blue'))
    assert r.status_code == 302
    row = db.execute("SELECT * FROM books WHERE media_type = 'record'").fetchone()
    assert (row['condition'], row['sleeve_condition'], row['price_paid_cents'], row['discogs_release_id']) == \
        ('VG+', 'Generic', 800, 1531111)


def test_add_book_with_condition(client, db, people):
    login(client, 'bob')
    r = client.post('/books/add', data=book_form(submit_book='1', condition='fine', value='15'))
    assert r.status_code == 302
    row = db.execute("SELECT condition, value_cents, value_source FROM books").fetchone()
    assert tuple(row) == ('fine', 1500, 'manual')


def test_movie_grade_on_a_record_field_is_refused(client, db, people):
    login(client, 'bob')
    r = client.post('/records/add', data=record_form(condition='like_new'))
    assert r.status_code == 400
    assert scalar(db, 'SELECT COUNT(*) FROM books') == 0


# --- who sees what ------------------------------------------------------------

def test_condition_is_public_money_is_private(client, db, people):
    """carol (alice's friend) and bob (her household) see the condition but
    not what alice paid or what it's worth; alice does."""
    book = add_book(db, people['alice'])
    db.execute("UPDATE books SET condition = 'very_good', price_paid_cents = 1250, value_cents = 4000, "
               "value_source = 'manual', value_checked_at = '2026-11-14' WHERE id = ?", (book,))
    db.commit()
    for name in ('carol', 'bob'):
        login(client, name)
        html = client.get(f'/books/{book}').get_data(as_text=True)
        assert 'data-condition' in html and 'Very Good' in html
        assert 'data-price-paid' not in html and 'data-value' not in html and '$12.50' not in html
        client.get('/auth/logout')
    login(client, 'alice')
    html = client.get(f'/books/{book}').get_data(as_text=True)
    assert 'data-price-paid' in html and '$12.50' in html and '$40.00' in html
    assert 'Entered by you, 2026-11-14' in html


def test_record_condition_reads_record_then_sleeve(client, db, people):
    rec = db.execute("INSERT INTO books (title, author, added_by, media_type, format, condition, sleeve_condition) "
                     "VALUES ('Blue', 'Joni', ?, 'record', 'LP', 'NM', 'VG+')", (people['bob'],)).lastrowid
    db.commit()
    login(client, 'bob')
    html = client.get(f'/records/{rec}').get_data(as_text=True)
    assert 'NM / VG+' in html and 'Record: Near Mint (NM or M-) / Sleeve: Very Good Plus (VG+)' in html


def test_wishlist_add_page_has_no_copy_fields(client, db, people):
    login(client, 'bob')
    assert 'id="copy-fields"' not in client.get('/wishlist/add?type=book').get_data(as_text=True)
    assert 'id="copy-fields"' in client.get('/books/add').get_data(as_text=True)


# --- exports ------------------------------------------------------------------

def test_library_csv_has_copy_columns_and_hides_household_money(app, db, people):
    """Your own item's price and value are in your export; a household
    member's item shows its condition but not their money."""
    import csv, io
    from utils.export import library_csv
    mine = add_book(db, people['alice'], title='Mine')
    theirs = add_book(db, people['bob'], title='Theirs')
    db.execute("UPDATE books SET condition = 'fine', price_paid_cents = 999, value_cents = 2500, "
               "value_source = 'ebay', value_note = 'eBay: median asking price of 5 listings', "
               "value_checked_at = '2026-11-14 10:00:00' WHERE id IN (?, ?)", (mine, theirs))
    db.commit()
    with app.app_context():
        from utils.database import get_db
        rows = list(csv.DictReader(io.StringIO(library_csv(get_db(), people['alice']))))
    by_title = {r['Title']: r for r in rows}
    assert by_title['Mine']['Condition'] == 'fine'
    assert by_title['Mine']['Price Paid'] == '9.99' and by_title['Mine']['Value'] == '25.00'
    assert by_title['Mine']['Value Source'] == 'ebay: eBay: median asking price of 5 listings'
    assert by_title['Mine']['Value Checked'] == '2026-11-14'
    assert by_title['Theirs']['Condition'] == 'fine'
    assert by_title['Theirs']['Price Paid'] == '' and by_title['Theirs']['Value'] == ''


def test_data_zip_carries_your_photos(app, db, people, static_root):
    import io, zipfile
    from utils.export import data_zip
    book = add_book(db, people['alice'], title='Mine')
    other = add_book(db, people['bob'], title='Theirs')
    folder = static_root / 'uploads' / 'photos'
    for bid, name in ((book, 'a.jpg'), (other, 'b.jpg')):
        (folder / str(bid)).mkdir(parents=True, exist_ok=True)
        (folder / str(bid) / name).write_bytes(b'jpeg')
        db.execute("INSERT INTO item_photos (book_id, kind, path, caption) VALUES (?, 'back', ?, 'Back')",
                   (bid, f'uploads/photos/{bid}/{name}'))
    db.commit()
    with app.app_context():
        from utils.database import get_db
        z = zipfile.ZipFile(io.BytesIO(data_zip(get_db(), people['alice'])))
    assert f'photos/{book}/a.jpg' in z.namelist()
    assert not any(n.endswith('b.jpg') for n in z.namelist())
    assert 'Mine,back,Back' in z.read('photos.csv').decode()


# --- Stats: Collection value --------------------------------------------------

def test_collection_value_card_is_the_owners_only(client, db, people):
    a = add_book(db, people['alice'], title='One')
    b = add_book(db, people['alice'], title='Two')
    gone = add_book(db, people['alice'], title='Gone')
    add_book(db, people['alice'], title='Unvalued')
    db.execute("UPDATE books SET value_cents = 2000, value_source = 'ebay', value_checked_at = '2026-10-01', "
               "price_paid_cents = 500 WHERE id = ?", (a,))
    db.execute("UPDATE books SET value_cents = 1050, value_source = 'manual' WHERE id = ?", (b,))
    db.execute("UPDATE books SET value_cents = 99999, removed_at = '2026-01-01' WHERE id = ?", (gone,))
    db.commit()
    login(client, 'alice')
    html = client.get('/user/alice').get_data(as_text=True)
    assert 'id="collection-value"' in html
    assert '$30.50' in html and '2 of 3 valued' in html and '$5.00' in html
    assert 'Oldest fetched value: 2026-10-01' in html
    assert '$999.99' not in html and '$1,030.49' not in html      # the removed one isn't counted
    client.get('/auth/logout')
    login(client, 'carol')      # alice's friend
    assert 'id="collection-value"' not in client.get('/user/alice').get_data(as_text=True)


def test_no_card_without_values(client, db, people):
    add_book(db, people['bob'])
    login(client, 'bob')
    assert 'id="collection-value"' not in client.get('/user/bob').get_data(as_text=True)

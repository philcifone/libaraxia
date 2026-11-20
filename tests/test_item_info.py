"""16.0 (Phil, 2026-11-13): the item page's reading info, condensed. Status
and collections are chips that save on a tap and come back to the card
(#your-info), New collection puts the item in it, and the review, history
and tags are tabs; a session comes back to the History tab."""
import re

from conftest import add_book, add_review, login, scalar


def shelf(db, user_id, name, media_type='book'):
    cid = db.execute('INSERT INTO user_collections (user_id, name, media_type) VALUES (?, ?, ?)',
                     (user_id, name, media_type)).lastrowid
    db.commit()
    return cid


def test_info_card_is_chips_and_tabs(client, db, people):
    alice = people['alice']
    book = add_book(db, alice, title='Dune')
    inside, outside = shelf(db, alice, 'Favourites'), shelf(db, alice, 'Summer')
    db.execute('INSERT INTO collection_books (collection_id, book_id) VALUES (?, ?)', (inside, book))
    db.execute("INSERT INTO collections (user_id, book_id, status) VALUES (?, ?, 'currently reading')", (alice, book))
    db.commit()
    login(client, 'alice')
    page = client.get(f'/books/book/{book}').get_data(as_text=True)

    status = page[page.index('data-item-status'):page.index('data-item-collections')]
    pressed = re.findall(r'value="([^"]+)" class="chip"\s+aria-pressed="true"', status)
    assert pressed == ['currently reading']
    assert status.count('class="chip"') == 5                     # Unread + the four book statuses
    assert '<select' not in status

    chips = page[page.index('data-item-collections'):page.index('data-tabs')]
    assert f'value="{inside}" class="chip"\n                                    aria-pressed="true"' in chips
    assert f'value="{outside}" class="chip"\n                                    aria-pressed="false"' in chips
    assert chips.count('name="anchor" value="your-info"') == 2   # toggle form and New collection
    assert f'name="book_id" value="{book}"/>' in chips

    for key in ('review', 'history', 'tags'):
        assert f'role="tab" id="tab-item-{key}" aria-controls="item-{key}"' in page
        assert f'role="tabpanel" id="item-{key}"' in page
    # tags.js finds the item by the first [data-book-id]
    assert re.search(r'data-book-id="(\d+)"', page).group(1) == str(book)


def _heading(page):
    """The item heading card's markup (_item_heading.html)."""
    start = page.index('<div class="page-heading ')
    return page[start:page.index('</header>', start)]


def test_item_heading_has_the_cover_beside_the_title(client, db, people):
    """Phil, 2026-11-19: on the item page and Rate & review, the cover sits
    beside the title and creator inside the heading card, and the format
    icon is gone from it; the details card under it has no cover of its own."""
    book = add_book(db, people['alice'], title='Dune', author='Frank Herbert')
    login(client, 'alice')
    for url in (f'/books/book/{book}', f'/read/rate_review/{book}'):
        page = client.get(url).get_data(as_text=True)
        heading = _heading(page)
        assert 'class="item-heading-grid"' in heading, url
        assert heading.index('class="cover-stand') < heading.index('<h1') < heading.index('Frank Herbert'), url
        assert 'role="img"' not in heading, url
        assert page.count('class="cover-stand') == 1, url
    item = client.get(f'/books/book/{book}').get_data(as_text=True)
    assert '<div class="item-facts p-3 md:p-4 bg-primary rounded-lg">' in item


def test_status_and_collection_taps_come_back_to_the_card(client, db, people):
    alice = people['alice']
    book = add_book(db, alice, title='Dune')
    cid = shelf(db, alice, 'Favourites')
    login(client, 'alice')
    item = f'http://localhost/books/book/{book}'

    r = client.post('/collections/collections/status/add', headers={'Referer': item},
                    data={'id': book, 'status': 'want to read', 'anchor': 'your-info'})
    assert r.headers['Location'].endswith(f'/books/book/{book}#your-info')
    r = client.post('/collections/manage_book_collections', headers={'Referer': item + '#old'},
                    data={'book_id': book, 'collection_id': cid, 'anchor': 'your-info'})
    assert r.headers['Location'].endswith(f'/books/book/{book}#your-info')
    assert scalar(db, 'SELECT COUNT(*) FROM collection_books WHERE collection_id = ? AND book_id = ?', cid, book) == 1
    # Anything else in the field is ignored: the fragment is never echoed
    r = client.post('/collections/collections/status/add', headers={'Referer': item},
                    data={'id': book, 'status': 'untracked', 'anchor': 'evil'})
    assert r.headers['Location'].endswith(f'/books/book/{book}')


def test_new_collection_from_an_item_holds_it(client, db, people):
    alice, carol = people['alice'], people['carol']
    book = add_book(db, alice, title='Dune')
    login(client, 'alice')
    r = client.post('/collections/collections/create', headers={'Referer': f'http://localhost/books/book/{book}'},
                    data={'name': 'Desert', 'media_type': 'book', 'book_id': book, 'next': 'item', 'anchor': 'your-info'})
    assert r.headers['Location'].endswith('#your-info')
    cid = scalar(db, "SELECT collection_id FROM user_collections WHERE user_id = ? AND name = 'Desert'", alice)
    assert scalar(db, 'SELECT COUNT(*) FROM collection_books WHERE collection_id = ? AND book_id = ?', cid, book) == 1

    # Not a book you can see (bob isn't in carol's circle): the collection
    # is made, the book isn't put in it
    hidden = add_book(db, people['bob'], title='Private')
    login(client, 'carol')
    client.post('/collections/collections/create', data={'name': 'Mine', 'media_type': 'book', 'book_id': hidden})
    cid = scalar(db, "SELECT collection_id FROM user_collections WHERE user_id = ? AND name = 'Mine'", carol)
    assert cid and scalar(db, 'SELECT COUNT(*) FROM collection_books WHERE collection_id = ?', cid) == 0


def test_a_session_comes_back_to_the_history_tab(client, db, people):
    alice = people['alice']
    book = add_book(db, alice, title='Dune')
    login(client, 'alice')
    r = client.post(f'/read/manage_session/{book}', data={'date_started': '2026-01-01', 'date_completed': '2026-01-09'})
    assert r.headers['Location'].endswith(f'/books/book/{book}#item-history')
    session = scalar(db, 'SELECT session_id FROM reading_sessions WHERE book_id = ?', book)
    r = client.post(f'/read/delete_reading_session/{session}', data={'book_id': book, 'redirect_to': 'book_detail'})
    assert r.headers['Location'].endswith(f'/books/book/{book}#item-history')


def test_household_reviews_follow_your_info_full_width(client, db, people):
    alice, bob = people['alice'], people['bob']                 # one household
    book = add_book(db, alice, title='Dune')
    add_review(db, bob, book)
    login(client, 'alice')
    page = client.get(f'/books/book/{book}').get_data(as_text=True)
    assert page.index('id="your-info"') < page.index('id="household-reviews"')
    assert 'max-w-4xl mx-auto px-4' not in page


def test_audiobook_narrator_and_length(client, db, people):
    """Add an audiobook with a narrator and length; the item page shows them;
    switching it to a printed book clears both."""
    login(client, 'alice')
    form = {'submit_book': '1', 'title': 'Project Hail Mary', 'author': 'Andy Weir', 'format': 'Audiobook',
            'not_owned': '1', 'narrator': 'Ray Porter', 'length_hours': '16', 'length_minutes': '10'}
    client.post('/books/add', data=form)
    row = db.execute("SELECT * FROM books WHERE title = 'Project Hail Mary'").fetchone()
    assert (row['format'], row['narrator'], row['runtime_minutes'], row['owned']) == ('Audiobook', 'Ray Porter', 970, 0)
    page = client.get(f"/books/book/{row['id']}").get_data(as_text=True)
    # In the facts, not the heading (Phil, 2026-11-19)
    assert 'font-medium break-words">Ray Porter</p>' in page and '16 h 10 min' in page
    heading = page[page.index('<div class="page-heading '):page.index('</header>')]
    assert 'Ray Porter' not in heading

    client.post(f"/books/edit/{row['id']}", data={**form, 'format': 'Book'})
    row = db.execute('SELECT * FROM books WHERE id = ?', (row['id'],)).fetchone()
    assert (row['format'], row['narrator'], row['runtime_minutes']) == (None, None, None)
    assert 'Ray Porter' not in client.get(f"/books/book/{row['id']}").get_data(as_text=True)
    # The narrator is found by the Books search (and exported)
    db.execute("UPDATE books SET format = 'Audiobook', narrator = 'Ray Porter' WHERE id = ?", (row['id'],))
    db.commit()
    found = client.get('/base/index?search_term=porter&show=not_owned', headers={'X-Requested-With': 'XMLHttpRequest'}).get_json()
    assert [b['title'] for b in found['books']] == ['Project Hail Mary']
    from utils.export import library_csv
    assert library_csv(db, people['alice']).splitlines()[1].endswith(',Ray Porter')


def test_ebook_format(client, db, people):
    from utils import media
    login(client, 'alice')
    client.post('/books/add', data={'submit_book': '1', 'title': 'Snow Crash', 'author': 'Neal Stephenson',
                                    'format': 'Ebook', 'not_owned': '1', 'narrator': 'ignored'})
    row = db.execute("SELECT * FROM books WHERE title = 'Snow Crash'").fetchone()
    assert (row['format'], row['narrator'], row['owned']) == ('Ebook', None, 0)
    assert media.is_digital(row) and media.is_digital('Audiobook') and not media.is_digital(None)
    assert media.book_format('Ebook') == 'Ebook' and media.book_format('Book') is None
    assert (media.audio_length('1', '30'), media.audio_length('', '90'), media.audio_length('x', '-3')) == (90, 90, None)
    assert media.length_parts(970) == (16, 10) and media.length_parts(None) == ('', '')

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


def test_item_badge_puts_cover_and_facts_on_one_midline(client, db, people):
    book = add_book(db, people['alice'], title='Dune')
    login(client, 'alice')
    page = client.get(f'/books/book/{book}').get_data(as_text=True)
    assert '<div class="self-center md:self-start md:row-span-2">' in page
    assert 'item-facts self-center md:self-start' in page


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


def test_a_plain_book_has_the_open_book_icon_like_movies_and_music(client, db, people):
    """Phil, 2026-11-13: the title card's right-hand icon, as a movie's or an
    album's format has, for a plain book too; an audiobook keeps its own."""
    book = add_book(db, people['alice'], title='Dune')
    login(client, 'alice')
    page = client.get(f'/books/book/{book}').get_data(as_text=True)
    assert 'role="img"\n                  aria-label="Book" title="Book"' in page
    assert '<path d="M12 7v14"/>' in page
    db.execute("UPDATE books SET format = 'Audiobook' WHERE id = ?", (book,))
    db.commit()
    page = client.get(f'/books/book/{book}').get_data(as_text=True)
    assert 'aria-label="Audiobook"' in page and '<path d="M12 7v14"/>' not in page

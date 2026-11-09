"""Grid search matching and list view (ROADMAP 7.2b)."""
import pathlib

from conftest import add_book, login
from utils.search import fold, match


def test_fold_ignores_case_accents_punctuation_and_spaces():
    assert fold('Les Misérables!') == 'lesmiserables'
    assert fold('Catch-22') == fold('catch 22') == 'catch22'
    assert fold(1999) == '1999'
    assert fold(None) is None


def test_match_needs_every_word_somewhere():
    sql, params = match('harari lessons', ['title', 'author'])
    assert sql.count(' AND ') == 1 and params == ['%harari%'] * 2 + ['%lessons%'] * 2
    assert match('  --  ', ['title']) == ('1', [])     # nothing searchable: everything


def _titles(client, term, path='/books/search'):
    page = client.get(path, query_string={'search_term': term}).get_data(as_text=True)
    return page


def test_library_search_folds_and_matches_words_in_any_order(client, db, people):
    alice = people['alice']
    add_book(db, alice, title='Les Misérables', author='Victor Hugo')
    add_book(db, alice, title='Catch-22', author='Joseph Heller')
    lessons = add_book(db, alice, title='21 Lessons for the 21st Century', author='Yuval Noah Harari')
    db.execute("UPDATE books SET isbn = '9780525512172', subtitle = 'Essays' WHERE id = ?", (lessons,))
    db.execute("INSERT INTO book_tags (book_id, user_id, tag_name) VALUES (?, ?, 'non-fiction')", (lessons, alice))
    db.commit()
    login(client, 'alice')
    assert 'Les Misérables' in _titles(client, 'les miserables')
    assert 'Catch-22' in _titles(client, 'catch 22')
    for term in ('harari lessons', '9780525512172', 'essays', 'nonfiction'):
        assert '21 Lessons for the 21st Century' in _titles(client, term), term
    assert '21 Lessons' not in _titles(client, 'harari dune')


def test_movie_search_uses_the_same_matching(client, db, people):
    db.execute("INSERT INTO books (title, author, added_by, media_type, format) VALUES"
               " ('Amélie', 'Jean-Pierre Jeunet', ?, 'video', 'DVD')", (people['alice'],))
    db.commit()
    login(client, 'alice')
    assert 'Amélie' in _titles(client, 'amelie jeunet', '/videos/')


def test_search_hints_at_matching_wishlist_entries(client, db, people):
    alice = people['alice']
    want = add_book(db, alice, title='Dune Messiah', author='Frank Herbert')
    db.execute('INSERT INTO wishlist (user_id, book_id) VALUES (?, ?)', (alice, want))
    db.commit()
    login(client, 'alice')
    page = _titles(client, 'messiah')
    assert 'On your wishlist:' in page and 'Dune Messiah' in page
    assert 'On your wishlist:' not in _titles(client, 'hobbit')


def test_list_view_columns_and_infinite_scroll_json(client, db, people):
    """The grid's cards carry list view's columns (.book-meta: year, your
    status, your rating); infinite scroll's JSON has the same fields."""
    alice = people['alice']
    book = add_book(db, alice, title='Dune', author='Frank Herbert')
    db.execute("UPDATE books SET publish_year = 1965 WHERE id = ?", (book,))
    db.execute("INSERT INTO collections (user_id, book_id, status) VALUES (?, ?, 'read')", (alice, book))
    db.execute("INSERT INTO read_data (user_id, book_id, rating) VALUES (?, ?, 4)", (alice, book))
    db.commit()
    login(client, 'alice')
    page = client.get('/base/index').get_data(as_text=True)
    assert 'data-view="grid"' in page and 'class="book-meta"' in page
    assert '<span class="book-year">1965</span>' in page
    assert '<span class="book-status">Read</span>' in page and 'Rated 4 of 5' in page
    data = client.get('/base/index?page=1', headers={'X-Requested-With': 'XMLHttpRequest'}).get_json()
    card = next(b for b in data['books'] if b['title'] == 'Dune')
    assert (card['year'], card['status'], card['rating']) == (1965, 'Read', 4)
    css = pathlib.Path('static/styles.css').read_text()
    assert '#book-container[data-view="list"]' in css and '.book-meta { display: none; }' in css


def test_add_page_search_says_it_is_not_your_library(client, db, people):
    login(client, 'alice')
    page = client.get('/books/add').get_data(as_text=True)
    assert 'not your library' in page and '/have/' in page

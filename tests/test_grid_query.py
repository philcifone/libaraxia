"""utils/grid_query.py (ROADMAP 14a step 1): the ids a grid shows.

Bulk edit's "select all N in this view" has to name exactly the items the
grid renders, in the same order. These tests were first written against the
grids before the query was pulled out of base.library_page, so
test_books_grid_order pins what the Books grid returned then (literal
titles); test_view_ids_match_grid then holds the extracted query to the
rendered pages for every filter and sort, in all three sections.
"""
import re
from urllib.parse import parse_qsl

import pytest
from werkzeug.datastructures import MultiDict

from conftest import add_user, login
from utils import media
from utils import grid_query
from utils.database import get_db

# (section, URL of its own grid, URL of its household grid, view keys)
SECTIONS = {
    media.BOOK: ('/base/index', '/base/shared-library', 'book:mine', 'book:household'),
    media.VIDEO: ('/videos/', '/videos/shared', 'video:mine', 'video:household'),
    media.RECORD: ('/records/', '/records/shared', 'record:mine', 'record:household'),
}
FORMATS = {media.BOOK: (None, 'Audiobook'), media.VIDEO: ('VHS', 'DVD'), media.RECORD: ('LP', 'CD')}

LINK = re.compile(r'href="[^"]*?/(\d+)"\s+class="book-link')


class Who:
    """What view_ids needs of a user: an id (it never reads anything else)."""
    def __init__(self, id):
        self.id = id


def put(db, owner, title, kind, **cols):
    """One catalog row. `cols` are books columns (genre, format, owned, ...)."""
    cols = {'title': title, 'author': 'Anon', 'added_by': owner, 'media_type': kind, **cols}
    names = ', '.join(cols)
    cur = db.execute(f"INSERT INTO books ({names}) VALUES ({', '.join('?' * len(cols))})",
                     list(cols.values()))
    return cur.lastrowid


def seed(db, people, kind):
    """A small shelf with every property the filters and sorts look at.
    Returns {title: id}. alice owns the first six, bob the last two."""
    alice, bob = people['alice'], people['bob']
    plain, other = FORMATS[kind]
    s1, s2 = media.STATUSES[kind][:2]
    ids = {}
    rows = [
        # title, owner, extra columns
        ('Alpha Cooking', alice, dict(genre='Cooking', format=plain, publisher='Penguin',
                                      publish_year=2001, author='Zed', created_at='2024-01-05 10:00:00')),
        ('Beta Cookbook', alice, dict(genre='cooking', format=other, publish_year=1999,
                                      author='Amy', created_at='2024-03-01 10:00:00')),
        ('Gamma', alice, dict(genre='Fiction', format=plain, publish_year=2010, author='Max',
                              created_at='2023-06-01 10:00:00')),
        ('Delta Zeta', alice, dict(genre='Fiction', format=other, owned=0, publish_year=2005,
                                   author='Amy', created_at='2024-02-01 10:00:00')),
        ('Epsilon', alice, dict(removed_at='2024-05-01 00:00:00', author='Ned',
                                created_at='2022-01-01 10:00:00')),
        ('Zeta café', alice, dict(genre='Fiction', format=plain, publish_year=2010,
                                       created_at='2024-04-01 10:00:00')),
        ('Bob Fiction', bob, dict(genre='Fiction', format=plain, publish_year=2015, author='Bob',
                                  created_at='2024-01-20 10:00:00')),
        ('Bob Cooking', bob, dict(genre='Cooking', format=other, publish_year=2000, author='Bob',
                                  created_at='2024-02-20 10:00:00')),
    ]
    for title, owner, cols in rows:
        ids[title] = put(db, owner, title, kind, **cols)

    def status(user, title, st):
        db.execute('INSERT INTO collections (user_id, book_id, status) VALUES (?, ?, ?)',
                   (user, ids[title], st))

    def rate(user, title, n):
        db.execute('INSERT INTO read_data (user_id, book_id, rating) VALUES (?, ?, ?)',
                   (user, ids[title], n))

    def tag(user, title, name):
        db.execute('INSERT INTO book_tags (user_id, book_id, tag_name) VALUES (?, ?, ?)',
                   (user, ids[title], name))

    def finish(user, title, date):
        db.execute('INSERT INTO reading_sessions (user_id, book_id, date_completed) VALUES (?, ?, ?)',
                   (user, ids[title], date))

    status(alice, 'Alpha Cooking', s1)
    status(alice, 'Gamma', s2)
    status(alice, 'Delta Zeta', s1)
    status(bob, 'Bob Fiction', s1)           # bob's marks must not leak into alice's filters
    rate(alice, 'Alpha Cooking', 4)
    rate(alice, 'Gamma', 2)
    rate(bob, 'Bob Cooking', 5)
    tag(alice, 'Alpha Cooking', 'kitchen')
    tag(alice, 'Beta Cookbook', 'kitchen')
    tag(alice, 'Gamma', 'shelf')
    tag(bob, 'Bob Fiction', 'kitchen')
    finish(alice, 'Gamma', '2024-06-01')
    finish(alice, 'Alpha Cooking', '2023-01-01')
    db.commit()
    return ids


def queries(kind):
    """Every filter and sort the grids offer, as query strings."""
    plain, other = FORMATS[kind]
    s1, s2 = media.STATUSES[kind][:2]
    fmt = other if plain is None else plain
    return [
        '',
        'search_term=cook',
        'search_term=cafe',                      # accents ignored
        'search_term=penguin',                   # a column besides the title
        'search_term=kitchen',                   # the viewer's tags are searched too
        'search_term=nothing+matches+this',
        'genre=cooking',                         # case-insensitive
        'genre=Fiction',
        f'format={fmt}',
        f'format={other}',
        f'read_status={s1}',
        f'read_status={s2}',
        'rating=3',
        'rating=1',
        'tags[]=kitchen',
        'tags[]=kitchen&tags[]=shelf',
        'show=not_owned',
        'show=removed',
        'show=all',
        'show=bogus',                            # unknown Show falls back to the shelf
        'sort_by=author&sort_order=desc',
        'sort_by=author&sort_order=asc',
        'sort_by=publish_year&sort_order=desc',
        'sort_by=created_at&sort_order=desc',
        'sort_by=created_at&sort_order=asc',
        'sort_by=rating&sort_order=desc',        # the viewer's ratings, unrated last
        'sort_by=finished&sort_order=desc',      # the viewer's sessions
        'sort_by=bogus&sort_order=sideways',     # unknown sort falls back to title
        f'genre=fiction&read_status={s1}&sort_by=created_at&sort_order=desc',
        'show=all&search_term=zeta&sort_by=publish_year',
    ]


def rendered_ids(client, url):
    """Item ids in the order the grid page lists them."""
    page = client.get(url)
    assert page.status_code == 200, url
    return [int(i) for i in LINK.findall(page.get_data(as_text=True))]


def resolve(app, db, user_id, view, args):
    """view_ids as a route calls it: inside an app context (the household
    views read the household through models.get_library_members, which wants
    one) on the request-scoped connection, which has the fold() SQL function
    the searches need. `db` is the test's own connection, used to seed."""
    with app.app_context():
        return grid_query.view_ids(get_db(), Who(user_id), view, args)


def args_of(query):
    return MultiDict(parse_qsl(query, keep_blank_values=True))


def titles_of(db, ids):
    return [db.execute('SELECT title FROM books WHERE id = ?', (i,)).fetchone()[0] for i in ids]


# --- what the Books grid returned before the query moved ---------------------

BOOKS_PINNED = {
    '': ['Alpha Cooking', 'Beta Cookbook', 'Gamma', 'Zeta café'],
    'search_term=cook': ['Alpha Cooking', 'Beta Cookbook'],
    'search_term=cafe': ['Zeta café'],
    'search_term=penguin': ['Alpha Cooking'],
    'search_term=kitchen': ['Alpha Cooking', 'Beta Cookbook'],
    'genre=cooking': ['Alpha Cooking', 'Beta Cookbook'],
    'format=Audiobook': ['Beta Cookbook'],
    'format=Book': ['Alpha Cooking', 'Gamma', 'Zeta café'],
    'read_status=read': ['Alpha Cooking'],
    'rating=3': ['Alpha Cooking'],
    'tags[]=kitchen&tags[]=shelf': ['Alpha Cooking', 'Beta Cookbook', 'Gamma'],
    'show=not_owned': ['Delta Zeta'],
    'show=removed': ['Epsilon'],
    'show=all': ['Alpha Cooking', 'Beta Cookbook', 'Delta Zeta', 'Epsilon', 'Gamma', 'Zeta café'],
    'sort_by=author&sort_order=desc': ['Alpha Cooking', 'Gamma', 'Zeta café', 'Beta Cookbook'],
    'sort_by=created_at&sort_order=desc': ['Zeta café', 'Beta Cookbook', 'Alpha Cooking', 'Gamma'],
    'sort_by=rating&sort_order=desc': ['Alpha Cooking', 'Gamma', 'Beta Cookbook', 'Zeta café'],
    'sort_by=finished&sort_order=desc': ['Gamma', 'Alpha Cooking', 'Beta Cookbook', 'Zeta café'],
}


def test_books_grid_order(client, db, people):
    """The literal results of the Books grid, so the extraction can't have
    changed what it shows."""
    seed(db, people, media.BOOK)
    login(client, 'alice')
    for query, expected in BOOKS_PINNED.items():
        got = titles_of(db, rendered_ids(client, '/base/index?' + query))
        assert got == expected, query


# --- the extracted query against every grid -----------------------------------

@pytest.mark.parametrize('kind', [media.BOOK, media.VIDEO, media.RECORD])
def test_view_ids_match_grid_own(app, client, db, people, kind):
    ids = seed(db, people, kind)
    url, _, view, _ = SECTIONS[kind]
    login(client, 'alice')
    for query in queries(kind):
        rendered = rendered_ids(client, f'{url}?{query}')
        resolved = resolve(app, db, people['alice'], view, args_of(query))
        assert resolved == rendered, query
    # The test would pass vacuously on an empty shelf
    assert len(rendered_ids(client, url)) >= 3 and ids


@pytest.mark.parametrize('kind', [media.BOOK, media.VIDEO, media.RECORD])
def test_view_ids_match_grid_household(app, client, db, people, kind):
    seed(db, people, kind)
    carol = people['carol']
    _, url, _, view = SECTIONS[kind]
    login(client, 'alice')
    members = [''] + [f'member={people["bob"]}', f'member={carol}']   # carol isn't in the household
    for member in members:
        for query in queries(kind):
            full = '&'.join(p for p in (query, member) if p)
            rendered = rendered_ids(client, f'{url}?{full}')
            resolved = resolve(app, db, people['alice'], view, args_of(full))
            assert resolved == rendered, full
    # Bob's items are really in there
    assert len(rendered_ids(client, url)) > len(rendered_ids(client, SECTIONS[kind][0]))


@pytest.mark.parametrize('kind', [media.BOOK, media.VIDEO, media.RECORD])
def test_view_ids_use_the_callers_marks(app, client, db, people, kind):
    """A household member's grid is filtered by their own statuses and
    ratings, not alice's."""
    seed(db, people, kind)
    _, _, view, _ = SECTIONS[kind]
    s1 = media.STATUSES[kind][0]
    args = args_of(f'read_status={s1}')
    alice = resolve(app, db, people['alice'], view, args)
    bob = resolve(app, db, people['bob'], view, args)
    assert alice != bob


def test_view_ids_refuse_unknown_views(app, db, people):
    me = people['alice']
    for view in ('', 'book', 'book:friend', 'friend:book', 'books:mine', 'book:mine; DROP TABLE books',
                 'book:search', None):
        with pytest.raises(ValueError):
            resolve(app, db, me, view, MultiDict())


def test_view_ids_accept_a_query_string(app, db, people):
    """The browser sends the page's query string as text."""
    seed(db, people, media.BOOK)
    me = people['alice']
    as_text = resolve(app, db, me, 'book:mine', 'genre=cooking&sort_by=author')
    as_args = resolve(app, db, me, 'book:mine', args_of('genre=cooking&sort_by=author'))
    assert as_text == as_args and len(as_text) == 2
    assert resolve(app, db, me, 'book:mine', '') == resolve(app, db, me, 'book:mine', None)


def test_view_ids_ignore_paging(app, db, people):
    """A grid pages by ?page=, a selection of the view is every page."""
    seed(db, people, media.BOOK)
    me = people['alice']
    everything = resolve(app, db, me, 'book:mine', '')
    assert resolve(app, db, me, 'book:mine', 'page=2&per_page=12') == everything


def test_view_ids_never_leave_the_circle(app, db, people):
    """Strangers' items never appear, whatever the arguments say."""
    stranger = add_user(db, 'dave')
    seed(db, people, media.BOOK)
    theirs = put(db, stranger, 'Dave Only', media.BOOK, genre='Cooking')
    db.commit()
    me = people['alice']
    for view in ('book:mine', 'book:household'):
        assert theirs not in resolve(app, db, me, view, 'show=all')

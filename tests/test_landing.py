"""Where form posts land (utils/landing.py, ROADMAP 16.0g step 7)."""
import re

import pytest

from conftest import add_book, login


@pytest.mark.parametrize('url,ok', [
    ('/books/3', True), ('http://localhost/feed/activity', True),
    ('https://evil.example/x', False), ('//evil.example/x', False),
    ('javascript:alert(1)', False), ('evil.example/x', False), ('', False), (None, False),
])
def test_same_site(app, url, ok):
    from utils.landing import same_site
    with app.test_request_context('/', base_url='http://localhost'):
        assert bool(same_site(url)) is ok


def test_back_prefers_a_same_site_next_then_the_referrer_then_the_fallback(app):
    from utils.landing import back_url
    ctx = lambda **kw: app.test_request_context('/', method='POST', base_url='http://localhost', **kw)
    with ctx(data={'next': '/records/'}, headers={'Referer': 'http://localhost/feed/activity'}):
        assert back_url('/x') == '/records/'
    with ctx(data={'next': 'https://evil.example/'}, headers={'Referer': 'http://localhost/feed/activity'}):
        assert back_url('/x') == 'http://localhost/feed/activity'
    with ctx(headers={'Referer': 'https://evil.example/'}):
        assert back_url('/x') == '/x'


def test_an_action_never_lands_off_site(client, db, people):
    book = add_book(db, people['alice'], 'Dune')
    login(client, 'alice')
    r = client.post('/collections/collections/status/add', data={'id': book, 'status': 'read'},
                    headers={'Referer': 'https://evil.example/phish'})
    assert r.status_code == 302 and 'evil' not in r.headers['Location']


def test_removing_from_the_wishlist_lands_by_where_you_were(client, db, people):
    alice = people['alice']
    film = add_book(db, alice, 'Jaws')
    db.execute("UPDATE books SET media_type = 'video' WHERE id = ?", (film,))
    held = add_book(db, people['bob'], 'Held')          # the household's: not deleted with the entry
    for b in (film, held):
        db.execute('INSERT INTO wishlist (user_id, book_id) VALUES (?, ?)', (alice, b))
    db.commit()
    login(client, 'alice')
    r = client.post(f'/wishlist/remove/{held}', headers={'Referer': f'http://localhost/books/{held}'})
    assert r.headers['Location'] == f'/books/{held}'                     # its page, not the shelf
    r = client.post(f'/wishlist/remove/{film}', headers={'Referer': 'http://localhost/wishlist/view?show=movies'})
    assert r.headers['Location'].startswith('/wishlist/view')


# POST rules from before 16.0g step 7 that don't have the agreed shape.
# Renamed only when touched for another reason (spec 2.2.3): they're only
# called by the app's own forms, so it's safe, but churn. Don't add to it.
OLD_SHAPES = {
    '/books/delete/<int:id>',
    '/books/edit/<int:id>',
    '/books/ownership/<int:id>',
    '/books/remove/<int:id>',
    '/books/restore/<int:id>',
    '/books/transfer/<int:book_id>',
    '/collections/delete_collection/<int:collection_id>',
    '/covers/crop/save/<int:book_id>',
    '/friends/accept/<int:request_id>',
    '/friends/decline/<int:request_id>',
    '/friends/dismiss_notification/<int:notification_id>',
    '/friends/remove/<int:friend_id>',
    '/friends/send_request/<username>',
    '/photos/<int:book_id>/<kind>',
    '/read/delete_reading_session/<int:session_id>',
    '/read/manage_session/<int:book_id>',
    '/read/rate_review/<int:book_id>',
    '/records/edit/<int:id>',
    '/user/household/accept/<int:invite_id>',
    '/user/household/decline/<int:invite_id>',
    '/user/household/invite/<int:user_id>',
    '/user/household/remove/<int:user_id>',
    '/values/fetch/<int:book_id>',
    '/videos/edit/<int:id>',
    '/wishlist/move_to_library/<int:book_id>',
    '/wishlist/quick_add/<int:book_id>',
    '/wishlist/remove/<int:book_id>',
    '/wishlist/update_notes/<int:book_id>',
}


def test_new_post_routes_are_thing_id_verb(app):
    """A POST route that takes an argument ends <arg>/<verb>, as
    /loans/<id>/lend (spec 2.2.3)."""
    shape = re.compile(r'<[^>]+>/[a-z_-]+$')
    rules = {r.rule for r in app.url_map.iter_rules() if 'POST' in r.methods and r.arguments}
    assert sorted(r for r in rules if not shape.search(r) and r not in OLD_SHAPES) == []
    assert sorted(OLD_SHAPES - rules) == [], 'renamed: take it off OLD_SHAPES'

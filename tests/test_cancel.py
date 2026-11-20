"""Cancel on every full-page form (layout walk 16.0, step 5,
docs/LAYOUT-WALK-SPEC.md section 5): a plain link (data-cancel) after the
main button, back where the form came from."""
import re

from conftest import add_book, login
from test_records import add_record
from test_videos import add_video


def cancel(client, url):
    """The page's Cancel link: (href, the rest of its attributes)."""
    r = client.get(url)
    assert r.status_code == 200, url
    html = r.get_data(as_text=True)
    links = re.findall(r'<a href="([^"]*)" data-cancel([^>]*)>Cancel</a>', html)
    assert len(links) == 1, (url, links)
    # after the main button, in the same row
    assert html.index('type="submit"', html.index('id="item-form"') if 'id="item-form"' in html
                      else html.index('id="review-form"')) < html.index('data-cancel')
    return links[0]


def test_edit_pages_cancel_to_the_item(client, db, people):
    alice = people['alice']
    book, video, record = add_book(db, alice, 'Dune'), add_video(db, alice), add_record(db, alice)
    login(client, 'alice')
    for edit, show in ((f'/books/edit/{book}', f'/books/{book}'),
                       (f'/videos/edit/{video}', f'/videos/{video}'),
                       (f'/records/edit/{record}', f'/records/{record}')):
        href, rest = cancel(client, edit)
        assert href == show, edit
        # photos save as you change them: the hover note says so
        assert 'title="Photos you changed are already saved' in rest


def test_add_pages_cancel_back_where_they_came_from(client, db, people):
    login(client, 'alice')
    href, rest = cancel(client, '/books/add')
    assert href == '/books/' and 'data-grid-crumb="book"' in rest      # the last Books grid, via common.js
    href, rest = cancel(client, '/videos/add')
    assert href == '/videos/' and 'data-grid-crumb="video"' in rest
    href, rest = cancel(client, '/wishlist/add?type=record')
    assert href == '/wishlist/view' and 'data-grid-crumb' not in rest
    # Reviews' "Add it as unshelved": back to Reviews, the crumb too
    r = client.get('/records/add?not_owned=1&then=review&title=Blue')
    html = r.get_data(as_text=True)
    href, rest = cancel(client, '/records/add?not_owned=1&then=review&title=Blue')
    assert href == '/reviews/?type=record' and 'data-grid-crumb' not in rest
    assert '<a href="/reviews/?type=record" class="crumb-link">Reviews</a>' in html


def test_review_cancels_where_submit_lands(client, db, people):
    """Cancel and Submit land in the same place (read.rate_review): Reviews
    when opened from there, else the item's page, a book's too (Phil,
    2026-11-19: it used to be the Library's Read shelf)."""
    alice = people['alice']
    book, video, record = add_book(db, alice, 'Dune'), add_video(db, alice), add_record(db, alice)
    login(client, 'alice')
    for item, page in ((book, f'/books/{book}'), (video, f'/videos/{video}'), (record, f'/records/{record}')):
        assert cancel(client, f'/read/rate_review/{item}')[0] == page
        r = client.post(f'/read/rate_review/{item}', data={'rating': '4'})
        assert r.status_code == 302 and r.location == page
    assert cancel(client, f'/read/rate_review/{book}?from=reviews')[0] == '/reviews/?type=book'
    r = client.post(f'/read/rate_review/{book}?from=reviews', data={'rating': '4', 'from': 'reviews'})
    assert r.location == '/reviews/?type=book'

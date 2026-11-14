"""Covers as boxes in the Shelf style, and one placeholder shape everywhere
(14c follow-ups, Phil 2026-11-12)."""
import pathlib
import re

from conftest import add_book, add_review, login

ROOT = pathlib.Path(__file__).resolve().parent.parent
CSS = (ROOT / 'static/styles.css').read_text()


def test_shelf_row_placeholders_are_titled_and_cover_shaped(client, db, people):
    """Collections showed a bare binding (no title); Reviews squeezed a 2:3
    cover into a fixed w-14 and broke titles between letters."""
    book = add_book(db, people['alice'], 'Essential Bukowski', 'Charles Bukowski')
    add_review(db, people['alice'], book)          # also marks it read
    login(client, 'alice')
    for url in ('/collections/collections', '/reviews/', '/user/alice'):
        html = client.get(url).get_data(as_text=True)
        row = html[html.index('class="shelf-row'):]
        placeholder = re.search(r'<div class="no-cover [^"]*"[^>]*>.*?</div>', row, re.S).group(0)
        assert 'Essential Bukowski' in placeholder, url
        assert 'h-28 w-auto aspect-[2/3]' in placeholder and 'w-14' not in placeholder, url


def test_placeholder_type_breaks_between_words():
    base = CSS[CSS.index('    .no-cover {'):]
    base = base[:base.index('}')]
    assert 'overflow-wrap: anywhere' not in base and 'overflow-wrap: break-word' in base
    assert 'container-type: inline-size' in base


def test_display_covers_are_wrapped_for_the_box():
    """Every cover picture on a display page sits in a .cover-box, the
    element the Shelf style draws the 3D faces on (an <img> can't have
    them). Form previews and admin pages stay flat on purpose, and so does
    the item page's enlarged cover (#cover-zoom): it is fitted into a
    fixed box with object-fit, so faces drawn on the box would miss it."""
    for name in ('_shelf_rows.html', 'activity_feed.html', '_wishlist_card.html', 'user_wishlist.html',
                 'reviews_list.html', 'reviews_find.html', 'rate_review.html', 'have.html', 'user.html',
                 'book_detail.html', '_book_grid.html'):
        text = (ROOT / 'templates' / name).read_text()
        text = re.sub(r'<dialog id="cover-zoom".*?</dialog>', '', text, flags=re.S)
        for img in re.findall(r'(.{0,40})<img src="\{\{ url_for\(\'static\', filename=[a-z_.]*\[?\'?cover_image_url', text):
            assert 'cover-box' in img, name


def test_spine_is_inside_the_box():
    """The base placeholder's spine is a left border, outside the padding
    box the faces start from; in the Shelf style it's an inset band."""
    rule = CSS[CSS.index(':root[data-style="shelf"] .no-cover {\n    border: 0;'):]
    rule = rule[:rule.index('}')]
    assert 'inset 6px 0 0 rgb(var(--accent))' in rule


def test_item_page_cover_is_a_box_without_a_bookcase():
    """The details card is the bookcase; the cover in it is a free box
    (its own bookcase was tried and dropped, Phil 2026-11-12)."""
    assert ':is(.page-heading, .case-card)' in CSS and '.cover-stand, .case-card' not in CSS
    stand = CSS[CSS.index(':root[data-style="shelf"] .cover-stand {\n    --box-depth'):]
    assert 'padding: var(--box-depth) var(--box-depth) 0 0' in stand[:stand.index('}')]
    detail = (ROOT / 'templates/book_detail.html').read_text()
    assert 'case-card' not in detail               # plain cards since Phil, 2026-11-13; the heading keeps its case


def test_feed_and_notifications_are_cards_like_reviews(client, db, people):
    """Phil, 2026-11-13: the feed and notifications went back from small
    bookcases to the rounded cards the Reviews lists use."""
    login(client, 'alice')
    assert 'case-card' not in client.get('/friends/notifications_page').get_data(as_text=True)
    feed = (ROOT / 'templates/activity_feed.html').read_text()
    assert 'case-card' not in feed and 'class="feed-card relative bg-secondary rounded-lg p-4 card flex gap-4 min-w-0"' in feed


def test_feed_reviews_are_clamped():
    """A long review printed in full made one feed card ~9,000px tall on a
    phone: it gets Read more like the item page's."""
    feed = (ROOT / 'templates/activity_feed.html').read_text()
    assert 'data-read-more>' in feed and 'id="feed-review-{{ loop.index }}" class="read-more-text' in feed


def test_no_stray_tokens_in_styles_css():
    """A leftover marker before a rule voids that rule's selector without
    any error (it happened once in 14c: every Shelf box variable vanished)."""
    assert '@@' not in CSS

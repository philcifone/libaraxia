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
    them). Form previews and admin pages stay flat on purpose."""
    for name in ('_shelf_rows.html', 'activity_feed.html', '_wishlist_card.html', 'user_wishlist.html',
                 'reviews_list.html', 'reviews_find.html', 'rate_review.html', 'have.html', 'user.html',
                 'book_detail.html', '_book_grid.html'):
        text = (ROOT / 'templates' / name).read_text()
        for img in re.findall(r'(.{0,40})<img src="\{\{ url_for\(\'static\', filename=[a-z_.]*\[?\'?cover_image_url', text):
            assert 'cover-box' in img, name


def test_spine_is_inside_the_box():
    """The base placeholder's spine is a left border, outside the padding
    box the faces start from; in the Shelf style it's an inset band."""
    rule = CSS[CSS.index(':root[data-style="shelf"] .no-cover {\n    border: 0;'):]
    rule = rule[:rule.index('}')]
    assert 'inset 6px 0 0 rgb(var(--accent))' in rule


def test_item_page_box_stands_on_its_shelf():
    """The box's far corner lands on the top face, as on the grid: the
    shelf is deeper than the box and the box stands in from its front."""
    stand = CSS[CSS.index(':root[data-style="shelf"] .cover-stand {\n    --frame: 10px;'):]
    stand = stand[:stand.index('}')]
    top = int(re.search(r'--ledge-top: (\d+)px', stand).group(1))
    sink = int(re.search(r'--sink: (\d+)px', stand).group(1))
    depth = int(re.search(r':root\[data-style="shelf"\] \.cover-stand \{ --box-depth: (\d+)px; \}', CSS).group(1))
    assert depth < sink < top


def test_feed_and_notifications_are_bookcases(client, db, people):
    login(client, 'alice')
    assert 'class="case-card' in client.get('/friends/notifications_page').get_data(as_text=True)
    assert 'case-card' in (ROOT / 'templates/activity_feed.html').read_text()


def test_no_stray_tokens_in_styles_css():
    """A leftover marker before a rule voids that rule's selector without
    any error (it happened once in 14c: every Shelf box variable vanished)."""
    assert '@@' not in CSS

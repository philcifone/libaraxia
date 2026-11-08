"""Page layout regressions (Phase 7): broken nesting, grid columns, phone widths.

The visual checks (light/dark, House/Classic, 390px and desktop) are done in a
headless browser; these tests pin the specific causes found that way."""
import pathlib
import re
from html.parser import HTMLParser
from unittest import mock

from conftest import add_book, login

ROOT = pathlib.Path(__file__).resolve().parent.parent

# Elements that never take a closing tag (HTML void elements, plus the SVG
# shapes our icons write as <path ... />).
VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'source',
        'track', 'wbr', 'path', 'circle', 'rect', 'line', 'polyline', 'polygon', 'use', 'stop'}


class _TagBalance(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack, self.problems = [], []

    def handle_starttag(self, tag, attrs):
        if tag not in VOID:
            self.stack.append((tag, self.getpos()[0]))

    def handle_startendtag(self, tag, attrs):
        pass  # <x ... /> opens and closes in one go

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if not any(t == tag for t, _ in self.stack):
            self.problems.append(f'stray </{tag}> at line {self.getpos()[0]}')
            return
        while self.stack[-1][0] != tag:
            t, line = self.stack.pop()
            self.problems.append(f'<{t}> from line {line} never closed')
        self.stack.pop()


def unbalanced_tags(html):
    """Problems with open/close tag nesting in a rendered page ([] if none).

    A stray </div> in a page template closes base.html's own wrapper early, and
    an unclosed one swallows whatever base.html puts after the content block, so
    the layout breaks in ways that only show at some widths."""
    parser = _TagBalance()
    parser.feed(html)
    return parser.problems + [f'<{t}> from line {line} never closed' for t, line in parser.stack]


def test_tag_balance_checker_catches_both_mistakes():
    assert unbalanced_tags('<div><p>ok</p><img src=x><svg><path d="M0"/></svg></div>') == []
    assert unbalanced_tags('<div></div></div>') == ['stray </div> at line 1']
    assert unbalanced_tags('<main><div></main>') == ['<div> from line 1 never closed']


def test_isbn_lookup_keeps_the_add_form_one_column(client, db, people):
    """Regression: after a manual ISBN lookup the add form split into two
    columns on phones. The "Data source" line had a bare `col-span-2`; below the
    md breakpoint the form grid has no column template, so spanning two columns
    made the grid invent a second one and every later field flowed into it."""
    details = {'title': 'Slaughterhouse-Five', 'author': 'Kurt Vonnegut', 'isbn': '9780385333849',
               'source': 'Google Books'}
    login(client, 'bob')
    with mock.patch('blueprints.books.fetch_book_details_from_isbn', return_value=details):
        r = client.post('/books/add', data={'isbn_lookup': '1', 'isbn': '9780385333849'})
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and 'Data source: Google Books' in html
    source_line = re.search(r'<div class="([^"]*)">Data source', html).group(1).split()
    assert 'md:col-span-2' in source_line and 'col-span-2' not in source_line
    assert unbalanced_tags(html) == []
    # ...and the ISBN tab stays selected after the lookup (it reset to Search),
    # with the ISBN still in its box
    assert re.search(r'data-method="code" data-active="true"', html)
    assert 'id="code-section" data-method="code" class="search-method-content"' in html
    assert 'id="search-section" data-method="search" class="search-method-content hidden"' in html
    assert 'value="9780385333849"' in html
    first = client.get('/books/add').get_data(as_text=True)
    assert 'data-method="search" data-active="true"' in first
    assert 'id="code-section" data-method="code" class="search-method-content hidden"' in first


def test_form_controls_can_shrink_in_flex_rows():
    """Regression: "input flex-1 + button" rows (add-book search, tags, reading
    goal, new shelf) pushed the button out of the card on phones, because a
    flex item's min-width defaults to its intrinsic width. styles.css resets it."""
    css = (ROOT / 'static' / 'styles.css').read_text()
    assert re.search(r'input, select, textarea \{\s*min-width: 0;', css)
    built = (ROOT / 'static' / 'css' / 'output.css').read_text()
    assert 'min-width: 0' in built or 'min-width:0' in built


def test_flash_colours_are_shared_and_themed(client, db, people):
    """Toasts used `text-white` on green/red fills: in House `white` is the ink
    colour, so it was dark text on olive (light) and pale text on bright green
    (dark). Both the template and showFlashMessage() now use .flash-* classes."""
    common = (ROOT / 'static' / 'common.js').read_text()
    partial = (ROOT / 'templates' / '_flash_messages.html').read_text()
    for cls in ('flash-success', 'flash-error', 'flash-info'):
        assert cls in common and cls in partial
    assert 'text-white' not in partial
    css = (ROOT / 'static' / 'styles.css').read_text()
    assert re.search(r'\.flash-success\s*\{[^}]*on-accent', css)
    assert re.search(r'\.flash-error\s*\{[^}]*on-accent', css)


def test_wishlist_book_page_is_balanced(client, db, people):
    """book_detail.html has a separate branch for wishlist books; check it too."""
    book = add_book(db, people['bob'], 'Want This', 'Someone')
    db.execute('INSERT INTO wishlist (user_id, book_id) VALUES (?, ?)', (people['bob'], book))
    db.commit()
    login(client, 'bob')
    r = client.get(f'/books/book/{book}')
    assert r.status_code == 200 and unbalanced_tags(r.get_data(as_text=True)) == []


def test_text_on_coloured_fills_uses_on_accent():
    """In House, Tailwind's `white` is mapped to the ink colour (so ~600 old
    `text-white` uses follow the theme). On an accent/red/green fill that gives
    dark-on-olive in light mode and pale-on-bright-green in dark mode, both
    under 4.5:1. Text on those fills must use `text-on-accent`."""
    fill = r'bg-(accent|green-\d+|red-\d+|blue-\d+|orange-\d+|gray-\d+)'
    pattern = re.compile(rf"{fill}[^\"'`]*\btext-white\b|\btext-white\b[^\"'`]*{fill}")
    files = list((ROOT / 'templates').rglob('*.html')) + list((ROOT / 'static').glob('*.js'))
    offenders = [f'{f.relative_to(ROOT)}:{n}' for f in files
                 for n, line in enumerate(f.read_text().splitlines(), 1) if pattern.search(line)]
    assert offenders == []


def _class_strings():
    """(file:line, [tokens]) for every class="..." / className = '...' in
    templates and static/*.js."""
    pattern = re.compile(r'''class="([^"]*)"|className\s*=\s*'([^']*)\'''', re.S)
    files = list((ROOT / 'templates').rglob('*.html')) + list((ROOT / 'static').glob('*.js'))
    for f in files:
        text = f.read_text()
        for m in pattern.finditer(text):
            line = text[:m.start()].count('\n') + 1
            yield f'{f.relative_to(ROOT)}:{line}', (m.group(1) or m.group(2) or '').split()


def test_component_classes_are_not_overridden():
    """Phase 7.1: cards and buttons get their border, shadow and hover "press"
    from .card / .card-link / .btn / .fab and the style's variables. Tailwind
    utilities sit in a later layer and win, so a shadow-* or transition-colors
    on the same element would silently switch the press effect off."""
    component = {'card', 'card-link', 'btn', 'fab'}
    clash = re.compile(r'^(hover:)?(shadow(-(sm|md|lg|xl|2xl))?|transition-colors|transition-all|hover:scale-105)$')
    offenders = [where for where, tokens in _class_strings()
                 if component & set(tokens) and any(clash.match(t) for t in tokens)]
    assert offenders == []


def test_cards_and_filled_buttons_use_the_components():
    """Every outlined panel (bg-secondary + border-card) is a .card, and every
    filled button or button-like link is a .btn, so a style can restyle them all."""
    fill = re.compile(r'^bg-(accent|red-\d+|blue-\d+|orange-\d+|green-\d+)$')
    old_cards = [w for w, t in _class_strings()
                 if {'border', 'border-card'} <= set(t) and any(re.match(r'^bg-secondary(-bg)?$', x) for x in t)]
    assert old_cards == []
    assert not [w for w, t in _class_strings() if 'hover:scale-105' in t]

    tag = re.compile(r'<(button|a)\b[^<>]*?\bclass="([^"]*)"', re.S)
    plain = []
    for f in list((ROOT / 'templates').rglob('*.html')) + list((ROOT / 'static').glob('*.js')):
        for m in tag.finditer(f.read_text()):
            tokens = m.group(2).split()
            if '{%' in m.group(2) or '${' in m.group(2):
                continue  # conditional fills (active shelf chips) are chips, not buttons
            if any(fill.match(t) for t in tokens) and not {'btn', 'fab'} & set(tokens):
                plain.append(f'{f.relative_to(ROOT)}: {" ".join(tokens)[:60]}')
    assert plain == []


def test_sidebar_has_the_mode_shortcut(client, db, people):
    """7.1: Mode can be switched from the sidebar on any page, without a trip
    to the profile. Same buttons and endpoint as Profile -> Appearance."""
    db.execute("UPDATE users SET color_mode = 'dark' WHERE id = ?", (people['bob'],))
    db.commit()
    login(client, 'bob')
    html = client.get('/base/index').get_data(as_text=True)
    picker = html[html.index('data-theme-picker'):html.index('auth/logout')]
    assert 'data-value="dark"\n                            aria-pressed="true"' in picker
    assert picker.count('class="theme-opt') == 3
    r = client.post('/user/update_theme', json={'mode': 'light'})
    assert r.status_code == 200 and r.get_json()['success']
    assert db.execute('SELECT color_mode FROM users WHERE id = ?', (people['bob'],)).fetchone()[0] == 'light'


def test_book_page_cover_has_no_film_frame(client, db, people):
    """The 7.1 film frame came off books (Phil, 2026-11-05). Its CSS is parked
    in docs/parked/film-frame.css for VHS/DVD, not loaded by the app."""
    book = add_book(db, people['bob'], 'Dune', 'Frank Herbert')
    login(client, 'bob')
    html = client.get(f'/books/book/{book}').get_data(as_text=True)
    assert 'film-frame' not in html and 'film-edge' not in html
    assert 'film-frame' not in (ROOT / 'static/styles.css').read_text()
    assert '.film-frame' in (ROOT / 'docs/parked/film-frame.css').read_text()


def test_fab_does_not_block_the_sidebar_or_page():
    """Regression: the add-book FAB (z-50) sat on top of the open sidebar,
    covering the Mode switch and Logout on phones, and its container (which
    includes the invisible menu above the button) swallowed clicks on the page
    underneath. Now it's under the sidebar and click-through except the button."""
    fab = (ROOT / 'templates' / '_add_fab.html').read_text()
    sidebar = (ROOT / 'templates' / '_sidebar.html').read_text()
    container = re.search(r'<div class="([^"]*)" id="fab-container">', fab).group(1).split()
    assert 'pointer-events-none' in container
    fab_z = int(next(t for t in container if t.startswith('z-'))[2:])
    sidebar_z = int(re.search(r'id="sidebar"\s+class="[^"]*\bz-(\d+)', sidebar).group(1))
    assert fab_z < sidebar_z
    assert re.search(r'id="fab-toggle"\s+class="pointer-events-auto', fab)
    backdrop_z = int(re.search(r'id="fab-backdrop" class="[^"]*\bz-(\d+)', fab).group(1))
    assert backdrop_z < fab_z   # the open menu's click-to-close backdrop sits under it


def test_no_native_alert_or_confirm():
    """7.3: alert()/confirm() are replaced by toasts (showFlashMessage) and the
    styled confirmDialog()/confirmSubmit() in common.js. Native dialogs ignore
    the theme, block the page, and on phones look like a system warning."""
    calls = re.compile(r'(?<![\w.])(alert|confirm)\(')
    offenders = []
    for f in (ROOT / 'static').glob('*.js'):
        for n, line in enumerate(f.read_text().splitlines(), 1):
            code = line.split('//')[0]
            if calls.search(code):
                offenders.append(f'{f.name}:{n}: {line.strip()[:70]}')
    assert offenders == []
    common = (ROOT / 'static' / 'common.js').read_text()
    assert 'function confirmDialog(' in common and 'function confirmSubmit(' in common


class _Names(HTMLParser):
    """Collects form fields and buttons that have no accessible name."""
    FIELDS = {'input', 'select', 'textarea'}
    SKIP_TYPES = {'hidden', 'submit', 'button', 'reset', 'image'}

    def __init__(self):
        super().__init__()
        self.label_for, self.fields, self.label_depth = set(), [], 0
        self.buttons, self.open_button = [], None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'label':
            self.label_depth += 1
            if a.get('for'):
                self.label_for.add(a['for'])
        elif tag in self.FIELDS and a.get('type', 'text') not in self.SKIP_TYPES:
            named = a.get('aria-label') or a.get('aria-labelledby') or a.get('title') or self.label_depth
            self.fields.append((a.get('id'), a.get('name'), bool(named)))
        elif tag == 'button':
            self.open_button = {'named': bool(a.get('aria-label') or a.get('title')), 'text': '', 'id': a.get('id')}
        elif tag == 'img' and self.open_button is not None and a.get('alt'):
            self.open_button['text'] += a['alt']

    def handle_endtag(self, tag):
        if tag == 'label':
            self.label_depth -= 1
        elif tag == 'button' and self.open_button is not None:
            self.buttons.append(self.open_button)
            self.open_button = None

    def handle_data(self, data):
        if self.open_button is not None:
            self.open_button['text'] += data.strip()

    def unnamed(self):
        fields = [f'field id={i} name={n}' for i, n, named in self.fields if not named and i not in self.label_for]
        buttons = [f'button id={b["id"]}' for b in self.buttons if not b['named'] and not b['text']]
        return fields + buttons


def test_every_field_and_button_has_a_name(client, db, people):
    """7.3 accessibility: every form field has a <label for>, a wrapping label
    or an aria-label (a placeholder isn't a label: it disappears as you type),
    and every icon-only button has an aria-label. Screen readers otherwise
    announce "edit text" / "button" with no clue what it's for."""
    book = add_book(db, people['alice'], 'Dune', 'Frank Herbert')
    login(client, 'alice')
    pages = ['/base/index', '/books/add', f'/books/edit/{book}', f'/books/book/{book}', '/wishlist/view',
             '/user/alice', f'/read/rate_review/{book}', '/collections/collections', '/feed/activity',
             '/friends/notifications_page', '/admin/settings', '/user/import_goodreads_page']
    problems = {}
    for url in pages:
        parser = _Names()
        parser.feed(client.get(url).get_data(as_text=True))
        if parser.unnamed():
            problems[url] = parser.unnamed()
    assert problems == {}


def test_empty_states(client, db, people):
    """7.3: an empty library, filters that match nothing and a search with no
    results each say so (and what to do), instead of a blank page."""
    login(client, 'carol')                       # carol has no books
    text = lambda url: ' '.join(client.get(url).get_data(as_text=True).split())
    assert 'Your library is empty' in text('/base/index') and '/user/import_goodreads_page' in text('/base/index')
    assert 'No books match these filters' in text('/base/index?genre=Nope')
    page = text('/books/search?search_term=zzzz')
    assert 'No books match &#34;zzzz&#34;' in page or 'No books match "zzzz"' in page
    assert 'Your wishlist is empty' in text('/wishlist/view')
    feed = text('/feed/activity')
    assert 'Nothing in your feed yet' in feed and 'Find friends' not in feed   # link removed 2026-11-07

    add_book(db, people['carol'], 'Dune', 'Frank Herbert')
    assert 'Your library is empty' not in text('/base/index') and 'Dune' in text('/base/index')


def test_reading_chart_months(db, people):
    """7.3: books finished per month for the profile chart. Twelve months
    ending now; a quiet year falls back to the twelve months ending at the
    last finished book. Rereads in one month count once."""
    from datetime import datetime
    from blueprints.user import reading_by_month

    alice = people['alice']
    assert reading_by_month(db, alice) is None          # nothing finished yet

    one, two, three = (add_book(db, alice, f'Book {n}', 'Someone') for n in (1, 2, 3))
    for book_id, day in [(one, '2026-03-02'), (one, '2026-03-20'),          # reread: counts once
                         (two, '2026-03-21'), (three, '2025-11-30 18:00:00')]:
        db.execute('INSERT INTO reading_sessions (user_id, book_id, date_completed) VALUES (?, ?, ?)',
                   (alice, book_id, day))
    db.commit()

    chart = reading_by_month(db, alice, today=datetime(2026, 4, 15))
    assert len(chart['bars']) == 12
    assert (chart['start'], chart['end']) == ('May 2025', 'April 2026')
    by_name = {bar['name']: bar['books'] for bar in chart['bars']}
    assert by_name['November 2025'] == 1 and by_name['March 2026'] == 2
    assert chart['peak'] == 2 and chart['total'] == 3
    assert [bar['pct'] for bar in chart['bars'] if bar['books']] == [50, 100]

    # Two years later nothing is in the window: it ends at the last read.
    later = reading_by_month(db, alice, today=datetime(2028, 6, 1))
    assert later['end'] == 'March 2026' and later['total'] == 3


def test_reading_chart_on_the_profile(client, db, people):
    alice = people['alice']
    book = add_book(db, alice, 'Dune', 'Frank Herbert')
    db.execute("INSERT INTO reading_sessions (user_id, book_id, date_completed) VALUES (?, ?, date('now'))", (alice, book))
    db.commit()
    login(client, 'alice')
    page = client.get('/user/alice').get_data(as_text=True)
    assert 'Books finished per month' in page and page.count('class="chart-col"') == 12
    assert 'Show as a table' in page


def test_one_no_cover_placeholder(client, db, people):
    """7.3: a book without a cover gets the same placeholder everywhere (the
    _no_cover.html partial or its JS twin noCoverHtml), with the title on it,
    instead of a mix of "No Image Available" boxes and book icons."""
    for path in list((ROOT / 'templates').rglob('*.html')) + list((ROOT / 'static').glob('*.js')):
        text = path.read_text()
        assert 'No Image Available' not in text and 'No Cover Available' not in text, path.name

    book = add_book(db, people['alice'], 'A Very Particular Book', 'Some Author')
    login(client, 'alice')
    for url in ('/base/index', f'/books/book/{book}'):
        page = client.get(url).get_data(as_text=True)
        start = page.index('class="no-cover ')
        assert 'A Very Particular Book' in page[start:start + 400], url


def test_covers_have_a_loading_skeleton():
    css = (ROOT / 'static/styles.css').read_text()
    common = (ROOT / 'static/common.js').read_text()
    # An attribute, not a class: script.js's grid/list switch rewrites className.
    assert 'img.book-cover-img:not([data-loaded])' in css
    assert "document.addEventListener('load'" in common and "dataset.loaded = '1'" in common


def test_view_switch_keeps_cover_positioning():
    """The grid/list switch rewrites each cover box's className; it must keep
    `relative`, or the Removed badge (absolute) loses its anchor."""
    script = (ROOT / 'static/script.js').read_text()
    for line in re.findall(r"cover\.className = '([^']*)'", script):
        assert 'relative' in line.split(), line


def test_view_bar_sorts_in_place(client, db, people):
    """7.2b: sort and grid/list sit in a bar above the grid, not inside the
    search row. Sorting stays on the page you're on and keeps the other
    parameters; filters likewise. GET forms carry no CSRF token."""
    add_book(db, people['alice'], 'Dune', 'Frank Herbert')
    login(client, 'alice')

    page = client.get('/base/index?show_removed=include&sort_by=publish_year').get_data(as_text=True)
    bar = page[page.index('class="view-bar'):]
    bar = bar[:bar.index('id="book-container"')]
    assert 'action="/base/index"' in bar and 'id="grid-view-btn"' in bar
    assert '<input type="hidden" name="show_removed" value="include">' in bar
    assert 'name="sort_by" value=' not in bar                  # the selects carry the sort
    assert 'Oldest first' in bar and 'A–Z' not in bar           # a year isn't A–Z
    assert '1 book' in bar

    dropdown = page[page.index('search-form-container'):page.index('class="view-bar')]
    assert 'id="sort-form"' not in dropdown and 'grid-view-btn' not in dropdown

    shared = client.get('/base/shared-library?member=%d' % people['bob']).get_data(as_text=True)
    sort_form = shared[shared.index('id="sort-form"') - 80:]
    assert 'action="/base/shared-library"' in sort_form[:200]
    assert '<input type="hidden" name="member" value="%d">' % people['bob'] in sort_form
    assert 'action="/base/shared-library"' in shared[shared.index('id="filter-form"') - 10:][:200]

    search = client.get('/books/search?search_term=dune').get_data(as_text=True)
    filter_form = search[search.index('id="filter-form"'):]
    assert 'action="/books/search"' in filter_form[:100]
    assert '<input type="hidden" name="search_term" value="dune">' in filter_form

    for html in (page, shared, search):
        for form in re.findall(r'<form[^>]*method="GET".*?</form>', html, re.S | re.I):
            assert 'csrf_token' not in form


def test_clear_filters_keeps_search_and_sort():
    script = (ROOT / 'static/script.js').read_text()
    body = script[script.index('function clearFilters'):][:400]
    assert 'FILTER_PARAMS.forEach' in body and 'window.location.pathname;' not in body


def test_search_row_sits_under_the_tabs(client, people):
    """Search and the filter button are one row under the page's tabs (the
    header's magnifying glass is gone), on every grid page and the wishlist."""
    login(client, 'alice')
    for url in ('/base/index', '/base/shared-library', '/videos/', '/records/shared'):
        page = client.get(url).get_data(as_text=True)
        assert 'id="search-toggle"' not in page, url
        tabs = page.index('class="tab ')
        row = page.index('search-form-container')
        assert tabs < row, url
        assert 'id="filter-toggle"' in page and 'aria-controls="filter-panel"' in page, url
    search = client.get('/books/search?search_term=x').get_data(as_text=True)
    assert 'search-form-container' in search and 'pt-20' in search
    wishlist = client.get('/wishlist/view').get_data(as_text=True)
    assert 'id="search-toggle"' not in wishlist


def test_accent_colour_is_saved_and_on_every_page(client, db, people):
    """8B.5: Profile -> Appearance -> Accent. Saved per user, put on <html
    data-accent>, House style only (the picker hides under Classic)."""
    login(client, 'bob')
    assert 'data-accent="green"' in client.get('/base/index').get_data(as_text=True)
    page = client.get('/user/bob').get_data(as_text=True)
    assert 'data-accent-picker' in page and page.count('data-kind="accent"') == 7
    r = client.post('/user/update_theme', json={'accent': 'blue'})
    assert r.status_code == 200 and r.get_json()['accent'] == 'blue'
    assert db.execute('SELECT accent FROM users WHERE id = ?', (people['bob'],)).fetchone()[0] == 'blue'
    assert 'data-accent="blue"' in client.get('/base/index').get_data(as_text=True)
    # Style and mode are left alone; nonsense is refused
    assert db.execute('SELECT theme_style, color_mode FROM users WHERE id = ?',
                      (people['bob'],)).fetchone()[:] == ('house', 'system')
    assert client.post('/user/update_theme', json={'accent': 'chartreuse'}).status_code == 400


def test_every_accent_has_css():
    """Each models.ACCENTS key has its shades in styles.css (green is the fallback)."""
    import os
    from models import ACCENTS
    css = open(os.path.join(os.path.dirname(__file__), '..', 'static', 'styles.css')).read()
    for key in ACCENTS:
        assert f'[data-swatch="{key}"]' in css, key
        if key != 'green':
            assert f':root[data-accent="{key}"]' in css, key


def test_pages_share_the_heading_card(client, db, people):
    """8B.6: Feed, Notifications, Wishlist, Collections and Admin open with
    the same icon-and-name card as the grids (page_heading)."""
    login(client, 'alice')                                      # admin
    for url, name in [('/feed/activity', 'Activity Feed'), ('/friends/notifications_page', 'Notifications'),
                      ('/wishlist/view', 'Wishlist'), ('/collections/collections', 'Collections'),
                      ('/admin/settings', 'Admin Settings')]:
        page = client.get(url, follow_redirects=True).get_data(as_text=True)
        h1 = re.search(r'<h1 class="flex items-center justify-center gap-3[^"]*">(.*?)</h1>', page, re.S)
        assert h1 and '<svg' in h1.group(1) and name in h1.group(1), url


def test_no_back_to_catalog_links():
    """8B.8: breadcrumbs (_icons.html crumbs) replaced the back links."""
    for path in pathlib.Path('templates').rglob('*.html'):
        text = path.read_text()
        assert 'Back to Catalog' not in text and '<span class="mr-2">←</span>' not in text, path


def test_item_page_crumbs_follow_the_section(client, db, people):
    book = add_book(db, people['alice'], title='Dune')
    login(client, 'alice')
    page = client.get(f'/books/book/{book}').get_data(as_text=True)
    assert '<a href="/base/index" class="crumb-link">Library</a>' in page
    assert '<li aria-current="page" class="crumb-here">Dune</li>' in page


def test_style_names_and_classic_accents(client, db, people):
    """Styles show as Negative Earth / OG (keys unchanged), and Classic takes
    the accent too, through its own --acc-l shades."""
    login(client, 'alice')
    page = client.get('/user/alice').get_data(as_text=True)
    assert 'Negative Earth' in page and '>OG<' in page.replace('\n', '').replace(' ', '')
    css = pathlib.Path('static/styles.css').read_text()
    assert '[data-accent-picker] { display: none; }' not in css
    classic = css[css.index('/* ---- Classic palette.'):]
    assert classic.count('--accent: var(--acc-l, 79 125 25)') == 3


def test_tmdb_logo_with_the_notice(client, db, people, monkeypatch):
    monkeypatch.setenv('TMDB_API_KEY', 'not-a-real-key')
    login(client, 'alice')
    page = client.get('/videos/add').get_data(as_text=True)
    assert 'src="/static/logos/tmdb.svg"' in page and 'not endorsed or certified by TMDB' in page
    svg = pathlib.Path('static/logos/tmdb.svg').read_text()
    assert '<script' not in svg.lower()

"""Page layout regressions (Phase 7): broken nesting, grid columns, phone widths.

The visual checks (light/dark, House/Classic, 390px and desktop) are done in a
headless browser; these tests pin the specific causes found that way."""
import os
import pathlib
import re
from html.parser import HTMLParser
from unittest import mock

from conftest import add_book, login, scalar

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
    to the profile. Same buttons and endpoint as Settings -> Account -> Appearance."""
    db.execute("UPDATE users SET color_mode = 'dark' WHERE id = ?", (people['bob'],))
    db.commit()
    login(client, 'bob')
    html = client.get('/base/index').get_data(as_text=True)
    # Since 2026-11-09 one sun/moon toggle under the welcome (sidebar.js picks
    # the other mode; styles.css shows the moon in light mode, the sun in dark)
    head = html[html.index('Welcome,'):html.index('<!-- Navigation -->')]
    assert 'data-mode-toggle data-mode-picker' in head
    assert 'mode-icon-moon' in head and 'mode-icon-sun' in head
    css = (ROOT / 'static/styles.css').read_text()
    assert ':root[data-mode="dark"] .mode-icon-sun { display: inline; }' in css
    assert "closest('[data-mode-toggle]')" in (ROOT / 'static/sidebar.js').read_text()
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
             '/friends/notifications_page', '/user/settings', '/user/import_goodreads_page']
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
    from utils.stats import by_month as reading_by_month

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
    by_name = {bar['name']: bar['items'] for bar in chart['bars']}
    assert by_name['November 2025'] == 1 and by_name['March 2026'] == 2
    assert chart['peak'] == 2 and chart['total'] == 3
    assert [bar['pct'] for bar in chart['bars'] if bar['items']] == [50, 100]

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
    assert 'Books read per month' in page and page.count('class="chart-col"') == 12
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
    assert 'book' not in bar.replace('book-container', '').replace('Select', '')   # the count isn't in the bar

    dropdown = page[page.index('search-form-container'):page.index('class="view-bar')]
    assert 'id="sort-form"' not in dropdown and 'grid-view-btn' not in dropdown
    assert '1 book matches' in dropdown                          # it is under the search box

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
    """8B.5: Settings -> Account -> Appearance -> Accent. Saved per user, put on <html
    data-accent>, House style only (the picker hides under Classic)."""
    login(client, 'bob')
    assert 'data-accent="green"' in client.get('/base/index').get_data(as_text=True)
    page = client.get('/user/settings').get_data(as_text=True)
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
                      ('/user/settings', 'Settings')]:
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
    page = client.get('/user/settings').get_data(as_text=True)
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


def test_og_dark_accent_text_is_readable():
    """OG dark: accent text uses the pale --acc-t shades (>= 4.5:1 on its
    greys), through --accent-text, which text-accent and the CSS text rules use."""
    css = pathlib.Path('static/styles.css').read_text()
    classic = css[css.index('/* ---- Classic palette.'):]
    assert classic.count('--accent-text: var(--acc-t, 142 192 72)') == 2
    for name in ('aqua', 'blue', 'purple', 'orange', 'red', 'yellow'):
        rule = re.search(r'\[data-swatch="' + name + r'"\]\s*\{([^}]*)\}', css).group(1)
        assert '--acc-t:' in rule and '--acc-t-hover:' in rule, name
    built = pathlib.Path('static/css/output.css').read_text()
    assert 'color: rgb(var(--accent-text) / var(--tw-text-opacity, 1))' in built
    assert not re.search(r'(?<![-\w])color: rgb\(var\(--accent\)\);', css)   # borders may keep it


def test_outrun_style_is_dark_only_with_neon_accents(client, db, people):
    """Outrun: selectable, dark only with fixed fonts (Mode and Font pickers
    marked so the CSS hides them, with a note), a neon shade for every
    accent, self-hosted OFL fonts."""
    login(client, 'alice')
    r = client.post('/user/update_theme', json={'style': 'outrun'})
    assert r.status_code == 200
    page = client.get('/user/settings').get_data(as_text=True)
    assert 'data-style="outrun"' in page
    assert page.count('data-mode-picker') == 2          # sidebar + Appearance
    assert 'data-outrun-note' in page and 'data-font-picker' in page

    css = pathlib.Path('static/styles.css').read_text()
    assert 'html:root[data-style="outrun"]' in css      # outranks House dark blocks
    # Outrun's fonts are fixed: no font choice applies, Mode and Font pickers hide
    for key in ('baskerville', 'garamond', 'literata', 'jost'):
        assert f':root[data-font="{key}"]:not([data-style="outrun"])' in css
    assert ':root[data-style="outrun"] :is([data-mode-picker], [data-font-picker])' in css
    assert 'monoton' not in css.lower() and 'exo 2' not in css.lower()
    for name in ('aqua', 'blue', 'purple', 'orange', 'red', 'yellow'):
        rule = re.search(r'\[data-swatch="' + name + r'"\]\s*\{([^}]*)\}', css).group(1)
        assert '--acc-n:' in rule, name
    for font, file in (('audiowide', 'audiowide-latin-400-normal.woff2'),
                       ('vt323', 'vt323-latin-400-normal.woff2')):
        d = pathlib.Path('static/fonts') / font
        assert (d / file).is_file() and (d / 'OFL.txt').is_file(), font


def test_shelf_style_bookcase(client, db, people):
    """Shelf (10.1 light pass): selectable in both modes, and the bookcase's
    ledge gradient uses the same numbers as the rows it sits under."""
    login(client, 'alice')
    assert client.post('/user/update_theme', json={'style': 'shelf', 'mode': 'dark'}).status_code == 200
    page = client.get('/base/index').get_data(as_text=True)
    assert 'data-style="shelf"' in page and 'data-mode="dark"' in page

    css = pathlib.Path('static/styles.css').read_text()
    case = css[css.index('/* ---- Shelf: the library grid as a bookcase'):]
    assert 'row-gap: var(--shelf-gap)' in case
    assert '--shelf-pitch: calc(var(--cover-h) + var(--ledge) + var(--shelf-gap))' in case
    assert 'padding-bottom: var(--ledge)' in case
    assert 'height: var(--cover-h)' in case
    # every shelf token has a dark value too
    assert css.count('--shelf-front: 80 54 34;') == 2


def test_font_choice_saved_and_on_the_page(client, db, people):
    """Font (Settings -> Account -> Appearance): saved per user, on <html data-font>,
    each choice has a CSS block and self-hosted OFL files; unknown is refused."""
    login(client, 'alice')
    page = client.get('/user/settings').get_data(as_text=True)
    assert 'data-font="theme"' in page and 'data-kind="font"' in page
    assert client.post('/user/update_theme', json={'font': 'comic-sans'}).status_code == 400
    assert client.post('/user/update_theme', json={'font': 'garamond'}).status_code == 200
    assert scalar(db, "SELECT font FROM users WHERE username = 'alice'") == 'garamond'
    assert 'data-font="garamond"' in client.get('/base/index').get_data(as_text=True)

    from models import FONTS
    css = pathlib.Path('static/styles.css').read_text()
    for key in FONTS:
        if key != 'theme':
            assert f':root[data-font="{key}"]' in css and f'.font-opt[data-value="{key}"]' in css, key
    for font in ('libre-baskerville', 'eb-garamond', 'literata', 'jost'):
        d = pathlib.Path('static/fonts') / font
        assert any(d.glob('*.woff2')) and (d / 'OFL.txt').is_file(), font
        assert f"/static/fonts/{font}/" in css, font


def test_shelf_style_reaches_every_cover_grid():
    """Shelf: the bookcase is a class, kept when the view switches, and on a
    friend's library too; House's heavy form outline leaves Shelf alone."""
    assert 'shelf-grid grid' in pathlib.Path('templates/_book_grid.html').read_text()
    # A friend's library is the same grid since 11.3
    assert "{% include '_book_grid.html' %}" in pathlib.Path('templates/friend_library.html').read_text()
    js = pathlib.Path('static/script.js').read_text()
    # switchView keeps shelf-grid and only drops .grid in list view
    assert "container.classList.toggle('grid', !list)" in js
    assert 'cover-stand' in pathlib.Path('templates/book_detail.html').read_text()
    css = pathlib.Path('static/styles.css').read_text()
    assert ':root:not([data-style="classic"]):not([data-style="shelf"]) :is(' in css
    assert '#book-container.grid' not in css


def test_shelf_covers_only_and_movie_rack(client, db, people):
    """Shelf: shelf.js is on every page; the bookcase shows covers only, the
    title and author visually hidden but there for screen readers, with a
    focus ring for the keyboard; the Movies grid can be a rack."""
    login(client, 'alice')
    page = client.get('/base/index').get_data(as_text=True)
    assert "static/shelf.js" in page
    assert 'class="book-title' in pathlib.Path('templates/_book_grid.html').read_text()  # still in the markup
    js = pathlib.Path('static/shelf.js').read_text()
    assert 'peek' not in js
    css = pathlib.Path('static/styles.css').read_text()
    hidden = css[css.index('No title label on the bookcase'):]
    hidden = hidden[:hidden.index('}')]
    assert 'clip: rect(0, 0, 0, 0)' in hidden and 'width: 1px' in hidden
    assert '.book-link:focus-visible :is(.cover-box, .no-cover)' in css
    assert '.book-info { opacity' not in css and 'peek' not in css
    start = css.index('/* ---- Shelf: the movie rack')
    end = css.find('/* ---- ', start + 1)                 # up to the next section
    rack = css[start:end if end > 0 else None]
    assert '.shelf-grid.grid[data-media="video"]' in rack
    assert '--shelf-frame' in rack
    # Every movie stands in the white case; a long title drops the director
    assert 'aspect-ratio: 5 / 8' in rack and '.no-cover-long .no-cover-author { display: none; }' in rack
    assert 'no-cover-long' in pathlib.Path('templates/_no_cover.html').read_text()
    assert 'no-cover-long' in pathlib.Path('static/common.js').read_text()


def test_shelf_boxes_and_the_rack_easter_egg(client, db, people):
    """Shelf: every grid cover is wrapped in .cover-box (a 3D box in the
    bookcase, display: contents elsewhere). The movie rack is opt-in: the egg
    button is on the Movies grid only, and every rack rule needs
    data-rack="store", which shelf.js sets before the first paint."""
    alice = people['alice']
    for media_type, fmt in (('video', 'VHS'), ('record', 'LP')):
        db.execute("INSERT INTO books (title, author, added_by, media_type, format) VALUES ('Heat', 'Mann', ?, ?, ?)",
                   (alice, media_type, fmt))
    add_book(db, alice, title='A Book')
    db.commit()
    login(client, 'alice')
    css = pathlib.Path('static/styles.css').read_text()
    assert '.cover-box { display: contents; }' in css
    # One cover component (16.0): the macro and its JS twin make the box, and
    # the grid (server-rendered and infinite scroll) goes through them
    assert '<span class="cover-box' in pathlib.Path('templates/_covers.html').read_text()
    assert '<span class="cover-box"><img' in pathlib.Path('static/common.js').read_text()
    assert 'cover_img(' in pathlib.Path('templates/_book_grid.html').read_text()
    assert 'coverBoxHtml(' in pathlib.Path('static/script.js').read_text()
    # The egg: Movies only
    assert 'data-click="toggleRack"' in client.get('/videos/').get_data(as_text=True)
    assert 'data-click="toggleRack"' not in client.get('/base/index').get_data(as_text=True)
    assert 'data-click="toggleRack"' not in client.get('/records/').get_data(as_text=True)
    # Every rule in the rack section is scoped to the toggle
    start = css.index('/* ---- Shelf: the movie rack')
    end = css.find('/* ---- ', start + 1)                 # up to the next section
    rack = css[start:end if end > 0 else None]
    selectors = [line for line in rack.splitlines() if line.lstrip().startswith(':root')]
    assert selectors and all('[data-rack="store"]' in line for line in selectors)
    # shelf.js runs in <head> without defer, so the rack doesn't flash in
    page = client.get('/videos/').get_data(as_text=True)
    tag = page[page.index('static/shelf.js') - 60:page.index('static/shelf.js') + 40]
    assert 'defer' not in tag
    js = pathlib.Path('static/shelf.js').read_text()
    assert "root.dataset.rack = 'store'" in js and 'toggleRack' in js


def test_no_cover_marks_long_titles(client, db, people):
    """_no_cover.html adds no-cover-long past 30 characters."""
    from flask import render_template_string
    with client.application.test_request_context():
        short = render_template_string("{% with title='Stalker', author='A' %}{% include '_no_cover.html' %}{% endwith %}")
        long = render_template_string("{% with title='The Good, the Bad and the Ugly!', author='A' %}{% include '_no_cover.html' %}{% endwith %}")
    assert 'no-cover-long' not in short and 'no-cover-long' in long


def test_search_box_carries_the_count_and_one_row_view_bar(client, db, people):
    """The search box says how many items there are ("Search your 2 books");
    searched or filtered, it doesn't, and the line under the box counts the
    matches. The view bar carries no count, so the sort menus keep the width."""
    from conftest import add_book
    alice = people['alice']
    add_book(db, alice, title='One')
    add_book(db, alice, title='Two')
    login(client, 'alice')
    page = client.get('/base/index').get_data(as_text=True)
    assert 'placeholder="Search your 2 books"' in page
    assert ' match' not in page[page.index('search-form-container'):page.index('class="view-bar')]
    page = client.get('/base/index?show=all').get_data(as_text=True)
    assert 'placeholder="Search your books"' in page
    assert '2 books match' in page[page.index('search-form-container'):page.index('class="view-bar')]
    assert '2 books' not in page[page.index('class="view-bar'):page.index('id="book-container"')]


def test_filter_pills_show_only_applied_filters(client, db, people):
    """ROADMAP 11.0: the panel's fields only filter on Apply, so the pills and
    the funnel's count come from the page as loaded, and a pending change
    shows on the Apply button instead of as a pill."""
    js = pathlib.Path('static/script.js').read_text()
    assert 'function countFilterChanges' in js and 'appliedFilters = readFilterState()' in js
    assert 'updateActiveFilters' not in js
    login(client, 'alice')
    page = client.get('/base/index').get_data(as_text=True)
    assert 'data-change="filtersChanged"' in page and 'id="apply-filters"' in page


def test_no_status_reads_unread(client, db, people):
    """11.0: no status is "Unread" (Unwatched, Not listened to), not Untracked."""
    from utils.media import media_labels
    assert [media_labels(t)['no_status'] for t in ('book', 'video', 'record')] == [
        'Unread', 'Unwatched', 'Not listened to']
    book = add_book(db, people['alice'], title='Never opened')
    login(client, 'alice')
    page = client.get(f'/books/book/{book}').get_data(as_text=True)
    assert '>Unread</option>' in page and 'Untracked' not in page


def test_status_filter_options_use_labels(client, db, people):
    """The Library's status filter shows "Did Not Finish", not the stored value."""
    book = add_book(db, people['alice'], title='Abandoned')
    db.execute("INSERT INTO collections (user_id, book_id, status) VALUES (?, ?, 'did not finish')",
               (people['alice'], book))
    db.commit()
    login(client, 'alice')
    page = client.get('/base/index').get_data(as_text=True)
    assert re.search(r'value="did not finish"[^>]*>\s*Did Not Finish', page)


def test_shelves_one_entry_and_section_switch(client, db, people):
    """ROADMAP 11.1: one Shelves entry in the sidebar; every Shelves page has
    the Books | Movies | Music switch, which keeps the scope; the sidebar link
    returns you to the section you used last."""
    login(client, 'alice')
    page = client.get('/base/index').get_data(as_text=True)
    nav = page[page.index('<!-- Navigation -->'):]
    nav = nav[:nav.index('</nav>')]
    assert 'href="/base/shelves"' in nav and 'Shelves' in nav
    assert 'href="/videos/"' not in nav and 'href="/records/"' not in nav   # no separate entries
    # The switch keeps the scope
    shared = client.get('/videos/shared').get_data(as_text=True)
    assert 'href="/base/shared-library"' in shared and 'href="/records/shared"' in shared
    assert 'href="/videos/friends"' not in shared        # no Friends' tab (11.3)
    for old in ('/base/friends-libraries', '/videos/friends', '/records/friends'):
        assert client.get(old).headers['Location'].endswith('/friends/'), old
    # A friend's books link to the same friend's movies and music
    friend = client.get('/base/library/carol').get_data(as_text=True)
    assert 'href="/videos/user/carol"' in friend and 'href="/records/user/carol"' in friend
    # Last section used: books at first, then whatever you visited
    client.delete_cookie('shelf_section')
    assert client.get('/base/shelves').headers['Location'].endswith('/base/index')
    client.get('/records/')
    assert client.get('/base/shelves').headers['Location'].endswith('/records/')
    client.get('/videos/shared')
    assert client.get('/base/shelves').headers['Location'].endswith('/videos/')
    # A bad cookie falls back to books
    client.set_cookie('shelf_section', 'nonsense')
    assert client.get('/base/shelves').headers['Location'].endswith('/base/index')


def test_shelf_records_stand_on_the_shelf():
    """The square-cover rule for records is keyed on #book-container, which
    outweighed the Shelf bookcase, so the Music shelf was a cover's width tall
    and lost its bottom ledge. The Shelf block restates the height at the
    same weight, after it."""
    css = pathlib.Path('static/styles.css').read_text()
    square = css.index('#book-container[data-media="record"] .book-cover {')
    fix = css.index(':root[data-style="shelf"] #book-container.shelf-grid.grid[data-media="record"] .book-cover {')
    assert fix > square
    assert 'height: var(--cover-h);' in css[fix:fix + 200]


def test_shelf_album_rows_are_as_tall_as_a_column_is_wide():
    """A square album is limited by its column's width, so the Music shelf's
    --cover-h is a column's width (container units on the grid's parent),
    with the column count per breakpoint, not books' fixed height."""
    css = pathlib.Path('static/styles.css').read_text()
    assert ':has(> :is(#book-container, .wishlist-grid).shelf-grid.grid[data-media="record"])' in css
    assert '--cover-h: round(down, var(--col-w), 1px);' in css
    for cols in ('--cols: 3;', '--cols: 4;', '--cols: 5;'):
        assert cols in css


def test_friends_page_and_notifications_under_the_welcome(client, db, people):
    """ROADMAP 11.3: Friends is a sidebar page of people, each opening their
    shelves (and the count per section); Notifications sits under the
    welcome with the number waiting."""
    add_book(db, people['carol'], title='Carols Book')
    db.execute("INSERT INTO friend_requests (sender_id, receiver_id, status) VALUES (?, ?, 'pending')",
               (people['bob'], people['carol']))
    db.commit()
    login(client, 'alice')
    page = client.get('/friends/').get_data(as_text=True)
    assert 'carol' in page and '1 book' in page
    assert 'href="/base/library/carol"' in page and 'href="/videos/user/carol"' in page
    assert 'bob' not in page.split('id="your-friends"')[1].split('Find friends')[0]   # household, not a friend
    assert 'id="friend-search-input"' in page and 'friends.js' in page
    # A friend's shelves: crumbs back to Friends, no scope tabs
    shelf = client.get('/base/library/carol').get_data(as_text=True)
    assert "carol's Shelves" in shelf and 'aria-label="Whose shelves"' not in shelf
    assert 'href="/friends/"' in shelf
    # Notifications: under the welcome, with a count when something waits
    login(client, 'carol')
    page = client.get('/friends/').get_data(as_text=True)
    head = page[page.index('Welcome,'):page.index('<!-- Navigation -->')]
    assert 'aria-label="Notifications, 1 waiting"' in head
    assert 'href="/user/settings"' in head               # the gear: Settings, for everyone (14c)
    nav = page[page.index('<!-- Navigation -->'):]
    nav = nav[:nav.index('</nav>')]
    assert 'notifications' not in nav and 'Settings' not in nav


def test_shelf_coverless_titles_break_between_words():
    """A coverless box on the bookcase prints its title at a size that
    follows the box (a size container, cqw type), and breaks lines between
    words: the base .no-cover's overflow-wrap: anywhere split "Fahrenheit"
    mid-word on a phone. The box's own padding mustn't use cqw (it would
    resolve against the page)."""
    css = (ROOT / 'static/styles.css').read_text()
    start = css.index('The printing on a coverless box')
    block = css[start:css.index('::before', start)]
    assert 'container-type: inline-size' in block
    assert 'overflow-wrap: break-word' in block and 'hyphens: auto' in block
    assert 'cqw' in block.split('.no-cover-title')[1]
    padding = [line for line in block.splitlines() if 'padding:' in line]
    assert padding and not any('cqw' in line for line in padding)


def test_profile_stats_same_blocks_for_every_type(client, db, people):
    """12.1: Overview | Insights on top, Books | Movies | Music under them
    (only the types the user has), the same blocks per type, and every type
    links to its grid: yours on your profile, the friend's on theirs."""
    from test_videos import add_video
    alice = people['alice']
    add_book(db, alice, 'Dune', 'Frank Herbert')
    add_video(db, alice)
    login(client, 'carol')                               # alice's friend
    page = client.get('/user/alice').get_data(as_text=True)
    stats = page[page.index('id="stats"'):]
    assert stats.count('data-stats-view=') == 2
    assert 'data-stats-kind="book"' in stats and 'data-stats-kind="video"' in stats
    assert 'data-stats-kind="record"' not in stats
    # One overview and one insights panel per type plus All (12.2), which
    # comes first and is the one shown
    assert stats.count('data-stats-panel') == 6
    assert stats.count(' hidden>') == 5
    assert 'data-stats-kind="all" aria-pressed="true"' in stats
    assert 'data-kind="all" data-view="overview">' in stats
    for words in ('Books owned', 'Movies and shows owned', 'Hours watched', 'Pages read', 'Top authors', 'Top directors'):
        assert words in stats
    assert 'href="/base/library/alice"' in stats and 'href="/videos/user/alice"' in stats
    assert 'tab-library' not in page                     # the old Library tab is gone


def test_appearance_card_and_two_mode_buttons(client, db, people):
    """12.4: Appearance is its own collapsible card, not part of Settings, and
    Mode is Light | Dark plus a "Follow system" link (hidden by CSS while
    following). 'system' stays the stored default and a valid choice."""
    login(client, 'alice')
    page = client.get('/user/settings').get_data(as_text=True)
    card = page[page.index('<details class="appearance-card'):]
    card = card[:card.index('</details>')]
    assert 'id="appearance-settings" data-theme-picker' in card
    assert '<details class="appearance-card bg-secondary rounded-xl card">' in page     # closed
    modes = re.findall(r'data-kind="mode" data-value="(\w+)"', card)
    assert sorted(modes) == ['dark', 'light', 'system'] and 'class="theme-opt follow-system' in card
    # The sidebar's shortcut is the sun/moon toggle (test_sidebar_has_the_mode_shortcut)
    sidebar = page[page.index('Welcome,'):page.index('auth/logout')]
    assert 'data-mode-toggle' in sidebar and 'data-kind="mode"' not in sidebar
    css = (ROOT / 'static/styles.css').read_text()
    assert ':root[data-mode="system"] .follow-system { display: none; }' in css
    js = (ROOT / 'static/sidebar.js').read_text()
    assert 'function syncModeButtons' in js and "prefers-color-scheme: dark" in js
    # Following the system is still a mode you can go back to
    assert client.post('/user/update_theme', json={'mode': 'dark'}).status_code == 200
    assert client.post('/user/update_theme', json={'mode': 'system'}).status_code == 200


def test_a_dead_avatar_link_shows_the_letter(client, db, people, static_root):
    """An avatar whose file is gone falls back to the letter placeholder on
    the server-rendered pages and in the friend search, instead of the
    browser's broken-image icon."""
    (static_root / 'uploads' / 'avatars').mkdir(parents=True)
    (static_root / 'uploads' / 'avatars' / 'carol.jpg').write_bytes(b'x')
    db.execute("UPDATE users SET avatar_url = 'uploads/avatars/gone.jpg' WHERE username = 'alice'")
    db.execute("UPDATE users SET avatar_url = 'uploads/avatars/carol.jpg' WHERE username = 'carol'")
    db.commit()
    login(client, 'alice')
    page = client.get('/friends/').get_data(as_text=True)
    assert 'uploads/avatars/carol.jpg' in page          # a file that's there still shows
    assert 'uploads/avatars/gone.jpg' not in page       # the sidebar's own avatar: the letter
    login(client, 'carol')
    found = {u['username']: u['avatar_url'] for u in client.get('/friends/search_users?q=ali').get_json()}
    assert found['alice'] is None


def test_dead_cover_links_get_the_placeholder_everywhere(client, db, people, static_root):
    """A cover whose file is gone is drawn as the title placeholder, like no
    cover at all, on every page that shows covers (and in the grid's
    infinite-scroll JSON), never as the browser's broken-image icon."""
    from conftest import add_book as put, add_review
    (static_root / 'uploads').mkdir()
    (static_root / 'uploads' / 'here.jpg').write_bytes(b'x')
    gone = put(db, people['alice'], title='Gone Book', cover='uploads/gone.jpg')
    put(db, people['alice'], title='Here Book', cover='uploads/here.jpg')
    add_review(db, people['alice'], gone)
    login(client, 'alice')
    for url in ('/base/index', f'/books/book/{gone}', f'/read/rate_review/{gone}',
                '/user/alice', '/reviews/?type=book', '/have/?q=Gone+Book'):
        page = client.get(url).get_data(as_text=True)
        assert 'uploads/gone.jpg' not in page, url
        assert 'no-cover' in page, url
    assert 'uploads/here.jpg' in client.get('/base/index').get_data(as_text=True)
    cards = client.get('/base/index?page=1', headers={'X-Requested-With': 'XMLHttpRequest'}).get_json()['books']
    covers = {c['title']: c['cover_image_url'] for c in cards}
    assert covers == {'Gone Book': None, 'Here Book': 'uploads/here.jpg'}


def test_item_page_cover_is_a_shelf_box(client, db, people, static_root):
    """The Shelf style draws the item page's cover as a 3D box (14c): the
    image sits in .cover-box and the stand says which kind of item it is."""
    import os
    from conftest import add_book, login
    os.makedirs(static_root / 'uploads', exist_ok=True)
    (static_root / 'uploads' / 'c.jpg').write_bytes(b'x')
    book = add_book(db, people['alice'], cover='uploads/c.jpg')
    login(client, 'alice')
    html = client.get(f'/books/book/{book}').get_data(as_text=True)
    assert 'class="cover-stand w-72 md:w-full max-w-[300px] mx-auto" data-media="book"' in html
    assert '<span class="cover-box"><img src="/static/uploads/c.jpg"' in html


def test_buttons_take_the_styles_corners():
    """.btn has no radius of its own: every button gets a rounded-* utility
    (radius tokens: rounded in OG and Shelf, square in Negative Earth and
    Outrun), and the crop tool and bulk edit use the tokens (ROADMAP 14c)."""
    import glob, re
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pat = re.compile(r'class(?:Name)?\s*=\s*["\']([^"\']*)["\']')
    missing = []
    for path in glob.glob(f'{root}/templates/**/*.html', recursive=True) + glob.glob(f'{root}/static/*.js'):
        for n, line in enumerate(open(path, encoding='utf-8'), 1):
            for classes in pat.findall(line):
                words = classes.split()
                if 'btn' in words and not any(w.startswith('rounded') for w in words) and '{{' not in classes:
                    missing.append(f'{os.path.relpath(path, root)}:{n}')
    assert missing == []
    css = open(f'{root}/static/styles.css', encoding='utf-8').read()
    assert '.bulk-sheet { border-radius: var(--r-xl)' in css
    assert '.crop-dialog .crop-stage, .crop-dialog .crop-panel { border-radius: var(--r-xl); }' in css


def _css_selectors(text):
    """Every rule's selectors in a stylesheet, whitespace-normalised."""
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.S)
    found, buf = set(), ''
    for ch in text:
        if ch == '{':
            sel = ' '.join(buf.split())
            if sel and not sel.startswith('@'):
                found |= {' '.join(part.split()) for part in sel.split(',')}
            buf = ''
        elif ch in '};':
            buf = ''
        else:
            buf += ch
    return found


def test_every_rule_in_styles_css_ships_in_output_css():
    """Tailwind drops a component rule whose class it can't find in the
    templates, and a class written as `no-cover-{{ size }}` can't be found:
    the small placeholder's rule had silently never shipped (14c). Every
    selector in styles.css must reach the committed output.css (safelist
    the class in tailwind.config.js, or run npm run build:css)."""
    src = _css_selectors((ROOT / 'static/styles.css').read_text())
    out = _css_selectors((ROOT / 'static/css/output.css').read_text())
    keyframe_steps = re.compile(r'^(from|to|[\d.]+%)$')
    assert sorted(s for s in src - out if not keyframe_steps.match(s)) == []


def test_one_cover_component(app):
    """Style pass (16.0): a cover picture's markup lives in cover_img()
    (_covers.html) and coverBoxHtml() (common.js) only, so a change to the
    cover reaches every page. The box carries a spare .cover-sheen layer,
    hidden unless a style turns it on, and every value is escaped."""
    with app.test_request_context():
        macro = app.jinja_env.get_template('_covers.html').module.cover_img
        html = str(macro('uploads/c.jpg', 'A <b> "title"', 'w-full', 'shrink-0', lazy=True, author='O\'Brien & co'))
    assert html.startswith('<span class="cover-box shrink-0"><img src="/static/uploads/c.jpg"')
    assert 'alt="A &lt;b&gt; &#34;title&#34;"' in html
    assert 'data-author="O&#39;Brien &amp; co"' in html
    assert 'loading="lazy"' in html and 'class="w-full"' in html
    assert html.endswith('<span class="cover-sheen" aria-hidden="true"></span></span>')
    css = pathlib.Path('static/styles.css').read_text()
    assert '.cover-sheen { display: none; }' in css
    # Nobody hand-writes the box any more
    for path in pathlib.Path('templates').rglob('*.html'):
        if path.name != '_covers.html':
            assert '<span class="cover-box' not in path.read_text(), path
    for path in pathlib.Path('static').glob('*.js'):
        if path.name != 'common.js':
            assert 'class="cover-box' not in path.read_text(), path


def test_item_add_and_edit_pages_have_one_heading_card(client, db, people):
    """Style pass (16.0): the item page's title and the Add and Edit pages'
    headings are heading cards above the page's cards (in Shelf, a small
    bookcase), one per page, made by heading_card() like every other page."""
    alice = people['alice']
    book = add_book(db, alice, title='Dune')
    db.commit()
    login(client, 'alice')
    for url in (f'/books/book/{book}', '/books/add', '/videos/add', '/records/add',
                '/wishlist/add?type=book', f'/books/edit/{book}'):
        page = client.get(url).get_data(as_text=True)
        assert page.count('class="page-heading ') == 1, url
    item = client.get(f'/books/book/{book}').get_data(as_text=True)
    # the title is in the heading card, before the details card
    heading = item.index('class="page-heading ')
    assert heading < item.index('<h1', heading) < item.index('Dune', heading) < item.index('case-card', heading)


def test_shelf_site_title_stays_cream():
    """Shelf's walnut headings (16.0 step 3) must not reach the site title on
    the wooden top bar, which is one cream in both modes (Phil, 2026-11-13)."""
    css = pathlib.Path('static/styles.css').read_text()
    assert ':is(.font-display.text-content-primary, .no-cover):not(.site-title)' in css
    assert ':root[data-style="shelf"] .topbar .site-title { color: rgb(245 232 206); }' in css


def test_feed_card_layout(client, db, people):
    """Style pass (16.0): an activity card is a small grid (cover, activity,
    like row), the like row in the layout instead of pinned in a corner, and
    in Shelf the cover stands on the case's ledge."""
    feed = pathlib.Path('templates/activity_feed.html').read_text()
    assert 'class="feed-row"' in feed and 'feed-main' in feed and 'feed-actions' in feed
    assert 'absolute bottom-6 right-6' not in feed and 'pb-16' not in feed
    css = pathlib.Path('static/styles.css').read_text()
    assert 'grid-template-areas: "cover main" "cover actions";' in css
    assert 'grid-template-areas: "main main" "cover actions";' in css     # phone
    assert ':root[data-style="shelf"] .feed-card .feed-cover {\n    align-self: end;' in css


def test_stacked_shelves_in_one_bookcase(client, db, people):
    """Style pass (16.0): Reviews and Collections set their rows of covers in
    one bookcase (.shelf-case round _shelf_rows.html). Every shelf has its
    row, empty when it has no covers: hidden in the other styles, a bare
    ledge in Shelf's case. Making a collection is a tool, so it has its own
    card, outside the case."""
    login(client, 'alice')
    for url in ('/reviews/', '/collections/collections'):
        page = client.get(url).get_data(as_text=True)
        assert 'class="shelf-case ' in page, url
        assert 'shelf-item' in page and 'shelf-link' in page and 'shelf-label' in page, url
    page = client.get('/collections/collections').get_data(as_text=True)
    case = page.index('class="shelf-case ')
    assert page.index('name="name"') > page.index('</section>', case)      # the form is after the case
    assert 'Create collection' in page and 'Create Shelf' not in page      # UI: shelf = what you own
    css = pathlib.Path('static/styles.css').read_text()
    assert '.shelf-row:empty { display: none; }' in css
    assert ':root[data-style="shelf"] .shelf-case .shelf-row:empty {' in css
    assert "background-attachment: local, local, local, local, local, local, local, scroll, scroll;" in css
    assert "overscroll-behavior-x: none;" in css          # no rubber-band past the last cover
    # The case's inside left panel, with each ledge running back into it;
    # the row's piece stays put (positioned outside the scroller) over the covers
    assert ':root[data-style="shelf"] .shelf-case .shelf-row::after {' in css
    assert ':root[data-style="shelf"] .shelf-case .shelf-item { position: relative; }' in css


def test_wishlists_are_the_library_grid_with_a_quick_add(client, db, people):
    """16.0 step 7: your wishlist and a friend's share one card
    (_wishlist_card.html) and the library grid's hooks, so the Shelf style
    draws each section as the library's bookcase. Yours has the round (+)
    on the cover (a POST to move_to_library, named for screen readers) as
    well as the card's button; a friend's has shop searches and no (+)."""
    book = add_book(db, people['carol'], title='Wanted Book')
    db.execute('INSERT INTO wishlist (user_id, book_id, notes) VALUES (?, ?, ?)', (people['carol'], book, 'gift'))
    db.commit()
    login(client, 'carol')
    page = client.get('/wishlist/view').get_data(as_text=True)
    assert 'class="wishlist-grid shelf-grid grid ' in page and 'data-media="book"' in page
    assert 'wishlist-item book-item' in page and 'class="book-info ' in page
    quick = page.index('class="wishlist-quick-add"')
    action = f'action="/wishlist/move_to_library/{book}"'
    assert page.rfind(action, 0, quick) > page.index('class="cover-anchor"')   # on the cover
    assert 'aria-label="Add Wanted Book to your Library"' in page
    assert page.count(action) == 2                                          # the (+) and the button

    login(client, 'alice')                                                   # carol's friend
    page = client.get('/wishlist/user/carol').get_data(as_text=True)
    assert 'class="wishlist-grid shelf-grid grid ' in page and 'wishlist-item book-item' in page
    assert 'page-heading' in page and '?wishlist_owner=carol' in page
    assert 'wishlist-quick-add' not in page and 'move_to_library' not in page
    assert 'bookshop.org' in page                                            # media.buy_links

    css = pathlib.Path('static/styles.css').read_text()
    # The Movies rack easter egg stays on the library grid, not the wishlist's
    assert not re.search(r'\[data-rack="store"\][^{]*?(?<!#book-container)\.shelf-grid', css)
    assert ':root[data-style="shelf"] .shelf-grid.grid .wishlist-quick-add {' in css
    assert '.wishlist-quick-add { display: none; }' in css
    # A coverless item two links deep gets its own width (iPhone Safari: spine only)
    assert ':root[data-style="shelf"] .wishlist-grid.shelf-grid.grid .no-cover {' in css


def test_one_page_frame_and_cases_inside_it():
    """16.0 (Phil, 2026-11-13: headings, grids and pages one width): wide
    pages share .page-frame (no hand-written max-w-7xl gutters, no
    Tailwind `container`, no padding on <body> pushing a page further in),
    and in Shelf every case keeps its right face inside the frame, as the
    grid does, so a heading case and the grid under it end together."""
    templates = pathlib.Path('templates')
    for path in templates.glob('*.html'):
        src = path.read_text()
        assert 'max-w-7xl mx-auto px-4 sm:px-6 lg:px-8' not in src, path
        assert not re.search(r'block body_class %\}[^{]*\bp-6\b', src), path
        if path.name != '_empty_state.html':
            assert 'container mx-auto' not in src, path
    css = pathlib.Path('static/styles.css').read_text()
    assert '@apply max-w-7xl mx-auto px-4 sm:px-6 lg:px-8;' in css
    assert css.count('margin-right: var(--case-run);') >= 2      # small cases, stacked shelves (the grid has its own)


def test_case_headings_stand_outside_the_bookcase(client, db, people):
    """Collections has no visible headings inside its case (screen readers
    keep them); the profile's headings sit above their bookcases."""
    login(client, 'alice')
    page = client.get('/collections/collections').get_data(as_text=True)
    assert '<h2 id="status-shelves" class="sr-only">' in page
    assert '<h2 id="custom-shelves" class="sr-only">' in page
    assert 'shelf-case-heading' not in page
    css = pathlib.Path('static/styles.css').read_text()
    assert 'shelf-case-heading' not in css
    assert ':root[data-style="shelf"] .case-wrap {' in css
    src = pathlib.Path('templates/user.html').read_text()
    assert src.count('class="case-wrap ') == 2 and 'shelf-case-heading' not in src

"""Page layout regressions (Phase 7): broken nesting, grid columns, phone widths.

The visual checks (light/dark, House/Classic, 390px and desktop) are done in a
headless browser; these tests pin the specific causes found that way."""
import os
import pathlib
import re
from html.parser import HTMLParser
from unittest import mock

import pytest

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
    r = client.get(f'/books/{book}')
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
    html = client.get('/books/').get_data(as_text=True)
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


def test_short_screen_sidebar_clears_the_top_bar_and_fills_the_drawer():
    """16.0 (Phil, 2026-11-13): on a phone-height screen the compact sidebar
    put the avatar 2px under the 4rem top bar and ended 170px short. The
    avatar's top (.75rem padding + its margin) clears the bar by 20px, the
    rows grow with the height, and the breakpoint covers the tall layout's
    770px. Measured in a browser at 600-844px tall; this guards the numbers."""
    css = (ROOT / 'static/styles.css').read_text()
    block = css[css.index('@media (max-height: 800px)'):]
    block = block[:block.index('\n}\n')]
    assert 'margin-top: 4.5rem' in block                       # 12px + 72px = 64px bar + 20px
    assert '#sidebar .nav-link { padding: var(--side-row) .75rem; }' in block
    assert 'clamp(.3rem, calc(.4rem + (100dvh - 627px) / 18), .75rem)' in block
    assert '@media (max-height: 760px)' not in css


def test_book_page_cover_has_no_film_frame(client, db, people):
    """The 7.1 film frame came off books (Phil, 2026-11-05). Its CSS is parked
    in docs/parked/film-frame.css for VHS/DVD, not loaded by the app."""
    book = add_book(db, people['bob'], 'Dune', 'Frank Herbert')
    login(client, 'bob')
    html = client.get(f'/books/{book}').get_data(as_text=True)
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
    pages = ['/books/', '/books/add', f'/books/edit/{book}', f'/books/{book}', '/wishlist/view',
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
    assert 'Your library is empty' in text('/books/') and '/user/import_goodreads_page' in text('/books/')
    assert 'No books match these filters' in text('/books/?genre=Nope')
    page = text('/books/?search_term=zzzz')                 # the grid searches itself (16.0)
    assert 'No books on your shelf match &#34;zzzz&#34;' in page and 'Clear the search' in page
    assert 'Your wishlist is empty' in text('/wishlist/view')
    feed = text('/feed/activity')
    assert 'Nothing in your feed yet' in feed and 'Find friends' not in feed   # link removed 2026-11-07

    add_book(db, people['carol'], 'Dune', 'Frank Herbert')
    assert 'Your library is empty' not in text('/books/') and 'Dune' in text('/books/')


def test_a_search_hidden_by_filters_says_so(client, db, people):
    """Phil, 2026-11-19: "Infinite jest" with From: Goodreads on said "No
    books on your shelf match", though the book was on it; the household's
    shelves drew an empty bookcase instead of anything. Both pages now say
    when it's the filters, with a link that keeps the search and drops them."""
    add_book(db, people['alice'], 'Dune', 'Frank Herbert')
    login(client, 'alice')
    text = lambda url: ' '.join(client.get(url).get_data(as_text=True).split())
    for home, whose in (('/books/', 'your shelf'), ('/books/shared', 'the household&#39;s shelves')):
        page = text(home + '?search_term=Dune&genre=Nope')
        assert 'No books match &#34;Dune&#34; with these filters' in page, home
        assert f'href="{home}?search_term=Dune"' in page and 'Clear the filters' in page, home
        assert 'Dune' in text(home + '?search_term=Dune')       # without the filter it's there
        page = text(home + '?search_term=zzzz')
        assert f'No books on {whose} match &#34;zzzz&#34;' in page and 'Clear the search' in page, home
        assert 'No books match these filters' in text(home + '?genre=Nope'), home


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
    for url in ('/books/', f'/books/{book}'):
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

    page = client.get('/books/?show_removed=include&sort_by=publish_year').get_data(as_text=True)
    bar = page[page.index('class="view-bar'):]
    bar = bar[:bar.index('id="book-container"')]
    assert 'action="/books/"' in bar and 'id="grid-view-btn"' in bar
    assert '<input type="hidden" name="show_removed" value="include">' in bar
    assert 'name="sort_by" value=' not in bar                  # the selects carry the sort
    assert 'Oldest first' in bar and 'A–Z' not in bar           # a year isn't A–Z
    assert 'book' not in re.sub(r'"/books/[^"]*"', '', bar).replace('book-container', '').replace('Select', '')   # the count isn't in the bar

    dropdown = page[page.index('search-form-container'):page.index('class="view-bar')]
    assert 'id="sort-form"' not in dropdown and 'grid-view-btn' not in dropdown
    assert '1 book matches' in dropdown                          # it is under the search box

    shared = client.get('/books/shared?member=%d' % people['bob']).get_data(as_text=True)
    sort_form = shared[shared.index('id="sort-form"') - 80:]
    assert 'action="/books/shared"' in sort_form[:200]
    assert '<input type="hidden" name="member" value="%d">' % people['bob'] in sort_form
    assert 'action="/books/shared"' in shared[shared.index('id="filter-form"') - 10:][:200]

    search = client.get('/books/shared?search_term=dune').get_data(as_text=True)
    filter_form = search[search.index('id="filter-form"'):]
    assert 'action="/books/shared"' in filter_form[:100]
    assert '<input type="hidden" name="search_term" value="dune">' in filter_form
    # ...and a new search keeps the filters, sort and members in view (16.0)
    filtered = client.get('/books/shared?genre=Fiction&sort_by=author&member=%d' % people['bob']).get_data(as_text=True)
    box = filtered[filtered.index('role="search"') - 200:filtered.index('id="search_term"')]
    assert 'action="/books/shared"' in box
    for kept in ('name="genre" value="Fiction"', 'name="sort_by" value="author"', 'name="member" value="%d"' % people['bob']):
        assert kept in box, kept

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
    for url in ('/books/', '/books/shared', '/videos/', '/records/shared'):
        page = client.get(url).get_data(as_text=True)
        assert 'id="search-toggle"' not in page, url
        tabs = page.index('class="tab ')
        row = page.index('search-form-container')
        assert tabs < row, url
        assert 'id="filter-toggle"' in page and 'aria-controls="filter-panel"' in page, url
    search = client.get('/books/shared?search_term=x').get_data(as_text=True)
    assert 'search-form-container' in search and 'pt-20' in search
    wishlist = client.get('/wishlist/view').get_data(as_text=True)
    assert 'id="search-toggle"' not in wishlist


def test_accent_colour_is_saved_and_on_every_page(client, db, people):
    """8B.5: Settings -> Account -> Appearance -> Accent. Saved per user, put on <html
    data-accent>, House style only (the picker hides under Classic)."""
    login(client, 'bob')
    assert 'data-accent="green"' in client.get('/books/').get_data(as_text=True)
    page = client.get('/user/settings').get_data(as_text=True)
    assert 'data-accent-picker' in page and page.count('data-kind="accent"') == 7
    r = client.post('/user/update_theme', json={'accent': 'blue'})
    assert r.status_code == 200 and r.get_json()['accent'] == 'blue'
    assert db.execute('SELECT accent FROM users WHERE id = ?', (people['bob'],)).fetchone()[0] == 'blue'
    assert 'data-accent="blue"' in client.get('/books/').get_data(as_text=True)
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
    page = client.get(f'/books/{book}').get_data(as_text=True)
    # The section crumb is marked for common.js, which points it at the
    # grid you were last on (sort and filters kept)
    assert '<a href="/books/" class="crumb-link" data-grid-crumb="book">Library</a>' in page
    assert '<li aria-current="page" class="crumb-here">Dune</li>' in page


def test_library_grids_are_remembered_for_the_crumb(client, db, people):
    """The four library grids carry data-remember-grid (common.js saves
    their address per media type for the tab); a collection's grid doesn't,
    so the Library crumb never leads there."""
    add_book(db, people['alice'], title='Dune')
    add_book(db, people['carol'], title='Emma')     # a friend's grid shows only with books
    for media in ('video', 'record'):                 # likewise Movies and Music
        db.execute("INSERT INTO books (title, author, added_by, media_type) VALUES ('X', 'Y', ?, ?)",
                   (people['alice'], media))
    db.commit()
    login(client, 'alice')
    for url in ('/books/', '/books/shared', '/books/user/carol', '/videos/', '/records/'):
        page = client.get(url).get_data(as_text=True)
        assert 'data-remember-grid' in page, url
    js = pathlib.Path('static/common.js').read_text()
    assert "a[data-grid-crumb]" in js and 'sessionStorage' in js


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
    assert re.search(r'src="/static/logos/tmdb\.svg\?v=\w+"', page) and 'not endorsed or certified by TMDB' in page
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
    assert 'color:rgb(var(--accent-text)/var(--tw-text-opacity,1))' in built.replace(' ', '')
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


def test_cyberpunk_style_is_dark_only_with_outruns_fonts(client, db, people):
    """Cyberpunk (forked from Outrun, Phil 2026-11-18): selectable, dark only
    with Outrun's fixed fonts (Mode and Font pickers hidden, the same note),
    every accent's Gruvbox bright shade, and none of Outrun's scenery."""
    login(client, 'alice')
    assert client.post('/user/update_theme', json={'style': 'cyberpunk'}).status_code == 200
    page = client.get('/user/settings').get_data(as_text=True)
    assert 'data-style="cyberpunk"' in page and 'data-outrun-note' in page

    css = pathlib.Path('static/styles.css').read_text()
    assert 'html:root[data-style="cyberpunk"] {' in css          # outranks House dark blocks
    for key in ('baskerville', 'garamond', 'literata', 'jost'):
        assert f':root[data-font="{key}"]:not([data-style="outrun"]):not([data-style="cyberpunk"])' in css
    assert ':root[data-style="cyberpunk"] :is([data-mode-picker], [data-font-picker])' in css
    assert ':root:is([data-style="outrun"], [data-style="cyberpunk"]) [data-outrun-note]' in css
    for name in ('aqua', 'blue', 'purple', 'orange', 'red', 'yellow', 'green'):
        rule = re.search(r'\[data-swatch="' + name + r'"\]\s*\{([^}]*)\}', css).group(1)
        assert '--acc-c:' in rule and '--acc-ch:' in rule, name
    cyber = re.search(r'html:root\[data-style="cyberpunk"\] \{([^}]*)\}', css).group(1)
    assert '--accent: var(--acc-c,' in cyber and '--cp-alert:' in cyber
    # Outrun's look stays Outrun's: no sky, grid, sunset or neon in Cyberpunk
    assert '--neon-' not in cyber
    assert not re.search(r'data-style="cyberpunk"\][^{]*body::(before|after)[^{]*\{[^}]*perspective', css)


def test_shelf_style_bookcase(client, db, people):
    """Shelf (10.1 light pass): selectable in both modes, and the bookcase's
    ledge gradient uses the same numbers as the rows it sits under."""
    login(client, 'alice')
    assert client.post('/user/update_theme', json={'style': 'shelf', 'mode': 'dark'}).status_code == 200
    page = client.get('/books/').get_data(as_text=True)
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
    assert 'data-font="garamond"' in client.get('/books/').get_data(as_text=True)

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
    assert 'cover-stand' in pathlib.Path('templates/_item_heading.html').read_text()
    css = pathlib.Path('static/styles.css').read_text()
    assert ':root:not([data-style="classic"]):not([data-style="shelf"]):not([data-style="cyberpunk"]) :is(' in css
    assert '#book-container.grid' not in css


def test_shelf_covers_only_and_movie_rack(client, db, people):
    """Shelf: shelf.js is on every page; the bookcase shows covers only, the
    title and author visually hidden but there for screen readers, with a
    focus ring for the keyboard; the Movies grid can be a rack."""
    login(client, 'alice')
    page = client.get('/books/').get_data(as_text=True)
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
    assert '<span class="cover-box"${boxAttrsHtml({ media, format, faces })}><img' in pathlib.Path('static/common.js').read_text()
    assert 'cover_img(' in pathlib.Path('templates/_book_grid.html').read_text()
    assert 'coverBoxHtml(' in pathlib.Path('static/script.js').read_text()
    # The egg: Movies only
    assert 'data-click="toggleRack"' in client.get('/videos/').get_data(as_text=True)
    assert 'data-click="toggleRack"' not in client.get('/books/').get_data(as_text=True)
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
    page = client.get('/books/').get_data(as_text=True)
    assert 'placeholder="Search your 2 books"' in page
    assert ' match' not in page[page.index('search-form-container'):page.index('class="view-bar')]
    page = client.get('/books/?show=all').get_data(as_text=True)
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
    page = client.get('/books/').get_data(as_text=True)
    assert 'data-change="filtersChanged"' in page and 'id="apply-filters"' in page


def test_no_status_reads_unread(client, db, people):
    """11.0: no status is "Unread" (Unwatched, Not listened to), not Untracked."""
    from utils.media import media_labels
    assert [media_labels(t)['no_status'] for t in ('book', 'video', 'record')] == [
        'Unread', 'Unwatched', 'Not listened to']
    book = add_book(db, people['alice'], title='Never opened')
    login(client, 'alice')
    page = client.get(f'/books/{book}').get_data(as_text=True)
    assert 'name="status" value="untracked" class="chip"' in page and '>Unread</button>' in page and 'Untracked' not in page


def test_status_filter_options_use_labels(client, db, people):
    """The Library's status filter shows "Did Not Finish", not the stored value."""
    book = add_book(db, people['alice'], title='Abandoned')
    db.execute("INSERT INTO collections (user_id, book_id, status) VALUES (?, ?, 'did not finish')",
               (people['alice'], book))
    db.commit()
    login(client, 'alice')
    page = client.get('/books/').get_data(as_text=True)
    assert re.search(r'value="did not finish"[^>]*>\s*Did Not Finish', page)


def test_shelves_one_entry_and_section_switch(client, db, people):
    """ROADMAP 11.1: one Shelves entry in the sidebar; every Shelves page has
    the Books | Movies | Music switch, which keeps the scope; the sidebar link
    returns you to the section you used last."""
    login(client, 'alice')
    page = client.get('/books/').get_data(as_text=True)
    nav = page[page.index('<!-- Navigation -->'):]
    nav = nav[:nav.index('</nav>')]
    assert 'href="/base/shelves"' in nav and 'Shelves' in nav
    assert 'href="/videos/"' not in nav and 'href="/records/"' not in nav   # no separate entries
    # The switch keeps the scope
    shared = client.get('/videos/shared').get_data(as_text=True)
    assert 'href="/books/shared"' in shared and 'href="/records/shared"' in shared
    assert 'href="/videos/friends"' not in shared        # no Friends' tab (11.3)
    for old in ('/base/friends-libraries', '/videos/friends', '/records/friends'):
        assert client.get(old).headers['Location'].endswith('/friends/'), old
    # A friend's books link to the same friend's movies and music
    friend = client.get('/books/user/carol').get_data(as_text=True)
    assert 'href="/videos/user/carol"' in friend and 'href="/records/user/carol"' in friend
    # Last section used: books at first, then whatever you visited
    client.delete_cookie('shelf_section')
    assert client.get('/base/shelves').headers['Location'].endswith('/books/')
    client.get('/records/')
    assert client.get('/base/shelves').headers['Location'].endswith('/records/')
    client.get('/videos/shared')
    assert client.get('/base/shelves').headers['Location'].endswith('/videos/')
    # A bad cookie falls back to books
    client.set_cookie('shelf_section', 'nonsense')
    assert client.get('/base/shelves').headers['Location'].endswith('/books/')


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
    card = page[page.index('data-friend="'):]
    card = card[:card.index('data-friend-shelf')+200]
    # 16.0: avatar and name open the profile, "See their shelf" the shelves,
    # and the counts are plain text
    assert card.count('href="/user/carol"') == 2 and 'href="/books/user/carol"' in card
    counts = card[card.index('data-friend-counts'):card.index('</p>', card.index('data-friend-counts'))]
    assert '<a ' not in counts and '1 book' in counts
    assert 'bob' not in page.split('id="your-friends"')[1].split('Find friends')[0]   # household, not a friend
    assert 'id="friend-search-input"' in page and 'friends.js' in page
    # A friend's shelves: crumbs back to Friends, no scope tabs
    shelf = client.get('/books/user/carol').get_data(as_text=True)
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
    assert 'href="/books/user/alice"' in stats and 'href="/videos/user/alice"' in stats
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
    for url in ('/books/', f'/books/{gone}', f'/read/rate_review/{gone}',
                '/user/alice', '/reviews/?type=book', '/have/?q=Gone+Book'):
        page = client.get(url).get_data(as_text=True)
        assert 'uploads/gone.jpg' not in page, url
        assert 'no-cover' in page, url
    assert 'uploads/here.jpg' in client.get('/books/').get_data(as_text=True)
    cards = client.get('/books/?page=1', headers={'X-Requested-With': 'XMLHttpRequest'}).get_json()['books']
    covers = {c['title']: c['cover_image_url'] for c in cards}
    assert covers == {'Gone Book': None, 'Here Book': 'uploads/here.jpg'}


def test_item_page_cover_is_a_shelf_box(client, db, people, static_root):
    """The Shelf style draws the item page's cover as a 3D box (14c): the
    image sits in .cover-box, which says which kind of item it is (layout
    walk step 1: the box, not the stand)."""
    import os
    from conftest import add_book, login
    os.makedirs(static_root / 'uploads', exist_ok=True)
    (static_root / 'uploads' / 'c.jpg').write_bytes(b'x')
    book = add_book(db, people['alice'], cover='uploads/c.jpg')
    login(client, 'alice')
    html = client.get(f'/books/{book}').get_data(as_text=True)
    assert 'class="cover-stand w-full">' in html
    # In the heading, beside the title (Phil, 2026-11-19); the facts under it
    assert html.index('class="item-heading-grid"') < html.index('class="cover-stand') < html.index('class="item-facts ')
    assert '<span class="cover-box" data-media="book" data-format=""><img src="/static/uploads/c.jpg"' in html


def test_item_page_cover_opens_bigger(client, db, people, static_root):
    """A tap on the item page's cover shows it bigger in a dialog (16.0,
    Phil 2026-11-13); a method=dialog form closes it without JS. No
    picture, no dialog: the placeholder isn't worth enlarging."""
    import os
    from conftest import add_book, login
    os.makedirs(static_root / 'uploads', exist_ok=True)
    (static_root / 'uploads' / 'c.jpg').write_bytes(b'x')
    with_cover = add_book(db, people['alice'], cover='uploads/c.jpg')
    without = add_book(db, people['alice'], title='No Cover')
    login(client, 'alice')
    html = client.get(f'/books/{with_cover}').get_data(as_text=True)
    # openCover (book_detail.js): the zoom, unless there's a gallery or (in
    # the Shelf style) the photos for the 3D view; a cover alone has neither
    assert 'data-click="openCover" data-target="cover-zoom"' in html
    assert '<dialog id="item-3d"' not in html and '<dialog id="photo-gallery"' not in html
    dialog = html[html.index('<dialog id="cover-zoom"'):]
    dialog = dialog[:dialog.index('</dialog>')]
    assert '<form method="dialog">' in dialog and 'src="/static/uploads/c.jpg"' in dialog
    html = client.get(f'/books/{without}').get_data(as_text=True)
    assert 'cover-zoom' not in html and 'item-3d' not in html


def test_shelf_chips_recessed_until_chosen():
    """Shelf style (Phil, 2026-11-13): an unchosen chip is a well (inset
    shadow), the chosen one raised in the accent like the Shelf .btn."""
    import pathlib
    css = pathlib.Path('static/styles.css').read_text()
    well = css[css.index(':root[data-style="shelf"] .chip {'):]
    assert 'box-shadow: inset 0 2px' in well[:well.index('}')]
    chosen = css[css.index(':root[data-style="shelf"] .chip[aria-pressed="true"] {'):]
    chosen = chosen[:chosen.index('}')]
    assert 'rgb(var(--accent))' in chosen and 'var(--sh-sm)' in chosen


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


def _selector_form(sel):
    """One selector as both the source and the minified build write it
    (16.0g: output.css is minified): no space around > + ~, attribute
    values unquoted where they can be, ::before / ::after as :before /
    :after, and "  " as " "."""
    sel = ' '.join(sel.split())
    sel = re.sub(r'\s*([>+~])\s*', r'\1', sel)
    sel = re.sub(r'="([\w-]+)"\]', r'=\1]', sel)
    sel = re.sub(r'\(\s+', '(', sel)
    sel = sel.replace(':nth-child(1)', ':first-child').replace(':nth-child(even)', ':nth-child(2n)')
    return re.sub(r'::(before|after|placeholder|selection|marker)', r':\1', sel)


def _css_selectors(text):
    """Every rule's selectors in a stylesheet, normalised (_selector_form)."""
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.S)
    found, buf = set(), ''
    for ch in text:
        if ch == '{':
            sel = ' '.join(buf.split())
            if sel and not sel.startswith('@'):
                found |= {_selector_form(part) for part in sel.split(',')}
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
    for url in (f'/books/{book}', '/books/add', '/videos/add', '/records/add',
                '/wishlist/add?type=book', f'/books/edit/{book}'):
        page = client.get(url).get_data(as_text=True)
        assert page.count('class="page-heading ') == 1, url
    item = client.get(f'/books/{book}').get_data(as_text=True)
    # the cover and the title are in the heading card, before the details card
    heading = item.index('class="page-heading ')
    assert heading < item.index('cover-stand', heading) < item.index('<h1', heading) < item.index('<span data-fit-title-text>Dune', heading) < item.index('item-facts')


def test_shelf_site_title_stays_cream():
    """Shelf's walnut headings (16.0 step 3) must not reach the site title on
    the wooden top bar, which is one cream in both modes (Phil, 2026-11-13)."""
    css = pathlib.Path('static/styles.css').read_text()
    assert ':is(.font-display.text-content-primary, .no-cover):not(.site-title)' in css
    assert ':root[data-style="shelf"] .topbar .site-title { color: rgb(245 232 206); }' in css


def test_feed_card_layout(client, db, people):
    """Style pass (16.0, Phil 2026-11-13): an activity card is the Reviews
    list's card: cover left, title, creator, one line of rating / who did
    what / when, the review clamped, then the like (no corner-pinned like,
    no card grid of its own)."""
    feed = pathlib.Path('templates/activity_feed.html').read_text()
    reviews = pathlib.Path('templates/reviews_list.html').read_text()
    card = 'bg-secondary rounded-lg p-4 card flex gap-4 min-w-0'
    assert card in feed and card in reviews
    assert 'feed-row' not in feed and 'absolute bottom-6 right-6' not in feed and 'pb-16' not in feed
    assert "'w-20 max-h-32 object-contain rounded shadow-sm'" in feed
    assert 'feed-row' not in pathlib.Path('static/styles.css').read_text()


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
    # No framed bottom under the last shelf (it read as a second shelf); a
    # case that ends with Collections' note gets a bare ledge to stand on
    case = css[css.index(':root[data-style="shelf"] .shelf-case {'):]
    assert 'border-bottom-width: 0;' in case[:case.index('}')]
    assert '<div class="shelf-row mt-4"></div>' in pathlib.Path('templates/collections.html').read_text()
    src = pathlib.Path('templates/user.html').read_text()
    # Collections, Wishlist and Borrowed (16.0d)
    assert src.count('class="case-wrap ') == 3 and 'shelf-case-heading' not in src


def test_have_matches_are_feed_cards(client, db, people):
    """Layout walk 16.0 step 6 (Phil): Do I Have This? matches are the
    feed's card (they were small bookcases in Shelf), the whole card one
    link, the cover a box for its item."""
    add_book(db, people['alice'], title='Dune', cover='uploads/x.jpg')
    login(client, 'alice')
    page = client.get('/have/?q=dune').get_data(as_text=True)
    assert 'case-card' not in page and 'case-cover' not in page
    match = re.search(r'<a href="/books/\d+" class="feed-card [^"]*card-link[^"]*">(.*?)</a>', page, re.S)
    assert match and 'data-media="book"' in match.group(1) and 'Dune' in match.group(1)


def test_have_album_covers_are_square(client, db, people):
    """An album's cover in Do I Have This? is square, not squeezed into a
    book's slot (Phil, 2026-11-13): the picture keeps its own shape
    (object-contain), the placeholder is w-20 h-20."""
    from test_records import add_record
    add_record(db, people['alice'], title='Mule', artist='Orville Peck')
    login(client, 'alice')
    page = client.get('/have/?q=mule').get_data(as_text=True)
    match = page[page.index('class="feed-card '):]
    match = match[:match.index('</a>')]
    assert re.search(r'class="no-cover [^"]*\bh-20 w-20\b', match)


def test_infinite_scroll_finds_the_grid_by_data_not_layout_classes():
    """The grid's paging state lives on its wrapper (data-current-page);
    script.js found it as `.container[data-current-page]`, so swapping the
    wrapper's width class for .page-frame (16.0) stopped the grid at its
    first page. Find it by the data attribute only."""
    js = pathlib.Path('static/script.js').read_text()
    assert "document.querySelector('[data-current-page]')" in js
    assert not re.search(r"querySelector\('\.[\w-]+\[data-current-page\]", js)
    assert 'data-current-page=' in pathlib.Path('templates/_book_grid.html').read_text()


def test_cover_glare_feed_dates_and_search_crumbs(client, db, people):
    """16.0 steps 9-10: Shelf lays a still glare over every cover (the
    .cover-sheen layer, with --sheen-shift for a tilt to drive later); the
    feed shows days, not timestamps (F13); a search keeps its page's
    heading above the search row (F11; since 16.0 the grid itself)."""
    css = pathlib.Path('static/styles.css').read_text()
    rule = css[css.index(':root[data-style="shelf"] .cover-sheen {'):]
    rule = rule[:rule.index('}')]
    assert 'display: block;' in rule and 'var(--sheen-shift, 0%)' in rule and 'pointer-events: none;' in rule
    assert '.cover-sheen { display: none; }' in css                     # every other style
    assert '{{ activity.date[:10] }}' in pathlib.Path('templates/activity_feed.html').read_text()
    add_book(db, people['alice'], title='Dune')
    login(client, 'alice')
    page = client.get('/books/shared?search_term=dune').get_data(as_text=True)
    assert page.index('<h1') < page.index('search-form-container')


def test_notifications_card_has_no_heading_of_its_own(client, db, people):
    """Phil, 2026-11-13: the page heading says Notifications; the card under
    it lost its "Recent Activity" heading and bell. Screen readers still
    get the section's name."""
    login(client, 'alice')
    page = client.get('/friends/notifications_page').get_data(as_text=True)
    card = page[page.index('data-recent-activity'):]
    card = card[:card.index('</section>')]
    assert 'aria-label="Recent activity"' in page
    assert '<h2' not in card and 'Recent Activity' not in card


def test_add_page_keeps_a_draft_and_crop_blocks_zoom():
    """Phil, 2026-11-14: a reload wiped a half-entered movie, and the crop
    zoomed in while a corner was dragged. The add form keeps a draft
    (restored only into an empty form, dropped once it's really sent), the
    add page has no pull-to-refresh, and the crop tool cancels pinches and
    caps the viewport while it's open."""
    js = pathlib.Path('static/add_item.js').read_text()
    assert 'libaraxia:add-draft:' in js and "addEventListener('pagehide', saveDraft)" in js
    assert "event.target === form && !event.defaultPrevented) dropDraft()" in js
    assert "!root.dataset.lookupUrl && !root.dataset.autoLookup && !$('title')?.value.trim()" in js
    crop = pathlib.Path('static/cover_crop.js').read_text()
    assert "addEventListener('gesturestart', stopGesture, { passive: false })" in crop
    assert 'maximum-scale=1' in crop and 'lockZoom(false)' in crop
    css = pathlib.Path('static/styles.css').read_text()
    assert 'html:has(#add-item) { overscroll-behavior-y: none; }' in css
    assert '.crop-dialog { touch-action: manipulation; }' in css


def test_record_item_box_is_thinner():
    """An album's box is about half a book's depth, on the item page as on
    the grid (Phil, 2026-11-14): each page sets a thin depth beside the
    book's, and a record's box takes it (layout walk step 1)."""
    css = pathlib.Path('static/styles.css').read_text()
    assert ':root[data-style="shelf"] .cover-stand {\n    --box-depth: 9px;\n    --box-thin: 5px;' in css
    assert ':root[data-style="shelf"] .shelf-grid.grid {\n    --box-depth: 7px;\n    --box-thin: 4px;\n}' in css
    assert (':root[data-style="shelf"] :is(.cover-box, .no-cover):is([data-media="record"], '
            '[data-media="video"][data-format="DVD"]) {\n    --box-depth: var(--box-thin);') in css
    # a vinyl sleeve is card: 1px everywhere, in its cover's edge colour a
    # shade darker; CDs and cassettes keep the record depth (Phil, 2026-11-16)
    assert (':root[data-style="shelf"] :is(.cover-box, .no-cover)[data-media="record"]'
            ':not([data-format="CD"], [data-format="Cassette"]) {\n    --box-depth: 1px;') in css
    assert 'color-mix(in srgb, rgb(var(--edge, var(--box-side))) 70%, black)' in css
    common = pathlib.Path('static/common.js').read_text()
    assert "addEventListener('load', event => paintVinylEdge(event.target), true)" in common
    assert ("const VINYL_COVER = '.cover-box[data-media=\"record\"]"
            ":not([data-format=\"CD\"], [data-format=\"Cassette\"]) > img';") in common

def test_item_page_has_no_pointer_to_the_tools(client, db, people):
    """The "Mark it unshelved, transfer it or delete it ... under Edit"
    line is gone from the item page (Phil, 2026-11-15)."""
    book = add_book(db, people['alice'])
    login(client, 'alice')
    assert '#book-tools' not in client.get(f'/books/{book}').get_data(as_text=True)


def test_dvd_box_is_thinner_than_vhs(client, db, people):
    """A DVD case is thinner than a VHS clamshell (Phil, 2026-11-15): its
    box knows the format, on the item page and the grid, server-drawn and
    script-drawn cards alike (the thin-depth rule: test above)."""
    dvd = add_book(db, people['alice'], title='Heat')
    db.execute("UPDATE books SET media_type = 'video', format = 'DVD' WHERE id = ?", (dvd,))
    db.commit()
    login(client, 'alice')
    box = '<span class="cover-box" data-media="video" data-format="DVD">'
    nobox = 'class="no-cover no-cover-md w-full h-full" data-media="video" data-format="DVD"'
    assert nobox in client.get('/videos/').get_data(as_text=True)
    assert 'data-media="video" data-format="DVD"' in client.get(f'/videos/{dvd}').get_data(as_text=True)
    common = pathlib.Path('static/common.js').read_text()
    assert ' data-media="${escapeHtml(media)}" data-format="${escapeHtml(format || \'\')}"' in common
    script = pathlib.Path('static/script.js').read_text()
    assert 'media: book.media_type, format: book.format, faces: book.faces' in script
    assert box.startswith('<span class="cover-box"')


def test_headings_have_no_subtitles_and_one_height(client, db, people):
    """The feed, Do I Have This? and the wishlists lost their taglines, and
    every page heading is as tall as the Shelves one (Phil, 2026-11-15)."""
    login(client, 'alice')
    for url in ('/feed/activity', '/have/', '/wishlist/view', '/wishlist/user/carol'):
        page = client.get(url, follow_redirects=True).get_data(as_text=True)
        assert 'page-title' in page, url
        heading = page.split('page-title', 1)[1].split('</h1>', 1)[1][:200]
        assert '<p class="mt-1 text-sm' not in heading, url
    macro = pathlib.Path('templates/_icons.html').read_text()
    assert 'gap-3 min-h-10 text-2xl font-display' in macro


def test_tabs_are_raised_and_recessed_in_every_style():
    """The active tab is raised and the rest recessed in every style, not
    just Shelf (Phil, 2026-11-15: the others had missed it)."""
    css = pathlib.Path('static/styles.css').read_text()
    assert '\n:is(.tab, .search-method-btn) {\n    background-color: var(--tab-recess);' in css
    assert ':root[data-style="shelf"] :is(.tab, .search-method-btn)' not in css
    assert '[data-style="classic"] .tab-active' not in css


def test_avatars_are_square_in_negative_earth_outrun_and_cyberpunk():
    """Every avatar is .avatar: round, square in Negative Earth, Outrun and
    Cyberpunk (Phil, 2026-11-15). No avatar keeps a bare rounded-full, which would stay round."""
    css = pathlib.Path('static/styles.css').read_text()
    assert (':root:is([data-style="house"], [data-style="outrun"], [data-style="cyberpunk"])'
            ' .avatar { border-radius: 0; }') in css
    for path in list(pathlib.Path('templates').rglob('*.html')) + list(pathlib.Path('static').glob('*.js')):
        for line in path.read_text().splitlines():
            if 'rounded-full' in line:
                assert 'avatar' not in line and 'username' not in line, f'{path}: {line.strip()}'


def test_wishlist_covers_show_the_format(client, db, people):
    """A wishlist cover carries its format (Phil, 2026-11-15): VHS or DVD,
    LP or CD at a glance, an icon or a vinyl size's short name; a plain
    book has none. On your list and on a friend's."""
    items = {}
    for title, mtype, fmt in [('Tape', 'video', 'VHS'), ('Disc', 'video', 'DVD'), ('Vinyl', 'record', 'LP'),
                              ('Single', 'record', '7in'), ('Novel', 'book', None), ('Heard', 'book', 'Audiobook')]:
        book = add_book(db, people['alice'], title)
        db.execute('UPDATE books SET media_type = ?, format = ? WHERE id = ?', (mtype, fmt, book))
        db.execute('INSERT INTO wishlist (user_id, book_id) VALUES (?, ?)', (people['alice'], book))
        items[title] = book
    db.commit()
    login(client, 'alice')
    page = ''.join(client.get(f'/wishlist/view?show={tab}').get_data(as_text=True)
                   for tab in ('books', 'movies', 'music'))
    for fmt in ('VHS', 'DVD', 'LP', '7in', 'Audiobook'):
        assert f'data-format-badge="{fmt}"' in page, fmt
    assert page.count('data-format-badge=') == 5               # not the plain book
    assert 'aria-label="Cartridge"' in page                    # the UI's name for VHS
    assert '>7&#34;<' in page                                  # a size with no icon: its short name (escaped)
    login(client, 'carol')                                     # alice's friend
    assert 'data-format-badge="VHS"' in client.get('/wishlist/user/alice').get_data(as_text=True)


def test_book_box_shows_pages():
    """A book's flat box, wherever it is shown, has lined pages on its top
    and side unless a photo or placeholder fills that face; audiobooks and
    unowned books too (Phil, 2026-11-16)."""
    css = pathlib.Path('static/styles.css').read_text()
    who = ':root[data-style="shelf"] :is(.cover-box, .no-cover)[data-media="book"]'
    assert 'Audiobook"]):not([style*="--face-' not in css
    assert who + ':not([style*="--face-side"])::before {' in css
    assert who + ':not([style*="--face-top"])::after {' in css
    assert 'repeating-linear-gradient(90deg,\n        rgb(var(--box-side)) 0 var(--leaf)' in css
    # finer leaves on a 2x or 3x screen, so a 5px box shows several lines
    # rather than one (Phil, 2026-11-17)
    assert '@media (min-resolution: 3dppx)' in css
    assert '--leaf: calc(2px / 3); --leaf-line: calc(1px / 3);' in css


def test_cyberpunk_cards_are_never_clipped():
    """Cyberpunk's HUD shapes (phase 2): cards get filled corners drawn on
    an overlay, never clip-path, which would cut off menus hanging out of a
    card (the filter panel) and focus rings inside it. Only boxes with
    nothing sticking out are cut: header bars, buttons, chips, avatars."""
    css = pathlib.Path('static/styles.css').read_text()
    section = css[css.index('/* ---- Cyberpunk shapes (phase 2)'):]
    rules = re.findall(r'([^{}]+)\{([^}]*)\}', section)
    clipped = [sel.strip() for sel, body in rules if 'clip-path' in body]
    assert clipped, 'expected cut corners somewhere'
    for sel in clipped:
        assert not re.search(r'\.card(-link)?\b', sel), sel
    # The cut edges' gradients read --cp-edge, so they must be declared on
    # the elements that set it, not on :root (where it isn't set yet)
    root = re.search(r':root\[data-style="cyberpunk"\] \{([^}]*)\}', section).group(1)
    assert '--cp-diag' not in root
    # Positioned cards stay positioned; the overlay only makes static ones relative
    assert ':is(.card, .card-link):not(.absolute, .fixed, .sticky, dialog) { position: relative; }' in section


def test_cyberpunk_boot_screen_once_per_login(client, people):
    """Cyberpunk's boot screen (phase 3): base.html carries the login mark
    (the seed drawn at login) and loads cyberpunk.js in <head>, not deferred,
    so the screen is up before the first paint. The script boots once per
    mark, never with reduced motion or blocked storage; the screen is CSS."""
    login(client, 'alice')
    page = client.get('/collections/collections').get_data(as_text=True)
    head = page[:page.index('</head>')]
    assert '<meta name="login-mark" content="' in head
    assert head.index('name="login-mark"') < head.index('cyberpunk.js')
    assert re.search(r'<script src="/static/cyberpunk\.js\?v=\w+"></script>', head)   # not deferred
    js = pathlib.Path('static/cyberpunk.js').read_text()
    assert "prefers-reduced-motion: reduce" in js and 'localStorage' in js and 'catch' in js
    # Five seconds (Phil, 2026-11-18), the last line ending in the cursor;
    # the text goes in with textContent, never innerHTML
    assert 'const END = 5000;' in js and "'> ENTERING LIBARAXIA '" in js and 'cursor: true' in js
    assert 'innerHTML' not in js
    css = pathlib.Path('static/styles.css').read_text()
    assert ':root[data-style="cyberpunk"][data-boot="on"]::before' in css
    assert '.cp-boot { display: none; }' in css             # only Cyberpunk shows it
    # The CRT layer never catches a click and is off in print
    crt = css[css.index('/* ---- Cyberpunk finishing touches (phase 3)'):]
    assert 'pointer-events: none' in crt and '@media print' in crt
    # Signed out (the sign-in page): no mark, so no boot
    client.post('/auth/logout')
    assert 'login-mark' not in client.get('/auth/login').get_data(as_text=True)


def test_cyberpunk_boot_readouts_on_the_first_page_after_login_only(client, db, people):
    """The boot screen's readouts (pass 2, Phil 2026-11-18): the first full
    page after a login in Cyberpunk carries the user's counts; later pages
    don't (no query), and neither does another style, which leaves them for
    the first Cyberpunk page instead. Shelf counts skip removed and
    never-owned rows."""
    alice, carol = people['alice'], people['carol']
    add_book(db, alice, title='Dune')
    removed = add_book(db, alice, title='Gone')
    unowned = add_book(db, alice, title='Borrowed')
    db.execute("UPDATE books SET removed_at = CURRENT_TIMESTAMP WHERE id = ?", (removed,))
    db.execute("UPDATE books SET owned = 0 WHERE id = ?", (unowned,))
    db.execute("INSERT INTO user_collections (user_id, name) VALUES (?, 'Favourites')", (alice,))
    db.execute("UPDATE users SET theme_style = 'house' WHERE id = ?", (alice,))
    db.commit()
    login(client, 'alice')
    assert 'boot-stats' not in client.get('/collections/collections').get_data(as_text=True)
    db.execute("UPDATE users SET theme_style = 'cyberpunk' WHERE id = ?", (alice,))
    db.commit()
    page = client.get('/collections/collections').get_data(as_text=True)
    head = page[:page.index('</head>')]
    friends = scalar(db, 'SELECT COUNT(*) FROM friendships WHERE user_id_1 = ? OR user_id_2 = ?', alice, alice)
    assert friends >= 1                                         # carol, from the seed
    meta = re.search(r'<meta name="boot-stats"[^>]*>', head).group(0)
    assert 'data-user="alice"' in meta
    assert 'data-items="1"' in meta and 'data-lists="1"' in meta and f'data-friends="{friends}"' in meta
    assert head.index('name="boot-stats"') < head.index('cyberpunk.js')
    # Once: the next page has none
    assert 'boot-stats' not in client.get('/collections/collections').get_data(as_text=True)
    js = pathlib.Path('static/cyberpunk.js').read_text()
    assert "meta[name=\"boot-stats\"]" in js and "'OK'" in js       # falls back to OK


def test_cyberpunk_glitch_is_timed_not_on_hover_or_tap(client):
    """The glitch (pass 2, Phil 2026-11-18): once on the page title as the
    page loads, then one cover or heading every 10 s, on a timer, so it is
    the same on a phone; no hover or tap triggers, skipped in a hidden tab,
    none with reduced motion."""
    js = pathlib.Path('static/cyberpunk.js').read_text()
    glitch = js[js.index('function glitch('):]
    assert 'const EVERY = 10000;' in glitch and 'setInterval(random, EVERY)' in glitch
    assert 'document.hidden' in glitch
    # Covers, item page titles and headings; never a grid card's title (Phil)
    pool = re.search(r"const POOL = '([^']*)'", glitch).group(1)
    assert '.detail-title' in pool and '.book-cover' in pool and 'book-title' not in pool
    assert 'class="detail-title ' in pathlib.Path('templates/_item_heading.html').read_text()
    assert not re.search(r"addEventListener\('(mouse|pointer|touch|click)", glitch)
    css = pathlib.Path('static/styles.css').read_text()
    rules = css[css.index('/* ---- Cyberpunk glitch'):]
    assert ':root[data-style="cyberpunk"] .cp-glitch {' in rules
    assert '@media (prefers-reduced-motion: reduce)' in rules
    # The cover brackets are hover-only on a mouse (never a tap) or keyboard focus
    polish = css[css.index('/* ---- Cyberpunk polish'):]
    assert '@media (hover: hover)' in polish and '.book-link:focus-visible .book-cover::after' in polish


def test_login_messages_wait_for_the_cyberpunk_boot_screen():
    """The login's flashes (Welcome, unread notifications) close after 5 s,
    as long as the boot screen lasts: their clock starts when it's gone."""
    common = pathlib.Path('static/common.js').read_text()
    dismiss = common[common.index('function scheduleFlashDismiss'):]
    assert 'dataset.boot' in dismiss and "'cyberpunk:booted'" in dismiss
    assert "new Event('cyberpunk:booted')" in pathlib.Path('static/cyberpunk.js').read_text()


def test_the_closed_sidebar_takes_no_tab_stops(client, people):
    """The sidebar is a drawer slid off-screen when closed; its links took
    Tab stops (and were read out) all the same, in every style. Closed it's
    inert, from the first paint (the markup) and after (sidebar.js)."""
    login(client, 'alice')
    page = client.get('/collections/collections').get_data(as_text=True)
    assert re.search(r'<div id="sidebar"\s+class="[^"]*"\s+inert>', page)
    js = pathlib.Path('static/sidebar.js').read_text()
    assert 'sidebar.inert = !open;' in js and 'hamburger.focus()' in js


def _subject(selector):
    """The last compound of a CSS selector (what the rule styles), splitting
    on combinators outside parentheses."""
    depth, last = 0, 0
    for i, ch in enumerate(selector):
        depth += ch == '('
        depth -= ch == ')'
        if depth == 0 and ch in ' >+~':
            last = i + 1
    return selector[last:]


def test_card_position_rules_leave_dialogs_fixed():
    """The confirm dialog is a .card. A modal <dialog> centres in the viewport
    only while it's position: fixed; a style that makes every .card relative
    (Cyberpunk's HUD corners) opened it at the top of the page instead."""
    css = (ROOT / 'static' / 'styles.css').read_text()
    css = re.sub(r'/\*.*?\*/', '', css, flags=re.S)
    checked = 0
    for selectors, body in re.findall(r'([^{}]+)\{([^{}]*)\}', css):
        if not re.search(r'(^|;|\s)position:\s*(relative|absolute|static)', body):
            continue
        for selector in re.split(r',(?![^()]*\))', selectors):
            subject = _subject(selector.strip())
            # Rules on every card: the subject starts with .card or :is(.card
            # (not a pseudo-element, not a card scoped inside something)
            if '::' in subject or not re.match(r'(:is\()?\.card(?![-\w])', subject):
                continue
            checked += 1
            assert re.search(r':not\([^)]*\bdialog\b', subject) or subject.startswith('.card.'), \
                f'{selector.strip()} also moves the confirm <dialog>'
    assert checked                      # the Cyberpunk rule is still there to check


def test_dangerous_confirms_say_yes_and_what_they_do():
    """The confirm dialog's button never reads a bare OK for something
    dangerous (Phil, 2026-11-19): "Yes, delete", "Yes, leave". Runs
    common.js's yesLabel under node; skipped without it."""
    import json
    import shutil
    import subprocess
    node = shutil.which('node')
    if node is None:
        pytest.skip('node is not installed')
    js = (ROOT / 'static' / 'common.js').read_text()
    source = re.search(r'const DANGER_WORDS = .*?\n', js).group(0) + \
        re.search(r'function yesLabel\(message\) \{.*?\n\}\n', js, re.S).group(0)
    messages = ['Delete this loan record?', 'Leave the household? You can be invited back.',
                "Remove this user's avatar?", 'This cannot be undone.', 'Sure?']
    out = subprocess.run([node, '-e', source + f'console.log(JSON.stringify({json.dumps(messages)}.map(yesLabel)))'],
                         capture_output=True, text=True, timeout=30, check=True)
    assert json.loads(out.stdout) == ['Yes, delete', 'Yes, leave', 'Yes, remove', 'Yes, continue', 'Yes, continue']
    # The default is used for dangerous confirms, and no page asks for a bare verb
    assert 'ok = ok || (danger ? yesLabel(message)' in js
    pages = '\n'.join(p.read_text() for p in (ROOT / 'templates').rglob('*.html'))
    scripts = '\n'.join(p.read_text() for p in (ROOT / 'static').glob('*.js'))
    assert not re.search(r'data-confirm-ok="(OK|Delete|Remove)"', pages)
    assert not re.search(r"ok: '(OK|Delete|Remove)'", scripts)


def test_empty_detail_fields_say_not_set(client, db, people):
    """An empty field on an item page keeps its label and says "Not set" in
    a marked, muted line: it used to print Python's None ("None pages")."""
    book = add_book(db, people['alice'])
    login(client, 'alice')
    page = client.get(f'/books/{book}').get_data(as_text=True)
    facts = page.split('item-facts', 1)[1].split('</div>\n                </div>', 1)[0]
    # publisher, year, page count, ISBN and genre are all empty on this book
    assert facts.count('data-unset') == 5
    assert 'None' not in facts
    db.execute("UPDATE books SET page_count = 320, publisher = 'Scribner' WHERE id = ?", (book,))
    db.commit()
    page = client.get(f'/books/{book}').get_data(as_text=True)
    assert page.count('data-unset') == 3 and '320 pages' in page


def test_box_shadow_stays_off_the_shelf():
    """A Shelf cover's shadow falls on the wall to its right and never
    below its base (Phil, 2026-11-14: a shadow under it made it float):
    the offset is up, and the blur is no more than offset plus spread."""
    css = pathlib.Path('static/styles.css').read_text()
    assert '--box-shadow: calc(var(--box-depth) + 6px) -4px 8px -4px rgb(0 0 0 / var(--box-shade));' in css
    assert 'box-contact' not in css and 'box-cast' not in css


def test_og_walnut_palette(client, db, people):
    """OG can take Shelf's parchment and walnut (Phil, 2026-11-15): a saved
    users.palette on <html data-palette>, a picker shown in OG only, and
    CSS that matches OG alone."""
    login(client, 'alice')
    assert 'data-palette="theme"' in client.get('/books/').get_data(as_text=True)
    assert client.post('/user/update_theme', json={'palette': 'mahogany'}).status_code == 400
    assert client.post('/user/update_theme', json={'style': 'classic', 'palette': 'walnut'}).status_code == 200
    assert scalar(db, 'SELECT palette FROM users WHERE id = ?', people['alice']) == 'walnut'
    page = client.get('/user/settings').get_data(as_text=True)
    assert 'data-palette="walnut"' in page and 'data-kind="palette"' in page
    css = pathlib.Path('static/styles.css').read_text()
    assert ':root[data-style="classic"][data-palette="walnut"] {' in css
    assert ':root[data-style="classic"][data-palette="walnut"][data-mode="dark"] {' in css
    assert ':root:not([data-style="classic"]) [data-palette-picker] { display: none; }' in css


def test_no_byline_without_a_creator(client, db, people):
    """No bare "by" under the title when an item has no author, director or
    artist (Phil, 2026-11-15)."""
    book = add_book(db, people['alice'], 'Anonymous Work', '')
    login(client, 'alice')
    assert 'data-byline' not in client.get(f'/books/{book}').get_data(as_text=True)
    db.execute("UPDATE books SET author = 'Someone' WHERE id = ?", (book,))
    db.commit()
    assert 'data-byline' in client.get(f'/books/{book}').get_data(as_text=True)


# ---- One cover box everywhere (layout walk step 1, docs/LAYOUT-WALK-SPEC.md section 2)

def test_every_cover_call_passes_its_item():
    """Phil, 2026-11-19: the feed's covers were the plain grey box while the
    grid's were each item's own (a book's pages, a vinyl sleeve, a DVD's
    depth, its photos). The box now takes its item, so every cover_img call
    and every _no_cover.html include in templates/ passes item= (item=none
    where a placeholder is not the item's box: the rack's printed label). A
    new list that forgets it fails here."""
    calls = 0
    for path in sorted((ROOT / 'templates').glob('*.html')):
        if path.name in ('_covers.html', '_no_cover.html'):
            continue
        text = path.read_text()
        for call in re.findall(r'cover_img\((?:[^()]|\([^()]*\))*\)', text):
            calls += 1
            assert 'item=' in call, f'{path.name}: {call}'
        for include in re.findall(r'{% with ((?:(?!%}).)*)%}\s*{% include \'_no_cover.html\' %}', text):
            calls += 1
            assert 'item=' in include, f'{path.name}: {include}'
        # an include outside a {% with %} can't pass it
        assert text.count("{% include '_no_cover.html' %}") == len(
            re.findall(r'%}\s*{% include \'_no_cover.html\' %}', text)), path.name
    assert calls >= 20


def _rules(css):
    """(selector, body) of every plain rule, @media blocks included."""
    css = re.sub(r'/\*.*?\*/', '', css, flags=re.S)
    return re.findall(r'([^{}@;]+)\{([^{}]*)\}', css)


def test_per_type_box_rules_are_on_the_box():
    """The Shelf box's per-type rules (depth, plastic colours, a book's
    pages, the vinyl edge, the faces' photos) key on the box's own
    data-media / data-format / style, never on a wrapper (the grid's
    .book-item, the item page's .cover-stand), so the grid, the item page
    and the lists can't drift apart again. The video-store rack's cases
    are the exception: they're the rack's own look, on the grid only."""
    css = (ROOT / 'static/styles.css').read_text()
    checked = 0
    for selector, body in _rules(css):
        selector = ' '.join(selector.split())
        if not re.search(r'data-media|data-format|--face-', selector) or 'data-rack="store"' in selector:
            continue
        boxy = re.search(r'--box-(depth|thin|top|side)\s*:', body) or (
            re.search(r'(cover-box|no-cover)[^,]*::(before|after)', selector) and 'background' in body)
        if not boxy:
            continue
        checked += 1
        for wrapper in ('.shelf-grid', '.cover-stand', '.book-item'):
            assert wrapper not in selector, selector
    assert checked >= 8


def test_lists_draw_each_items_box(client, db, people):
    """Rendered, not just written: on the feed, Reviews, Collections, the
    profile, Do I Have This?, the rate page and Borrowed, every cover box
    and placeholder carries its item's type and format, the vinyl's and
    the book's alike."""
    alice, carol = people['alice'], people['carol']
    book = add_book(db, alice, title='Dune')
    lp = add_book(db, alice, title='Blue Train')
    db.execute("UPDATE books SET media_type = 'record', format = 'LP' WHERE id = ?", (lp,))
    for item in (book, lp):
        db.execute('INSERT INTO read_data (user_id, book_id, rating, comment) VALUES (?, ?, 4, ?)',
                   (alice, item, 'Good'))
        db.execute("INSERT INTO collections (user_id, book_id, status) VALUES (?, ?, 'read')", (alice, item))
    db.execute('INSERT INTO loans (book_id, lent_by, borrower_id, borrower_name, lent_at) '
               "VALUES (?, ?, ?, 'carol', date('now'))", (lp, alice, carol))
    db.commit()
    pages = {'alice': ['/feed/activity', '/reviews/', '/reviews/?type=record', '/collections/collections',
                       '/user/alice', '/have/?q=Dune', f'/read/rate_review/{book}'],
             'carol': ['/loans/borrowed', '/feed/activity']}
    for who, urls in pages.items():
        login(client, who)
        for url in urls:
            html = client.get(url).get_data(as_text=True)
            boxes = re.findall(r'<(?:span|div) class="(?:cover-box|no-cover)[ "][^>]*>', html)
            assert boxes, url
            for tag in boxes:
                assert re.search(r'data-media="(book|video|record)" data-format="[^"]*"', tag), (url, tag)
            if url in ('/reviews/?type=record', '/loans/borrowed'):
                assert 'data-media="record" data-format="LP"' in html, url


def test_cover_box_takes_the_book_id_over_a_rows_own(app, db, people):
    """A feed, review or loan row's `id` is its own; `book_id` is the book's,
    so that's the one the faces and the ring are looked up by."""
    book = add_book(db, people['alice'])
    db.execute("UPDATE books SET media_type = 'video', format = 'VHS', owned = 0 WHERE id = ?", (book,))
    db.commit()
    with app.test_request_context():
        cover_box = app.jinja_env.globals['cover_box']
        row = {'id': 9999, 'book_id': book, 'media_type': 'video', 'format': 'VHS', 'owned': 1}
        assert cover_box(row) == {'media': 'video', 'format': 'VHS', 'faces': '', 'ring': None}
        # an unshelved movie has no copy, so no format (as on the grid)
        assert cover_box(dict(row, owned=0))['format'] == ''
        assert cover_box(None) == {}


def test_box_attrs_match_their_js_twin(app):
    """_covers.html box_attrs and common.js boxAttrsHtml give a box the same
    attributes, so a grid card added by infinite scroll is the same box as
    one the server drew."""
    import json
    import shutil
    import subprocess
    node = shutil.which('node')
    if not node:
        pytest.skip('node not installed')
    cases = [{'media': 'record', 'format': 'LP', 'faces': ''},
             {'media': 'video', 'format': '', 'faces': '--face-top: url("/static/uploads/t.jpg"); '},
             {'media': 'book', 'format': 'Audiobook', 'faces': ''},
             {}]
    with app.test_request_context():
        macro = app.jinja_env.get_template('_covers.html').module.box_attrs
        server = [str(macro(c)) for c in cases]
    src = (ROOT / 'static/common.js').read_text()
    escape = re.search(r'function escapeHtml\(text\) \{.*?\n\}', src, re.S).group(0)
    fn = re.search(r'function boxAttrsHtml\(.*?\n\}', src, re.S).group(0)
    out = subprocess.run([node, '-e', escape + '\n' + fn + f'\nconsole.log(JSON.stringify({json.dumps(cases)}.map(boxAttrsHtml)))'],
                         capture_output=True, text=True, check=True).stdout
    # the same attributes once read (Jinja writes a quote as &#34;, escapeHtml as &quot;)
    import html
    assert [html.unescape(a) for a in json.loads(out)] == [html.unescape(a) for a in server]
    assert all('url("' not in a for a in json.loads(out) + server)     # never a raw quote in style="..."
    assert server[0] == ' data-media="record" data-format="LP"' and server[3] == ''


# ---- The catalog cabinet on every tab row (layout walk step 2, spec section 3)

def test_no_hand_built_tab_rows():
    """Every page-level tab row is _shelves.html tab_row (the cabinet's
    drawers in Shelf), so a new hand-built row fails here. The item page's
    tabs stay their own (Phil, 2026-11-19); Stats' switches became drawers
    the same day."""
    allowed = {'_shelves.html', 'book_detail.html'}
    for path in sorted((ROOT / 'templates').rglob('*.html')):
        if path.name in allowed:
            continue
        text = path.read_text()
        assert not re.search(r'class="tab[ "]', text), path.name
        assert 'role="tablist"' not in text and 'role="tab"' not in text, path.name


def test_every_tab_row_is_a_cabinet(client, db, people):
    """Rendered: the tab rows of Collections, the wishlist, Reviews and its
    pages, the profile, Settings, Admin and Placeholders are cabinets (the
    shelf pages' too, which go on into the search band). A row that ends the
    cabinet has its plinth (cabinet-end); the wishlist's filter is the band
    under its drawers."""
    alice = people['alice']
    book = add_book(db, alice, title='Dune')
    db.execute('INSERT INTO wishlist (user_id, book_id) VALUES (?, ?)', (alice, add_book(db, alice, title='Want')))
    db.commit()
    login(client, 'alice')
    ending = ['/collections/collections', '/reviews/', '/reviews/all/mine', '/reviews/all/friends', '/reviews/find',
              '/user/carol', '/user/settings', '/faces/admin']
    for url in ending:
        html = client.get(url).get_data(as_text=True)
        rows = re.findall(r'<div class="tab-row [^"]*"', html)
        assert rows, url
        assert all('cabinet-part cabinet-drawers cabinet-top cabinet-end' in r for r in rows), (url, rows)
    # Settings holds Admin's row too, inside its Admin panel
    assert client.get('/user/settings').get_data(as_text=True).count('class="tab-row') == 2
    shelf = client.get('/books/').get_data(as_text=True)
    assert re.search(r'<div class="tab-row page-frame [^"]*cabinet-part cabinet-drawers cabinet-top"', shelf)
    wish = client.get('/wishlist/view').get_data(as_text=True)
    assert re.search(r'<div class="tab-row [^"]*cabinet-part cabinet-drawers cabinet-top"', wish)
    assert '<div class="cabinet-part cabinet-end mb-8">\n            <div class="cabinet-band">' in wish
    # in-page tabs: their open drawer is the aria-selected one
    css = (ROOT / 'static/styles.css').read_text()
    assert ':root[data-style="shelf"] .cabinet-drawers :is(.tab-active, .tab[aria-selected="true"]) {' in css
    assert ':root[data-style="shelf"] .cabinet-end.cabinet-top > .card,' in css


def test_stats_switches_are_one_cabinet(client, db, people):
    """Stats (Phil, 2026-11-19): the type's drawers on top, Overview |
    Insights in a band under them, one cabinet, out of the numbers' card.
    Toggle buttons for user.js (data-click, aria-pressed), not initTabs,
    so they aren't hidden waiting for it. Books only: one row, both ends."""
    from test_videos import add_video
    alice = people['alice']
    add_book(db, alice, 'Dune', 'Frank Herbert')
    login(client, 'carol')
    one = client.get('/user/alice').get_data(as_text=True)
    one = one[one.index('data-stats '):]
    assert re.findall(r'<div class="tab-row ([^"]*)"', one) == ['pb-4 cabinet-part cabinet-drawers cabinet-top cabinet-end']
    add_video(db, alice)
    stats = client.get('/user/alice').get_data(as_text=True)
    stats = stats[stats.index('data-stats '):]
    rows = re.findall(r'<div class="tab-row ([^"]*)"(.*?)>\s*<div class="([^"]*)">', stats)
    assert [(r[0], r[1], r[2]) for r in rows] == [
        ('pb-3 cabinet-part cabinet-drawers cabinet-top', '', 'bg-secondary rounded-xl overflow-hidden card'),
        ('pb-4 cabinet-part cabinet-drawers cabinet-end', '', 'bg-secondary rounded-xl overflow-hidden card cabinet-band'),
    ]
    assert stats.index('data-stats-kind="all"') < stats.index('data-stats-view="overview"') < stats.index('data-stats-panel')
    assert 'data-click="statsView" data-stats-view="overview" aria-pressed="true"' in stats
    js = (ROOT / 'static/user.js').read_text()
    assert "button.classList.toggle('tab-active', on);\n        button.setAttribute('aria-pressed'" in js


def test_tab_row_is_hidden_until_the_script_runs():
    """In-page tabs only work with JS: without it every panel shows, so the
    row (the whole cabinet, not just its buttons) stays hidden until
    initTabs shows it. Switching style on Settings, now a cabinet too,
    doesn't reload: only the shelf pages' server-laid view bar needs it."""
    js = (ROOT / 'static/common.js').read_text()
    assert ":scope > [data-tab-row] [role=\"tablist\"]" in js
    assert "const row = list.closest('[data-tab-row]') ?? list;" in js and 'row.hidden = false;' in js
    css = (ROOT / 'static/styles.css').read_text()
    assert '[data-tabs] [data-tab-row][hidden] {' in css
    assert "document.querySelector('.view-bar.cabinet-part')" in (ROOT / 'static/sidebar.js').read_text()


def test_a_deeper_ledge_front_also_resets_the_ledge_height():
    """--ledge-h is calc(--ledge-top + --ledge-front), and a custom
    property's var() is worked out where it is declared. A rule that changes
    --ledge-front without declaring --ledge-h again keeps the old height, so
    the ledge doesn't grow (step 3's captioned rows: the captions vanished).
    Setting it on the element that declares the height (the grid, the small
    cases) is fine: there the height is worked out from the element's own
    front. So each rule setting --ledge-front declares the height too, or
    its element (the selector's last classes) is one that declares it."""
    css = (ROOT / 'static' / 'styles.css').read_text()
    css = re.sub(r'/\*.*?\*/', '', css, flags=re.S)

    def last_classes(selector):
        """Classes of the last compound in each of the selector's parts
        (:is(a, b) counts as one compound)."""
        out = set()
        for part in re.split(r',(?![^(]*\))', selector):
            last = re.sub(r'\(([^)]*)\)', lambda m: '(' + m.group(1).replace(' ', '') + ')',
                          part.strip()).split()[-1]
            out |= set(re.findall(r'\.[\w-]+', last))
        return out

    rules = [(sel.strip(), body) for sel, body in re.findall(r'([^{}]+)\{([^{}]*)\}', css)]
    owns_height = lambda body: re.search(r'--ledge(-h)?\s*:', body)
    owners = set().union(*(last_classes(sel) for sel, body in rules if owns_height(body)))
    fronts = [(sel, body) for sel, body in rules if re.search(r'--ledge-front\s*:', body)]
    assert fronts, 'no rule sets --ledge-front'
    for selector, body in fronts:
        assert owns_height(body) or last_classes(selector) <= owners, selector


def test_shelf_captions_sit_on_the_ledge_front():
    """Reviews' captions (stars, a friend's name) are printed on the ledge's
    front in Shelf: taken out of the figure's flow, cream on the wood."""
    css = (ROOT / 'static' / 'styles.css').read_text()
    rule = re.search(r'\.shelf-case \.shelf-figure figcaption \{([^}]*)\}', css)
    assert rule and 'position: absolute' in rule.group(1)
    assert 'var(--shelf-label)' in rule.group(1)


def test_walk_pages_have_the_framed_heading(client, db, people):
    """Layout walk step 7: Borrowed and the admin pages printed a bare <h1>;
    they get page_heading like every other page (CLAUDE.md: titles with
    page_heading), and Borrowed's empty line is a card."""
    login(client, 'alice')                                # an admin
    for url in ('/loans/borrowed', '/admin/backups', '/admin/placeholder_covers', '/faces/admin',
                '/admin/orphaned_images', '/admin/unowned_books'):
        html = client.get(url).get_data(as_text=True)
        assert 'class="page-heading' in html, url
        assert '<h1 class="text-3xl' not in html, url
    html = client.get('/loans/borrowed').get_data(as_text=True)
    assert re.search(r'<div class="bg-secondary [^"]*card[^"]*">\s*<p[^>]*>Nothing borrowed right now', html)


def test_one_gap_under_every_heading_and_tab_row(client, db, people):
    """Phil, 2026-11-19: the space under a heading is the Shelves page's
    (its heading to its catalog), on every page, and so is the space under a
    tab row or the catalog. heading_card owns the heading's mb-4 and tab_row
    its pb-4, so no page passes its own; a space-y container's margin is
    evened out to the same 1rem; and in Shelf a top face's room above a case
    never merges into the gap (on Reviews it had left 6px)."""
    calls = ''.join(p.read_text() for p in (ROOT / 'templates').rglob('*.html'))
    assert not re.search(r'page_heading\([^)]*\bclass=', calls)
    assert not re.search(r"heading_card\('[^']*\bmb-", calls)
    assert not re.search(r"(?:tab_row|section_switch)\([^)]*class='pb-[5-9]", calls)
    login(client, 'alice')
    for url in ('/reviews/', '/collections/collections', '/wishlist/view', '/feed/activity'):
        html = client.get(url).get_data(as_text=True)
        assert re.search(r'<div class="page-heading [^"]*\bmb-4\b', html), url
    css = (ROOT / 'static' / 'styles.css').read_text()
    assert '[class*="space-y-"] > :is(.page-heading, .tab-row) + :not([hidden]) { margin-top: 1rem; }' in css
    assert ':root[data-style="shelf"] .cabinet-top { padding-top: var(--run); }' in css
    assert ':root[data-style="shelf"] .cabinet-end + .shelf-case { margin-top: calc(1rem + var(--case-run)); }' in css
    assert ':root[data-style="shelf"] .view-bar + .shelf-grid.grid { margin-top: calc(1rem + var(--ledge-top)); }' in css
    # The top's room is the part's padding now, not the card's margin
    top = re.search(r':root\[data-style="shelf"\] \.cabinet-top > \.card \{([^}]*)\}', css).group(1)
    assert 'margin-top' not in top


def test_wishlist_drawers_have_no_counts(client, db, people):
    """Phil, 2026-11-19: the counts made the drawer labels two and three
    lines tall, and each section's heading has its own."""
    db.execute('INSERT INTO wishlist (user_id, book_id) VALUES (?, ?)',
               (people['alice'], add_book(db, people['alice'], 'Dune')))
    db.commit()
    login(client, 'alice')
    html = client.get('/wishlist/view').get_data(as_text=True)
    row = re.search(r'<div class="tab-row.*?</nav>', html, re.S).group(0)
    assert 'opacity-75' not in row and '(' not in row


def test_shelf_row_covers_link_to_their_items(client, db, people):
    """Phil, 2026-11-19: on Collections and Reviews a cover opens its item's
    page, and the shelf's name row its whole list. The card used to be one
    link, to the list; a link can't hold links, so it's a plain card now."""
    alice = people['alice']
    book = add_book(db, alice, 'Dune')
    db.execute("INSERT INTO collections (user_id, book_id, status) VALUES (?, ?, 'read')", (alice, book))
    db.execute("INSERT INTO read_data (user_id, book_id, rating, comment) VALUES (?, ?, 4, 'good')", (alice, book))
    db.commit()
    login(client, 'alice')
    for url in ('/collections/collections', '/reviews/'):
        html = client.get(url).get_data(as_text=True)
        assert f'<a href="/books/{book}" class="shelf-cover block">' in html, url
        assert re.search(r'<a href="[^"]+" class="shelf-label ', html), url
        assert not re.search(r'<a [^>]*class="shelf-link', html), url
        # no link inside another
        for card in re.findall(r'<div class="shelf-link.*?\n        </div>', html, re.S):
            depth = 0
            for tag in re.findall(r'</?a\b', card):
                depth += 1 if tag == '<a' else -1
                assert depth <= 1, url


def test_show_everything_includes_ownerless_items_you_have_data_on(client, db, people):
    """Phil, 2026-11-19: "if I want to see everything, I want to see
    *everything*". Show: Everything also lists an item with no owner (from
    before items had owners) that you reviewed, marked No owner; ownerless
    items you never touched, and other people's, stay out; the default view
    and a friend's grid never show them."""
    from conftest import add_review
    alice, carol = people['alice'], people['carol']
    mine = add_book(db, alice, 'Infinite Jest')
    old = db.execute("INSERT INTO books (title, author) VALUES ('Infinite Jest', 'DFW')").lastrowid
    stray = db.execute("INSERT INTO books (title, author) VALUES ('Stray', 'Nobody')").lastrowid
    db.commit()
    add_review(db, alice, old)
    add_review(db, carol, stray)                  # carol's data, not alice's
    login(client, 'alice')

    def ids(url):
        r = client.get(url, headers={'X-Requested-With': 'XMLHttpRequest'})
        return {b['id']: b for b in r.get_json()['books']}

    everything = ids('/books/?show=all')
    assert set(everything) == {mine, old}
    assert everything[old]['no_owner'] and not everything[mine]['no_owner']
    page = client.get('/books/?show=all').get_data(as_text=True)
    assert page.count('data-no-owner>No owner</span>') == 1
    # The search finds it too, and the default and Unshelved views don't
    assert set(ids('/books/?show=all&search_term=jest')) == {mine, old}
    assert set(ids('/books/')) == {mine}
    assert old not in ids('/books/?show=not_owned')
    # The household's Everything: your own ownerless items
    assert old in ids('/books/shared?show=all')
    # A friend's grid (carol looking at alice's): never
    login(client, 'carol')
    assert set(ids("/books/user/alice?show=all")) <= {mine}

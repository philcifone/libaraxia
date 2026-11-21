"""The header's style, accent and font cyclers (ROADMAP 14c)."""
from conftest import login, scalar
from models import ACCENTS, FONTS, THEME_STYLES


def test_sidebar_has_the_three_cyclers(client, people):
    login(client, 'alice')
    html = client.get('/collections/collections').get_data(as_text=True)
    assert f'data-cycle="style"' in html and f'data-cycle-values="{",".join(THEME_STYLES)}"' in html
    assert f'data-cycle-values="{",".join(ACCENTS)}"' in html
    # The font one is hidden in Outrun with the other font pickers
    assert 'data-cycle="font" data-font-picker' in html and f'data-cycle-values="{",".join(FONTS)}"' in html


def test_cycling_saves_each_step(client, db, people):
    login(client, 'alice')
    for style in THEME_STYLES:          # a full round, one save per click
        assert client.post('/user/update_theme', json={'style': style}).get_json()['success']
    assert scalar(db, 'SELECT theme_style FROM users WHERE id = ?', people['alice']) == list(THEME_STYLES)[-1]
    assert client.post('/user/update_theme', json={'font': 'nope'}).status_code == 400


def test_cyclers_sit_in_their_own_row_behind_a_toggle(client, people):
    """14c follow-up: the cyclers are a second row under the icons, hidden
    until the toggle right of the light/dark one opens it."""
    login(client, 'carol')
    html = client.get('/collections/collections').get_data(as_text=True)
    icons = html[html.index('class="sidebar-icons'):html.index('id="sidebar-cyclers"')]
    assert 'data-mode-toggle' in icons and 'data-cycle=' not in icons
    assert icons.index('data-mode-toggle') < icons.index('data-cyclers-toggle')
    assert 'aria-controls="sidebar-cyclers" aria-expanded="false"' in icons
    row = html[html.index('id="sidebar-cyclers"'):]
    row = row[:row.index('</div>')]
    assert ' hidden>' in row.split('\n')[0] and row.count('data-cycle=') == 3
    css = open('static/styles.css').read()
    assert '#sidebar-cyclers[hidden] { display: none; }' in css


def test_style_cycler_skips_cyberpunk(client, people):
    """Cyberpunk is Appearance only (Phil, 2026-11-21): the style cycler still
    names it (its title while in it) but never steps to it, so it never sets
    off the boot screen on the next page."""
    login(client, 'alice')
    html = client.get('/collections/collections').get_data(as_text=True)
    style = html[html.index('data-cycle="style"'):]
    assert 'data-cycle-skip="cyberpunk"' in style[:style.index('>')]
    assert html.count('data-cycle-skip=') == 1                  # accent and font skip nothing
    js = open('static/sidebar.js').read()
    assert "button.dataset.cycleSkip" in js and '.filter(v => !skip.includes(v))' in js


def test_choosing_cyberpunk_in_appearance_boots_there(client, people):
    """Choosing Cyberpunk in Appearance plays the boot on that page, once
    saved, and stores the login's mark so the next page doesn't boot again."""
    sidebar = open('static/sidebar.js').read()
    assert "kind === 'style' && value === 'cyberpunk') window.cyberpunkStart?.()" in sidebar
    assert 'const saved = await setAppearance(kind, value);' in sidebar
    js = open('static/cyberpunk.js').read()
    assert 'window.cyberpunkStart = () => start(true);' in js
    # A live boot ignores the stored mark (it is the first) but still stores it
    assert "if (!live && localStorage.getItem(KEY) === mark) return null;" in js
    assert 'localStorage.setItem(KEY, mark);' in js

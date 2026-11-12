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

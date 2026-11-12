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

"""Tabs on Profile and Admin Settings (ROADMAP 14c): server-rendered ARIA
tabs that common.js turns on; without JS every panel shows."""
import re

from conftest import login


def panels(html):
    """{panel id: its HTML up to the next panel} for role="tabpanel" divs."""
    parts = re.split(r'<div role="tabpanel" id="([\w-]+)"', html)
    return {parts[i]: parts[i + 1] for i in range(1, len(parts), 2)}


def test_own_profile_has_four_tabs_with_old_anchors_inside(client, people):
    login(client, 'alice')
    html = client.get('/user/alice').get_data(as_text=True)
    assert 'role="tablist" aria-label="Profile" hidden' in html     # shown by JS only
    p = panels(html)
    assert list(p) == ['overview', 'reviews', 'library', 'account']
    assert 'id="library-backups"' in p['library'] and 'Export Library to CSV' in p['library']
    assert 'id="email-display"' in p['account'] and 'account-removal-dialog' in p['account']
    assert 'id="appearance-settings"' in p['account']
    assert html.count('id="account"') == 1


def test_friends_profile_has_no_tabs(client, people):
    login(client, 'alice')
    r = client.get('/user/carol')
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert 'role="tablist" aria-label="Profile"' not in html and 'role="tabpanel"' not in html


def test_admin_settings_tabs(client, people):
    login(client, 'alice')
    html = client.get('/admin/settings').get_data(as_text=True)
    p = panels(html)
    assert list(p) == ['users', 'households', 'maintenance']
    assert 'id="user-form-panel"' in p['users']
    assert 'Shared Library Groups' in p['households']
    assert 'Orphaned Images' in p['maintenance']


def test_household_actions_return_to_their_tab(client, people):
    login(client, 'alice')
    r = client.post('/admin/add_library_member', data={})
    assert r.headers['Location'].endswith('#households')

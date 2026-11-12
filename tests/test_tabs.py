"""Tabs on Profile and Settings (ROADMAP 14c): server-rendered ARIA tabs that
common.js turns on; without JS every panel shows. Profile is about the person
(Overview, Stats, Reviews); Settings (the gear, everyone) holds Library and
Account, plus Admin for admins."""
import re

from conftest import login


def panels(html):
    """{panel id: its HTML up to the next panel} for role="tabpanel" divs."""
    parts = re.split(r'<div role="tabpanel" id="([\w-]+)"', html)
    return {parts[i]: parts[i + 1] for i in range(1, len(parts), 2)}


def test_own_profile_has_overview_stats_reviews(client, people):
    login(client, 'alice')
    html = client.get('/user/alice').get_data(as_text=True)
    assert 'role="tablist" aria-label="Profile" hidden' in html     # shown by JS only
    p = panels(html)
    assert list(p) == ['overview', 'stats', 'reviews']
    # Settings-like things moved to the Settings page
    assert 'id="library-backups"' not in html and 'id="appearance-settings"' not in html
    assert 'account-removal-dialog' not in html


def test_friends_profile_has_the_same_tabs(client, people):
    login(client, 'alice')
    r = client.get('/user/carol')
    assert r.status_code == 200
    assert list(panels(r.get_data(as_text=True))) == ['overview', 'stats', 'reviews']


def test_non_friend_profile_has_no_tabs(client, people):
    login(client, 'bob')                         # alice's household, not her friend
    html = client.get('/user/alice').get_data(as_text=True)
    assert 'role="tablist"' not in html and 'role="tabpanel"' not in html


def test_settings_for_everyone_with_old_anchors_inside(client, people):
    login(client, 'carol')                       # not an admin
    html = client.get('/user/settings').get_data(as_text=True)
    assert 'role="tablist" aria-label="Settings" hidden' in html
    p = panels(html)
    assert list(p) == ['library', 'account']
    assert 'id="library-backups"' in p['library'] and 'Export Library to CSV' in p['library']
    assert 'id="email-display"' in p['account'] and 'account-removal-dialog' in p['account']
    assert 'id="appearance-settings"' in p['account']
    assert html.count('id="account"') == 1
    assert 'admin_settings.js' not in html


def test_admins_get_the_admin_tab_with_its_own_tabs(client, people):
    login(client, 'alice')
    html = client.get('/user/settings').get_data(as_text=True)
    p = panels(html)
    assert list(p) == ['library', 'account', 'admin', 'users', 'households', 'maintenance']
    assert 'id="user-form-panel"' in p['users']
    assert 'Shared Library Groups' in p['households']
    assert 'Orphaned Images' in p['maintenance']
    assert 'admin_settings.js' in html


def test_old_admin_settings_address_redirects(client, people):
    login(client, 'alice')
    r = client.get('/admin/settings')
    assert r.status_code == 302 and r.headers['Location'].endswith('/user/settings#admin')
    login(client, 'carol')
    assert client.get('/admin/settings').status_code in (302, 403)


def test_household_actions_return_to_their_tab(client, people):
    login(client, 'alice')
    r = client.post('/admin/add_library_member', data={})
    assert r.headers['Location'].endswith('/user/settings#households')

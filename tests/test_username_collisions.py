"""A value a user picks never collides with how the site works (Phil,
2026-11-12): a user called "settings" would have a profile at
/user/settings, which is the Settings page. models.username_error refuses
such names, read from the live URL map, and names are unique ignoring case
(migration 033)."""
import sqlite3

import pytest

from conftest import add_user, login, scalar
from models import USERNAME_RESERVED, USERNAME_TAKEN, username_error, username_shadows_route


def static_siblings(app):
    """Every fixed path segment that sits where a <username> also can, e.g.
    'settings' beside /user/<username>. Found the same way a new route
    would be, so this test grows with the app."""
    rules = [r.rule.strip('/').split('/') for r in app.url_map.iter_rules()]
    found = set()
    for rule in app.url_map.iter_rules():
        if 'username' not in rule.arguments:
            continue
        segs = rule.rule.strip('/').split('/')
        i = segs.index('<username>')
        found |= {r[i] for r in rules
                  if len(r) == len(segs) and r[:i] == segs[:i] and not r[i].startswith('<')}
    return found


def test_every_fixed_page_beside_a_username_is_reserved(app):
    with app.test_request_context():
        siblings = static_siblings(app)
        assert 'settings' in siblings and 'export_data' in siblings
        for name in siblings:
            if len(name) >= 3:                     # shorter ones fail the rules anyway
                assert username_shadows_route(name), name
                assert username_shadows_route(name.capitalize()), name
        for name in ('alice', 'Phil', 'set.tings', 'settings2', 'user'):
            assert not username_shadows_route(name), name


def test_errors_name_the_problem(app, db, people):
    with app.test_request_context():
        assert username_error(db, 'settings') == USERNAME_RESERVED
        assert username_error(db, 'ALICE') == USERNAME_TAKEN                  # case doesn't make it new
        assert username_error(db, 'Alice', people['alice']) is None          # recasing your own is fine
        assert username_error(db, 'a b') not in (None, USERNAME_RESERVED, USERNAME_TAKEN)
        assert username_error(db, 'dora') is None


def test_register_refuses_a_page_name_and_a_case_twin(client, db, people):
    before = scalar(db, 'SELECT COUNT(*) FROM users')
    for name in ('settings', 'Settings', 'Carol'):
        r = client.post('/auth/register', data={'username': name, 'email': f'{name}x@example.test',
                                                'password': 'long-enough-pw'})
        assert r.status_code == 200, name                 # the form again, with the reason
    assert scalar(db, 'SELECT COUNT(*) FROM users') == before


def test_rename_refuses_a_page_name(client, db, people):
    login(client, 'carol')
    r = client.post('/user/update_username', json={'username': 'update_email'})
    assert r.status_code == 400 and r.get_json()['message'] == USERNAME_RESERVED
    r = client.post('/user/update_username', json={'username': 'BOB'})
    assert r.status_code == 400 and r.get_json()['message'] == USERNAME_TAKEN
    assert scalar(db, 'SELECT username FROM users WHERE id = ?', people['carol']) == 'carol'


def test_admin_add_user_refuses_a_page_name(client, db, people):
    login(client, 'alice')
    client.post('/admin/create_user', data={'username': 'settings', 'email': 's@example.test',
                                            'password': 'long-enough-pw'})
    assert scalar(db, "SELECT COUNT(*) FROM users WHERE username = 'settings'") == 0


def test_the_database_refuses_a_case_twin_too(db, people):
    with pytest.raises(sqlite3.IntegrityError):
        add_user(db, 'ALICE')

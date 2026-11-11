"""/bulk routes (ROADMAP 14a step 4): login, JSON shapes, 409, the banner,
and that nothing here is exempt from CSRF."""
import pytest

from conftest import add_book, login


def post(client, url, **body):
    return client.post(url, json=body)


def books(db, owner, genres):
    ids = []
    for i, genre in enumerate(genres):
        bid = add_book(db, owner, title=f'Book {i}')
        db.execute('UPDATE books SET genre = ? WHERE id = ?', (genre, bid))
        ids.append(bid)
    db.commit()
    return ids


def genre_of(db, book_id):
    return db.execute('SELECT genre FROM books WHERE id = ?', (book_id,)).fetchone()[0]


def test_every_route_wants_a_login(client, people):
    for method, url in (('post', '/bulk/plan'), ('post', '/bulk/apply'), ('post', '/bulk/1/undo'),
                        ('get', '/bulk/genres')):
        r = getattr(client, method)(url, json={})
        assert r.status_code in (302, 401), url


def test_plan_shape(client, db, people):
    ids = books(db, people['alice'], ['Cooking', 'Cooking', 'Cookbook', 'Cookbooks'])
    login(client, 'alice')
    r = post(client, '/bulk/plan', action='genre', params={'genre': 'Cookbooks'}, ids=ids)
    assert r.status_code == 200
    plan = r.get_json()['plan']
    assert plan['describe'] == 'Set genre to “Cookbooks”'
    assert (plan['changes'], plan['same']) == (3, 1)
    assert [(g['before'], g['count']) for g in plan['groups']] == [('Cooking', 2), ('Cookbook', 1)]
    assert {i['title'] for i in plan['groups'][0]['items']} == {'Book 0', 'Book 1'}
    assert plan['fingerprint'] and plan['skipped'] == []
    assert genre_of(db, ids[0]) == 'Cooking'                       # nothing written


def test_plan_errors_are_specific_and_json(client, db, people):
    ids = books(db, people['alice'], ['A'])
    login(client, 'alice')
    r = post(client, '/bulk/plan', action='genre', params={}, ids=ids)
    assert r.status_code == 400 and r.get_json() == {'success': False, 'error': 'Pick a genre first.'}
    assert post(client, '/bulk/plan', action='title', params={'title': 'x'}, ids=ids).status_code == 400
    assert post(client, '/bulk/plan', action='genre', params={'genre': 'x'}, ids=[]).status_code == 400
    assert client.post('/bulk/plan', data='not json').status_code == 400
    assert post(client, '/bulk/plan', action='genre', params={'genre': 'x'},
                ids=list(range(1, 600))).status_code == 400          # over the cap


def test_apply_writes_and_sets_the_banner(client, db, people):
    ids = books(db, people['alice'], ['Cooking', 'Cookbook', 'Reference'])
    login(client, 'alice')
    params = {'genre': 'Cookbooks'}
    fp = post(client, '/bulk/plan', action='genre', params=params, ids=ids).get_json()['plan']['fingerprint']
    r = post(client, '/bulk/apply', action='genre', params=params, ids=ids, fingerprint=fp,
             excluded_ids=[ids[2]])
    body = r.get_json()
    assert r.status_code == 200 and body['success'] and body['changed'] == 2
    assert body['summary'] == 'Genre set to Cookbooks on 2 items'
    assert [genre_of(db, i) for i in ids] == ['Cookbooks', 'Cookbooks', 'Reference']

    # The next page shows the banner once, with Undo
    page = client.get('/base/index').get_data(as_text=True)
    assert 'Genre set to Cookbooks on 2 items' in page
    assert f'/bulk/{body["edit_id"]}/undo' in page or f'data-edit-id="{body["edit_id"]}"' in page
    assert 'Genre set to Cookbooks on 2 items' not in client.get('/base/index').get_data(as_text=True)


def test_stale_apply_is_409_with_the_new_plan(client, db, people):
    ids = books(db, people['alice'], ['Cooking', 'Cookbook'])
    login(client, 'alice')
    params = {'genre': 'Cookbooks'}
    fp = post(client, '/bulk/plan', action='genre', params=params, ids=ids).get_json()['plan']['fingerprint']
    db.execute("UPDATE books SET genre = 'Elsewhere' WHERE id = ?", (ids[0],))
    db.commit()
    r = post(client, '/bulk/apply', action='genre', params=params, ids=ids, fingerprint=fp)
    body = r.get_json()
    assert r.status_code == 409 and body['stale'] is True and body['success'] is False
    assert body['plan']['fingerprint'] != fp and body['plan']['groups'][0]['before'] == 'Elsewhere'
    assert [genre_of(db, i) for i in ids] == ['Elsewhere', 'Cookbook']
    assert client.get('/base/index').get_data(as_text=True).count('Genre set') == 0


def test_apply_without_a_matching_fingerprint_changes_nothing(client, db, people):
    ids = books(db, people['alice'], ['Cooking'])
    login(client, 'alice')
    r = post(client, '/bulk/apply', action='genre', params={'genre': 'X'}, ids=ids, fingerprint='nope')
    assert r.status_code == 409 and genre_of(db, ids[0]) == 'Cooking'


def test_undo_route_and_its_banner(client, db, people):
    ids = books(db, people['alice'], ['Cooking'])
    login(client, 'alice')
    params = {'genre': 'Food'}
    fp = post(client, '/bulk/plan', action='genre', params=params, ids=ids).get_json()['plan']['fingerprint']
    edit = post(client, '/bulk/apply', action='genre', params=params, ids=ids, fingerprint=fp).get_json()['edit_id']
    client.get('/base/index')                                       # the apply banner is shown and gone
    r = client.post(f'/bulk/{edit}/undo')
    assert r.status_code == 200 and r.get_json()['summary'] == 'Undone: 1 restored.'
    assert genre_of(db, ids[0]) == 'Cooking'
    page = client.get('/base/index').get_data(as_text=True)
    assert 'Undone: 1 restored.' in page and f'/bulk/{edit}/undo' not in page   # no Undo on an undo
    again = client.post(f'/bulk/{edit}/undo')
    assert again.status_code == 400 and 'Already undone' in again.get_json()['error']


def test_undo_is_not_available_to_other_users(client, db, people):
    ids = books(db, people['alice'], ['Cooking'])
    login(client, 'alice')
    params = {'genre': 'Food'}
    fp = post(client, '/bulk/plan', action='genre', params=params, ids=ids).get_json()['plan']['fingerprint']
    edit = post(client, '/bulk/apply', action='genre', params=params, ids=ids, fingerprint=fp).get_json()['edit_id']
    login(client, 'carol')
    assert client.post(f'/bulk/{edit}/undo').status_code == 400
    assert genre_of(db, ids[0]) == 'Food'


def test_a_household_member_cannot_apply_to_the_owners_books(client, db, people):
    ids = books(db, people['alice'], ['Cooking'])
    login(client, 'bob')
    r = post(client, '/bulk/plan', action='genre', params={'genre': 'X'}, ids=ids)
    plan = r.get_json()['plan']
    assert plan['changes'] == 0 and plan['skipped'][0]['reason'] == 'Not yours'
    assert post(client, '/bulk/apply', action='genre', params={'genre': 'X'}, ids=ids,
                fingerprint=plan['fingerprint']).status_code == 400
    assert genre_of(db, ids[0]) == 'Cooking'


def test_genres_route(client, db, people):
    books(db, people['alice'], ['Cooking', 'cooking', 'Fiction'])
    books(db, people['bob'], ['Poetry'])
    login(client, 'alice')
    got = client.get('/bulk/genres?type=book').get_json()
    assert got['success'] and got['genres'] == [{'value': 'Cooking', 'count': 2}, {'value': 'Fiction', 'count': 1}]
    assert client.get('/bulk/genres?type=video').get_json()['genres'] == []
    assert client.get('/bulk/genres?type=bogus').status_code == 400


def test_the_bulk_routes_are_not_csrf_exempt(app):
    """The test config turns CSRF off; check nobody exempted these routes."""
    csrf = app.extensions['csrf']
    exempt = getattr(csrf, '_exempt_views', set()) | getattr(csrf, '_exempt_blueprints', set())
    assert not [e for e in exempt if 'bulk' in str(e)]

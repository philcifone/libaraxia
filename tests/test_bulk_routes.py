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
    assert [(g['key'], g['count']) for g in plan['groups']] == [('Cooking', 2), ('Cookbook', 1)]
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
    assert body['plan']['fingerprint'] != fp and body['plan']['groups'][0]['key'] == 'Elsewhere'
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


def test_options_route(client, db, people):
    db.execute("INSERT INTO user_collections (user_id, name, media_type) VALUES (?, 'Jazz', 'book')",
               (people['alice'],))
    db.commit()
    login(client, 'alice')
    got = client.get('/bulk/options?type=video').get_json()
    assert got['success'] and got['section'] == 'Movies'
    assert [s['value'] for s in got['statuses']] == ['watched', 'want to watch', 'untracked']
    assert got['shelves'] == []
    assert [s['name'] for s in client.get('/bulk/options?type=book').get_json()['shelves']] == ['Jazz']
    assert client.get('/bulk/options?type=bogus').status_code == 400
    assert client.get('/bulk/options').status_code == 200            # defaults to books


def test_the_other_actions_work_through_the_routes(client, db, people):
    ids = books(db, people['alice'], ['A', 'B'])
    login(client, 'alice')
    for action, params, summary in (('tag_add', {'tag': 'Gift'}, 'Tag “gift” added to 2 items'),
                                    ('status', {'status': 'read'}, 'Status set to Read on 2 items'),
                                    ('remove', {'note': 'sold'}, 'Removed 2 items from the library')):
        fp = post(client, '/bulk/plan', action=action, params=params, ids=ids).get_json()['plan']['fingerprint']
        r = post(client, '/bulk/apply', action=action, params=params, ids=ids, fingerprint=fp)
        assert r.status_code == 200 and r.get_json()['summary'] == summary, action
    bad = post(client, '/bulk/plan', action='shelf_add', params={'shelf_id': 999, 'media_type': 'book'}, ids=ids)
    assert bad.status_code == 400 and bad.get_json()['error'] == 'That collection was not found.'


def test_selection_route_lists_what_each_item_has_now(client, db, people):
    """The choose step's list: each item's current values, the viewer's own
    marks, and nothing the viewer can't see."""
    alice, bob = people['alice'], people['bob']
    mine, theirs = books(db, alice, ['Cooking', None])
    db.execute("INSERT INTO collections (user_id, book_id, status) VALUES (?, ?, 'read')", (alice, mine))
    db.execute("INSERT INTO book_tags (user_id, book_id, tag_name) VALUES (?, ?, 'gift')", (alice, mine))
    db.execute("INSERT INTO book_tags (user_id, book_id, tag_name) VALUES (?, ?, 'bobs')", (bob, mine))
    stranger = add_book(db, people['carol'], title='Carol only')
    db.execute('UPDATE books SET added_by = ? WHERE id = ?', (bob, theirs))       # household: visible, not hers
    db.commit()
    login(client, 'alice')
    items = post(client, '/bulk/selection', ids=[mine, theirs]).get_json()['items']
    assert [(i['id'], i['genre'], i['status'], i['tags']) for i in items] == [
        (mine, 'Cooking', 'Read', ['gift']), (theirs, None, 'Unread', [])]
    assert items[0]['format'] == 'Book' and items[0]['owned'] and not items[0]['removed']
    # Bob (household, not an admin): his own marks, and only his item is "yours"
    login(client, 'bob')
    items = post(client, '/bulk/selection', ids=[mine, theirs, stranger]).get_json()['items']
    assert [(i['id'], i['tags'], i['yours']) for i in items] == [(mine, ['bobs'], False), (theirs, [], True)]
    assert post(client, '/bulk/selection', ids=['x']).status_code == 400


def test_a_view_selection_is_resolved_at_plan_time(client, db, people):
    """Select all 57 in this view: the server finds them with the grid's
    query, across pages, and apply writes only what the plan named."""
    alice = people['alice']
    ids = [add_book(db, alice, title=f'Cook {i:02}') for i in range(57)]
    add_book(db, alice, title='Something else')
    login(client, 'alice')
    body = dict(action='genre', params={'genre': 'Cookbooks'}, view='book:mine', args='search_term=cook&page=1')
    plan = post(client, '/bulk/plan', **body).get_json()['plan']
    assert plan['changes'] == 57 and sorted(plan['ids']) == ids
    assert len(post(client, '/bulk/selection', view='book:mine', args='search_term=cook').get_json()['items']) == 57

    # A book that joins the view after the review isn't written
    late = add_book(db, alice, title='Cook late')
    r = post(client, '/bulk/apply', action='genre', params={'genre': 'Cookbooks'}, ids=plan['ids'],
             fingerprint=plan['fingerprint'])
    assert r.status_code == 200 and r.get_json()['summary'] == 'Genre set to Cookbooks on 57 items'
    assert genre_of(db, late) is None and all(genre_of(db, i) == 'Cookbooks' for i in ids)


def test_view_selection_on_search_and_household(client, db, people):
    alice, bob = people['alice'], people['bob']
    mine, bobs = add_book(db, alice, title='Dune'), add_book(db, bob, title='Dune Messiah')
    login(client, 'alice')
    for view, args in (('book:search', 'search_term=dune'), ('book:household', 'search_term=dune')):
        plan = post(client, '/bulk/plan', action='tag_add', params={'tag': 'sf'}, view=view, args=args)
        assert sorted(plan.get_json()['plan']['ids']) == [mine, bobs], view
    # alice's own grid is hers alone (?member= is test_grid_query's)
    plan = post(client, '/bulk/plan', action='tag_add', params={'tag': 'sf'}, view='book:mine', args='search_term=dune')
    assert plan.get_json()['plan']['ids'] == [mine]


def test_view_selection_refuses_unknown_views_and_the_cap(client, db, people, monkeypatch):
    login(client, 'alice')
    for view in ('book:friend', 'nonsense', 'video:search'):
        r = post(client, '/bulk/plan', action='genre', params={'genre': 'x'}, view=view, args='')
        assert r.status_code == 400 and "can't be edited in bulk" in r.get_json()['error'], view
    from utils import bulk
    monkeypatch.setattr(bulk, 'MAX_ITEMS', 2)
    for i in range(3):
        add_book(db, people['alice'], title=f'B{i}')
    r = post(client, '/bulk/plan', action='genre', params={'genre': 'x'}, view='book:mine', args='')
    assert r.status_code == 400 and r.get_json()['error'].startswith('Too many for one edit (3)')

"""The Audiobookshelf client and key storage (ROADMAP 16.0e step 2,
docs/AUDIOBOOKSHELF-SPEC.md sections 4, 5 and 12). The network is blocked
in tests, so a fake session stands in for ABS."""
import json

import pytest
import requests

from utils import audiobookshelf as abs_
from utils.audiobookshelf import AbsError

KEY = 'eyJhbGciOiJIUzI1NiJ9.test-key.sig'
SECRET = 'test-secret-key'
BASE = 'http://192.168.1.171:13378'


class FakeResponse:
    def __init__(self, status=200, body=b'', headers=None):
        self.status_code = status
        self.body = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.headers = headers or {}
        self.closed = False

    def iter_content(self, size):
        for i in range(0, len(self.body), size):
            yield self.body[i:i + size]

    def close(self):
        self.closed = True


class FakeSession:
    """Answers by path; records every call (method, url, params, headers,
    allow_redirects) so tests can check what was sent."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def request(self, method, url, params=None, json=None, timeout=None, stream=None,
                allow_redirects=True, headers=None):
        self.calls.append({'method': method, 'url': url, 'params': params, 'headers': headers,
                           'allow_redirects': allow_redirects, 'timeout': timeout})
        answer = self.routes.get(url[len(BASE):], FakeResponse(404))
        if isinstance(answer, Exception):
            raise answer
        return answer


@pytest.fixture
def fake(monkeypatch):
    """fake(routes) installs a FakeSession for AUDIOBOOKSHELF_URL = BASE."""
    monkeypatch.setenv('AUDIOBOOKSHELF_URL', BASE)
    monkeypatch.delenv('AUDIOBOOKSHELF_PUBLIC_URL', raising=False)

    def install(routes):
        session = FakeSession(routes)
        monkeypatch.setattr(abs_, '_session', lambda: session)
        return session
    return install


ME = {
    'id': 'usr_1', 'username': 'phil', 'token': 'LEGACY-TOKEN-NEVER-KEPT', 'email': 'x@example.test',
    'mediaProgress': [
        {'libraryItemId': 'li_book', 'mediaItemType': 'book', 'progress': 1, 'isFinished': True,
         'startedAt': 1700000000000, 'finishedAt': 1700500000000, 'duration': 3600, 'currentTime': 3600,
         'lastUpdate': 1700500000000, 'userId': 'usr_1', 'id': 'p1'},
        {'libraryItemId': 'li_pod', 'mediaItemType': 'episode', 'episodeId': 'ep_1', 'progress': 0.5},
    ],
}


# --- configuration -----------------------------------------------------------

def test_no_url_no_feature(monkeypatch):
    monkeypatch.delenv('AUDIOBOOKSHELF_URL', raising=False)
    assert not abs_.enabled() and abs_.config_warnings() == []
    with pytest.raises(AbsError):
        abs_.me(KEY)


def test_urls_and_warnings(monkeypatch):
    monkeypatch.setenv('AUDIOBOOKSHELF_URL', BASE + '/')
    monkeypatch.delenv('AUDIOBOOKSHELF_PUBLIC_URL', raising=False)
    assert abs_.base_url() == BASE and abs_.public_url() == BASE
    assert abs_.config_warnings() == []                         # plain HTTP on the LAN is fine
    assert abs_.item_link('li_book') == BASE + '/item/li_book' and abs_.item_link('../x') is None
    monkeypatch.setenv('AUDIOBOOKSHELF_PUBLIC_URL', 'https://books.example.test')
    assert abs_.item_link('li_book') == 'https://books.example.test/item/li_book'
    monkeypatch.setenv('AUDIOBOOKSHELF_URL', 'http://books.example.test')
    assert 'unencrypted' in abs_.config_warnings()[0]
    monkeypatch.setenv('AUDIOBOOKSHELF_URL', 'ftp://192.168.1.2')
    assert not abs_.enabled() and 'not an http(s) URL' in abs_.config_warnings()[0]


# --- the client --------------------------------------------------------------

def test_me_keeps_book_progress_only(fake):
    session = fake({'/api/me': FakeResponse(body=ME)})
    who = abs_.me(KEY)
    assert (who['abs_user_id'], who['username']) == ('usr_1', 'phil')
    assert [b['libraryItemId'] for b in who['books']] == ['li_book']
    assert 'LEGACY-TOKEN-NEVER-KEPT' not in json.dumps(who) and 'x@example.test' not in json.dumps(who)
    call = session.calls[0]
    assert call['headers']['Authorization'] == f'Bearer {KEY}'
    assert KEY not in call['url'] and KEY not in json.dumps(call['params'])
    assert call['allow_redirects'] is False


def test_a_redirect_is_an_error_not_followed(fake):
    session = fake({'/api/me': FakeResponse(302, headers={'Location': 'http://evil.example.test/'})})
    with pytest.raises(AbsError) as e:
        abs_.me(KEY)
    assert not e.value.auth and len(session.calls) == 1


def test_refused_key_says_so(fake):
    fake({'/api/me': FakeResponse(401)})
    with pytest.raises(AbsError) as e:
        abs_.me(KEY)
    assert e.value.auth


def test_timeout_and_oversize_are_clean_failures(fake, monkeypatch, caplog):
    fake({'/api/me': requests.exceptions.ConnectTimeout(f'timed out {BASE}/api/me')})
    with pytest.raises(AbsError) as e:
        abs_.me(KEY)
    assert str(e.value) == "Audiobookshelf didn't answer."
    monkeypatch.setattr(abs_, 'MAX_ME', 100)
    fake({'/api/me': FakeResponse(body=ME)})
    with pytest.raises(AbsError):
        abs_.me(KEY)
    assert KEY not in caplog.text


def test_library_items_trims_and_skips_podcasts(fake):
    item = {'id': 'li_book', 'libraryId': 'lib_a', 'isMissing': False, 'path': '/audiobooks/x',
            'media': {'coverPath': '/metadata/x.jpg', 'duration': 58200.5, 'numAudioFiles': 12,
                      'metadata': {'title': 'Project Hail Mary', 'authorName': 'Andy Weir',
                                   'narratorName': 'Ray Porter', 'genres': ['Science Fiction'],
                                   'publishedYear': '2021', 'asin': 'B08G9PRS1K'}}}
    session = fake({
        '/api/libraries': FakeResponse(body={'libraries': [
            {'id': 'lib_a', 'mediaType': 'book'}, {'id': 'lib_p', 'mediaType': 'podcast'}]}),
        '/api/libraries/lib_a/items': FakeResponse(body={'results': [item, {'id': '../bad'}]}),
    })
    items = abs_.library_items(KEY)
    assert list(items) == ['li_book']
    got = items['li_book']
    assert (got['title'], got['narrator'], got['duration'], got['audio_files'], got['asin']) == \
        ('Project Hail Mary', 'Ray Porter', 58200.5, 12, 'B08G9PRS1K')
    assert 'path' not in got and 'coverPath' not in json.dumps(got)
    assert [c['url'][len(BASE):] for c in session.calls] == ['/api/libraries', '/api/libraries/lib_a/items']
    assert session.calls[1]['params'] == {'minified': 1, 'limit': 0}


def test_progress_and_cover(fake):
    fake({'/api/me/progress/li_book': FakeResponse(body={'libraryItemId': 'li_book', 'progress': 0.43,
                                                          'currentTime': 100, 'duration': 3600}),
          '/api/items/li_book/cover': FakeResponse(body=b'\x89PNG...')})
    assert abs_.progress(KEY, 'li_book')['progress'] == 0.43
    assert abs_.progress(KEY, 'li_other') is None                  # not started: ABS says 404
    assert abs_.cover(KEY, 'li_book') == b'\x89PNG...'
    with pytest.raises(AbsError):
        abs_.cover(KEY, '../../api/me')                             # never a path of someone's choosing


# --- the key at rest ---------------------------------------------------------

def test_seal_round_trip_and_wrong_secret():
    blob = abs_.seal(KEY, SECRET)
    assert KEY not in blob and abs_.unseal(blob, SECRET) == KEY
    assert abs_.unseal(blob, 'another-secret') is None              # SECRET_KEY changed: reconnect
    assert abs_.unseal('garbage', SECRET) is None


def test_connect_stores_the_key_encrypted(fake, db, people):
    fake({'/api/me': FakeResponse(body=ME)})
    alice = people['alice']
    assert abs_.connect(db, alice, f'  {KEY}\n', SECRET) == 'phil'
    db.commit()
    row = db.execute('SELECT * FROM abs_accounts WHERE user_id = ?', (alice,)).fetchone()
    assert KEY not in row['token_enc'] and (row['abs_user_id'], row['abs_username']) == ('usr_1', 'phil')
    assert abs_.token_for(db, alice, SECRET) == KEY
    assert 'token_enc' not in abs_.account(db, alice)
    abs_.connect(db, alice, KEY, SECRET)                            # again: one row, updated
    assert db.execute('SELECT COUNT(*) FROM abs_accounts').fetchone()[0] == 1

    abs_.disconnect(db, alice)
    assert abs_.account(db, alice) is None and abs_.token_for(db, alice, SECRET) is None


def test_connect_refuses_a_bad_key(fake, db, people):
    fake({'/api/me': FakeResponse(401)})
    with pytest.raises(AbsError) as e:
        abs_.connect(db, people['alice'], KEY, SECRET)
    assert e.value.auth
    with pytest.raises(AbsError):
        abs_.connect(db, people['alice'], 'has spaces in it', SECRET)
    assert abs_.account(db, people['alice']) is None


def test_account_goes_with_the_user(fake, db, people):
    fake({'/api/me': FakeResponse(body=ME)})
    abs_.connect(db, people['carol'], KEY, SECRET)
    db.execute("INSERT INTO abs_links (user_id, abs_item_id, outcome) VALUES (?, 'li_book', 'skipped')",
               (people['carol'],))
    db.execute('DELETE FROM users WHERE id = ?', (people['carol'],))
    assert db.execute('SELECT COUNT(*) FROM abs_accounts').fetchone()[0] == 0
    assert db.execute('SELECT COUNT(*) FROM abs_links').fetchone()[0] == 0


def test_the_key_never_reaches_a_personal_backup(fake, db, people):
    from utils.personal_backups import snapshot
    fake({'/api/me': FakeResponse(body=ME)})
    abs_.connect(db, people['alice'], KEY, SECRET)
    db.commit()
    dumped = json.dumps(snapshot(db, people['alice']), default=str)
    assert 'abs_accounts' not in dumped and KEY not in dumped
    assert db.execute('SELECT token_enc FROM abs_accounts').fetchone()[0] not in dumped

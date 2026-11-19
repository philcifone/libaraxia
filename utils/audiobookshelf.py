"""The Audiobookshelf connection (ROADMAP 16.0e, docs/AUDIOBOOKSHELF-SPEC.md):
configuration, the read-only API client, and each user's encrypted API key.

One ABS server for the site (AUDIOBOOKSHELF_URL in .env, the LAN address);
each user pastes their own key in Settings. Nothing here writes to ABS.

The client only ever calls the configured origin, so that origin is the
allow-list: a private address is fine (book_utils._get_public, which refuses
private addresses, is for URLs that come from outside), and a user can't
type a URL. Redirects are errors, not followed. The key travels only in the
Authorization header, never a URL, and is never logged; neither is a
response body (/api/me carries the user's legacy token, dropped here).

No Flask: the caller passes the app's SECRET_KEY to seal/unseal and the
connect helpers, and commits.
"""
import base64
import ipaddress
import json
import logging
import os
import re
from urllib.parse import urlsplit

import requests
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

log = logging.getLogger(__name__)

# Timeouts in seconds: a sync waits; the item page's progress line must not
TIMEOUT = 10
QUICK_TIMEOUT = 1.5

# Response size caps, read streamed (Phil's /api/me is 344 KB, a library
# listing 740 KB, a cover about 9 KB)
MAX_ME = 5 * 1024 * 1024
MAX_LISTING = 20 * 1024 * 1024
MAX_COVER = 10 * 1024 * 1024
MAX_SMALL = 256 * 1024

# An ABS id (library item, library, user): a UUID or ABS's own short ids.
# Checked before it goes into a URL path.
ITEM_ID = re.compile(r'^[A-Za-z0-9_-]{1,64}$')

# A pasted API key: a JWT in practice; anything printable without spaces
TOKEN = re.compile(r'^[\x21-\x7e]{8,4096}$')


class AbsError(Exception):
    """An ABS call that didn't work. The message is safe to show; `auth` is
    True when ABS refused the key (Settings then says Reconnect),
    `not_found` when it answered 404."""

    def __init__(self, message="Audiobookshelf didn't answer.", auth=False, not_found=False):
        super().__init__(message)
        self.auth = auth
        self.not_found = not_found


# ------------------------------------------------------------ configuration

def _origin(value):
    """A configured URL, trimmed of a trailing slash, or None if it isn't an
    http(s) URL with a host. A path is kept (ABS behind a sub-path)."""
    value = (value or '').strip().rstrip('/')
    parts = urlsplit(value)
    if parts.scheme not in ('http', 'https') or not parts.hostname or parts.query or parts.fragment:
        return None
    return value


def base_url():
    """The URL the server calls (AUDIOBOOKSHELF_URL), or None: no URL, no
    feature (no Settings card, every /abs route a 404)."""
    return _origin(os.getenv('AUDIOBOOKSHELF_URL'))


def public_url():
    """The URL for links a browser follows (AUDIOBOOKSHELF_PUBLIC_URL, a
    tunnel for a phone away from home), else the server URL."""
    return _origin(os.getenv('AUDIOBOOKSHELF_PUBLIC_URL')) or base_url()


def enabled():
    return base_url() is not None


def config_warnings():
    """Startup warnings about the configuration (app.py logs them): a URL
    that can't be used, or plain HTTP to a public host, which would send
    every user's key across the internet unencrypted. Plain HTTP on the LAN
    is what every ABS app on that network already does."""
    raw = (os.getenv('AUDIOBOOKSHELF_URL') or '').strip()
    if not raw:
        return []
    url = base_url()
    if not url:
        return ['AUDIOBOOKSHELF_URL is not an http(s) URL; the Audiobookshelf connection is off.']
    parts = urlsplit(url)
    if parts.scheme == 'http':
        try:
            private = not ipaddress.ip_address(parts.hostname).is_global
        except ValueError:
            # A name: only .local / .lan / .home.arpa and localhost are sure to be local
            private = parts.hostname == 'localhost' or parts.hostname.endswith(('.local', '.lan', '.home.arpa'))
        if not private:
            return ['AUDIOBOOKSHELF_URL is plain http:// to a host that may be public; '
                    'API keys would cross the internet unencrypted. Use https:// or the LAN address.']
    return []


# ------------------------------------------------------------ the key at rest

def _fernet(secret):
    """Fernet under a key derived from the app's SECRET_KEY, labelled for
    this one use, so it never doubles as a session-signing key."""
    if not secret:
        raise ValueError('SECRET_KEY is needed to store Audiobookshelf keys')
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=None,
               info=b'libaraxia audiobookshelf api key v1').derive(secret.encode())
    return Fernet(base64.urlsafe_b64encode(key))


def seal(token, secret):
    """The API key, encrypted for abs_accounts.token_enc."""
    return _fernet(secret).encrypt(token.encode()).decode()


def unseal(blob, secret):
    """The API key back, or None if it can't be read (SECRET_KEY changed, or
    the row is damaged): Settings shows Reconnect."""
    try:
        return _fernet(secret).decrypt((blob or '').encode()).decode()
    except (InvalidToken, ValueError):
        return None


# ------------------------------------------------------------ the client

def _session():
    """A requests session; tests replace this with a fake."""
    return requests.Session()


def _call(token, path, *, method='GET', params=None, payload=None,
          timeout=TIMEOUT, max_bytes=MAX_SMALL, raw=False):
    """One call to the configured server: parsed JSON (or bytes with `raw`).
    Raises AbsError, never anything carrying the key or the body."""
    base = base_url()
    if not base:
        raise AbsError('Audiobookshelf is not set up on this site.')
    url = base + path
    try:
        with _session() as s:
            resp = s.request(method, url, params=params, json=payload, timeout=timeout, stream=True,
                             allow_redirects=False,
                             headers={'Authorization': f'Bearer {token}', 'Accept': 'application/json'})
            try:
                status = resp.status_code
                if 300 <= status < 400:
                    log.warning('Audiobookshelf %s answered a redirect (%s); not followed', path, status)
                    raise AbsError()
                if status in (401, 403):
                    raise AbsError('Audiobookshelf refused the API key.', auth=True)
                if status == 404:
                    raise AbsError('Not found on Audiobookshelf.', not_found=True)
                if status != 200:
                    log.warning('Audiobookshelf %s answered %s', path, status)
                    raise AbsError()
                body = bytearray()
                for chunk in resp.iter_content(64 * 1024):
                    body += chunk
                    if len(body) > max_bytes:
                        log.warning('Audiobookshelf %s answered more than %s bytes; dropped', path, max_bytes)
                        raise AbsError()
            finally:
                resp.close()
    except AbsError:
        raise
    except requests.RequestException as e:
        # The exception's text can hold the URL, never the key (a header)
        log.warning('Audiobookshelf %s failed: %s', path, type(e).__name__)
        raise AbsError() from None
    if raw:
        return bytes(body)
    try:
        return json.loads(body)
    except ValueError:
        log.warning('Audiobookshelf %s answered something that is not JSON', path)
        raise AbsError() from None


def _check_id(item_id):
    if not isinstance(item_id, str) or not ITEM_ID.match(item_id):
        raise AbsError('Not found on Audiobookshelf.', not_found=True)
    return item_id


# Progress fields kept from ABS (times in seconds, dates in ms since the epoch)
PROGRESS_FIELDS = ('libraryItemId', 'progress', 'currentTime', 'duration', 'isFinished',
                   'startedAt', 'finishedAt', 'lastUpdate', 'ebookProgress')


def _progress_row(p):
    return {k: p.get(k) for k in PROGRESS_FIELDS}


def me(token, timeout=TIMEOUT):
    """{'abs_user_id', 'username', 'books': [progress rows]}: who the key
    belongs to and their book progress. Podcast episodes are dropped, as is
    everything else in the answer (the legacy `token` included)."""
    data = _call(token, '/api/me', max_bytes=MAX_ME, timeout=timeout)
    if not isinstance(data, dict) or not data.get('id') or not data.get('username'):
        raise AbsError()
    books = [_progress_row(p) for p in data.get('mediaProgress') or []
             if isinstance(p, dict) and p.get('mediaItemType', 'book') == 'book'
             and not p.get('episodeId') and p.get('libraryItemId')]
    return {'abs_user_id': str(data['id']), 'username': str(data['username']), 'books': books}


def _trim_item(item):
    """What the import needs from one minified library item."""
    media = item.get('media') or {}
    meta = media.get('metadata') or {}
    return {
        'id': item.get('id'),
        'library_id': item.get('libraryId'),
        'title': meta.get('title') or '',
        'subtitle': meta.get('subtitle') or '',
        'author': meta.get('authorName') or '',
        'narrator': meta.get('narratorName') or '',
        'series': meta.get('seriesName') or '',
        'publisher': meta.get('publisher') or '',
        'year': meta.get('publishedYear') or '',
        'genres': [g for g in meta.get('genres') or [] if isinstance(g, str)],
        'isbn': meta.get('isbn') or '',
        'asin': meta.get('asin') or '',
        'description': meta.get('description') or '',
        'duration': media.get('duration') or 0,         # seconds
        'audio_files': media.get('numAudioFiles') or 0,
        'ebook_format': media.get('ebookFormat') or '',
        'missing': bool(item.get('isMissing') or item.get('isInvalid')),
    }


def library_items(token):
    """{abs item id: trimmed metadata} for every item in every book library
    the key can see (podcast libraries are skipped). One listing per
    library, minified: cheaper than fetching items one by one."""
    data = _call(token, '/api/libraries')
    libraries = data.get('libraries') if isinstance(data, dict) else None
    items = {}
    for lib in libraries or []:
        if not isinstance(lib, dict) or lib.get('mediaType') != 'book':
            continue
        lib_id = _check_id(lib.get('id'))
        listing = _call(token, f'/api/libraries/{lib_id}/items',
                        params={'minified': 1, 'limit': 0}, max_bytes=MAX_LISTING)
        for item in (listing.get('results') if isinstance(listing, dict) else None) or []:
            if isinstance(item, dict) and isinstance(item.get('id'), str) and ITEM_ID.match(item['id']):
                items[item['id']] = _trim_item(item)
    return items


def progress(token, item_id, timeout=QUICK_TIMEOUT):
    """One item's progress for the key's user, or None if they haven't
    started it."""
    try:
        data = _call(token, f'/api/me/progress/{_check_id(item_id)}', timeout=timeout)
    except AbsError as e:
        if e.not_found:
            return None
        raise
    return _progress_row(data) if isinstance(data, dict) else None


def cover(token, item_id):
    """An item's cover image, as bytes (the caller validates it with Pillow)."""
    return _call(token, f'/api/items/{_check_id(item_id)}/cover', max_bytes=MAX_COVER, raw=True)


def item_link(item_id):
    """The item's page on ABS for a browser (public URL), or None."""
    base = public_url()
    if not base or not isinstance(item_id, str) or not ITEM_ID.match(item_id):
        return None
    return f'{base}/item/{item_id}'


# ------------------------------------------------------------ accounts

def account(conn, user_id):
    """The user's abs_accounts row (without the key), or None."""
    row = conn.execute('''SELECT user_id, abs_user_id, abs_username, connected_at, last_sync_at
                          FROM abs_accounts WHERE user_id = ?''', (user_id,)).fetchone()
    return dict(row) if row else None


def token_for(conn, user_id, secret):
    """The user's API key, decrypted, or None (not connected, or unreadable)."""
    row = conn.execute('SELECT token_enc FROM abs_accounts WHERE user_id = ?', (user_id,)).fetchone()
    return unseal(row['token_enc'], secret) if row else None


def connect(conn, user_id, token, secret):
    """Check a pasted key against ABS and store it, encrypted. Returns the
    ABS username. Raises AbsError (bad key, server down). Caller commits."""
    token = (token or '').strip()
    if not TOKEN.match(token):
        raise AbsError("That doesn't look like an Audiobookshelf API key.")
    who = me(token)
    conn.execute('''
        INSERT INTO abs_accounts (user_id, token_enc, abs_user_id, abs_username)
        VALUES (?, ?, ?, ?)
        ON CONFLICT (user_id) DO UPDATE SET
            token_enc = excluded.token_enc, abs_user_id = excluded.abs_user_id,
            abs_username = excluded.abs_username, connected_at = CURRENT_TIMESTAMP
    ''', (user_id, seal(token, secret), who['abs_user_id'], who['username']))
    return who['username']


def disconnect(conn, user_id):
    """Forget the key and the waiting review. What was imported stays, and
    so do the links (a later reconnect picks them up). Caller commits."""
    conn.execute('DELETE FROM abs_staging WHERE user_id = ?', (user_id,))
    conn.execute('DELETE FROM abs_accounts WHERE user_id = ?', (user_id,))

"""Add Album lookups from Discogs (ROADMAP 8B.10), ahead of MusicBrainz.

MusicBrainz often answers 503 when it's busy, through no fault of ours.
Discogs has a personal access token (DISCOGS_TOKEN in .env, from
discogs.com/settings/developers) and allows 60 requests a minute with it.
Without a token this module is off and Add Album uses MusicBrainz alone.

Same shape as music_lookup, so the page doesn't care which answered:
  albums(text, kind, page, by) -> the Search tab: one row per album
      (a Discogs master), 12 a page, "X by Y" as title + artist (16.0)
  pressings(master_id, kind, page) -> that album's pressings
  main_release(master_id) -> the album's main pressing, for "Use this"
  search(text, kind) -> one row per pressing (Do I have this?, the cover
      finder, and the Search tab when no album matches: a release with
      no master)
  lookup(release_id) -> {'found', 'details', 'sources', 'cover'}

Being a good API citizen (Phil asked for gentle):
  - a User-Agent naming the app, and the token in a header (never in a URL,
    so it can't end up in a log);
  - one request per MIN_INTERVAL per process, results cached for 6 hours,
    and nothing fetched that the person didn't ask for (a search is one
    request, picking a result is one more, plus its cover image);
  - a 429 (rate limited) or 5xx is Busy: we stop and the caller may try
    MusicBrainz instead, never Discogs again straight away.
Their API terms ask for attribution; the Search tab shows "Data provided
by Discogs" under Discogs results (add_item.js).

Every request goes through book_utils._get_public (public hosts only,
checked on every redirect hop; the token header goes with the first hop
only), every image through save_best_cover. Search-result thumbnails are
shown through /books/thumbnail, which allows i.discogs.com.
"""
import json
import os
import re
import threading
import time
from urllib.parse import urlencode

from flask import current_app

from utils import book_utils
from utils import media
from utils.search import by_or_plain, fits

API = 'https://api.discogs.com'
MAX_JSON_BYTES = 2 * 1024 * 1024
MIN_INTERVAL = 1.1          # seconds between requests: under their 60/min
CACHE_SECONDS = 6 * 3600

# The Search tab's format choice (?format=) -> Discogs' format filter.
# '' searches all three; digital-only releases are dropped from the rows.
SEARCH_FORMATS = {'vinyl': 'Vinyl', 'cd': 'CD', 'cassette': 'Cassette'}
PHYSICAL = {'Vinyl', 'CD', 'CDr', 'SACD', 'Hybrid', 'Cassette', 'Shellac'}
PAGE = 12                   # Search tab rows per page ("Show more" asks for the next)


class Busy(Exception):
    """Discogs is rate limiting us (429), failing (5xx) or not answering."""


def token():
    return (os.environ.get('DISCOGS_TOKEN') or '').strip()


def enabled():
    return bool(token())


def user_agent():
    return 'Libaraxia/1.0 +https://github.com/philcifone/libaraxia'


# ------------------------------------------------------------ HTTP

_lock = threading.Lock()
_last_request = 0.0
_cache = {}


def _throttle():
    """Wait until MIN_INTERVAL has passed since this process's last request."""
    global _last_request
    with _lock:
        wait = _last_request + MIN_INTERVAL - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_request = time.monotonic()


def _get(path, **params):
    """GET Discogs JSON. None for a miss (404); Busy for 429/5xx/no answer."""
    url = f'{API}{path}' + (f'?{urlencode(params)}' if params else '')
    _throttle()
    headers = {'User-Agent': user_agent(), 'Accept': 'application/json',
               'Authorization': f'Discogs token={token()}'}
    try:
        response = book_utils._get_public(url, headers=headers)
    except Exception as e:
        current_app.logger.warning(f'Discogs {path} failed: {e.__class__.__name__}')
        raise Busy() from e
    if response is None:
        raise Busy()
    try:
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            # 401 means a bad token: worth a log line, the page just says busy
            current_app.logger.info(f'Discogs {path} returned {response.status_code}')
            raise Busy()
        body = response.raw.read(MAX_JSON_BYTES + 1, decode_content=True)
        if len(body) > MAX_JSON_BYTES:
            return None
        return json.loads(body)
    except ValueError as e:
        raise Busy() from e
    finally:
        response.close()


def _cached(key, compute):
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_SECONDS:
        return hit[1]
    value = compute()
    # Misses aren't kept: an empty answer, or a page (rows, more) with no rows
    if value and (not isinstance(value, tuple) or value[0]):
        if len(_cache) > 500:
            _cache.clear()
        _cache[key] = (time.time(), value)
    return value


# ------------------------------------------------------------ pieces

def _artist_name(name):
    """Discogs tells same-named artists apart with ' (2)': drop it."""
    return re.sub(r'\s*\(\d+\)$', '', (name or '').strip())


def _artists(artists):
    """[{'name', 'anv', 'join'}] -> 'Simon & Garfunkel'. `anv` is the name
    as credited on this release, when it differs."""
    artists = [a for a in artists or [] if isinstance(a, dict)]
    out = ''
    for i, a in enumerate(artists):
        out += _artist_name(a.get('anv') or a.get('name'))
        join = (a.get('join') or '').strip()
        if i < len(artists) - 1:            # the last artist's join is noise
            out += ', ' if join in ('', ',') else f' {join} '
    return out.strip()


def album_format(tokens):
    """Our stored format (media.FORMATS[RECORD]) from Discogs' format words:
    a search row's flat list (['Vinyl', 'LP', 'Album']) or a release's
    formats flattened (name, then descriptions). None if it's none of ours
    (then the form keeps its own choice)."""
    words = set(tokens or [])
    if 'Vinyl' in words or 'Shellac' in words:
        if 'EP' in words:
            return 'EP'
        if '7"' in words:
            return '7in'
        if '10"' in words:
            return '10in'
        if words & {'Single', 'Maxi-Single'}:
            return '12in' if '12"' in words else '7in'
        return 'LP'
    if words & {'CD', 'CDr', 'SACD', 'Hybrid'}:
        return 'CD'
    if 'Cassette' in words:
        return 'Cassette'
    return None


def _format_words(formats):
    """A release's formats [{'name', 'descriptions'}] as one flat list."""
    words = []
    for f in formats or []:
        words.append(f.get('name') or '')
        words += f.get('descriptions') or []
    return words


def _seconds(duration):
    """'3:32' or '1:02:10' -> seconds; None if blank or odd."""
    parts = (duration or '').strip().split(':')
    if not all(p.isdigit() for p in parts) or len(parts) not in (2, 3):
        return None
    total = 0
    for p in parts:
        total = total * 60 + int(p)
    return total


def tracklist(release):
    """'A1 Second Hand News (2:43)' per line; headings (sides, discs) as
    their own lines, the way the release lists them."""
    lines = []
    for t in release.get('tracklist') or []:
        if t.get('type_') == 'heading':
            lines.append(' '.join((t.get('title') or '').split()))
            continue
        if t.get('type_') not in (None, 'track', 'index'):
            continue
        # Discogs data has the odd tab or double space inside titles
        line = ' '.join(f"{t.get('position') or ''} {t.get('title') or ''}".split())
        if t.get('duration'):
            line += f" ({t['duration']})"
        lines.append(line)
    return '\n'.join(l for l in lines if l)


def _length_minutes(release):
    total = sum(_seconds(t.get('duration')) or 0 for t in release.get('tracklist') or []
                if t.get('type_') in (None, 'track'))
    return round(total / 60) or None


def _covers(release):
    """Cover candidates: the primary image, then the rest."""
    images = release.get('images') or []
    primary = [i.get('uri') for i in images if i.get('type') == 'primary']
    return [u for u in primary + [i.get('uri') for i in images] if u]


# ------------------------------------------------------------ the lookups

def _rows(data):
    """Search-tab rows from a /database/search answer (physical releases only)."""
    rows = []
    for r in (data or {}).get('results') or []:
        words = r.get('format') or []
        if not r.get('id') or not (set(words) & PHYSICAL):
            continue                        # digital-only: not a thing on a shelf
        # Search titles are "Artist - Title"
        artist, _, title = (r.get('title') or '').partition(' - ')
        if not title:
            artist, title = '', artist
        fmt = album_format(words)
        labels = r.get('label') or []
        year = r.get('year')
        catno = r.get('catno') or ''
        rows.append({
            'id': r['id'],
            'source': 'discogs',
            'title': title.strip(),
            'artist': _artist_name(artist),
            'year': int(year) if str(year or '').isdigit() else None,
            'country': r.get('country') or '',
            'label': labels[0] if labels else '',
            'catalog_number': '' if catno.lower() == 'none' else catno,
            'format': fmt,
            'format_label': media.format_label(fmt) if fmt else ', '.join(words[:2]),
            'thumb': r.get('thumb') or r.get('cover_image') or '',
        })
    return rows


def _more(data):
    """Whether a paged Discogs answer has another page."""
    pages = (data or {}).get('pagination') or {}
    return (pages.get('page') or 1) < (pages.get('pages') or 1)


def search_page(text, kind='', page=1, limit=PAGE):
    """One page of releases matching `text` (artist and title words, Discogs'
    own matching, which forgives small typos) of format `kind` ('vinyl',
    'cd', 'cassette'; '' = any physical one): (rows, more). Same rows as
    music_lookup.search, plus 'source': 'discogs'. Raises Busy."""
    text = (text or '').strip()
    if len(text) < 2:
        return [], False

    def compute():
        params = {'q': text, 'type': 'release', 'per_page': limit, 'page': page}
        if kind in SEARCH_FORMATS:
            params['format'] = SEARCH_FORMATS[kind]
        data = _get('/database/search', **params)
        return _rows(data), _more(data)
    return _cached(('search', kind, text.lower(), page, limit), compute)


def search(text, kind='', limit=12):
    """The first page of search_page, rows only (Do I have this?, the cover
    finder). Raises Busy."""
    return search_page(text, kind, 1, limit)[0]


def _album_rows(data):
    """Search-tab rows from a type=master answer: one per album."""
    rows = []
    for r in (data or {}).get('results') or []:
        if not r.get('id'):
            continue
        artist, _, title = (r.get('title') or '').partition(' - ')
        if not title:
            artist, title = '', artist
        year = r.get('year')
        rows.append({
            'id': r['id'],
            'source': 'discogs',
            'level': 'album',
            'title': title.strip(),
            'artist': _artist_name(artist),
            'year': int(year) if str(year or '').isdigit() else None,
            'thumb': r.get('thumb') or r.get('cover_image') or '',
        })
    return rows


def albums(text, kind='', page=1, by=None):
    """The Search tab (16.0): albums (Discogs masters) matching `text`, one
    row each, PAGE a page; `kind` keeps albums that have a pressing in that
    format. "X by Y" asks for title X by artist Y (utils.search.by_or_plain).
    (rows, more, by). Raises Busy."""
    text = (text or '').strip()
    if len(text) < 2:
        return [], False, False

    def run(split, page):
        params = {'type': 'master', 'per_page': PAGE, 'page': page}
        if split:
            params['release_title'], params['artist'] = split
        else:
            params['q'] = text
        if kind in SEARCH_FORMATS:
            params['format'] = SEARCH_FORMATS[kind]

        def compute():
            data = _get('/database/search', **params)
            return _album_rows(data), _more(data)
        return _cached(('albums', kind, str(split).lower() if split else text.lower(), page), compute)
    return by_or_plain(text, run, page, by,
                       keep=lambda r, split: fits(split, r['title'], r['artist']))


def pressings(master_id, kind='', page=1):
    """An album's pressings (its master's versions), physical ones only, of
    format `kind` if given: (rows, more), rows as search()'s. Raises Busy."""
    def compute():
        params = {'per_page': 25, 'page': page}
        if kind in SEARCH_FORMATS:
            params['format'] = SEARCH_FORMATS[kind]
        data = _get(f'/masters/{int(master_id)}/versions', **params)
        rows = []
        for v in (data or {}).get('versions') or []:
            major = v.get('major_formats') or []
            if not v.get('id') or not (set(major) & PHYSICAL):
                continue
            # "LP, Album, Ltd": the descriptions under its major format
            words = list(major) + [w.strip() for w in (v.get('format') or '').split(',') if w.strip()]
            fmt = album_format(words)
            released = str(v.get('released') or '')
            catno = (v.get('catno') or '').strip()
            rows.append({
                'id': v['id'],
                'source': 'discogs',
                'title': (v.get('title') or '').strip(),
                'artist': '',                   # the album row has it
                'year': int(released[:4]) if released[:4].isdigit() else None,
                'country': v.get('country') or '',
                'label': (v.get('label') or '').strip(),
                'catalog_number': '' if catno.lower() == 'none' else catno,
                'format': fmt,
                'format_label': media.format_label(fmt) if fmt else ', '.join(major[:2]),
                'thumb': v.get('thumb') or '',
            })
        return rows, _more(data)
    return _cached(('pressings', int(master_id), kind, page), compute)


def main_release(master_id):
    """The release Discogs names as an album's main pressing (its id), for
    "Use this" on an album row; None if the album isn't there. Raises Busy."""
    def compute():
        data = _get(f'/masters/{int(master_id)}') or {}
        return data.get('main_release')
    return _cached(('main', int(master_id)), compute)


def barcode_search(ean):
    """Releases with this barcode (`ean`: media.normalize_barcode's 13
    digits). Discogs keeps barcodes as printed, so a UPC-A is asked for as
    its 12 digits. Several pressings can share one; best match first.
    Raises Busy."""
    code = ean[1:] if len(ean) == 13 and ean.startswith('0') else ean
    return _cached(('barcode', code), lambda: _rows(
        _get('/database/search', barcode=code, type='release', per_page=5)))


def release_details(release_id):
    """Form fields for one Discogs release, and its cover candidates:
    (details, covers), or (None, []) if Discogs doesn't know it."""
    def compute():
        r = _get(f'/releases/{int(release_id)}')
        if not r:
            return None
        labels = r.get('labels') or []
        label = labels[0] if labels else {}
        catno = (label.get('catno') or '').strip()
        notes = [tracklist(r)]
        where = ' '.join(str(x) for x in (r.get('country'), r.get('year') or None) if x)
        if where:
            notes.append(f'Pressing: {where}')
        genres = (r.get('genres') or []) + (r.get('styles') or [])
        return {
            'details': {
                'title': r.get('title') or '',
                'subtitle': '',
                'author': _artists(r.get('artists')),
                'publisher': _artist_name(label.get('name')),
                'catalog_number': '' if catno.lower() == 'none' else catno,
                'year': r.get('year') or '',
                'runtime_minutes': _length_minutes(r) or '',
                'format': album_format(_format_words(r.get('formats'))) or '',
                'genre': genres[0] if genres else '',
                'description': '\n\n'.join(n for n in notes if n),
            },
            'covers': _covers(r),
        }
    hit = _cached(('release', int(release_id)), compute)
    if not hit:
        return None, []
    return dict(hit['details']), list(hit['covers'])


def lookup(release_id):
    """Pre-fill for Add Album from a picked Discogs release; the same shape
    as music_lookup.lookup. Raises Busy."""
    details, covers = release_details(release_id)
    if not details:
        return {'found': False, 'details': {}, 'sources': [], 'cover': None}
    cover = book_utils.save_best_cover(covers)
    return {'found': True, 'details': details, 'sources': ['Discogs'], 'cover': cover}

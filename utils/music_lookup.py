"""Music lookups (Phase 8.7, CDs and cassettes since 8B.1): MusicBrainz for
release data, the Cover Art Archive for covers. Open data, no API key.

Add Album's Search tab lists physical releases (vinyl, CD, cassette, or one
of them: the format choice beside the search box) matching what was typed
(each word must be in the artist or the title), one row per pressing:
format, label, cat. no., year and country tell the pressings apart. Picking
one fetches the release and fills the form: artist, title, label, cat. no.,
year, format, length (summed track lengths), tracklist, genre, cover.

MusicBrainz rules (https://musicbrainz.org/doc/MusicBrainz_API/Rate_Limiting):
  - a User-Agent naming the application and a contact (MUSICBRAINZ_CONTACT
    in .env, default the project's URL);
  - at most one request a second per client. Each process waits its turn
    (_throttle); with several gunicorn workers a short burst could still
    pass, which for one household doesn't happen in practice. A 503 is
    MusicBrainz saying "slow down": Busy, and the page says try again.
Results are cached per process for 6 hours, so paging back and forth
through the form doesn't ask again.

Every request goes through book_utils._get_public (public hosts only,
checked on every redirect hop), every image through save_best_cover.
Search-result covers are shown through /books/thumbnail, which allows
coverartarchive.org (book_utils.THUMBNAIL_HOSTS).
"""
import json
import os
import threading
import time
from urllib.parse import urlencode

from flask import current_app

from utils import book_utils
from utils import media
from utils.search import JOINERS, by_or_plain, fits

MB_API = 'https://musicbrainz.org/ws/2'
CAA = 'https://coverartarchive.org'
MAX_JSON_BYTES = 2 * 1024 * 1024
MIN_INTERVAL = 1.1          # seconds between requests (MusicBrainz allows 1/s)
PAGE = 12                   # Search tab rows per page ("Show more" asks for the next)
BROWSE = 50                 # an album's releases per request (they're filtered after)
CACHE_SECONDS = 6 * 3600

# MusicBrainz's `format` field matches whole values only: "Vinyl" doesn't
# match '12" Vinyl' and "CD" doesn't match "Enhanced CD", so every variant
# we'd store as that format is listed. Keys are the Search tab's format
# choice (?format=); the choice "" searches all of them.
MB_FORMATS = {
    'vinyl': ('Vinyl', '12" Vinyl', '10" Vinyl', '7" Vinyl'),
    # A hybrid SACD lists one medium per layer: 'Hybrid SACD (CD layer)', ...
    'cd': ('CD', 'Enhanced CD', 'HDCD', 'SHM-CD', 'Blu-spec CD', 'Copy Control CD',
           'Hybrid SACD (CD layer)', 'SACD', 'CD-R'),
    'cassette': ('Cassette',),
}


class Busy(Exception):
    """MusicBrainz is rate limiting us (503) or not answering."""


def user_agent():
    contact = (os.environ.get('MUSICBRAINZ_CONTACT') or '').strip() or 'https://github.com/philcifone/libaraxia'
    return f'Libaraxia/1.0 ( {contact} )'


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


def _mb(path, **params):
    """GET MusicBrainz JSON. None for a miss (404); Busy for 503 or no answer."""
    params['fmt'] = 'json'
    url = f'{MB_API}{path}?{urlencode(params)}'
    _throttle()
    try:
        response = book_utils._get_public(url, headers={'User-Agent': user_agent(),
                                                        'Accept': 'application/json'})
    except Exception as e:
        current_app.logger.warning(f'MusicBrainz {path} failed: {e.__class__.__name__}')
        raise Busy() from e
    if response is None:
        raise Busy()
    try:
        if response.status_code in (429, 503):
            raise Busy()
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            current_app.logger.info(f'MusicBrainz {path} returned {response.status_code}')
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

def _escape(term):
    """A word safe inside a Lucene query: its special characters escaped."""
    return ''.join('\\' + ch if ch in '+-&|!(){}[]^"~*?:\\/' else ch for ch in term)


def _words(text):
    """The query words, escaped, joining words left out, at most ten."""
    return [_escape(w) for w in (text or '').split() if w.strip() and w.lower() not in JOINERS][:10]


def _formats(kind):
    """The MusicBrainz media formats that count as `kind` ('' = all ours)."""
    return MB_FORMATS[kind] if kind in MB_FORMATS else \
        tuple(f for group in MB_FORMATS.values() for f in group)


def build_query(text, kind=''):
    """'joni mitchell blue' -> every word in the artist or the title, physical
    releases of `kind` ('vinyl', 'cd', 'cassette'; '' = any of them). Words,
    not a phrase, so 'mitchell blue' finds it too."""
    terms = [f'(release:{w} OR artist:{w})' for w in _words(text)]
    formats = ' OR '.join('"' + f.replace('"', '\\"') + '"' for f in _formats(kind))
    return ' AND '.join(terms + [f'format:({formats})'])


def album_query(text, split=None):
    """The release-group query for the Search tab's albums: every word in
    the album title or the artist, or with `split` (title, artist) each in
    its own field. Release groups have no format to filter on."""
    if split:
        title, artist = split
        terms = [f'releasegroup:{w}' for w in _words(title)] + [f'artist:{w}' for w in _words(artist)]
    else:
        terms = [f'(releasegroup:{w} OR artist:{w})' for w in _words(text)]
    return ' AND '.join(terms)


def _artist(credit):
    """An artist-credit list -> 'Simon & Garfunkel'."""
    return ''.join(f"{c.get('name', '')}{c.get('joinphrase', '')}"
                   for c in credit or [] if isinstance(c, dict)).strip()


def _labels(release):
    """(label, cat. no.) of a release's first label entry; '' where missing."""
    for info in release.get('label-info') or []:
        name = ((info.get('label') or {}).get('name') or '').strip()
        catno = (info.get('catalog-number') or '').strip()
        if catno.lower() == '[none]':
            catno = ''
        if name or catno:
            return name, catno
    return '', ''


def _year(date):
    return int(date[:4]) if (date or '')[:4].isdigit() else None


def album_format(release):
    """Our stored format for a release (media.FORMATS[RECORD]): from its
    media formats ('7" Vinyl', 'CD', 'Cassette') and, for vinyl, its release
    group's type (Album, EP, Single). A vinyl single is a 7" unless it says
    12" or 10". A set mixing vinyl with a CD (a bonus disc) counts as vinyl."""
    media_formats = [m.get('format') or '' for m in release.get('media') or []]
    formats = ' '.join(media_formats)
    # By substring, so variants the search list doesn't name still land right
    if 'Vinyl' not in formats:
        if 'CD' in formats:
            return 'CD'
        if 'Cassette' in formats:
            return 'Cassette'
    kind = ((release.get('release-group') or {}).get('primary-type') or '').lower()
    if kind == 'ep':
        return 'EP'
    if '7"' in formats:
        return '7in'
    if '10"' in formats:
        return '10in'
    if kind == 'single':
        return '12in' if '12"' in formats else '7in'
    return 'LP'


def _clock(ms):
    seconds = round(ms / 1000)
    return f'{seconds // 60}:{seconds % 60:02d}'


def tracklist(release):
    """'A1 All I Want (3:32)' per line; sides from the track numbers, and a
    'Disc 2' line between the records of a set."""
    lines = []
    discs = release.get('media') or []
    for i, disc in enumerate(discs):
        if len(discs) > 1:
            lines.append(f'Disc {i + 1}' if not lines else f'\nDisc {i + 1}')
        for track in disc.get('tracks') or []:
            title = track.get('title') or (track.get('recording') or {}).get('title') or ''
            number = track.get('number') or track.get('position') or ''
            length = track.get('length') or (track.get('recording') or {}).get('length')
            lines.append(f"{number} {title}".strip() + (f' ({_clock(length)})' if length else ''))
    return '\n'.join(lines)


def _length_minutes(release):
    total = sum(t.get('length') or 0 for m in release.get('media') or [] for t in m.get('tracks') or [])
    return round(total / 60000) or None


def _genre(release):
    """The release's (or its release group's) most-voted genre, or ''."""
    for source in (release, release.get('release-group') or {}):
        genres = [g for g in source.get('genres') or [] if g.get('name')]
        if genres:
            return max(genres, key=lambda g: g.get('count') or 0)['name'].title()
    return ''


def cover_urls(mbid, group_id=None, size=500):
    """Cover Art Archive front images: this pressing's, then its release
    group's (many pressings have no scans of their own)."""
    urls = [f'{CAA}/release/{mbid}/front-{size}']
    if group_id:
        urls.append(f'{CAA}/release-group/{group_id}/front-{size}')
    return urls


# ------------------------------------------------------------ the lookups

def _release_row(r, group=None):
    """A Search-tab row for one release (a pressing)."""
    label, catno = _labels(r)
    fmt = album_format(r)
    group = group or (r.get('release-group') or {}).get('id')
    return {
        'id': r['id'],
        'title': r.get('title') or '',
        'artist': _artist(r.get('artist-credit')),
        'year': _year(r.get('date')),
        'country': r.get('country') or '',
        'label': label,
        'catalog_number': catno,
        'format': fmt,
        'format_label': media.format_label(fmt),
        # The release group's art: most pressings have none of their own
        'thumb': cover_urls(r['id'], group, 250)[-1],
    }


def search_page(text, kind='', page=1, limit=PAGE):
    """One page of releases matching `text` for the Search tab (of format
    `kind`, see MB_FORMATS; '' = vinyl, CD or cassette): (rows, more), rows
    {'id', 'title', 'artist', 'year', 'country', 'label', 'catalog_number',
     'format', 'format_label', 'thumb'}, best match first. Raises Busy."""
    text = (text or '').strip()
    if len(text) < 2 or not _words(text):
        return [], False

    def compute():
        offset = (page - 1) * limit
        data = _mb('/release/', query=build_query(text, kind), limit=limit, offset=offset) or {}
        found = [r for r in data.get('releases') or [] if r.get('id')]
        return [_release_row(r) for r in found], offset + len(data.get('releases') or []) < (data.get('count') or 0)
    return _cached(('search', kind, text.lower(), page, limit), compute)


def search(text, kind='', limit=12):
    """The first page of search_page, rows only (Do I have this?, the cover
    finder). Raises Busy."""
    return search_page(text, kind, 1, limit)[0]


def albums(text, kind='', page=1, by=None):
    """The Search tab (16.0): albums (release groups) matching `text`, one
    row each, PAGE a page. "X by Y" asks for title X by artist Y
    (utils.search.by_or_plain). `kind` isn't used here (release groups have
    no format); the pressings list narrows by it. (rows, more, by). Raises Busy."""
    text = (text or '').strip()
    if len(text) < 2 or not _words(text):
        return [], False, False

    def run(split, page):
        query = album_query(text, split)
        if not query:
            return [], False

        def compute():
            offset = (page - 1) * PAGE
            data = _mb('/release-group/', query=query, limit=PAGE, offset=offset) or {}
            groups = data.get('release-groups') or []
            rows = [{
                'id': g['id'],
                'source': 'musicbrainz',
                'level': 'album',
                'title': g.get('title') or '',
                'artist': _artist(g.get('artist-credit')),
                'year': _year(g.get('first-release-date')),
                'thumb': f"{CAA}/release-group/{g['id']}/front-250",
            } for g in groups if g.get('id')]
            return rows, offset + len(groups) < (data.get('count') or 0)
        return _cached(('albums', query, page), compute)
    return by_or_plain(text, run, page, by,
                       keep=lambda r, split: fits(split, r['title'], r['artist']))


def pressings(group_id, kind='', page=1):
    """An album's releases (MusicBrainz browses a release group's releases),
    physical ones of format `kind` ('' = any of ours): (rows, more), rows as
    search()'s. BROWSE a request, filtered after, so a page can be short.
    Raises Busy."""
    wanted = set(_formats(kind))

    def compute():
        offset = (page - 1) * BROWSE
        data = _mb('/release', **{'release-group': group_id, 'inc': 'labels+media+release-groups',
                                  'limit': BROWSE, 'offset': offset}) or {}
        releases = data.get('releases') or []
        rows = [_release_row(r, group_id) for r in releases
                if r.get('id') and {m.get('format') for m in r.get('media') or []} & wanted]
        return rows, offset + len(releases) < (data.get('release-count') or 0)
    return _cached(('pressings', group_id, kind, page), compute)


def main_release(group_id, kind=''):
    """The pressing "Use this" on an album row fills the form from: the
    earliest dated one of the first page (of `kind`, if given). None if the
    album has none. Raises Busy."""
    rows = pressings(group_id, kind, 1)[0]
    if not rows:
        return None
    return min(rows, key=lambda r: (r['year'] is None, r['year'] or 0))['id']


def barcode_search(ean):
    """MusicBrainz release ids with this barcode, best match first (`ean`:
    media.normalize_barcode's 13 digits). Releases store the barcode as
    printed, so a UPC-A is asked for both ways. Raises Busy."""
    codes = {ean, ean[1:]} if ean.startswith('0') else {ean}
    query = ' OR '.join(f'barcode:{c}' for c in sorted(codes))

    def compute():
        data = _mb('/release/', query=query, limit=5) or {}
        return [r['id'] for r in data.get('releases') or [] if r.get('id')]
    return _cached(('barcode', ean), compute)


def release_details(mbid):
    """Form fields for one release id, and its cover candidates:
    (details, covers), or (None, []) if MusicBrainz doesn't know it."""
    def compute():
        r = _mb(f'/release/{mbid}', inc='artist-credits+labels+recordings+release-groups+genres')
        if not r:
            return None
        label, catno = _labels(r)
        notes = [tracklist(r)]
        where = ' '.join(str(x) for x in (r.get('country'), _year(r.get('date'))) if x)
        if where:
            notes.append(f'Pressing: {where}')
        group = r.get('release-group') or {}
        return {
            'details': {
                'title': r.get('title') or '',
                'subtitle': (r.get('disambiguation') or '').strip(),
                'author': _artist(r.get('artist-credit')),
                'publisher': label,
                'catalog_number': catno,
                'year': _year(r.get('date')) or _year(group.get('first-release-date')) or '',
                'runtime_minutes': _length_minutes(r) or '',
                'format': album_format(r),
                'genre': _genre(r),
                'description': '\n\n'.join(n for n in notes if n),
            },
            'covers': cover_urls(r['id'], group.get('id')),
        }
    hit = _cached(('release', mbid), compute)
    if not hit:
        return None, []
    return dict(hit['details']), list(hit['covers'])


def lookup(mbid):
    """Pre-fill for the Add Album form from a picked release. Same shape as
    media_lookup.lookup: {'found', 'details', 'sources', 'cover'}; `cover` is
    a saved file under static/uploads (the form sends it back as
    existing_cover_url, which process_image re-checks). Raises Busy."""
    details, covers = release_details(mbid)
    if not details:
        return {'found': False, 'details': {}, 'sources': [], 'cover': None}
    # Covers are downloaded per call (a cached path could have been cleaned up)
    cover = book_utils.save_best_cover(covers)
    sources = ['MusicBrainz'] + (['Cover Art Archive'] if cover else [])
    return {'found': True, 'details': details, 'sources': sources, 'cover': cover}

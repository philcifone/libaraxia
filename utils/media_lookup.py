"""Video lookups (Phase 8.2): barcode -> UPCitemdb -> TMDb.

Manual entry is the main path; this only pre-fills the Add Video form.
Coverage for VHS barcodes is patchy, so every step may come back empty and
the caller then just shows the form with the barcode filled in.

    1. UPCitemdb (free trial endpoint, no key; about 100 lookups a day and
       a few a minute) turns a UPC/EAN into a product title such as
       "Jaws [VHS]", the brand (the studio/distributor) and sleeve photos.
    2. The title is cleaned of tape noise ("[VHS]", "Widescreen", "(1975)").
    3. TMDb (needs TMDB_API_KEY in .env; optional) finds the film by title
       and year: director, runtime, synopsis, genre, poster.

Merging keeps what belongs to the tape from UPCitemdb (studio, barcode,
sleeve photo first) and the film data from TMDb. TMDb also serves the
title-only lookup for tapes with no barcode.

Every request goes through book_utils._get_public (public hosts only,
checked on every redirect hop) and every image through save_best_cover
(same guard, placeholder check, resized and stored under static/uploads).
TMDb's key is sent as a Bearer header when it's a v4 read access token, so
it never appears in a URL or a log line; a v3 key has to go in the query.
"""
import json
import os
import re
import time
from urllib.parse import urlencode

from flask import current_app

from utils import book_utils
from utils import media

UPCITEMDB_URL = 'https://api.upcitemdb.com/prod/trial/lookup'
TMDB_API = 'https://api.themoviedb.org/3'
TMDB_IMAGES = 'https://image.tmdb.org/t/p/w500'
TMDB_THUMBS = 'https://image.tmdb.org/t/p/w185'     # search results
MAX_JSON_BYTES = 2 * 1024 * 1024

# Lookups are cached per process for a while: UPCitemdb's daily allowance
# is small, and re-scanning the same tape shouldn't spend it again.
CACHE_SECONDS = 6 * 3600
_cache = {}


def tmdb_key():
    return (os.environ.get('TMDB_API_KEY') or '').strip()


# ------------------------------------------------------------ HTTP

def _get_json(url, params=None, headers=None):
    """GET JSON through the SSRF guard. None on any failure (logged without
    the query string, so a key in it never reaches the log)."""
    full = f'{url}?{urlencode(params)}' if params else url
    try:
        response = book_utils._get_public(full, headers=headers)
        if response is None:
            return None
        if response.status_code != 200:
            current_app.logger.info(f'Lookup {url} returned {response.status_code}')
            return None
        body = response.raw.read(MAX_JSON_BYTES + 1, decode_content=True)
        if len(body) > MAX_JSON_BYTES:
            return None
        return json.loads(body)
    except Exception as e:
        current_app.logger.warning(f'Lookup {url} failed: {e.__class__.__name__}')
        return None


def _tmdb(path, **params):
    key = tmdb_key()
    if not key:
        return None
    headers = None
    if len(key) > 40:                       # v4 read access token (a JWT)
        headers = {'Authorization': f'Bearer {key}', 'Accept': 'application/json'}
    else:                                   # v3 API key
        params['api_key'] = key
    return _get_json(f'{TMDB_API}{path}', params, headers)


# ------------------------------------------------------------ titles

# Words that describe the tape, not the film, matched case-insensitively as
# whole words. STRONG ones never belong to a film title and go anywhere;
# WEAK ones can ("A New Hope", "My Pal Trigger", "Stereo"), so they only go
# when they're inside brackets with other tape notes: "(Used, PAL)".
_STRONG = [
    r'vhs(?:\s+tape)?', r'dvd', r'blu-?ray', r'laser\s*disc', r'betamax', r'video\s*cassette', r'videotape', r'ntsc',
    r'widescreen', r'full\s*screen', r'letterbox(?:ed)?', r'pan\s*(?:and|&)\s*scan',
    r'hi-?fi', r'clamshell', r'slipcase', r'digitally\s+remastered',
    r'(?:special|collector\'?s?|limited|deluxe)\s+edition',
    r'(?:\d+(?:st|nd|rd|th)\s+)?anniversary\s+edition',
]
_WEAK = [r'pal', r'secam', r'stereo', r'mono', r'new', r'used', r'sealed', r'rare', r'oop',
         r'edition', r'remastered', r'director\'?s\s+cut', r'special', r'collector\'?s?']
_STRONG_RE = re.compile(r'\b(?:' + '|'.join(_STRONG) + r')\b', re.IGNORECASE)
_ANY_RE = re.compile(r'\b(?:' + '|'.join(_STRONG + _WEAK) + r')\b', re.IGNORECASE)
_YEAR_RE = re.compile(r'[\(\[]\s*((?:19|20)\d{2})\s*[\)\]]')


def clean_title(raw):
    """("Jaws (1975) [VHS] Widescreen") -> ("Jaws", 1975).

    Removes bracketed tape notes, a "(year)", the noise words above and the
    punctuation they leave behind. Returns (title, year or None)."""
    raw = raw or ''
    # Sellers append keywords after the format: "Goodfellas [DVD]  Feature
    # Thriller Drama". A bracket naming a format ends the title.
    fmt = re.search(r'[\(\[]\s*(?:vhs|dvd|blu-?ray|laser\s*disc|betamax)\b[^\)\]]*[\)\]]', raw, re.IGNORECASE)
    if fmt and fmt.start() > 0:
        tail = _YEAR_RE.search(raw[fmt.end():])          # keep a "(1975)" after it
        raw = raw[:fmt.start()] + (f' ({tail.group(1)})' if tail else '')
    year_match = _YEAR_RE.search(raw)
    year = int(year_match.group(1)) if year_match else None
    title = _YEAR_RE.sub(' ', raw)
    # Brackets holding only tape notes ("[VHS]", "(Used, PAL)") go entirely
    title = re.sub(r'[\(\[]([^\)\]]*)[\)\]]',
                   lambda m: ' ' if not _ANY_RE.sub('', m.group(1)).strip(' ,-/&') else m.group(0),
                   title)
    title = _STRONG_RE.sub(' ', title)
    # "Widescreen Edition" leaves a bare "Edition" at the end
    title = re.sub(r'[\s,-]+edition\s*$', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\s*[-:/|,]+\s*$', '', re.sub(r'\s+', ' ', title)).strip(' -:/|,')
    title = re.sub(r'[\(\[]\s*[\)\]]', '', title).strip()
    return title or raw.strip(), year


# ------------------------------------------------------------ sources

def upcitemdb(barcode):
    """{'title', 'brand', 'description', 'category', 'images'} for a
    barcode, or None. `category` is UPCitemdb's ("Media > Music & Sound
    Recordings"): Do I have this? uses it to tell a CD from a film."""
    ean = media.normalize_barcode(barcode)
    if not ean:
        return None
    # UPCitemdb knows UPC-A as 12 digits
    code = ean[1:] if ean.startswith('0') else ean
    data = _get_json(UPCITEMDB_URL, {'upc': code})
    items = (data or {}).get('items') or []
    if not items:
        return None
    item = items[0]
    return {
        'title': (item.get('title') or '').strip(),
        'brand': (item.get('brand') or item.get('publisher') or '').strip(),
        'description': (item.get('description') or '').strip(),
        'category': (item.get('category') or '').strip(),
        'images': [u for u in (item.get('images') or []) if isinstance(u, str)][:5],
    }


def tmdb_search(query, year=None, limit=8):
    """Films matching a title, for the Add Movie page's Search tab: a list of
    {'id', 'title', 'year', 'poster'} (poster is a small TMDb image URL,
    shown through /books/thumbnail), best match first. [] without a key."""
    if not query or not tmdb_key():
        return []
    params = {'query': query, 'include_adult': 'false'}
    if year:
        params['year'] = year
    results = (_tmdb('/search/movie', **params) or {}).get('results') or []
    films = []
    for r in results[:limit]:
        if not isinstance(r.get('id'), int):
            continue
        release = r.get('release_date') or ''
        films.append({
            'id': r['id'],
            'title': r.get('title') or '',
            'year': int(release[:4]) if release[:4].isdigit() else None,
            'poster': f"{TMDB_THUMBS}{r['poster_path']}" if r.get('poster_path') else None,
        })
    return films


def tmdb_details(movie_id, fallback_title=''):
    """Film data for one TMDb id: director, year, runtime, synopsis, genre,
    poster. None if TMDb doesn't answer."""
    if not tmdb_key():
        return None
    movie = _tmdb(f"/movie/{int(movie_id)}", append_to_response='credits')
    if not movie:
        return None
    crew = (movie.get('credits') or {}).get('crew') or []
    directors = [c.get('name') for c in crew if c.get('job') == 'Director' and c.get('name')]
    genres = [g.get('name') for g in movie.get('genres') or [] if g.get('name')]
    release = movie.get('release_date') or ''
    return {
        'title': movie.get('title') or fallback_title,
        'director': ', '.join(directors[:2]),
        'year': int(release[:4]) if release[:4].isdigit() else None,
        'runtime': movie.get('runtime') or None,
        'description': (movie.get('overview') or '').strip(),
        'genre': genres[0] if genres else '',
        'poster': f"{TMDB_IMAGES}{movie['poster_path']}" if movie.get('poster_path') else None,
    }


def tmdb_movie(title, year=None):
    """Film data for a title (and year, if known), or None.

    Tries with the year first, then without: a tape's "(1985)" is often
    the video release, not the film's."""
    if not title or not tmdb_key():
        return None
    results = []
    if year:
        results = ((_tmdb('/search/movie', query=title, year=year, include_adult='false') or {})
                   .get('results') or [])
    if not results:
        results = ((_tmdb('/search/movie', query=title, include_adult='false') or {})
                   .get('results') or [])
    if not results:
        return None
    return tmdb_details(results[0]['id'], title)


# ------------------------------------------------------------ the lookup

def _cached(key, compute):
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_SECONDS:
        return hit[1]
    value = compute()
    # Only hits are kept: a miss may be UPCitemdb's rate limit, so try again later
    if value.get('found'):
        if len(_cache) > 500:
            _cache.clear()
        _cache[key] = (time.time(), value)
    return value


def _merge(barcode, upc, film):
    """Form fields from what the sources found (either may be None)."""
    upc = upc or {}
    film = film or {}
    cleaned, year = clean_title(upc.get('title'))
    details = {
        'barcode': media.normalize_barcode(barcode) if barcode else '',
        'title': film.get('title') or cleaned or '',
        'author': film.get('director') or '',
        'publisher': upc.get('brand') or '',
        'year': film.get('year') or year or '',
        'runtime_minutes': film.get('runtime') or '',
        'genre': film.get('genre') or '',
        'description': film.get('description') or upc.get('description') or '',
        'format': media.DEFAULT_VIDEO_FORMAT,
    }
    # Sleeve photos of this tape first, then the film's poster
    covers = list(upc.get('images') or []) + ([film['poster']] if film.get('poster') else [])
    return details, covers


def lookup(barcode=None, title=None, year=None, tmdb_id=None):
    """Pre-fill for the Add Movie form: by barcode (UPCitemdb, then TMDb on
    the cleaned title), by title (TMDb only), or by a TMDb id picked from
    the Search tab's results.

    Returns {'found': bool, 'details': {...}, 'sources': [...], 'cover': path
    or None}. `cover` is a saved file under static/uploads; the form sends
    it back as existing_cover_url, which process_image re-checks.
    """
    if tmdb_id:
        key = ('tmdb', int(tmdb_id))
    elif barcode:
        key = ('barcode', media.normalize_barcode(barcode))
    else:
        key = ('title', (title or '').lower(), year)

    def compute():
        sources = []
        upc = upcitemdb(barcode) if barcode and not tmdb_id else None
        if upc:
            sources.append('UPCitemdb')
        if tmdb_id:
            film = tmdb_details(tmdb_id)
        else:
            query, query_year = (clean_title(upc['title']) if upc else (title, year))
            film = tmdb_movie(query, query_year or year)
        if film:
            sources.append('TMDb')
        details, covers = _merge(barcode, upc, film)
        return {'found': bool(sources), 'details': details, 'sources': sources, 'covers': covers}

    result = dict(_cached(key, compute))
    # Covers are downloaded per call (a cached path could have been cleaned up)
    result['cover'] = book_utils.save_best_cover(result.pop('covers')) if result['found'] else None
    return result

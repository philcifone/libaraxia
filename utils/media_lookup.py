"""Video lookups (Phase 8.2): barcode -> UPCitemdb -> TMDb.

Manual entry is the main path; this only pre-fills the Add Video form.
Coverage for VHS barcodes is patchy, so every step may come back empty and
the caller then just shows the form with the barcode filled in.

    1. UPCitemdb (free trial endpoint, no key; about 100 lookups a day and
       a few a minute) turns a UPC/EAN into a product title such as
       "Jaws [VHS]", the brand (the studio/distributor) and sleeve photos.
    2. The title is cleaned of tape noise ("[VHS]", "Widescreen", "(1975)").
    3. TMDb (needs TMDB_API_KEY in .env; optional) finds the film or TV
       show by title and year: director (a show's creators), runtime,
       synopsis, genre, poster. Movies and TV are searched together
       (/search/multi, ROADMAP 15.1); a box set's "Season 2" is taken off
       the title first (split_season) and fills the form's Season.

Each result says its kind ('movie' / 'tv'), which fills the form's Kind.
TMDb numbers movies and shows separately, so a picked id travels with its
kind. A show's runtime is left empty: which episodes a set holds isn't
known, and a per-episode figure would read as the whole set's.

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


# A box set's season in a product title: "The Wire: The Complete First
# Season", "Friends - Season 3", "Twin Peaks Complete Series". Matched from
# the season words to the end of the title.
_ORDINALS = {'first': 1, 'second': 2, 'third': 3, 'fourth': 4, 'fifth': 5, 'sixth': 6,
             'seventh': 7, 'eighth': 8, 'ninth': 9, 'tenth': 10}
_SEASON_RE = re.compile(
    r'[\s:,\-\u2013]*\b(?:the\s+)?(?:'
    r'complete\s+(?P<series>series)'
    r'|(?:complete\s+)?(?P<ord>' + '|'.join(_ORDINALS) + r'|\d+(?:st|nd|rd|th))\s+season'
    # a range, unless it's a disc count ("Season 1 - 5 Disc Set")
    # two ("Season 1 & 2", "Seasons 1 and 2") before a range
    r'|seasons?\s+(?P<pair>\d+\s*(?:&|and)\s*\d+)'
    r'|seasons?\s+(?P<num>\d+(?:\s*[-\u2013]\s*\d+(?!\s*-?\s*discs?\b))?)'
    r')\b.*$', re.IGNORECASE)


def split_season(title):
    """("The Wire: The Complete First Season") -> ("The Wire", "Season 1").

    The title without its season words, and the season as the form stores
    it ("Season 2", "Seasons 1-3", "Complete series"), or None when the
    title names no season (then it's returned unchanged)."""
    title = title or ''
    found = _SEASON_RE.search(title)
    if not found or found.start() == 0:
        return title, None
    if found.group('series'):
        season = 'Complete series'
    elif found.group('pair'):
        first, second = re.findall(r'\d+', found.group('pair'))   # "1 and 2" -> "Seasons 1 & 2"
        season = f'Seasons {first} & {second}'
    elif found.group('ord'):
        word = found.group('ord').lower()                  # 'first', or '2nd'
        number = _ORDINALS.get(word) or int(word[:-2])
        season = f'Season {number}'
    else:
        number = re.sub(r'\s+', '', found.group('num'))    # '2', or a range '1-3'
        is_range = any(dash in number for dash in '-\u2013')
        season = f"{'Seasons' if is_range else 'Season'} {number}"
    return title[:found.start()].strip(' :,-\u2013'), season


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
    """Movies and TV shows matching a title, for the Add page's Search tab
    and Do I have this?: a list of {'id', 'kind', 'title', 'year', 'poster'}
    (kind 'movie' / 'tv'; poster a small TMDb image URL, shown through
    /books/thumbnail), best match first. [] without a key.

    One /search/multi call, in TMDb's own order (people are dropped). A
    year puts that year's results first rather than filtering: a tape's
    year is often the video release, not the film's."""
    if not query or not tmdb_key():
        return []
    found = _tmdb_multi(query, 1)[0]
    if year:
        found.sort(key=lambda f: f['year'] != year)       # stable: TMDb's order otherwise
    return found[:limit]


def _tmdb_multi(query, tmdb_page):
    """One page of TMDb's /search/multi (20 a page, people dropped): (rows,
    total pages)."""
    data = _tmdb('/search/multi', query=query, include_adult='false', page=tmdb_page) or {}
    found = []
    for r in data.get('results') or []:
        kind = {'movie': media.MOVIE, 'tv': media.TV}.get(r.get('media_type'))
        if not kind or not isinstance(r.get('id'), int):
            continue
        # Movies have a title and release date, shows a name and first air date
        release = (r.get('release_date') if kind == media.MOVIE else r.get('first_air_date')) or ''
        found.append({
            'id': r['id'],
            'kind': kind,
            'title': (r.get('title') if kind == media.MOVIE else r.get('name')) or '',
            'year': int(release[:4]) if release[:4].isdigit() else None,
            'poster': f"{TMDB_THUMBS}{r['poster_path']}" if r.get('poster_path') else None,
        })
    return found, data.get('total_pages') or 0


SEARCH_PAGE = 10    # Add Movie's Search tab: rows per page, half a TMDb page


def tmdb_search_page(query, page=1):
    """One page of Add Movie's Search tab (16.0, "Show more"): (rows, more),
    rows as tmdb_search's. Our page n is one half of TMDb's page (n + 1) // 2."""
    if not query or not tmdb_key():
        return [], False
    tmdb_page, second_half = (page + 1) // 2, page % 2 == 0
    rows, pages = _tmdb_multi(query, tmdb_page)
    half = rows[SEARCH_PAGE:] if second_half else rows[:SEARCH_PAGE]
    more = (not second_half and len(rows) > SEARCH_PAGE) or tmdb_page < pages
    return half, more


def tmdb_details(tmdb_id, fallback_title='', kind=None):
    """Data for one TMDb id: director (a show's creators), year, runtime,
    synopsis, genre, poster and 'kind'. `kind` 'tv' asks TMDb's TV numbering
    (tmdb_tv_details), anything else its movies. None if TMDb doesn't answer."""
    if not tmdb_key():
        return None
    if kind == media.TV:
        return tmdb_tv_details(tmdb_id, fallback_title)
    movie = _tmdb(f"/movie/{int(tmdb_id)}", append_to_response='credits')
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
        'kind': media.MOVIE,
    }


def tmdb_tv_details(show_id, fallback_title=''):
    """A TV show's data, the same keys as a film's: its creators in
    'director' (the form's Creator), the first air year, no runtime (see the
    module docstring). None if TMDb doesn't answer."""
    show = _tmdb(f"/tv/{int(show_id)}")
    if not show:
        return None
    creators = [c.get('name') for c in show.get('created_by') or [] if c.get('name')]
    genres = [g.get('name') for g in show.get('genres') or [] if g.get('name')]
    aired = show.get('first_air_date') or ''
    return {
        'title': show.get('name') or fallback_title,
        'director': ', '.join(creators[:2]),
        'year': int(aired[:4]) if aired[:4].isdigit() else None,
        'runtime': None,
        'description': (show.get('overview') or '').strip(),
        'genre': genres[0] if genres else '',
        'poster': f"{TMDB_IMAGES}{show['poster_path']}" if show.get('poster_path') else None,
        'kind': media.TV,
    }


def tmdb_movie(title, year=None, kind=None):
    """Movie or TV data for a title (and year, if known), or None: TMDb's
    best match of either kind (tmdb_search). `kind` 'tv' (the title named a
    season) prefers a show when there is one."""
    if not title or not tmdb_key():
        return None
    results = tmdb_search(title, year)
    if kind == media.TV:
        results = [r for r in results if r['kind'] == media.TV] or results
    if not results:
        return None
    return tmdb_details(results[0]['id'], title, results[0]['kind'])


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
    cleaned, season = split_season(cleaned)
    # TMDb's kind, else a season in the product's name makes it TV
    kind = film.get('kind') or (media.TV if season else media.MOVIE)
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
        'video_kind': kind,
        'season': season if kind == media.TV and season else '',
    }
    # Sleeve photos of this tape first, then the film's poster
    covers = list(upc.get('images') or []) + ([film['poster']] if film.get('poster') else [])
    return details, covers


def lookup(barcode=None, title=None, year=None, tmdb_id=None, kind=None):
    """Pre-fill for the Add Movie or Show form: by barcode (UPCitemdb, then
    TMDb on the cleaned title), by title (TMDb only), or by a TMDb id picked
    from the Search tab's results (`kind` 'tv' for a show's id).

    Returns {'found': bool, 'details': {...}, 'sources': [...], 'cover': path
    or None}. `cover` is a saved file under static/uploads; the form sends
    it back as existing_cover_url, which process_image re-checks.
    """
    kind = media.TV if kind == media.TV else media.MOVIE
    if tmdb_id:
        key = ('tmdb', kind, int(tmdb_id))
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
            film = tmdb_details(tmdb_id, kind=kind)
        else:
            query, query_year = (clean_title(upc['title']) if upc else (title, year))
            query, season = split_season(query)
            film = tmdb_movie(query, query_year or year, media.TV if season else None)
        if film:
            sources.append('TMDb')
        details, covers = _merge(barcode, upc, film)
        return {'found': bool(sources), 'details': details, 'sources': sources, 'covers': covers}

    result = dict(_cached(key, compute))
    # Covers are downloaded per call (a cached path could have been cleaned up)
    result['cover'] = book_utils.save_best_cover(result.pop('covers')) if result['found'] else None
    return result

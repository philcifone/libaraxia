"""Covers for the background fetcher (utils/cover_jobs.py), any media type.

Books are looked up by ISBN (book_utils.fetch_cover_for_book). Movies and
albums mostly have no such key, so the fetcher only keeps a cover it can
trust, because a wrong cover on the shelf is worse than none:

  movie  a barcode: UPCitemdb's photos of that product. Then TMDb's poster
         for the title (and year), only if the film TMDb returns has the
         same title.
  album  a barcode: the release Discogs (or MusicBrainz) files under it.
         Otherwise artist + title searched on Discogs (MusicBrainz without
         a token, or when Discogs is busy), and only a release with the same
         title by the same artist counts. An album without a barcode needs
         its artist: a bare title ("Blue") matches too many records.

"Find a better cover" on the movie and album add and edit pages uses the
same sources (cover_search_steps), but there the user picks, so it offers
the best few matches of each search instead of only exact ones.

"Same title" (same_title) compares the folded words, ignoring a leading
article and anything in brackets on either side ("Rumours (Remastered)" is
Rumours), and nothing else: "Jaws 2" is not Jaws. Each source's own module
rate-limits and caches; a source that's busy counts as not found, and the
next run tries the item again.
"""
import logging
import re

from utils import book_utils, discogs_lookup, media, media_lookup, music_lookup
from utils.have_online import words

logger = logging.getLogger(__name__)

ARTICLES = {'the', 'a', 'an'}
_BRACKETS = re.compile(r'\([^)]*\)|\[[^\]]*\]')

# The Discogs / MusicBrainz search kind for an album's stored format
_SEARCH_KIND = {'CD': 'cd', 'Cassette': 'cassette'}      # anything else is vinyl


def _core(text):
    """The words that make a title or name: folded, brackets and a leading
    article dropped. 'The Wall (Remastered)' -> ['wall']."""
    w = words(_BRACKETS.sub(' ', text or ''))
    return w[1:] if len(w) > 1 and w[0] in ARTICLES else w


def same_title(ours, theirs):
    """True when two titles are the same once folded (see the module docstring)."""
    a, b = _core(ours), _core(theirs)
    return bool(a) and a == b


def same_artist(ours, theirs):
    """True when every word of our artist is in theirs ('Joni Mitchell' in
    'Joni Mitchell'; 'Simon Garfunkel' in 'Simon & Garfunkel'). Discogs
    numbers duplicate names ('Nirvana (2)'), which the brackets rule drops."""
    a, b = _core(ours), set(_core(theirs))
    return bool(a) and all(w in b for w in a)


# ------------------------------------------------------------ movies

def video_cover_urls(item):
    """Cover candidates for a movie, best first; [] when none can be trusted."""
    urls = []
    if item['barcode']:
        upc = media_lookup.upcitemdb(item['barcode'])
        if upc:
            urls += upc.get('images') or []
    if media_lookup.tmdb_key() and item['title']:
        film = media_lookup.tmdb_movie(item['title'], item['publish_year'])
        if film and film.get('poster') and same_title(item['title'], film.get('title')):
            urls.append(film['poster'])
    return urls


# ------------------------------------------------------------ albums

def _discogs_release_covers(rows, item, check):
    """Covers of the first Discogs row that passes; [] if none does."""
    for row in rows:
        if not check or (same_title(item['title'], row.get('title'))
                         and same_artist(item['author'], row.get('artist'))):
            return discogs_lookup.release_details(row['id'])[1]
    return []


def _mb_release_covers(rows, item):
    for row in rows:
        if same_title(item['title'], row.get('title')) and same_artist(item['author'], row.get('artist')):
            return music_lookup.release_details(row['id'])[1]
    return []


def album_cover_urls(item):
    """Cover candidates for an album, best first; [] when none can be trusted."""
    ean = (media.normalize_barcode(item['barcode']) if item['barcode'] else None) or ''
    kind = _SEARCH_KIND.get(item['format'] or '', 'vinyl')
    query = f"{item['author'] or ''} {item['title'] or ''}".strip()
    use_discogs = discogs_lookup.enabled()

    # The barcode names the very release: no title check needed
    if ean:
        if use_discogs:
            try:
                covers = _discogs_release_covers(discogs_lookup.barcode_search(ean), item, check=False)
                if covers:
                    return covers
            except discogs_lookup.Busy:
                pass
        try:
            ids = music_lookup.barcode_search(ean)
            if ids:
                covers = music_lookup.release_details(ids[0])[1]
                if covers:
                    return covers
        except music_lookup.Busy:
            pass

    if not item['author']:
        return []
    if use_discogs:
        try:
            return _discogs_release_covers(discogs_lookup.search(query, kind), item, check=True)
        except discogs_lookup.Busy:
            pass
    try:
        return _mb_release_covers(music_lookup.search(query, kind), item)
    except music_lookup.Busy:
        return []


# ------------------------------------------------------------ the fetcher's entry

def fetch_cover(conn, item):
    """Look up and save a cover for one item (a books row with id, title,
    author, isbn, barcode, format, publish_year, media_type). Commits and
    returns True when a cover was saved. Network: call it from
    utils/cover_jobs.py, never inside a request."""
    if item['media_type'] == media.BOOK:
        return book_utils.fetch_cover_for_book(conn, item)
    try:
        urls = video_cover_urls(item) if item['media_type'] == media.VIDEO else album_cover_urls(item)
    except Exception:
        logger.exception(f"Error looking up a cover for '{item['title']}'")
        return False
    path = book_utils.save_best_cover(urls) if urls else None
    return bool(path) and book_utils.store_found_cover(conn, item['id'], path)


# ------------------------------------------------------------ "Find a better cover"

PICK_LIMIT = 4          # results per search offered on the add / edit pages


def _best_first(rows, title, artist=''):
    """Search rows with exact matches first (same title, and artist if
    given), each group in the source's order; the first PICK_LIMIT."""
    def exact(r):
        return same_title(title, r.get('title')) and (not artist or same_artist(artist, r.get('artist')))
    return sorted(rows, key=lambda r: not exact(r))[:PICK_LIMIT]


def _release_label(source, row):
    """'Discogs: LP, US, 1971' -- what tells pressings apart."""
    bits = [row.get('format_label'), row.get('country'), str(row.get('year') or '')]
    detail = ', '.join(b for b in bits if b)
    return f'{source}: {detail}' if detail else source


def cover_search_steps(media_type, title='', author='', barcode='', year=None, fmt=''):
    """The movie / album cover search as named steps, the same shape as
    book_utils.cover_search_steps: [(label, run)], where run() returns
    [(url, source), ...]. Nothing is fetched until a step runs; a step may
    raise (Busy, a timeout) and the caller carries on with the next."""
    ean = (media.normalize_barcode(barcode) if barcode else None) or ''
    steps = []
    if media_type == media.VIDEO:
        if ean:
            def upc():
                found = media_lookup.upcitemdb(ean) or {}
                return [(u, 'UPCitemdb (barcode)') for u in found.get('images') or []]
            steps.append(('UPCitemdb', upc))
        if title and media_lookup.tmdb_key():
            def tmdb():
                films = media_lookup.tmdb_search(title, year, limit=8) or media_lookup.tmdb_search(title, limit=8)
                return [(f['poster'].replace(media_lookup.TMDB_THUMBS, media_lookup.TMDB_IMAGES),
                         f"TMDb: {f['title']}" + (f" ({f['year']})" if f.get('year') else ''))
                        for f in _best_first(films, title) if f.get('poster')]
            steps.append(('TMDb', tmdb))
        return steps

    kind = _SEARCH_KIND.get(fmt or '', 'vinyl') if fmt else ''
    query = f'{author or ""} {title or ""}'.strip()
    if discogs_lookup.enabled() and (ean or query):
        def discogs():
            rows = discogs_lookup.barcode_search(ean)[:PICK_LIMIT] if ean else []
            if query:
                rows += _best_first(discogs_lookup.search(query, kind), title, author)
            found = []
            for row in rows:
                covers = discogs_lookup.release_details(row['id'])[1]
                found += [(u, _release_label('Discogs', row)) for u in covers[:1]]
            return found
        steps.append(('Discogs', discogs))
    if ean or query:
        def musicbrainz():
            found = []
            if ean:
                found += [(u, 'MusicBrainz (barcode)')
                          for mbid in music_lookup.barcode_search(ean)[:PICK_LIMIT]
                          for u in music_lookup.cover_urls(mbid)]
            if query:
                for row in _best_first(music_lookup.search(query, kind), title, author):
                    # The thumb is the release group's art; ask for the pressing's first
                    group = row.get('thumb') or ''
                    found.append((music_lookup.cover_urls(row['id'])[0], _release_label('MusicBrainz', row)))
                    if group:
                        found.append((group.replace('-250', '-500'), _release_label('MusicBrainz', row) + ' (album)'))
            return found
        steps.append(('MusicBrainz', musicbrainz))
    return steps

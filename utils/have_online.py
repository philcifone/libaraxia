"""Do I have this? "Not here": what is it, then? (ROADMAP 13b)

When the local check (utils/have.py) finds nothing, the page asks
/have/online for candidates from the outside sources, all at once:

  books   Google Books (Open Library when Google fails), book_utils
  movies  TMDb title search; for a barcode, UPCitemdb then TMDb, media_lookup
  music   Discogs when DISCOGS_TOKEN is set, MusicBrainz when it isn't or
          when Discogs is busy, discogs_lookup / music_lookup

Every source runs in its own thread and gets DEADLINE seconds in all. One
that hasn't answered by then is left out of this answer (its thread runs on
and fills the module's cache, so the next look is quick); a source that
fails or is busy is left out too. Nothing here downloads a cover or saves
anything: candidates carry the remote thumbnail (the page shows it through
coverSrc / /books/thumbnail) and the id the add page looks up on load.

"Most likely" (score_text) is a plain heuristic, in points:

  coverage    share of the words searched found in the title + creator
  +0.25       the title is exactly what was searched
  +0.25       creator + title (or title + creator) is exactly what was searched
  +0.2        the words searched hit both the creator and the title
  -0.15 x     share of the title's words that weren't searched

So "orville peck pony" scores the Discogs release Orville Peck - Pony at
1.0 + 0.25 + 0.2 = 1.45, and a book called "Pony" by someone else 0.33.
A barcode is either recognised or not, so its candidates get fixed scores
(BARCODE_SCORES).
"""
import re
from concurrent.futures import ThreadPoolExecutor, wait

from flask import current_app, url_for

from utils import book_utils, discogs_lookup, media, media_lookup, music_lookup
from utils.search import fold

DEADLINE = 5.0              # seconds for all sources together
PER_TYPE = 4                # candidates shown per type
SOURCE_LIMIT = 8            # results asked of each source

# One small pool per process. Threads left running past the deadline
# finish on their own (every HTTP call has its own timeout).
_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix='have-online')

# A barcode a source knows by that exact code beats one only found by the
# product name UPCitemdb gave it
BARCODE_SCORES = {'exact': 1.5, 'named': 1.0, 'product_only': 0.6}

# Text a source returns for a code it knows only as a music product
_MUSIC_CATEGORY = re.compile(r'\bmusic\b', re.IGNORECASE)


# ------------------------------------------------------------ ranking

def words(text):
    """The folded words of `text`: 'Orville Peck - Pony!' -> ['orville', 'peck', 'pony']."""
    return [w for w in (fold(part) for part in re.split(r'[\s\-/:,&.]+', text or '')) if w]


def score_text(query, title, creator=''):
    """How well a candidate fits the words searched (see the module docstring).
    0 when none of them is in its title or creator."""
    asked = words(query)
    if not asked:
        return 0.0
    title_words = words(title)
    creator_words = words(creator)
    known = set(title_words) | set(creator_words)
    covered = [w for w in asked if w in known]
    if not covered:
        return 0.0
    score = len(covered) / len(asked)
    joined = ''.join(asked)
    if joined == ''.join(title_words):
        score += 0.25
    if creator_words and joined in (''.join(creator_words + title_words),
                                    ''.join(title_words + creator_words)):
        score += 0.25
    if set(asked) & set(title_words) and set(asked) & set(creator_words):
        score += 0.2
    if title_words:
        extra = [w for w in title_words if w not in asked]
        score -= 0.15 * len(extra) / len(title_words)
    return round(score, 3)


def candidate(kind, source, title, creator='', year=None, thumb=None, detail='', ids=None):
    """One candidate, before scoring. `ids` is what its add page looks up:
    {'isbn'}, {'tmdb_id'}, {'discogs'} or {'mbid'}, plus 'barcode' for a
    scanned code."""
    return {'type': kind, 'source': source, 'title': title or '', 'creator': creator or '',
            'year': year or None, 'thumb': thumb or None, 'detail': detail or '',
            'ids': ids or {}, 'score': 0.0}


def rank(cands):
    """{'best': candidate or None, 'groups': [{'type', 'items'}]}: the best
    one on its own, then the rest by type, each type best first and the
    types in the order of their best. Ties keep the sources' own order."""
    order = sorted(range(len(cands)), key=lambda i: (-cands[i]['score'], i))
    ranked = [cands[i] for i in order if cands[i]['score'] > 0]
    if not ranked:
        return {'best': None, 'groups': []}
    best, rest = ranked[0], ranked[1:]
    groups = {}
    for c in rest:
        groups.setdefault(c['type'], [])
        if len(groups[c['type']]) < PER_TYPE:
            groups[c['type']].append(c)
    # The best one's type comes first: a wrong guess is one group away
    types = [best['type']] + [t for t in groups if t != best['type']]
    return {'best': best, 'groups': [{'type': t, 'items': groups[t]} for t in types if groups.get(t)]}


# ------------------------------------------------------------ sources (text)

def books_by_text(q):
    out = []
    for item in book_utils.search_google_books(q, SOURCE_LIMIT) or []:
        v = item.get('volumeInfo') or {}
        ids = v.get('industryIdentifiers') or []
        isbn = ids[0].get('identifier') if ids else None
        out.append(candidate(media.BOOK, 'books', v.get('title'), ', '.join(v.get('authors') or []),
                             (v.get('publishedDate') or '')[:4] or None,
                             (v.get('imageLinks') or {}).get('thumbnail'),
                             ids={'isbn': isbn} if isbn else {}))
    return out


def movies_by_text(q):
    if not media_lookup.tmdb_key():
        return []
    return [candidate(media.VIDEO, 'tmdb', f['title'], '', f.get('year'), f.get('poster'),
                      ids={'tmdb_id': f['id']})
            for f in media_lookup.tmdb_search(q, limit=SOURCE_LIMIT)]


def _album(row, source, barcode=None):
    ids = {'discogs': row['id']} if source == 'discogs' else {'mbid': row['id']}
    if barcode:
        ids['barcode'] = barcode
    # Pressings share a title: format, country and label tell them apart
    detail = ', '.join(x for x in (row.get('format_label'), row.get('country'), row.get('label')) if x)
    return candidate(media.RECORD, source, row.get('title'), row.get('artist'), row.get('year'),
                     row.get('thumb'), detail, ids)


def music_by_text(q):
    """Discogs first, MusicBrainz when there's no token or Discogs is busy
    (the same rule as /records/search)."""
    if discogs_lookup.enabled():
        try:
            return [_album(r, 'discogs') for r in discogs_lookup.search(q, limit=SOURCE_LIMIT)]
        except discogs_lookup.Busy:
            pass
    return [_album(r, 'musicbrainz') for r in music_lookup.search(q, limit=SOURCE_LIMIT)]


# ------------------------------------------------------------ sources (codes)

def book_by_isbn(isbn):
    """The book for an ISBN, without downloading its cover."""
    d = book_utils.fetch_google_books(isbn) or book_utils.fetch_open_library(isbn)
    if not d:
        return []
    # The second size: Google's 128 px (its first may be a "no image"
    # banner), Open Library's medium
    sizes = d.get('cover_candidates') or []
    thumb = sizes[1] if len(sizes) > 1 else (sizes[0] if sizes else None)
    c = candidate(media.BOOK, 'books', d.get('title'), d.get('author'), d.get('year'), thumb,
                  ids={'isbn': book_utils.normalize_isbn(isbn)})
    c['score'] = BARCODE_SCORES['exact']
    return [c]


def _upc(ean):
    """UPCitemdb's product for a code, cached like media_lookup's lookups
    (its free allowance is small)."""
    hit = media_lookup._cached(('have-upc', ean), lambda: {
        'found': bool(u := media_lookup.upcitemdb(ean)), 'upc': u})
    return hit.get('upc')


def movie_by_barcode(ean):
    """UPCitemdb names the product; TMDb says whether that's a film. A
    product UPCitemdb files under music isn't offered as a movie."""
    upc = _upc(ean)
    if not upc or not upc.get('title'):
        return []
    title, year = media_lookup.clean_title(upc['title'])
    films = media_lookup.tmdb_search(title, year, limit=1) if media_lookup.tmdb_key() and title else []
    if films:
        f = films[0]
        c = candidate(media.VIDEO, 'tmdb', f['title'], '', f.get('year'), f.get('poster'),
                      ids={'tmdb_id': f['id'], 'barcode': ean})
        c['score'] = BARCODE_SCORES['named']
        return [c]
    if _MUSIC_CATEGORY.search(upc.get('category') or ''):
        return []
    c = candidate(media.VIDEO, 'upcitemdb', title or upc['title'], upc.get('brand'), year,
                  next(iter(upc.get('images') or []), None), ids={'barcode': ean})
    c['score'] = BARCODE_SCORES['product_only']
    return [c]


def album_by_barcode(ean):
    """Discogs by barcode, MusicBrainz when there's no token or it's busy."""
    if discogs_lookup.enabled():
        try:
            rows = discogs_lookup.barcode_search(ean)
            if rows:
                c = _album(rows[0], 'discogs', ean)
                c['score'] = BARCODE_SCORES['exact']
                return [c]
        except discogs_lookup.Busy:
            pass
    ids = music_lookup.barcode_search(ean)
    if not ids:
        return []
    details, covers = music_lookup.release_details(ids[0])
    if not details:
        return []
    c = candidate(media.RECORD, 'musicbrainz', details.get('title'), details.get('author'),
                  details.get('year'), covers[-1] if covers else None,
                  media.format_label(details['format']) if details.get('format') else '',
                  {'mbid': ids[0], 'barcode': ean})
    c['score'] = BARCODE_SCORES['exact']
    return [c]


# ------------------------------------------------------------ the lookup

def _run(app, fn, arg):
    with app.app_context():
        return fn(arg)


def gather(jobs, deadline=None):
    """Run {name: (fn, arg)} at once. Returns ({name: [candidates]}, {name:
    'ok' | 'none' | 'slow' | 'failed'}). A slow or failing source is left
    out; nothing waits past the deadline."""
    app = current_app._get_current_object()
    futures = {name: _pool.submit(_run, app, fn, arg) for name, (fn, arg) in jobs.items()}
    wait(futures.values(), timeout=DEADLINE if deadline is None else deadline)
    found, status = {}, {}
    for name, future in futures.items():
        if not future.done():
            status[name] = 'slow'
            continue
        try:
            found[name] = future.result() or []
            status[name] = 'ok' if found[name] else 'none'
        except (discogs_lookup.Busy, music_lookup.Busy):
            status[name] = 'slow'
        except Exception:
            current_app.logger.exception(f'Do I have this? online lookup ({name}) failed')
            status[name] = 'failed'
    return found, status


def lookup(kind, value, query):
    """Candidates for a query the local check didn't find (`kind`, `value`
    from have.parse_query). {'best', 'groups', 'status', 'credits'}."""
    if kind == 'isbn':
        isbn = next((v for v in value if len(v) == 13), value[0])
        jobs = {media.BOOK: (book_by_isbn, isbn)}
    elif kind == 'barcode':
        jobs = {media.VIDEO: (movie_by_barcode, value), media.RECORD: (album_by_barcode, value)}
    elif kind == 'text' and len(query) >= 2:
        jobs = {media.BOOK: (books_by_text, query), media.VIDEO: (movies_by_text, query),
                media.RECORD: (music_by_text, query)}
    else:
        return {'best': None, 'groups': [], 'status': {}, 'credits': []}

    found, status = gather(jobs)
    cands = [c for name in jobs for c in found.get(name, [])]
    if kind == 'text':
        for c in cands:
            c['score'] = score_text(query, c['title'], c['creator'])
    ranked = rank(cands)
    shown = ([ranked['best']] if ranked['best'] else []) + [c for g in ranked['groups'] for c in g['items']]
    for c in shown:
        c.update(links(c, query))
        c['type_label'] = media.media_labels(c['type'])['Noun']
    # TMDb's and Discogs' terms ask for a credit wherever their data is shown
    credits = sorted({c['source'] for c in shown} & {'tmdb', 'discogs'})
    return {**ranked, 'status': status, 'credits': credits}


def links(c, query=''):
    """{'wishlist_url', 'shelf_url'} for a candidate: its type's add pages,
    carrying the id the page looks up on load (or the title, if it has none)."""
    ids = {k: v for k, v in c['ids'].items() if v}
    if not ids:
        ids = {'title': c['title'] or query, 'author': c['creator']}
        ids = {k: v for k, v in ids.items() if v}
    shelf = {media.BOOK: 'books.add_book', media.VIDEO: 'videos.add_video',
             media.RECORD: 'records.add_record'}[c['type']]
    return {'wishlist_url': url_for('wishlist.add_to_wishlist', type=c['type'], **ids),
            'shelf_url': url_for(shelf, **ids)}

"""Music section (Phase 8.7, "Vinyls" until 2026-11-08): LPs, EPs, singles,
CDs and cassettes.

A record is a `books` row with media_type = 'record' (migration 024). The
grid, tabs, add/edit forms and duplicate check are the shared section code
(blueprints/media_section.py, also used by Movies) on the `library_records`
view. Add Album: title search, barcode (typed or scanned, since 8B.12)
and manual entry. The search asks Discogs when DISCOGS_TOKEN is set
(utils/discogs_lookup.py, 8B.10), else or when it's busy MusicBrainz
(utils/music_lookup.py). The UI says "Music" and "album"; code, URLs and
the DB say "record".
"""
import re

from flask import request, jsonify, current_app, url_for
from flask_login import login_required

from blueprints.media_section import Section, make_blueprint
from utils import media
from utils import discogs_lookup, music_lookup
from utils.search import by_arg, next_page, page_arg
from utils.rate_limiting import limiter

def _add_context(values):
    """Add Album: arriving with a barcode (scanned on Add Book) opens the
    Barcode tab; otherwise Search."""
    return dict(active_method='code' if values.get('barcode_input') else 'search')


def _lookup_url(args):
    """?discogs=<release id> or ?mbid=<MusicBrainz id> (a release picked
    on Do I have this?): look it up on load."""
    discogs_id = (args.get('discogs') or '').strip()
    mbid = (args.get('mbid') or '').strip().lower()
    if discogs_id.isdigit() and len(discogs_id) <= 12 and discogs_lookup.enabled():
        return url_for('records.lookup', discogs=discogs_id)
    if MBID_RE.match(mbid):
        return url_for('records.lookup', mbid=mbid)
    return None


RECORDS = Section(
    media_type=media.RECORD,
    view='library_records',
    add_context=_add_context,
    lookup_url=_lookup_url,
    match_catalog_number=True,
    empty_text='Search for one by artist and title, scan its barcode, or type it in from its sleeve. '
               'Music is kept apart from your books and movies.',
)
records_blueprint = make_blueprint(RECORDS)

# A MusicBrainz id (MBID) is a UUID; nothing else goes into the lookup URL
MBID_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')

BUSY = 'The music database is busy right now. Wait a moment and try again, or fill the form in by hand.'


def _format_arg():
    """?format=vinyl|cd|cassette; anything else is '' (all three)."""
    kind = (request.args.get('format') or '').lower()
    return kind if kind in music_lookup.MB_FORMATS else ''


def _search_error(what):
    current_app.logger.exception(f'Music {what} failed')
    return jsonify({'success': False, 'error': 'The search failed. Try again, or fill the form in by hand.'}), 500


@records_blueprint.route('/search')
@login_required
@limiter.limit('120 per hour')
def search():
    """Releases matching ?q= (artist and title words), one per pressing,
    ?page= for "Show more"; ?format=vinyl|cd|cassette narrows it, anything
    else searches all three. The Search tab lists these when no album
    matches (/records/albums). Discogs answers when DISCOGS_TOKEN is set
    (8B.10); MusicBrainz when it isn't, or when Discogs is busy. Each row
    says which (`source`), and picking one asks /records/lookup with that
    source's id. `source` at the top says who answered, for the credit line."""
    query = (request.args.get('q') or '').strip()[:200]
    if len(query) < 2:
        return jsonify({'success': True, 'results': [], 'source': None, 'next': None})
    return _pressing_search(query, _format_arg(), page_arg(request.args))


def _pressing_search(query, kind, page, keep=None):
    """/records/search's answer: one page of pressings, Discogs first."""
    keep = keep or {}
    if _discogs_first():
        try:
            rows, more = discogs_lookup.search_page(query, kind, page)
            return jsonify({'success': True, 'source': 'discogs', 'results': rows,
                            'next': next_page(page, more, **keep)})
        except discogs_lookup.Busy:
            if page > 1:                # don't switch lists halfway down
                return jsonify({'success': False, 'error': BUSY}), 503
        except Exception:
            current_app.logger.exception('Discogs search failed')
    try:
        rows, more = music_lookup.search_page(query, kind, page)
    except music_lookup.Busy:
        return jsonify({'success': False, 'error': BUSY}), 503
    except Exception:
        return _search_error('search')
    return jsonify({'success': True, 'source': 'musicbrainz', 'next': next_page(page, more, **keep, **_pinned()),
                    'results': [{**r, 'source': 'musicbrainz'} for r in rows]})


def _discogs_first():
    """Ask Discogs, unless MusicBrainz answered this search's first page
    (Discogs was busy): "Show more" stays on one source's list (?src=mb)."""
    return discogs_lookup.enabled() and request.args.get('src') != 'mb'


def _pinned():
    """`next`'s source pin when MusicBrainz answered with Discogs on."""
    return {'src': 'mb'} if discogs_lookup.enabled() else {}


@records_blueprint.route('/albums')
@login_required
@limiter.limit('120 per hour')
def albums():
    """The Add Album page's Search tab (16.0, Phil: a search for one album
    came back as twelve pressings of another): one row per album matching
    ?q=, then its pressings (/records/pressings) or straight to the form
    ("Use this", /records/lookup?discogs_master= / ?mb_group=). "X by Y"
    searches title X by artist Y (utils.search.by_or_plain). Discogs first,
    as /records/search. When nothing matches as an album (a release with no
    Discogs master), the first page lists pressings instead (rows without
    level='album'). `next` is the parameters for "Show more" (page, by,
    level), utils.search.next_page."""
    query = (request.args.get('q') or '').strip()[:200]
    kind, page, by = _format_arg(), page_arg(request.args), by_arg(request.args)
    if len(query) < 2:
        return jsonify({'success': True, 'results': [], 'source': None, 'next': None})
    if request.args.get('level') == 'pressing':     # "Show more" on the no-album fallback
        return _pressing_search(query, kind, page, {'level': 'pressing'})
    if _discogs_first():
        try:
            rows, more, by = discogs_lookup.albums(query, kind, page, by)
            if rows or page > 1:
                return jsonify({'success': True, 'source': 'discogs', 'results': rows,
                                'next': next_page(page, more, by=by)})
            return _pressing_search(query, kind, 1, {'level': 'pressing'})
        except discogs_lookup.Busy:
            if page > 1:                # don't switch lists halfway down
                return jsonify({'success': False, 'error': BUSY}), 503
        except Exception:
            current_app.logger.exception('Discogs album search failed')
    try:
        rows, more, by = music_lookup.albums(query, kind, page, by)
    except music_lookup.Busy:
        return jsonify({'success': False, 'error': BUSY}), 503
    except Exception:
        return _search_error('album search')
    return jsonify({'success': True, 'source': 'musicbrainz', 'results': rows,
                    'next': next_page(page, more, by=by, **_pinned())})


@records_blueprint.route('/pressings')
@login_required
@limiter.limit('120 per hour')
def pressings():
    """One album's pressings for the Search tab: ?source=discogs&id=<master
    id> or ?source=musicbrainz&id=<release group MBID>, ?format= and ?page=
    as /records/search. Rows as /records/search's."""
    source = request.args.get('source')
    album_id = (request.args.get('id') or '').strip().lower()
    kind, page = _format_arg(), page_arg(request.args)
    try:
        if source == 'discogs' and album_id.isdigit() and len(album_id) <= 12 and discogs_lookup.enabled():
            rows, more = discogs_lookup.pressings(int(album_id), kind, page)
        elif source == 'musicbrainz' and MBID_RE.match(album_id):
            rows, more = music_lookup.pressings(album_id, kind, page)
            rows = [{**r, 'source': 'musicbrainz'} for r in rows]
        else:
            return jsonify({'success': False, 'error': 'Pick an album from the search results.'}), 400
    except (discogs_lookup.Busy, music_lookup.Busy):
        return jsonify({'success': False, 'error': BUSY}), 503
    except Exception:
        return _search_error('pressings')
    return jsonify({'success': True, 'source': source, 'results': rows, 'next': next_page(page, more)})


@records_blueprint.route('/lookup')
@login_required
@limiter.limit('60 per hour')
def lookup():
    """Pre-fill for Add Album from a picked release: ?discogs=<release id>
    or ?mbid=<MusicBrainz id>; from an album's main pressing,
    ?discogs_master=<master id> or ?mb_group=<release group MBID>; or from
    a typed or scanned ?barcode=. Answers {"success", "found", "details",
    "sources", "cover"} like /videos/lookup."""
    discogs_id = (request.args.get('discogs') or '').strip()
    mbid = (request.args.get('mbid') or '').strip().lower()
    if 'barcode' in request.args:
        return _barcode_lookup(request.args.get('barcode'))
    # "Use this" on an album row (16.0): the album's main pressing
    master = (request.args.get('discogs_master') or '').strip()
    group = (request.args.get('mb_group') or '').strip().lower()
    try:
        if master.isdigit() and len(master) <= 12 and discogs_lookup.enabled():
            discogs_id = str(discogs_lookup.main_release(int(master)) or '')
        elif MBID_RE.match(group):
            mbid = music_lookup.main_release(group, _format_arg()) or ''
        elif master or group:
            return jsonify({'success': False, 'error': 'Pick an album from the search results.'}), 400
    except (discogs_lookup.Busy, music_lookup.Busy):
        return jsonify({'success': False, 'error': BUSY}), 503
    if (master or group) and not (discogs_id or mbid):
        return jsonify({'success': True, 'found': False, 'details': {}, 'sources': [], 'cover': None})
    if discogs_id:
        if not discogs_id.isdigit() or len(discogs_id) > 12 or not discogs_lookup.enabled():
            return jsonify({'success': False, 'error': 'Pick a release from the search results.'}), 400
        source, fetch = discogs_lookup, lambda: discogs_lookup.lookup(int(discogs_id))
    elif MBID_RE.match(mbid):
        source, fetch = music_lookup, lambda: music_lookup.lookup(mbid)
    else:
        return jsonify({'success': False, 'error': 'Pick a release from the search results.'}), 400
    try:
        result = fetch()
    except source.Busy:
        return jsonify({'success': False, 'error': BUSY}), 503
    except Exception:
        current_app.logger.exception('Music lookup failed')
        return jsonify({'success': False, 'error': 'The lookup failed. Fill the form in by hand.'}), 500
    return jsonify({'success': True, **result})


def _barcode_lookup(raw):
    """The barcode tab (8B.12): Discogs first (one search, then the release),
    MusicBrainz if there's no token or Discogs is busy. The first release
    with the barcode fills the form; when pressings share one, that's close
    enough, and the cat. no. on the sleeve tells you which."""
    ean = media.normalize_barcode(raw)
    if not ean:
        return jsonify({'success': False, 'error': "That barcode isn't a valid UPC or EAN."}), 400
    if media.classify_code(ean) == media.BOOK:
        return jsonify({'success': False, 'error': "That's an ISBN: add it as a book."}), 400
    try:
        if discogs_lookup.enabled():
            try:
                rows = discogs_lookup.barcode_search(ean)
                result = discogs_lookup.lookup(rows[0]['id']) if rows else None
                if result:
                    return jsonify({'success': True, 'barcode': ean, **result})
            except discogs_lookup.Busy:
                pass                    # MusicBrainz next
        ids = music_lookup.barcode_search(ean)
        if ids:
            return jsonify({'success': True, 'barcode': ean, **music_lookup.lookup(ids[0])})
    except (music_lookup.Busy, discogs_lookup.Busy):
        return jsonify({'success': False, 'error': BUSY}), 503
    except Exception:
        current_app.logger.exception('Music barcode lookup failed')
        return jsonify({'success': False, 'error': 'The lookup failed. Fill the form in by hand.'}), 500
    return jsonify({'success': True, 'barcode': ean, 'found': False,
                    'details': {}, 'sources': [], 'cover': None})

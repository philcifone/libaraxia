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


@records_blueprint.route('/search')
@login_required
@limiter.limit('120 per hour')
def search():
    """The Add Album page's Search tab: releases matching ?q= (artist and
    title words), one per pressing; ?format=vinyl|cd|cassette narrows it,
    anything else searches all three. Discogs answers when DISCOGS_TOKEN is
    set (8B.10); MusicBrainz when it isn't, or when Discogs is busy. Each row
    says which (`source`), and picking one asks /records/lookup with that
    source's id. `source` at the top says who answered, for the credit line."""
    query = (request.args.get('q') or '').strip()[:200]
    kind = (request.args.get('format') or '').lower()
    if kind not in music_lookup.MB_FORMATS:
        kind = ''
    if len(query) < 2:
        return jsonify({'success': True, 'results': [], 'source': None})
    if discogs_lookup.enabled():
        try:
            return jsonify({'success': True, 'source': 'discogs',
                            'results': discogs_lookup.search(query, kind)})
        except discogs_lookup.Busy:
            pass                        # MusicBrainz next, one request, no retry here
        except Exception:
            current_app.logger.exception('Discogs search failed')
    try:
        results = [{**r, 'source': 'musicbrainz'} for r in music_lookup.search(query, kind)]
    except music_lookup.Busy:
        return jsonify({'success': False, 'error': BUSY}), 503
    except Exception:
        current_app.logger.exception('Music search failed')
        return jsonify({'success': False, 'error': 'The search failed. Try again, or fill the form in by hand.'}), 500
    return jsonify({'success': True, 'source': 'musicbrainz', 'results': results})


@records_blueprint.route('/lookup')
@login_required
@limiter.limit('60 per hour')
def lookup():
    """Pre-fill for Add Album from a picked release: ?discogs=<release id>
    or ?mbid=<MusicBrainz id>; or from a typed or scanned ?barcode=. Answers {"success", "found", "details",
    "sources", "cover"} like /videos/lookup."""
    discogs_id = (request.args.get('discogs') or '').strip()
    mbid = (request.args.get('mbid') or '').strip().lower()
    if 'barcode' in request.args:
        return _barcode_lookup(request.args.get('barcode'))
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

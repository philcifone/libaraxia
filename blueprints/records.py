"""Music section (Phase 8.7, "Vinyls" until 2026-11-08): LPs, EPs, singles,
CDs and cassettes.

A record is a `books` row with media_type = 'record' (migration 024). The
grid, tabs, add/edit forms and duplicate check are the shared section code
(blueprints/media_section.py, also used by Movies) on the `library_records`
view. Records have no barcode (Phil, 2026-11-07): Add Vinyl is a title
search on MusicBrainz plus manual entry (utils/music_lookup.py). The UI
says "Vinyls"; code, URLs and the DB say "record".
"""
import re

from flask import request, jsonify, current_app
from flask_login import login_required

from blueprints.media_section import Section, make_blueprint
from utils import media
from utils import music_lookup
from utils.rate_limiting import limiter

RECORDS = Section(
    media_type=media.RECORD,
    view='library_records',
    match_catalog_number=True,
    empty_text='Search for one by artist and title, or type it in from its sleeve. '
               'Music is kept apart from your books and movies.',
)
records_blueprint = make_blueprint(RECORDS)

# A MusicBrainz id (MBID) is a UUID; nothing else goes into the lookup URL
MBID_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')

BUSY = 'MusicBrainz is busy right now. Wait a moment and try again, or fill the form in by hand.'


@records_blueprint.route('/search')
@login_required
@limiter.limit('120 per hour')
def search():
    """The Add Vinyl page's Search tab: vinyl releases matching ?q= (artist
    and title words) on MusicBrainz, one per pressing. Picking one asks
    /records/lookup?mbid=, which fills the form."""
    query = (request.args.get('q') or '').strip()[:200]
    if len(query) < 2:
        return jsonify({'success': True, 'results': []})
    try:
        results = music_lookup.search(query)
    except music_lookup.Busy:
        return jsonify({'success': False, 'error': BUSY}), 503
    except Exception:
        current_app.logger.exception('Vinyl search failed')
        return jsonify({'success': False, 'error': 'The search failed. Try again, or fill the form in by hand.'}), 500
    return jsonify({'success': True, 'results': results})


@records_blueprint.route('/lookup')
@login_required
@limiter.limit('60 per hour')
def lookup():
    """Pre-fill for Add Vinyl from a picked release (?mbid=). Answers
    {"success", "found", "details", "sources", "cover"} like /videos/lookup."""
    mbid = (request.args.get('mbid') or '').strip().lower()
    if not MBID_RE.match(mbid):
        return jsonify({'success': False, 'error': 'Pick a release from the search results.'}), 400
    try:
        result = music_lookup.lookup(mbid)
    except music_lookup.Busy:
        return jsonify({'success': False, 'error': BUSY}), 503
    except Exception:
        current_app.logger.exception('Vinyl lookup failed')
        return jsonify({'success': False, 'error': 'The lookup failed. Fill the form in by hand.'}), 500
    return jsonify({'success': True, **result})

"""Movies & TV section (Phase 8, 15.1): VHS tapes ("Cartridges") and DVDs,
films and TV box sets (books.video_kind).

A video is a `books` row with media_type = 'video' (migration 023). The
grid, tabs, add/edit forms and duplicate check are the shared section code
(blueprints/media_section.py, also used by Vinyls) on the `library_videos`
view; this module adds the Movies lookups: UPCitemdb by barcode and TMDb by
title (utils/media_lookup.py). The UI says "Movies & TV"; code, URLs and
the DB say "video".
"""
from flask import request, jsonify, current_app, url_for
from flask_login import login_required

from blueprints.media_section import Section, make_blueprint
from utils import media
from utils import media_lookup
from utils.rate_limiting import limiter


def _add_context(values):
    """Add Movie: arriving with a barcode (scanned on Add Book) opens its
    tab; otherwise title search, when there's a TMDb key for it."""
    tmdb = bool(media_lookup.tmdb_key())
    code = values.get('barcode_input') or ''
    return dict(tmdb=tmdb, search_enabled=tmdb,
                active_method='code' if code or not tmdb else 'search')


def _lookup_url(args):
    """?tmdb_id= (a film or show picked on Do I have this?, &kind=tv for a
    show): look it up on load."""
    tmdb_id = args.get('tmdb_id', type=int)
    if not tmdb_id or tmdb_id < 1 or not media_lookup.tmdb_key():
        return None
    kind = media.video_kind(args.get('kind'))
    return url_for('videos.lookup', tmdb_id=tmdb_id, **({'kind': kind} if kind else {}))


VIDEOS = Section(
    media_type=media.VIDEO,
    view='library_videos',
    add_context=_add_context,
    lookup_url=_lookup_url,
    empty_text='Type one in from its box, or scan its barcode. Movies and TV are kept apart from your books.',
)
videos_blueprint = make_blueprint(VIDEOS)


@videos_blueprint.route('/lookup')
@login_required
@limiter.limit('60 per hour')
def lookup():
    """Pre-fill for the Add Video form (utils/media_lookup.py).

    ?barcode= asks UPCitemdb, then TMDb on the title it found; ?title= (and
    &year=) asks TMDb only, for tapes without a barcode; ?tmdb_id= is a film
    picked from the Search tab (/videos/search), &kind=tv for a show (TMDb
    numbers them apart). Always answers 200
    with {"success", "found", "details", "sources", "cover"}: not finding
    anything is normal for VHS, and the form is filled in by hand then.
    """
    barcode = (request.args.get('barcode') or '').strip()
    title = (request.args.get('title') or '').strip()[:200]
    year = request.args.get('year', type=int)
    tmdb_id = request.args.get('tmdb_id', type=int)
    kind = media.video_kind(request.args.get('kind'))
    if barcode and not media.normalize_barcode(barcode):
        return jsonify({'success': False, 'error': "That barcode isn't a valid UPC or EAN."}), 400
    if not barcode and not title and not tmdb_id:
        return jsonify({'success': False, 'error': 'Give a barcode or a title.'}), 400
    try:
        result = media_lookup.lookup(barcode=barcode or None, title=title or None, year=year,
                                     tmdb_id=tmdb_id, kind=kind)
    except Exception:
        current_app.logger.exception('Video lookup failed')
        return jsonify({'success': False, 'error': 'The lookup failed. Fill the form in by hand.'}), 500
    return jsonify({'success': True, 'tmdb': bool(media_lookup.tmdb_key()), **result})


@videos_blueprint.route('/search')
@login_required
@limiter.limit('120 per hour')
def search():
    """The Add Movie or Show page's Search tab: movies and TV shows matching
    ?q= on TMDb, each with its kind, to pick one from (then
    /videos/lookup?tmdb_id=&kind= fills the form). Needs
    TMDB_API_KEY; without it the tab says so and this answers an error."""
    query = (request.args.get('q') or '').strip()[:200]
    if not media_lookup.tmdb_key():
        return jsonify({'success': False, 'error': 'Title search needs a TMDb key (TMDB_API_KEY in .env).'}), 400
    if len(query) < 2:
        return jsonify({'success': True, 'results': []})
    try:
        results = media_lookup.tmdb_search(query)
    except Exception:
        current_app.logger.exception('Movie search failed')
        return jsonify({'success': False, 'error': 'The search failed. Try again, or use the barcode.'}), 500
    return jsonify({'success': True, 'results': results})

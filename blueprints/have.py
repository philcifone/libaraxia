"""Do I have this? (ROADMAP 8E): /have/?q=<barcode, ISBN or title>.

One page for the shop: scan or type, and the answer is yours / your
household's / on your wishlist / read but not owned / removed / not here,
with your status and rating. The scanner just reloads the page with the
code in ?q=, so the answer is rendered on the server and the page works
without the camera (or JavaScript). Matching is utils/have.py.
"""
from flask import Blueprint, current_app, jsonify, render_template, request
from flask_login import current_user, login_required

from utils import have, have_online
from utils.database import get_db
from utils.rate_limiting import limiter

have_blueprint = Blueprint('have', __name__, template_folder='templates')


@have_blueprint.route('/', methods=['GET'])
@login_required
def check():
    q = (request.args.get('q') or '').strip()[:200]
    result = have.find(get_db(), current_user.id, q) if q else None
    missed = bool(result and not result['matches'] and result['kind'] != 'bad_code')
    links = have.add_links(result['kind'], result['value'], q) if missed else []
    return render_template('have.html', q=q, result=result, add_links=links,
                           online=missed and have.worth_asking(result))


def _per_user():
    """Rate-limit key: the signed-in user, so a household behind one IP
    doesn't share an allowance."""
    return f'user:{current_user.id}' if current_user.is_authenticated else request.remote_addr


@have_blueprint.route('/online', methods=['GET'])
@login_required
@limiter.limit('60 per hour', key_func=_per_user)
def online():
    """"Not here": what it most likely is (ROADMAP 13b). have.js asks this
    after the page renders, so the local answer never waits on it. Checks
    locally again first and asks no one outside on a hit; see
    utils/have_online.py for the sources and the ranking."""
    q = (request.args.get('q') or '').strip()[:200]
    empty = {'success': True, 'best': None, 'groups': [], 'status': {}, 'credits': []}
    if not q:
        return jsonify(empty)
    result = have.find(get_db(), current_user.id, q)
    if result['matches'] or not have.worth_asking(result):
        return jsonify({**empty, 'local': bool(result['matches'])})
    try:
        found = have_online.lookup(result['kind'], result['value'], result['query'])
    except Exception:
        current_app.logger.exception('Do I have this? online lookup failed')
        return jsonify({'success': False, 'error': "Couldn't look it up online. Add it by hand below."}), 500
    return jsonify({'success': True, 'local': False, **found})

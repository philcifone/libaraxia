"""Do I have this? (ROADMAP 8E): /have/?q=<barcode, ISBN or title>.

One page for the shop: scan or type, and the answer is yours / your
household's / on your wishlist / read but not owned / removed / not here,
with your status and rating. The scanner just reloads the page with the
code in ?q=, so the answer is rendered on the server and the page works
without the camera (or JavaScript). Matching is utils/have.py.
"""
from flask import Blueprint, render_template, request
from flask_login import current_user, login_required

from utils import have
from utils.database import get_db

have_blueprint = Blueprint('have', __name__, template_folder='templates')


@have_blueprint.route('/', methods=['GET'])
@login_required
def check():
    q = (request.args.get('q') or '').strip()[:200]
    result = have.find(get_db(), current_user.id, q) if q else None
    links = have.add_links(result['kind'], result['value']) if result and not result['matches'] \
        and result['kind'] != 'bad_code' else []
    return render_template('have.html', q=q, result=result, add_links=links)

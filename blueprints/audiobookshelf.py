"""The Audiobookshelf connection (ROADMAP 16.0e, docs/AUDIOBOOKSHELF-SPEC.md):
connect and disconnect from Settings -> Library. The client, keys and rules
are utils/audiobookshelf.py; these routes read the form, commit, and come
back to the Settings card with a flash.

Every route is a 404 while AUDIOBOOKSHELF_URL isn't set, so the feature
doesn't exist on a site without a server.
"""
from flask import Blueprint, abort, current_app, flash, redirect, request, url_for
from flask_login import current_user, login_required

from utils import audiobookshelf as abs_
from utils.audiobookshelf import AbsError
from utils.database import get_db
from utils.rate_limiting import limiter

abs_blueprint = Blueprint('abs', __name__)


@abs_blueprint.before_request
def _only_when_configured():
    if not abs_.enabled():
        abort(404)


def _secret():
    return current_app.config['SECRET_KEY']


def _back():
    """Settings, at the Audiobookshelf card (its hash opens the Library tab)."""
    return redirect(url_for('user.settings', _anchor='audiobookshelf'))


def settings_context(conn, user_id):
    """What the Settings card needs (user.settings passes it as `abs`), or
    None when the feature is off. Never the key; `readable` is False when
    the stored key no longer decrypts (SECRET_KEY changed): Reconnect."""
    if not abs_.enabled():
        return None
    acct = abs_.account(conn, user_id)
    readable = bool(acct) and abs_.token_for(conn, user_id, _secret()) is not None
    return {'account': acct, 'readable': readable}


@abs_blueprint.route('/connect', methods=['POST'])
@login_required
@limiter.limit('10 per hour')
def connect():
    """Check a pasted key against ABS (/api/me) and keep it, encrypted."""
    conn = get_db()
    try:
        username = abs_.connect(conn, current_user.id, request.form.get('abs_token', ''), _secret())
        conn.commit()
        flash(f'Connected to Audiobookshelf as {username}.', 'success')
    except AbsError as e:
        conn.rollback()
        flash(str(e) if not e.auth else "Audiobookshelf didn't accept that key.", 'error')
    except Exception:
        conn.rollback()
        current_app.logger.exception('Audiobookshelf connect failed for user %s', current_user.id)
        flash('Something went wrong; nothing was saved.', 'error')
    return _back()


@abs_blueprint.route('/disconnect', methods=['POST'])
@login_required
@limiter.limit('30 per hour')
def disconnect():
    """Forget the key. What was imported stays."""
    conn = get_db()
    abs_.disconnect(conn, current_user.id)
    conn.commit()
    flash('Disconnected from Audiobookshelf. What you imported stays.', 'success')
    return _back()

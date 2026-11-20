from flask import flash, jsonify, redirect, request, url_for


def unauthorized(error):
    flash('You must be logged in to access this page.', 'danger')
    return redirect(url_for('auth.login'))  # Adjust route name if it's under a blueprint


STALE_PAGE_MESSAGE = 'That page was out of date, try again.'


def _same_site_referrer():
    """The Referer if it points at this site, else None (never an open redirect)."""
    from utils.landing import same_site
    return same_site(request.referrer)


def csrf_error(error):
    """A missing or stale CSRF token (ROADMAP 14c).

    Tokens no longer expire on a timer (WTF_CSRF_TIME_LIMIT = None), but one
    from before a re-login via remember-me belongs to the old session and no
    longer matches. Instead of Flask-WTF's bare 400, a form post flashes and
    goes back to the page it came from, which now carries a fresh token; a
    fetch (it sends the token in a header) gets the usual JSON error.
    """
    wants_json = (request.is_json
                  or request.headers.get('X-CSRFToken')
                  or request.headers.get('X-CSRF-Token')
                  or request.headers.get('X-Requested-With') == 'XMLHttpRequest')
    if wants_json:
        return jsonify({'success': False, 'error': STALE_PAGE_MESSAGE}), 400
    flash(STALE_PAGE_MESSAGE, 'warning')
    return redirect(_same_site_referrer() or url_for('base.home'))

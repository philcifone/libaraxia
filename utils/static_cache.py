"""Long browser caching for static files (ROADMAP 16.0g step 3,
docs/BACKEND-POLISH-SPEC.md section 1.3).

Without this the browser asks again for every script, stylesheet, font
and cover on every page (a 304 each time, but a round trip each). Now:

- Every url_for('static', ...) outside uploads/ carries v=<hash of the
  file>, so a changed file gets a new URL. No template changes.
- A response for a versioned URL, a font file or anything under uploads/
  says "keep this for a year, it won't change" (immutable).

Fonts are linked from the CSS by plain path, so they can't carry v; their
file names name the font, weight and style, and a changed font gets a new
name. Uploads (covers, photos, faces, avatars) are always saved under a
fresh random name, so a cached one is never stale. Uploads are `private`:
the browser keeps them, Cloudflare's edge doesn't, so a deleted photo
isn't served from someone else's cache for a year.
"""
import hashlib
import os

from flask import request

YEAR = 31536000
FONT_EXTENSIONS = ('.woff2', '.woff', '.ttf', '.otf')

# {filename: (mtime, version)}. Keyed on mtime, so an edited file on the
# dev server gets a new version without a restart.
_versions = {}


def version_of(static_folder, filename):
    """The first 10 hex digits of the file's SHA-256, or None if it's missing."""
    path = os.path.join(static_folder, filename)
    try:
        mtime = os.stat(path).st_mtime_ns
    except OSError:
        return None
    known = _versions.get(filename)
    if known and known[0] == mtime:
        return known[1]
    with open(path, 'rb') as f:
        version = hashlib.sha256(f.read()).hexdigest()[:10]
    _versions[filename] = (mtime, version)
    return version


def init_app(app):
    @app.url_defaults
    def _add_version(endpoint, values):
        if endpoint != 'static' or 'v' in values:
            return
        filename = values.get('filename') or ''
        if not filename or filename.startswith('uploads/'):
            return
        version = version_of(app.static_folder, filename)
        if version:
            values['v'] = version

    @app.after_request
    def _cache_headers(response):
        if request.endpoint != 'static' or response.status_code not in (200, 304):
            return response
        filename = (request.view_args or {}).get('filename', '')
        upload = filename.startswith('uploads/')
        if upload or 'v' in request.args or filename.endswith(FONT_EXTENSIONS):
            response.headers['Cache-Control'] = (f'{"private" if upload else "public"}, '
                                                 f'max-age={YEAR}, immutable')
        return response

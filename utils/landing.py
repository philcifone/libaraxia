"""Where a form post lands (ROADMAP 16.0g step 7,
docs/BACKEND-POLISH-SPEC.md section 2.2 and appendix B).

Most actions land on a fixed page: an item's own page, a list. The ones
done in place from many pages (a status from a grid card or the item page,
a friend request from Notifications or a profile) go back where they came
from, and only through here, so "back" is always this site:

1. the form's own `next` field, when it's a path on this site;
2. else the Referer, when it's this site;
3. else `fallback`.

Never an open redirect: a URL on another host, a scheme other than
http(s), or a protocol-relative `//host` is ignored.
"""
from urllib.parse import urlparse

from flask import redirect, request, url_for


def same_site(url):
    """`url` if it points at this site, else None."""
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.scheme not in ('', 'http', 'https'):
        return None
    if parsed.netloc and parsed.netloc != request.host:
        return None
    if not parsed.netloc and not url.startswith('/'):
        return None                     # a bare "evil.com/x" or "javascript:..."
    if url.startswith('//'):
        return None
    return url


def back_url(fallback=None):
    """The URL `back()` would go to."""
    return (same_site(request.form.get('next'))
            or same_site(request.referrer)
            or fallback
            or url_for('base.index'))


def back(fallback=None):
    """Redirect to back_url(fallback)."""
    return redirect(back_url(fallback))


def came_from(prefix):
    """Whether the post came from a page whose path starts with `prefix`
    (the wishlist's remove: back to the wishlist only from the wishlist)."""
    ref = same_site(request.referrer)
    return bool(ref) and urlparse(ref).path.startswith(prefix)

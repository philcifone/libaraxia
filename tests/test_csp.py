"""Phase 6: no inline scripts or handlers, a Content-Security-Policy that
enforces it, and remote search-result covers served through our own origin."""
import pathlib
import re

from PIL import Image

from conftest import login

TEMPLATES = pathlib.Path(__file__).resolve().parent.parent / 'templates'
STATIC = TEMPLATES.parent / 'static'


def test_templates_have_no_inline_scripts_or_handlers():
    """The CSP forbids both, so they would silently stop working."""
    problems = []
    for path in TEMPLATES.rglob('*.html'):
        html = path.read_text()
        for m in re.finditer(r'<script(?![^>]*\bsrc=)[^>]*>', html):
            problems.append(f'{path.name}: inline {m.group(0)}')
        for m in re.finditer(r'\son[a-z]+\s*=', html):
            problems.append(f'{path.name}: handler {m.group(0).strip()}')
        if 'javascript:' in html:
            problems.append(f'{path.name}: javascript: URL')
    assert problems == []


def test_scripts_do_not_generate_inline_handlers():
    """Markup built in JS (innerHTML) is under the same policy."""
    for path in STATIC.glob('*.js'):
        assert not re.search(r'<[a-z][^>]*\son[a-z]+=', path.read_text()), path.name


def test_pages_send_a_strict_csp(client, people):
    login(client, 'alice')
    for url in ['/base/index', '/auth/login']:
        policy = client.get(url).headers['Content-Security-Policy']
        directives = dict(d.strip().split(' ', 1) for d in policy.split(';'))
        assert directives['script-src'] == "'self'"
        assert directives['img-src'].split()[0] == "'self'" and 'https:' not in directives['img-src']
        assert directives['object-src'] == "'none'"


def test_thumbnail_proxy_only_fetches_cover_hosts(client, people, monkeypatch):
    from utils import book_utils
    fetched = []

    def fake_fetch(url):
        fetched.append(url)
        return Image.new('RGB', (400, 600), 'red')
    monkeypatch.setattr(book_utils, '_fetch_image', fake_fetch)
    login(client, 'alice')

    r = client.get('/books/thumbnail', query_string={'url': 'http://books.google.com/books/content?id=x&img=1'})
    assert r.status_code == 200 and r.mimetype == 'image/jpeg'
    assert Image.open(__import__('io').BytesIO(r.data)).size[1] <= 384      # re-encoded and shrunk
    assert fetched == ['https://books.google.com/books/content?id=x&img=1']  # upgraded to https

    for url in ['https://evil.example/x.jpg', 'http://127.0.0.1/x.jpg', 'file:///etc/passwd', '']:
        assert client.get('/books/thumbnail', query_string={'url': url}).status_code == 404
    assert len(fetched) == 1


def test_thumbnail_proxy_needs_login(client, people):
    r = client.get('/books/thumbnail', query_string={'url': 'https://covers.openlibrary.org/b/id/1-L.jpg'})
    assert r.status_code in (302, 401)


def test_vendored_scripts_match_their_listed_hash():
    """Every vendored script is in static/vendor/README.md with its sha512,
    so a swapped or edited file is noticed."""
    import base64
    import hashlib
    vendor = STATIC / 'vendor'
    readme = (vendor / 'README.md').read_text()
    files = sorted(vendor.glob('*.js'))
    assert files
    for path in files:
        digest = base64.b64encode(hashlib.sha512(path.read_bytes()).digest()).decode()
        row = next((line for line in readme.splitlines() if f'`{path.name}`' in line), None)
        assert row is not None, f'{path.name} is not listed in vendor/README.md'
        assert digest in row, f'{path.name} does not match its listed hash'


def test_csp_starts_no_blob_workers(client, people):
    """The scanner decodes on the main thread, so workers stay 'self' only."""
    login(client, 'alice')
    csp = client.get('/base/index').headers['Content-Security-Policy']
    directives = dict(d.strip().split(' ', 1) for d in csp.split(';'))
    assert directives['worker-src'] == "'self'"

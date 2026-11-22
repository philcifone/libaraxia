"""The home-screen app (Phil, 2026-11-22): a web app manifest, the icon on
every page (signed in or not, since "Add to Home Screen" can happen on the
sign-in page), and the status bar following the page's background."""
import json
import re
import pathlib

from conftest import login

ICONS = pathlib.Path('static/icons')


def test_manifest_is_served_and_names_real_icons(client):
    r = client.get('/static/icons/manifest.webmanifest')
    assert r.status_code == 200
    assert r.mimetype == 'application/manifest+json'
    manifest = json.loads(r.get_data(as_text=True))
    assert manifest['display'] == 'standalone'
    assert manifest['start_url'] == '/' and manifest['scope'] == '/'
    # Android wants a 192 and a 512, and a maskable one for its round icons
    sizes = {i['sizes'] for i in manifest['icons']}
    assert {'192x192', '512x512'} <= sizes
    assert any(i['purpose'] == 'maskable' for i in manifest['icons'])
    for icon in manifest['icons']:
        assert client.get(icon['src']).status_code == 200, icon['src']


def test_every_page_links_the_icons(client, people):
    """Signed out (the sign-in page) and signed in: base.html carries them."""
    pages = [client.get('/auth/login').get_data(as_text=True)]
    login(client, 'alice')
    pages.append(client.get('/collections/collections').get_data(as_text=True))
    for page in pages:
        head = page[:page.index('</head>')]
        assert '<link rel="manifest" href="/static/icons/manifest.webmanifest' in head
        assert 'rel="apple-touch-icon" href="/static/icons/apple-touch-icon.png' in head
        assert 'rel="icon" href="/static/icons/favicon.svg' in head
        assert '<meta name="theme-color"' in head


def test_pngs_are_rendered_at_their_sizes():
    """The PNGs come from the SVGs (static/icons/README.md); each is the size
    its name and the manifest say. PNG width and height sit at bytes 16-24."""
    for name, size in [('icon-512.png', 512), ('icon-192.png', 192),
                       ('apple-touch-icon.png', 180), ('favicon-32.png', 32)]:
        data = (ICONS / name).read_bytes()
        assert data[:8] == b'\x89PNG\r\n\x1a\n', name
        assert int.from_bytes(data[16:20], 'big') == size, name
        assert int.from_bytes(data[20:24], 'big') == size, name


def test_status_bar_follows_the_theme():
    js = pathlib.Path('static/common.js').read_text()
    assert 'function syncThemeColor()' in js
    assert "document.addEventListener('DOMContentLoaded', syncThemeColor);" in js
    assert 'syncThemeColor();' in pathlib.Path('static/sidebar.js').read_text()


def test_launch_splash_only_in_the_installed_app(client, people):
    """The launch splash (2026-11-22): loaded in <head>, not deferred, so its
    cover is up before the first paint; only in the installed app, once per
    launch, never in Cyberpunk (its boot screen instead); the word in Young
    Serif; built without innerHTML."""
    login(client, 'alice')
    page = client.get('/collections/collections').get_data(as_text=True)
    head = page[:page.index('</head>')]
    assert re.search(r'<script src="/static/splash\.js\?v=\w+"></script>', head)   # not deferred
    js = pathlib.Path('static/splash.js').read_text()
    assert "root.dataset.style === 'cyberpunk') return;" in js
    assert '(display-mode: standalone)' in js and 'navigator.standalone' in js
    assert 'sessionStorage' in js and 'catch' in js
    assert "'Libaraxia'" in js and 'innerHTML' not in js
    css = pathlib.Path('static/styles.css').read_text()
    splash = css[css.index('/* ---- Launch splash'):css.index('/* ==== Cyberpunk')]
    assert ':root[data-splash="on"]::before' in splash
    assert '"Young Serif"' in splash
    assert 'prefers-reduced-motion: reduce' in splash
    # Over the scanlines and every dialog (the highest elsewhere is 70)
    assert 'z-index: 100;' in splash
    assert 'const HOLD = 1100;' in js                   # about 1.35 s with the fade (Phil)

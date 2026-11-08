"""Phase 8.0: the pure parts of static/scanner.js (check digits, the
read confirmer, the default camera), run under node.

The browser parts (camera, decoding) can't run here; those are tested by
hand on a phone over HTTPS. Skipped when node isn't installed (GitHub's
ubuntu runners have it).
"""
import json
import pathlib
import shutil
import subprocess

import pytest

SCANNER = pathlib.Path(__file__).resolve().parent.parent / 'static' / 'scanner.js'
NODE = shutil.which('node')

pytestmark = pytest.mark.skipif(NODE is None, reason='node is not installed')


def run_js(body):
    """Run `body` with scanner.js's exports as `s`; it must print JSON."""
    script = f'const s = require({json.dumps(str(SCANNER))});\n{body}'
    out = subprocess.run([NODE, '-e', script], capture_output=True, text=True,
                         timeout=30, check=True)
    return json.loads(out.stdout)


def call(fn, *args):
    return run_js(f'console.log(JSON.stringify(s.{fn}(...{json.dumps(list(args))})))')


@pytest.mark.parametrize('code, ok', [
    ('9780306406157', True),     # the textbook ISBN-13 example
    ('9780306406158', False),    # last digit off by one
    ('9780316769488', True),     # The Catcher in the Rye
    ('4006381333931', True),     # non-book EAN-13
    ('0012345678905', True),     # UPC-A 012345678905 with the EAN-13 leading 0
    ('978030640615', False),     # 12 digits
    ('97803064061571', False),   # 14 digits
    ('978030640615X', False),
    ('', False),
])
def test_ean13(code, ok):
    assert call('isValidEan13', code) is ok


@pytest.mark.parametrize('code, ok', [
    ('012345678905', True),
    ('036000291452', True),      # a real UPC-A
    ('012345678900', False),
    ('12345678905', False),      # 11 digits
])
def test_upc_a(code, ok):
    assert call('isValidUpcA', code) is ok


@pytest.mark.parametrize('code, ok', [
    ('0306406152', True),
    ('0306406153', False),
    ('080442957X', True),        # check digit X
    ('080442957x', True),
    ('0804429570', False),
    ('03064061', False),
])
def test_isbn10(code, ok):
    assert call('isValidIsbn10', code) is ok


@pytest.mark.parametrize('raw, expected', [
    ('9780306406157', '9780306406157'),
    ('012345678905', '0012345678905'),     # UPC-A becomes EAN-13
    ('9780306406158', None),               # bad check digit
    ('0306406152', None),                  # ISBN-10 is never printed as a barcode
    ('96385074', None),                    # EAN-8 isn't accepted
    (' 9780306406157 ', '9780306406157'),
    (None, None),
])
def test_normalize_scanned_code(raw, expected):
    assert call('normalizeScannedCode', raw) == expected


def test_confirmer_needs_identical_reads_in_a_row():
    result = run_js('''
        let t = 0;
        const c = s.createReadConfirmer(3, 1500, () => t);
        const out = [];
        for (const code of ['A', 'A', 'B', 'A', 'A', 'A']) { t += 100; out.push(c.push(code)); }
        console.log(JSON.stringify(out));
    ''')
    # A, A then a B resets the run; only the third A in a row is accepted.
    assert result == [None, None, None, None, None, 'A']


def test_confirmer_forgets_stale_reads():
    result = run_js('''
        let t = 0;
        const c = s.createReadConfirmer(3, 1500, () => t);
        const out = [c.push('A'), c.push('A')];
        t += 5000;                       // barcode left the box for a while
        out.push(c.push('A'), c.push('A'), c.push('A'));
        console.log(JSON.stringify(out));
    ''')
    assert result == [None, None, None, None, 'A']


def labels(*names):
    return [{'deviceId': f'id{i}', 'label': n} for i, n in enumerate(names)]


@pytest.mark.parametrize('devices, expected', [
    # iPhone Pro: the Ultra Wide (macro autofocus; the main camera can't
    # focus close enough), not a lens-switching virtual camera.
    (labels('Front Camera', 'Back Triple Camera', 'Back Dual Wide Camera',
            'Back Ultra Wide Camera', 'Back Telephoto Camera', 'Back Camera'), 'id3'),
    (labels('Back Camera', 'Back Ultra Wide Camera'), 'id1'),
    # An iPhone without an Ultra Wide: the main back camera.
    (labels('Front Camera', 'Back Camera'), 'id1'),
    # Android: the plain back camera, not an (often fixed-focus) ultra-wide.
    (labels('camera2 1, facing front', 'camera2 0, facing back'), 'id1'),
    (labels('camera2 2, facing back ultra wide', 'camera2 0, facing back'), 'id1'),
    # Laptop: no back camera, keep the browser's choice.
    (labels('Integrated Camera (04f2:b6dd)'), None),
    (labels('Front Camera'), None),
    # Labels unreadable (no permission yet).
    (labels('', ''), None),
])
def test_preferred_back_camera(devices, expected):
    assert call('preferredBackCamera', devices) == expected


# Phase 8.2: what a code is. Must agree with utils/media.py classify_code,
# so the same cases run through both.
CLASSIFY_CASES = [
    ('9780306406157', 'book'),       # ISBN-13 (978)
    ('9791090636071', 'book'),       # ISBN-13 (979)
    ('0306406152', 'book'),          # ISBN-10
    ('080442957X', 'book'),          # ISBN-10, X check digit
    ('012345678905', 'video'),       # UPC-A
    ('0012345678905', 'video'),      # the same as EAN-13
    ('4006381333931', 'video'),      # non-book EAN-13
    ('012345678906', None),          # bad check digit
    ('', None),
]


@pytest.mark.parametrize('code, kind', CLASSIFY_CASES)
def test_classify_code_matches_server(code, kind):
    from utils import media
    assert call('classifyCode', code) == kind
    assert media.classify_code(code) == kind

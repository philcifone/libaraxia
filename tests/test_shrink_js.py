"""Photos are shrunk in the browser before upload (common.js shrinkSize,
prod 2026-11-21: a phone photo over a weak signal outlasted gunicorn's 30 s
timeout). The pure size helper runs under node; the inputs opt in with
data-shrink."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
NODE = shutil.which('node')


def shrink_sizes(cases):
    src = (ROOT / 'static' / 'common.js').read_text()
    fn = re.search(r'function shrinkSize\(w, h, max\) \{.*?\n\}', src, re.S).group(0)
    script = fn + f'\nconsole.log(JSON.stringify({json.dumps(cases)}.map(c => shrinkSize(...c))))'
    return json.loads(subprocess.run([NODE, '-e', script], capture_output=True, text=True, check=True).stdout)


@pytest.mark.skipif(not NODE, reason='node not installed')
def test_shrink_size_keeps_the_aspect_and_never_scales_up():
    assert shrink_sizes([
        [4032, 3024, 2400],     # a 12 MP phone photo, landscape
        [3024, 4032, 2400],     # portrait
        [8064, 6048, 2000],     # 48 MP
        [2400, 1000, 2400],     # already fits exactly
        [800, 600, 2400],       # small
        [0, 0, 2400],           # not decoded
    ]) == [[2400, 1800], [1800, 2400], [2000, 1500], None, None, None]


def test_every_image_upload_is_shrunk_first():
    """Each image file input opts in, with the longest side the server keeps."""
    found = {}
    for path in (ROOT / 'templates').rglob('*.html'):
        for tag in re.findall(r'<input type="file"[^>]*>', path.read_text()):
            if 'image' in tag:
                found.setdefault(path.name, []).append(re.search(r'data-shrink="(\d+)"', tag))
    assert found and all(all(found_on) for found_on in found.values()), found

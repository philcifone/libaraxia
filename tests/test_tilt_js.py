"""ROADMAP 16.0 step 12: the Shelf tilt glare. The pure maths of
static/tilt.js runs under node (skipped without it); the sensor, the
iPhone permission prompt and the feel are checked by hand on a phone over
HTTPS. The switch is in Settings -> Appearance, Shelf only."""
import json
import pathlib
import shutil
import subprocess

import pytest

from conftest import login

SCRIPT = pathlib.Path(__file__).resolve().parent.parent / 'static' / 'tilt.js'
NODE = shutil.which('node')
needs_node = pytest.mark.skipif(NODE is None, reason='node is not installed')


def call(fn, *args):
    script = (f'const s = require({json.dumps(str(SCRIPT))});\n'
              f'console.log(JSON.stringify(s.{fn}(...{json.dumps(list(args))})))')
    out = subprocess.run([NODE, '-e', script], capture_output=True, text=True, timeout=30, check=True)
    return json.loads(out.stdout)


@needs_node
def test_axes_follow_the_screen_not_the_device():
    # beta 10 (top away from you), gamma 20 (right edge down)
    assert call('tiltAxes', 10, 20, 0) == [20, 10]
    assert call('tiltAxes', 10, 20, 90) == [10, -20]       # landscape, turned left
    assert call('tiltAxes', 10, 20, 180) == [-20, -10]
    assert call('tiltAxes', 10, 20, 270) == [-10, 20]
    assert call('tiltAxes', 10, 20, -90) == [-10, 20]      # some browsers say -90


@needs_node
def test_shift_is_zero_at_rest_mirrors_the_tilt_and_stays_on_the_cover():
    assert call('tiltShift', [5, 40], [5, 40]) == 0
    assert call('tiltShift', [10, 0], [0, 0]) < 0          # tilt right, light slides left
    assert call('tiltShift', [-10, 0], [0, 0]) > 0
    assert call('tiltShift', [90, 90], [0, 0]) == -call('tiltShift', [-90, -90], [0, 0]) == -30


def test_tilt_switch_is_in_appearance_and_the_script_on_every_page(client, db, people):
    login(client, 'alice')
    page = client.get('/user/settings').get_data(as_text=True)
    assert 'data-tilt-picker' in page and 'data-tilt-note' in page
    assert page.count('data-click="setTilt"') == 2
    assert 'tilt-opt' in page and 'theme-opt" data-click="setTilt"' not in page   # not saved with the theme
    assert '/static/tilt.js" defer></script>' in page
    css = pathlib.Path('static/styles.css').read_text()
    assert ':root:not([data-style="shelf"]) [data-tilt-picker] { display: none; }' in css
    js = SCRIPT.read_text()
    for needle in ("'(prefers-reduced-motion: reduce)'", 'requestPermission', "'--sheen-shift'",
                   'requestAnimationFrame', "root.dataset.style !== 'shelf'"):
        assert needle in js, needle

"""ROADMAP 15.3: the pure helpers of static/cover_crop.js (rotation, box
resizing with a ratio, quad checks), run under node, and checked against the
server's renderer so both agree on what a rotated crop means.

The browser part (canvas, dragging, the loupe) is tested by hand, on a phone
over HTTPS. Skipped when node isn't installed.
"""
import json
import pathlib
import shutil
import subprocess

import pytest
from PIL import Image

from utils import cover_crop

SCRIPT = pathlib.Path(__file__).resolve().parent.parent / 'static' / 'cover_crop.js'
NODE = shutil.which('node')

pytestmark = pytest.mark.skipif(NODE is None, reason='node is not installed')


def call(fn, *args):
    script = (f'const s = require({json.dumps(str(SCRIPT))});\n'
              f'console.log(JSON.stringify(s.{fn}(...{json.dumps(list(args))})))')
    out = subprocess.run([NODE, '-e', script], capture_output=True, text=True, timeout=30, check=True)
    return json.loads(out.stdout)


RECT = {'v': 1, 'rotate': 0, 'mode': 'rect', 'box': [0.1, 0.2, 0.3, 0.4]}
QUAD = {'v': 1, 'rotate': 0, 'mode': 'quad', 'aspect': 0.5,
        'quad': [[0.1, 0.1], [0.8, 0.2], [0.9, 0.9], [0.2, 0.8]]}


def test_rotate_point_is_a_clockwise_quarter_turn():
    assert call('rotatePoint', [0, 0]) == [1, 0]        # top-left -> top-right
    assert call('rotatePoint', [1, 0]) == [1, 1]        # top-right -> bottom-right
    assert call('rotatePoint', [0.25, 0.75]) == [0.25, 0.25]


@pytest.mark.parametrize('geom', [RECT, QUAD])
def test_four_turns_are_the_identity(geom):
    out = call('rotateGeometry', geom, 4)
    assert out['rotate'] == 0 and out['mode'] == geom['mode']
    key = 'box' if geom['mode'] == 'rect' else 'quad'
    flat = lambda v: [n for p in v for n in (p if isinstance(p, list) else [p])]
    assert flat(out[key]) == pytest.approx(flat(geom[key]))
    # and a turn one way then back the other
    back = call('rotateGeometry', call('rotateGeometry', geom, 1), -1)
    assert flat(back[key]) == pytest.approx(flat(geom[key]))


def test_quad_aspect_turns_over():
    assert call('rotateGeometry', QUAD, 1)['aspect'] == 2


@pytest.mark.parametrize('geom', [RECT, QUAD])
@pytest.mark.parametrize('turns', [1, 2, 3])
def test_js_rotation_agrees_with_the_server_renderer(geom, turns):
    """Cropping the turned geometry out of the original gives the turned
    picture of the original crop."""
    img = Image.new('RGB', (80, 120), 'white')
    for x in range(80):
        for y in range(120):
            img.putpixel((x, y), (x * 3 % 256, y * 2 % 256, (x + y) % 256))
    turned = call('rotateGeometry', geom, turns)
    # The original crop, then turned the same number of quarter turns
    expected = cover_crop.render(img, cover_crop.parse_geometry(geom))
    for _ in range(turns):
        expected = expected.transpose(Image.Transpose.ROTATE_270)     # clockwise
    actual = cover_crop.render(img, cover_crop.parse_geometry(turned))
    if geom['mode'] == 'rect':
        assert actual.size == expected.size
    # Compare a handful of pixels away from the borders (rounding at the edges)
    w, h = expected.size
    actual = actual.resize(expected.size)
    for fx, fy in [(.3, .3), (.5, .5), (.7, .6)]:
        a = actual.getpixel((int(w * fx), int(h * fy)))
        e = expected.getpixel((int(w * fx), int(h * fy)))
        assert all(abs(p - q) <= 40 for p, q in zip(a, e)), (a, e)


def test_resize_rect_follows_the_pointer_with_the_opposite_corner_fixed():
    # drag the bottom-right corner of the full frame to the middle
    assert call('resizeRect', [0, 0, 1, 1], 2, [0.5, 0.5]) == [0, 0, 0.5, 0.5]
    # drag the top-left corner: the bottom-right (0.6, 0.6) stays
    box = call('resizeRect', [0.2, 0.2, 0.4, 0.4], 0, [0.1, 0.3])
    assert box == pytest.approx([0.1, 0.3, 0.5, 0.3])


def test_resize_rect_stays_in_the_image_and_above_the_minimum():
    assert call('resizeRect', [0, 0, 0.5, 0.5], 2, [3, 3]) == [0, 0, 1, 1]
    assert call('resizeRect', [0, 0, 0.5, 0.5], 2, [-3, -3])[2:] == [0.02, 0.02]
    # dragged past the fixed corner: it doesn't flip
    box = call('resizeRect', [0.4, 0.4, 0.2, 0.2], 2, [0.1, 0.1])
    assert box[0] == pytest.approx(0.4) and box[2] == pytest.approx(0.02)


@pytest.mark.parametrize('point', [[0.9, 0.3], [0.3, 0.9], [0.6, 0.6], [1.5, 1.5], [0.05, 0.05]])
def test_resize_rect_keeps_a_ratio(point):
    box = call('resizeRect', [0.2, 0.2, 0.3, 0.45], 2, point, {'ratio': 2 / 3})
    x, y, w, h = box
    assert w / h == pytest.approx(2 / 3)
    assert w >= 0.02 - 1e-9 and h >= 0.02 - 1e-9
    assert x + w <= 1 + 1e-9 and y + h <= 1 + 1e-9


def test_fit_ratio_and_conversion():
    # a 100 x 200 px image: a square box spans twice as much of the width as of the height
    assert call('fractionalRatio', 1, 100, 200) == 2
    x, y, w, h = call('fitRatio', [0, 0, 1, 1], 0.5)
    assert (w, h) == (0.5, 1) and x == 0.25
    assert call('ratioFor', '2:3', False, 100, 200) == pytest.approx(2 / 3)
    assert call('ratioFor', '2:3', True, 100, 200) == pytest.approx(1.5)
    assert call('ratioFor', '1:1', True, 100, 200) == 1
    assert call('ratioFor', 'original', True, 100, 200) == 0.5
    assert call('ratioFor', 'free', False, 100, 200) is None


def test_quad_checks_match_the_server():
    square = [[.1, .1], [.9, .1], [.9, .9], [.1, .9]]
    assert call('isConvex', square) is True
    assert call('quadArea', square) == pytest.approx(0.64)
    for bad in ([[.1, .1], [.9, .9], [.9, .1], [.1, .9]],           # bow-tie
                [[.1, .9], [.9, .9], [.9, .1], [.1, .1]],           # mirrored
                [[.1, .1], [.5, .4], [.9, .1], [.5, .9]]):          # dented
        assert call('isConvex', bad) is False
        assert cover_crop.is_convex_quad([tuple(p) for p in bad]) is False
    assert cover_crop.is_convex_quad([tuple(p) for p in square])


def test_bounding_box_and_rectangle_detection():
    assert call('boundingBox', QUAD['quad']) == pytest.approx([0.1, 0.1, 0.8, 0.8])
    assert call('isRectangle', [[.1, .1], [.9, .1], [.9, .9], [.1, .9]]) is True
    assert call('isRectangle', QUAD['quad']) is False


def test_to_geometry_is_what_the_server_accepts():
    state = {'rotate': 90, 'mode': 'rect', 'rect': [0.1, 0.2, 0.3, 0.4], 'quad': [], 'aspect': None}
    assert cover_crop.parse_geometry(call('toGeometry', state))
    state = {'rotate': 0, 'mode': 'quad', 'rect': [0, 0, 1, 1], 'aspect': 0.7,
             'quad': [[.1, .1], [.9, .1], [.9, .9], [.1, .9]]}
    assert cover_crop.parse_geometry(call('toGeometry', state))['aspect'] == 0.7

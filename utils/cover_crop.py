"""Cover crop and perspective correction (ROADMAP 15.3).

The browser (static/cover_crop.js) sends only *geometry*: fractions of the
image, never pixels. The server holds its own copy of the image (the "source"),
renders the crop with Pillow and saves the result as a normal cover.

Geometry is a small JSON document, validated by `parse_geometry`:

    {"v": 1, "rotate": 90, "mode": "rect", "box": [x, y, w, h]}
    {"v": 1, "rotate": 0,  "mode": "quad",
     "quad": [[x, y] x 4: top-left, top-right, bottom-right, bottom-left],
     "aspect": 0.6667}            # width / height, optional

`rotate` is clockwise degrees (0/90/180/270) and is applied first; every
coordinate is a fraction of the *rotated* image, i.e. of what the user sees.

Staged files: a freshly picked photo is uploaded once, at up to 2400 px, to
uploads/crop/<token>.jpg so the crop works from a big original instead of the
500x1000 cover. Only such staged files may be deleted because the browser
named them (`is_staged`); any other path the browser names is read, never
removed.
"""
import json
import math
import os
import re
import secrets
import time
from io import BytesIO

from flask import current_app
from PIL import Image, ImageOps, UnidentifiedImageError

from utils.book_utils import MAX_IMAGE_SIZE, allowed_file, save_cover_image
from utils.image_utils import delete_image_file, is_safe_upload_path

GEOMETRY_VERSION = 1
STAGE_MAX = (2400, 2400)            # staged originals are shrunk to this
STAGE_DIR = 'uploads/crop'
STAGE_MAX_AGE = 24 * 3600           # seconds before an abandoned staged file is swept
PREVIEW_MAX = 900                   # previews render from a copy at most this long
OUTPUT_MAX = 2 * max(MAX_IMAGE_SIZE)   # a rendered crop's long side, before the cover is shrunk
MIN_BOX = 0.02                      # smallest crop, as a fraction of each side
MIN_PIXELS = 16                     # ... and in source pixels
MIN_QUAD_AREA = 0.01                # smallest quad, as a fraction of the image
MAX_JSON_CHARS = 1000
_EPS = 1e-6
_STAGED_RE = re.compile(r'^uploads/crop/[A-Za-z0-9_-]{20,}\.jpg$')


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------

def _number(value, low=0.0, high=1.0, slack=_EPS):
    """A finite float in [low, high] (clamped when it overshoots by `slack`)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError('The crop has a bad number in it.')
    value = float(value)
    if not math.isfinite(value) or value < low - slack or value > high + slack:
        raise ValueError('The crop is outside the image.')
    return min(max(value, low), high)


def quad_area(quad):
    """Shoelace area of a polygon given as [(x, y), ...]."""
    total = 0.0
    for (x1, y1), (x2, y2) in zip(quad, quad[1:] + quad[:1]):
        total += x1 * y2 - x2 * y1
    return abs(total) / 2


def is_convex_quad(quad):
    """True if the four points, in top-left, top-right, bottom-right,
    bottom-left order, form a convex quadrilateral that isn't mirrored.

    Walk the edges and take the cross product of each pair of consecutive
    edges. A convex polygon turns the same way at every corner; a bow-tie
    (self-intersecting) or a dented quad flips sign somewhere. With y pointing
    down, the right winding for TL -> TR -> BR -> BL gives positive crosses.
    """
    for i in range(4):
        ax, ay = quad[i]
        bx, by = quad[(i + 1) % 4]
        cx, cy = quad[(i + 2) % 4]
        cross = (bx - ax) * (cy - by) - (by - ay) * (cx - bx)
        if cross <= _EPS:
            return False
    return True


def parse_geometry(raw):
    """Validate geometry (a JSON string or a dict) and return it normalized.
    Raises ValueError with a short, user-safe message on any problem."""
    if isinstance(raw, (str, bytes)):
        if len(raw) > MAX_JSON_CHARS:
            raise ValueError('The crop is too long.')
        try:
            raw = json.loads(raw)
        except (ValueError, RecursionError):
            raise ValueError('The crop is not valid.')
    if not isinstance(raw, dict) or raw.get('v') != GEOMETRY_VERSION or isinstance(raw.get('v'), bool):
        raise ValueError('The crop is not valid.')

    rotate = raw.get('rotate', 0)
    if isinstance(rotate, bool) or rotate not in (0, 90, 180, 270):
        raise ValueError('The rotation must be 0, 90, 180 or 270.')
    mode = raw.get('mode')

    if mode == 'rect':
        box = raw.get('box')
        if not isinstance(box, list) or len(box) != 4:
            raise ValueError('The crop box is not valid.')
        x, y, w, h = (_number(v) for v in box)
        if x + w > 1 + _EPS or y + h > 1 + _EPS:
            raise ValueError('The crop box runs off the image.')
        w, h = min(w, 1 - x), min(h, 1 - y)
        if w < MIN_BOX or h < MIN_BOX:
            raise ValueError('The crop box is too small.')
        return {'v': 1, 'rotate': int(rotate), 'mode': 'rect', 'box': [x, y, w, h]}

    if mode == 'quad':
        points = raw.get('quad')
        if not isinstance(points, list) or len(points) != 4:
            raise ValueError('The corners are not valid.')
        quad = []
        for point in points:
            if not isinstance(point, list) or len(point) != 2:
                raise ValueError('The corners are not valid.')
            quad.append((_number(point[0], slack=1e-3), _number(point[1], slack=1e-3)))
        if not is_convex_quad(quad):
            raise ValueError('The four corners must form a four-sided shape that does not cross itself.')
        if quad_area(quad) < MIN_QUAD_AREA:
            raise ValueError('The selected area is too small.')
        aspect = raw.get('aspect')
        if aspect is not None:
            aspect = _number(aspect, 0.1, 10, slack=0)
        return {'v': 1, 'rotate': int(rotate), 'mode': 'quad',
                'quad': [list(p) for p in quad], 'aspect': aspect}

    raise ValueError('The crop mode is not valid.')


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def perspective_coeffs(quad_px, out_w, out_h):
    """The 8 coefficients Pillow's Image.transform(PERSPECTIVE) wants.

    Pillow works backwards: for every pixel (u, v) of the *output* it asks
    where to read in the *input* (x, y):

        x = (a*u + b*v + c) / (g*u + h*v + 1)
        y = (d*u + e*v + f) / (g*u + h*v + 1)

    This is a homography; eight unknowns (a..h), and we know four pairs of
    points: the output rectangle's corners (0,0) (W,0) (W,H) (0,H) must land
    on the quad's corners. Multiply out the denominator and each pair gives
    two equations that are linear in the unknowns:

        a*u + b*v + c - g*u*x - h*v*x = x
        d*u + e*v + f - g*u*y - h*v*y = y

    Four pairs, eight equations, eight unknowns: solved below by Gaussian
    elimination with partial pivoting (swap in the largest pivot each step so
    rounding errors stay small). No numpy needed for a system this size.
    """
    corners = [(0, 0), (out_w, 0), (out_w, out_h), (0, out_h)]
    rows = []
    for (u, v), (x, y) in zip(corners, quad_px):
        rows.append([u, v, 1, 0, 0, 0, -u * x, -v * x, x])
        rows.append([0, 0, 0, u, v, 1, -u * y, -v * y, y])

    n = 8
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(rows[r][col]))
        if abs(rows[pivot][col]) < 1e-12:
            raise ValueError('The corners do not make a usable shape.')
        rows[col], rows[pivot] = rows[pivot], rows[col]
        for r in range(n):
            if r != col:
                factor = rows[r][col] / rows[col][col]
                if factor:
                    rows[r] = [a - factor * b for a, b in zip(rows[r], rows[col])]
    return tuple(rows[i][n] / rows[i][i] for i in range(n))


def output_size(quad_px, aspect=None):
    """Pixel size of a perspective-corrected crop: as wide as the quad's
    longer horizontal edge, as tall as its longer vertical one. With an
    `aspect` (width / height) the width is kept and the height follows. The
    long side is capped at OUTPUT_MAX."""
    tl, tr, br, bl = quad_px
    width = max(math.dist(tl, tr), math.dist(bl, br))
    height = max(math.dist(tl, bl), math.dist(tr, br))
    if aspect:
        height = width / aspect
    longest = max(width, height)
    if longest > OUTPUT_MAX:
        width, height = width * OUTPUT_MAX / longest, height * OUTPUT_MAX / longest
    return max(1, round(width)), max(1, round(height))


_QUARTER_TURNS = {
    0: None,
    90: Image.Transpose.ROTATE_270,    # Pillow's ROTATE_90 is counter-clockwise
    180: Image.Transpose.ROTATE_180,
    270: Image.Transpose.ROTATE_90,
}


def render(img, geom):
    """Render parsed geometry against an RGB image (already EXIF-upright)."""
    turn = _QUARTER_TURNS[geom['rotate']]
    if turn is not None:
        img = img.transpose(turn)
    width, height = img.size

    if geom['mode'] == 'rect':
        x, y, w, h = geom['box']
        left, top = round(x * width), round(y * height)
        right, bottom = min(width, round((x + w) * width)), min(height, round((y + h) * height))
        if right - left < MIN_PIXELS or bottom - top < MIN_PIXELS:
            raise ValueError('The crop box is too small.')
        return img.crop((left, top, right, bottom))

    quad_px = [(px * width, py * height) for px, py in geom['quad']]
    out_w, out_h = output_size(quad_px, geom.get('aspect'))
    if out_w < MIN_PIXELS or out_h < MIN_PIXELS:
        raise ValueError('The selected area is too small.')
    coeffs = perspective_coeffs(quad_px, out_w, out_h)
    return img.transform((out_w, out_h), Image.Transform.PERSPECTIVE, coeffs, Image.Resampling.BICUBIC)


def render_to_jpeg(img, geom, quality=80):
    """Bytes of a rendered preview."""
    out = BytesIO()
    render(img, geom).save(out, 'JPEG', quality=quality)
    return out.getvalue()


# ---------------------------------------------------------------------------
# Source files
# ---------------------------------------------------------------------------

def _static_root():
    return os.path.join(current_app.root_path, 'static')


def _source_file(path):
    """The real file behind a static-relative source path, or None unless it is
    an existing file inside static/uploads/ (and not an avatar)."""
    if not is_safe_upload_path(path):
        return None
    if os.path.normpath(path).replace(os.sep, '/').startswith('uploads/avatars/'):
        return None
    uploads_root = os.path.realpath(os.path.join(_static_root(), 'uploads'))
    full = os.path.realpath(os.path.join(_static_root(), path))
    if not full.startswith(uploads_root + os.sep) or not os.path.isfile(full):
        return None
    return full


def is_crop_source(path):
    """True if `path` (from the browser) may be cropped: a real file under
    uploads/, not an avatar."""
    return _source_file(path) is not None


def is_staged(path):
    """True only for files `stage_upload` made. These alone may be deleted
    because the browser named them."""
    return isinstance(path, str) and bool(_STAGED_RE.match(path))


def open_source(path):
    """Open a source as an upright RGB image. ValueError if it can't be used."""
    full = _source_file(path)
    if full is None:
        raise ValueError("That cover can't be cropped.")
    try:
        with Image.open(full) as img:
            img.load()
            return _to_rgb(ImageOps.exif_transpose(img))
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError):
        raise ValueError("That cover can't be read.")


def _to_rgb(img):
    """RGB, with transparency flattened onto white (GIF/PNG covers)."""
    if img.mode in ('RGBA', 'LA', 'P'):
        img = img.convert('RGBA')
        background = Image.new('RGB', img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[-1])
        return background
    return img if img.mode == 'RGB' else img.convert('RGB')


def downscale(img, longest=PREVIEW_MAX):
    """A copy at most `longest` px on its long side. Safe before render()
    because geometry is in fractions."""
    if max(img.size) <= longest:
        return img
    small = img.copy()
    small.thumbnail((longest, longest))
    return small


def stage_upload(file_storage):
    """Keep a picked photo as a big JPEG the crop tool can work from.

    Returns {source, width, height}. Raises ValueError for a non-image.
    Re-saving drops the EXIF block, which includes the phone's GPS position, so
    a staged file (and the cover made from it) never carries the location.
    """
    if not file_storage or not file_storage.filename or not allowed_file(file_storage.filename):
        raise ValueError('Pick a PNG, JPG or GIF image.')
    try:
        with Image.open(file_storage.stream) as img:
            img.load()
            img = _to_rgb(ImageOps.exif_transpose(img))
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError):
        raise ValueError("That file isn't an image we can read.")
    sweep_staged()
    img.thumbnail(STAGE_MAX)
    relative = f'{STAGE_DIR}/{secrets.token_urlsafe(16)}.jpg'
    full = os.path.join(_static_root(), relative)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    img.save(full, 'JPEG', quality=90)
    return {'source': relative, 'width': img.width, 'height': img.height}


def sweep_staged(max_age=STAGE_MAX_AGE):
    """Delete staged files nobody saved within `max_age` seconds."""
    folder = os.path.join(_static_root(), STAGE_DIR)
    if not os.path.isdir(folder):
        return
    cutoff = time.time() - max_age
    for name in os.listdir(folder):
        relative = f'{STAGE_DIR}/{name}'
        try:
            if is_staged(relative) and os.path.getmtime(os.path.join(folder, name)) < cutoff:
                delete_image_file(relative)
        except OSError:
            continue


# ---------------------------------------------------------------------------
# The save routes
# ---------------------------------------------------------------------------

def apply_form_crop(form, allowed_sources=()):
    """Render the crop a form asks for and save it as a cover.

    Returns the new path (relative to static/), or None when the form has no
    crop. Raises ValueError for a bad crop. The source must be a staged file
    or one of `allowed_sources` (the item's own cover, a fetched cover), so a
    crafted post can't crop (or delete) somebody else's cover. A staged
    source is deleted once the new cover is saved.
    """
    raw = (form.get('cover_crop') or '').strip()
    source = (form.get('crop_source') or '').strip()
    if not raw:
        return None
    if not (is_staged(source) or source in {s for s in allowed_sources if s}):
        raise ValueError("That cover can't be cropped.")
    geom = parse_geometry(raw)
    new_path = save_cover_image(render(open_source(source), geom))
    if is_staged(source):
        delete_image_file(source)
    return new_path


def crop_or_flash(form, allowed_sources=()):
    """apply_form_crop for a route: on a bad crop, say so, log it and return
    None so the form saves with the cover it would have had."""
    from flask import flash
    try:
        return apply_form_crop(form, allowed_sources)
    except ValueError as err:
        current_app.logger.warning('Cover crop refused: %s', err)
    except Exception:
        current_app.logger.exception('Cover crop failed')
    flash("Couldn't apply the crop, so the cover is unchanged.", 'error')
    return None

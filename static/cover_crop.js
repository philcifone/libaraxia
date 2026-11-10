// Cover crop and perspective tool (ROADMAP 15.3).
//
// A full-screen <dialog> (templates/_cover_crop.html) on the Add and Edit
// pages. It is non-destructive until the form is saved:
//
//   - It works on a *source* image the server already holds: the saved cover,
//     a cover a lookup / "Find a better cover" fetched (#existing_cover_url),
//     or a freshly picked file, which is first staged (uploaded once, at up to
//     2400 px, by POST /covers/crop/source).
//   - "Crop" posts {source, geometry} to /covers/crop/preview and shows the
//     JPEG that comes back. Nothing is stored. Every Crop renders from the
//     original source, never from the previous result, so tweaking never loses
//     quality and Undo is only a stack of geometries.
//   - "Save" writes the hidden inputs crop_source and cover_crop; the route
//     renders the real crop (utils/cover_crop.py) when the form is saved.
//
// Geometry (shared with the server): {v:1, rotate, mode:'rect', box:[x,y,w,h]}
// or {v:1, rotate, mode:'quad', quad:[tl,tr,br,bl], aspect}, all as fractions
// of the image *after* the clockwise `rotate` (0/90/180/270).
//
// The pure helpers at the top are exported for node (tests/test_cover_crop_js.py);
// the DOM part below runs only in a browser. Shared helpers (escapeHtml,
// getCSRFHeaders, registerActions) are in common.js.

'use strict';

// ---------------------------------------------------------------------------
// Pure helpers
// ---------------------------------------------------------------------------

const MIN_BOX = 0.02;           // smallest crop side, as a fraction
const MIN_AREA = 0.01;          // smallest quad, as a fraction of the image
const EPS = 1e-6;
const STAGE_PAD = 28;          // px of stage kept clear round the image

const clamp = (v, lo, hi) => Math.min(Math.max(v, lo), hi);

// Turning the view 90 degrees clockwise sends the point (x, y) to (1 - y, x):
// the top-left corner (0, 0) becomes the top-right (1, 0).
function rotatePoint([x, y]) {
    return [1 - y, x];
}

// The same turn for a box [x, y, w, h]: the new left edge is the old bottom
// edge seen from the right, and width and height swap.
function rotateBox([x, y, w, h]) {
    return [1 - (y + h), x, h, w];
}

// A quad's corners are named by position (top-left first), so after the turn
// the old bottom-left corner is the new top-left one, and so on.
function rotateQuad([tl, tr, br, bl]) {
    return [rotatePoint(bl), rotatePoint(tl), rotatePoint(tr), rotatePoint(br)];
}

// Geometry turned clockwise by `turns` quarter turns (negative = anticlockwise).
// The geometry's `rotate` grows with it, so it still describes the same crop of
// the *original* source.
function rotateGeometry(geom, turns = 1) {
    let g = geom;
    for (let i = 0, n = ((turns % 4) + 4) % 4; i < n; i++) {
        g = {
            ...g,
            rotate: (g.rotate + 90) % 360,
            ...(g.mode === 'rect' ? { box: rotateBox(g.box) } : {
                quad: rotateQuad(g.quad),
                aspect: g.aspect ? 1 / g.aspect : g.aspect,   // the output turns too
            }),
        };
    }
    return g;
}

function quadArea(quad) {
    let total = 0;
    for (let i = 0; i < 4; i++) {
        const [x1, y1] = quad[i];
        const [x2, y2] = quad[(i + 1) % 4];
        total += x1 * y2 - x2 * y1;
    }
    return Math.abs(total) / 2;
}

// Convex and not mirrored (top-left, top-right, bottom-right, bottom-left must
// wind clockwise on screen). Same rule as the server: the cross product of
// every pair of consecutive edges is positive.
function isConvex(quad) {
    for (let i = 0; i < 4; i++) {
        const [ax, ay] = quad[i];
        const [bx, by] = quad[(i + 1) % 4];
        const [cx, cy] = quad[(i + 2) % 4];
        if ((bx - ax) * (cy - by) - (by - ay) * (cx - bx) <= EPS) return false;
    }
    return true;
}

// Corner index: 0 top-left, 1 top-right, 2 bottom-right, 3 bottom-left.
const isLeft = corner => corner === 0 || corner === 3;
const isTop = corner => corner === 0 || corner === 1;

// Drag one corner of a box to `point` with the opposite corner fixed. `ratio`
// is the box's width / height in the same (fractional) units, or null for a
// free box. The box stays inside the image and at least `min` on each side.
function resizeRect([x, y, w, h], corner, point, { ratio = null, min = MIN_BOX } = {}) {
    const ax = isLeft(corner) ? x + w : x;           // the fixed corner
    const ay = isTop(corner) ? y + h : y;
    const sx = isLeft(corner) ? -1 : 1;              // which way from it the box grows
    const sy = isTop(corner) ? -1 : 1;
    const maxW = sx > 0 ? 1 - ax : ax;
    const maxH = sy > 0 ? 1 - ay : ay;
    let nw = Math.max(0, (clamp(point[0], 0, 1) - ax) * sx);
    let nh = Math.max(0, (clamp(point[1], 0, 1) - ay) * sy);

    if (ratio) {
        // Follow whichever axis the pointer moved further along
        nw = Math.max(nw, nh * ratio, min, min * ratio);
        nh = nw / ratio;
        if (nw > maxW) { nw = maxW; nh = nw / ratio; }
        if (nh > maxH) { nh = maxH; nw = nh * ratio; }
    } else {
        nw = Math.min(Math.max(nw, min), maxW);
        nh = Math.min(Math.max(nh, min), maxH);
    }
    return [sx > 0 ? ax : ax - nw, sy > 0 ? ay : ay - nh, nw, nh];
}

// Move a box by (dx, dy), keeping it inside the image.
function moveRect([x, y, w, h], dx, dy) {
    return [clamp(x + dx, 0, 1 - w), clamp(y + dy, 0, 1 - h), w, h];
}

// The largest box of this ratio inside `box`, centred in it.
function fitRatio([x, y, w, h], ratio) {
    let nw = w;
    let nh = h;
    if (w / h > ratio) nw = h * ratio; else nh = w / ratio;
    return [x + (w - nw) / 2, y + (h - nh) / 2, nw, nh];
}

// A ratio in pixels (width / height) as the fractional units the box uses on
// an image of imgW x imgH: w_frac / h_frac = ratio * imgH / imgW.
function fractionalRatio(pixelRatio, imgW, imgH) {
    return pixelRatio ? pixelRatio * imgH / imgW : null;
}

// The pixel ratio a Ratio menu choice means (null = free). Portrait is the
// base; landscape turns it over. Original and 1:1 ignore the orientation.
function ratioFor(choice, landscape, imgW, imgH) {
    if (choice === 'free') return null;
    if (choice === 'original') return imgW / imgH;
    const [a, b] = choice.split(':').map(Number);
    const r = a / b;
    return landscape && r !== 1 ? 1 / r : r;
}

function boundingBox(quad) {
    const xs = quad.map(p => p[0]);
    const ys = quad.map(p => p[1]);
    const x = Math.min(...xs);
    const y = Math.min(...ys);
    return [x, y, Math.max(...xs) - x, Math.max(...ys) - y];
}

function boxCorners([x, y, w, h]) {
    return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]];
}

// A quad that is an axis-aligned rectangle (nothing lost going back to Crop)
function isRectangle(quad, tol = 1e-3) {
    const [tl, tr, br, bl] = quad;
    return Math.abs(tl[1] - tr[1]) < tol && Math.abs(bl[1] - br[1]) < tol
        && Math.abs(tl[0] - bl[0]) < tol && Math.abs(tr[0] - br[0]) < tol;
}

// What goes to the server
function toGeometry({ rotate, mode, rect, quad, aspect }) {
    if (mode === 'rect') return { v: 1, rotate, mode, box: rect.map(round6) };
    return { v: 1, rotate, mode, quad: quad.map(p => p.map(round6)), aspect: aspect || null };
}

function round6(v) {
    return Math.round(v * 1e6) / 1e6;
}

if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        rotatePoint, rotateBox, rotateQuad, rotateGeometry, quadArea, isConvex, resizeRect,
        moveRect, fitRatio, fractionalRatio, ratioFor, boundingBox, boxCorners, isRectangle,
        toGeometry,
    };
}

// ---------------------------------------------------------------------------
// The tool (browser only)
// ---------------------------------------------------------------------------

if (typeof document !== 'undefined') {
    document.addEventListener('DOMContentLoaded', () => {
        if (document.getElementById('crop-dialog')) initCropTool();
    });
}

function initCropTool() {
    const $ = id => document.getElementById(id);
    const dialog = $('crop-dialog');
    const stage = $('crop-stage');
    const canvas = $('crop-canvas');
    const ctx = canvas.getContext('2d');
    const loupe = $('crop-loupe');
    const loupeCtx = loupe.getContext('2d');
    const overlay = $('crop-overlay');
    const dim = $('crop-dim');
    const outline = $('crop-outline');
    const thirds = $('crop-thirds');
    const handles = [...stage.querySelectorAll('.crop-handle')];
    const thumb = $('crop-thumb');
    const openButton = $('crop-open');
    const preview = $('cover-preview');
    const sourceInput = $('crop_source');
    const cropInput = $('cover_crop');
    const note = $('crop-note');
    const SVG_NS = 'http://www.w3.org/2000/svg';

    // Four rule-of-thirds lines, moved with the box
    const thirdLines = [0, 1, 2, 3].map(() => {
        const line = document.createElementNS(SVG_NS, 'line');
        thirds.appendChild(line);
        return line;
    });

    // --- State ------------------------------------------------------------------

    let source = null;              // uploads/... path of the image being cropped
    let image = null;               // its decoded <img>
    let rotate = 0;                 // clockwise degrees applied to the source
    let mode = 'rect';
    let ratioChoice = 'free';       // the Ratio chips: free, original, 1:1, 2:3, 3:4, 27:38
    let landscape = false;          // the Portrait / Landscape pair
    let rect = [0, 0, 1, 1];
    let quad = boxCorners(rect);
    let history = [];               // [{key, geom, blob, url}]: one per Crop press
    let busy = false;
    let requestId = 0;
    let layoutBox = { cw: 0, ch: 0, dispW: 0, dispH: 0, offX: 0, offY: 0 };
    let drag = null;
    let frame = 0;                  // pending requestAnimationFrame
    let invalidTimer = 0;
    let lastTap = null;
    let downPoint = null;

    // Applied to the form (survives closing the dialog)
    let savedUrl = null;            // blob URL shown in #cover-preview
    let originalPreview = null;     // #cover-preview's HTML before the first Save
    const stagedFiles = new WeakMap();   // File -> staged source path

    // --- Small helpers ----------------------------------------------------------

    const rotatedSize = () => (rotate % 180 === 0
        ? [image.naturalWidth, image.naturalHeight] : [image.naturalHeight, image.naturalWidth]);

    function announce(text) {
        $('crop-live').textContent = text;
    }

    function selectedRatio() {
        if (!image) return null;
        const [w, h] = rotatedSize();
        return ratioFor(ratioChoice, landscape, w, h);
    }

    function geometry() {
        return toGeometry({ rotate, mode, rect, quad, aspect: selectedRatio() });
    }

    function setBusyText(text) {
        const el = $('crop-busy');
        el.hidden = !text;
        el.textContent = text || '';
    }

    // Where the stage's drawing area starts on screen: inside its border (a
    // style's card edge, or the Shelf style's wooden frame), because layout()
    // and every stage pixel below count from there
    function stageOrigin() {
        const box = stage.getBoundingClientRect();
        return { left: box.left + stage.clientLeft, top: box.top + stage.clientTop };
    }

    // Normalized (0..1) -> stage pixels, and back
    const toStage = ([x, y]) => [layoutBox.offX + x * layoutBox.dispW, layoutBox.offY + y * layoutBox.dispH];
    const toNorm = (px, py) => [(px - layoutBox.offX) / layoutBox.dispW, (py - layoutBox.offY) / layoutBox.dispH];

    function corners() {
        return mode === 'rect' ? boxCorners(rect) : quad;
    }

    // --- Drawing ----------------------------------------------------------------

    // Draw the source turned clockwise by `turns` degrees into a W x H box at
    // the current origin. W x H is the *turned* size, so for 90 and 270 the
    // image itself is drawn H wide and W tall before the context rotates it.
    function paintRotated(target, W, H) {
        target.save();
        if (rotate === 0) {
            target.drawImage(image, 0, 0, W, H);
        } else if (rotate === 90) {
            target.translate(W, 0);
            target.rotate(Math.PI / 2);
            target.drawImage(image, 0, 0, H, W);
        } else if (rotate === 180) {
            target.translate(W, H);
            target.rotate(Math.PI);
            target.drawImage(image, 0, 0, W, H);
        } else {
            target.translate(0, H);
            target.rotate(-Math.PI / 2);
            target.drawImage(image, 0, 0, H, W);
        }
        target.restore();
    }

    // Fit the (rotated) image into the stage and repaint it. Runs on open, on
    // rotate and when the stage changes size (a phone turning over).
    function layout() {
        if (!image) return;
        const cw = stage.clientWidth;
        const ch = stage.clientHeight;
        if (!cw || !ch) return;
        const [rw, rh] = rotatedSize();
        // Leave room round the image so corner handles at its edges aren't clipped
        const scale = Math.min((cw - 2 * STAGE_PAD) / rw, (ch - 2 * STAGE_PAD) / rh);
        const dispW = rw * scale;
        const dispH = rh * scale;
        layoutBox = { cw, ch, dispW, dispH, offX: (cw - dispW) / 2, offY: (ch - dispH) / 2 };
        stage.style.setProperty('--picture-bottom', `${layoutBox.offY + dispH}px`);   // the Shelf ledge

        const dpr = Math.min(window.devicePixelRatio || 1, 2);
        canvas.width = Math.round(dispW * dpr);
        canvas.height = Math.round(dispH * dpr);
        canvas.style.width = `${dispW}px`;
        canvas.style.height = `${dispH}px`;
        canvas.style.transform = `translate3d(${layoutBox.offX}px, ${layoutBox.offY}px, 0)`;
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        paintRotated(ctx, dispW, dispH);

        draw();
    }

    // Move the shade, outline and handles. Cheap: no layout reads, only
    // attribute and transform writes, so it runs once per animation frame.
    function draw() {
        if (!image) return;
        const pts = corners().map(toStage);
        const d = pts.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`);
        // One evenodd path: the picture's rectangle with the crop shape cut
        // out (the SVG has no viewBox, so units are stage pixels and a stale
        // size can't skew it). The margin round the picture stays unshaded.
        const { offX, offY, dispW, dispH } = layoutBox;
        dim.setAttribute('d', `M${offX} ${offY}h${dispW}v${dispH}h${-dispW}Z M${d.join('L')}Z`);
        outline.setAttribute('points', d.join(' '));

        const showThirds = mode === 'rect';
        thirds.style.display = showThirds ? '' : 'none';
        if (showThirds) {
            const [x0, y0] = pts[0];
            const [x1, y1] = pts[2];
            const lines = [
                [x0 + (x1 - x0) / 3, y0, x0 + (x1 - x0) / 3, y1], [x0 + 2 * (x1 - x0) / 3, y0, x0 + 2 * (x1 - x0) / 3, y1],
                [x0, y0 + (y1 - y0) / 3, x1, y0 + (y1 - y0) / 3], [x0, y0 + 2 * (y1 - y0) / 3, x1, y0 + 2 * (y1 - y0) / 3],
            ];
            lines.forEach(([ax, ay, bx, by], i) => {
                thirdLines[i].setAttribute('x1', ax); thirdLines[i].setAttribute('y1', ay);
                thirdLines[i].setAttribute('x2', bx); thirdLines[i].setAttribute('y2', by);
            });
        }
        handles.forEach((handle, i) => {
            handle.style.transform = `translate3d(${pts[i][0] - 22}px, ${pts[i][1] - 22}px, 0)`;
        });
    }

    function scheduleDraw() {
        if (!frame) frame = requestAnimationFrame(() => { frame = 0; applyDrag(); });
    }

    function flashInvalid() {
        overlay.classList.add('is-invalid');
        clearTimeout(invalidTimer);
        invalidTimer = setTimeout(() => overlay.classList.remove('is-invalid'), 250);
    }

    // The magnifier: the area round the active corner at 3x, from the source
    // itself (not the shrunken canvas), with a crosshair. It sits away from the
    // finger and flips to the other side near an edge.
    function drawLoupe(corner) {
        const size = loupe.width;
        const [px, py] = toStage(corners()[corner]);
        let left = clamp(px - size / 2, 4, layoutBox.cw - size - 4);
        let top = py - size - 36;
        if (top < 4) top = py + 36;
        loupe.style.transform = `translate3d(${left}px, ${top}px, 0)`;
        loupe.hidden = false;

        const zoom = 3;
        const [nx, ny] = corners()[corner];
        loupeCtx.fillStyle = '#000';
        loupeCtx.fillRect(0, 0, size, size);
        loupeCtx.save();
        loupeCtx.translate(size / 2 - nx * layoutBox.dispW * zoom, size / 2 - ny * layoutBox.dispH * zoom);
        paintRotated(loupeCtx, layoutBox.dispW * zoom, layoutBox.dispH * zoom);
        loupeCtx.restore();
        const accent = getComputedStyle(document.documentElement).getPropertyValue('--accent').trim();
        loupeCtx.lineWidth = 1;
        loupeCtx.strokeStyle = accent ? `rgb(${accent})` : '#fff';
        loupeCtx.beginPath();
        loupeCtx.moveTo(size / 2, 0); loupeCtx.lineTo(size / 2, size);
        loupeCtx.moveTo(0, size / 2); loupeCtx.lineTo(size, size / 2);
        loupeCtx.stroke();
    }

    // --- Dragging ----------------------------------------------------------------

    // Move a corner of the current shape to p (normalized)
    function moveCorner(corner, p) {
        if (mode === 'rect') {
            const [w, h] = rotatedSize();
            rect = resizeRect(rect, corner, p, { ratio: fractionalRatio(selectedRatio(), w, h) });
            return;
        }
        const next = quad.map(q => q.slice());
        next[corner] = [clamp(p[0], 0, 1), clamp(p[1], 0, 1)];
        // A corner that would fold the shape or shrink it too far stays put
        if (isConvex(next) && quadArea(next) >= MIN_AREA) quad = next; else flashInvalid();
    }

    function applyDrag() {
        if (!drag || !drag.latest) return;
        const [cx, cy] = drag.latest;
        const [nx, ny] = toNorm(cx - drag.bounds.left, cy - drag.bounds.top);
        if (drag.kind === 'corner') {
            moveCorner(drag.corner, [nx + drag.grab[0], ny + drag.grab[1]]);
            draw();
            drawLoupe(drag.corner);
        } else {
            rect = moveRect(drag.rect0, nx - drag.start[0], ny - drag.start[1]);
            draw();
        }
    }

    function insideBox(n) {
        const [x, y, w, h] = rect;
        return mode === 'rect' && n[0] >= x && n[0] <= x + w && n[1] >= y && n[1] <= y + h;
    }

    stage.addEventListener('pointerdown', event => {
        if (!image || (event.pointerType === 'mouse' && event.button !== 0)) return;
        const handle = event.target.closest('.crop-handle');
        const bounds = stageOrigin();      // read once; not during the move
        const point = toNorm(event.clientX - bounds.left, event.clientY - bounds.top);
        if (handle) {
            const corner = Number(handle.dataset.corner);
            const at = corners()[corner];
            // Remember where on the handle it was grabbed, so the corner
            // doesn't jump to the finger
            drag = { kind: 'corner', corner, bounds, grab: [at[0] - point[0], at[1] - point[1]], handle };
            handle.classList.add('is-active');
            handle.focus({ preventScroll: true });
        } else {
            downPoint = [event.clientX, event.clientY];
            if (!insideBox(point)) return;
            drag = { kind: 'move', bounds, start: point, rect0: rect.slice() };
        }
        stage.setPointerCapture(event.pointerId);
        event.preventDefault();
    });

    stage.addEventListener('pointermove', event => {
        if (!drag) {
            if (image && event.pointerType === 'mouse') {
                const bounds = stageOrigin();
                stage.style.cursor = insideBox(toNorm(event.clientX - bounds.left, event.clientY - bounds.top)) ? 'move' : '';
            }
            return;
        }
        drag.latest = [event.clientX, event.clientY];     // the frame callback applies the newest
        scheduleDraw();
    });

    function endDrag() {
        if (!drag) return;
        drag.handle?.classList.remove('is-active');
        loupe.hidden = true;
        drag = null;
    }

    stage.addEventListener('pointerup', event => {
        const wasDrag = drag;
        applyDrag();
        endDrag();
        // A double tap crops. dblclick isn't reliable on touch, so two quick
        // taps close together on the image (not on a handle) do it by hand.
        if (event.pointerType === 'mouse' || wasDrag?.kind === 'corner' || !downPoint) return;
        if (Math.hypot(event.clientX - downPoint[0], event.clientY - downPoint[1]) > 6) return;
        const now = performance.now();
        if (lastTap && now - lastTap.time < 300 && Math.hypot(event.clientX - lastTap.x, event.clientY - lastTap.y) < 24) {
            lastTap = null;
            doCrop();
        } else {
            lastTap = { time: now, x: event.clientX, y: event.clientY };
        }
    });
    stage.addEventListener('pointercancel', endDrag);
    stage.addEventListener('lostpointercapture', endDrag);
    stage.addEventListener('dblclick', event => {
        if (!event.target.closest('.crop-handle')) doCrop();
    });

    // --- Keyboard -------------------------------------------------------------------

    stage.addEventListener('keydown', event => {
        const handle = event.target.closest('.crop-handle');
        if (event.key === 'Enter') {
            event.preventDefault();
            doCrop();
            return;
        }
        const arrows = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }[event.key];
        if (!handle || !arrows) return;
        event.preventDefault();
        const step = event.shiftKey ? 10 : 1;
        const corner = Number(handle.dataset.corner);
        const [x, y] = corners()[corner];
        moveCorner(corner, [x + arrows[0] * step / layoutBox.dispW, y + arrows[1] * step / layoutBox.dispH]);
        draw();
    });

    dialog.addEventListener('keydown', event => {
        if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'z') {
            event.preventDefault();
            undo();
        }
    });

    // --- Toolbar ---------------------------------------------------------------------

    function setPressed(button, on) {
        button.setAttribute('aria-pressed', String(on));
    }

    function syncToolbar() {
        dialog.querySelectorAll('[data-crop-mode]').forEach(b => setPressed(b, b.dataset.cropMode === mode));
        dialog.querySelectorAll('[data-crop-ratio]').forEach(b => setPressed(b, b.dataset.cropRatio === ratioChoice));
        // Free, Original and 1:1 have no tall or wide version
        const fixedShape = ratioChoice === 'free' || ratioChoice === '1:1' || ratioChoice === 'original';
        dialog.querySelectorAll('[data-crop-orient]').forEach(b => {
            setPressed(b, !fixedShape && (b.dataset.cropOrient === 'landscape') === landscape);
            b.disabled = fixedShape;
        });
    }

    // Replace the whole shape (undo, reset, rotate, reopening a saved crop)
    function setGeometry(g) {
        rotate = g.rotate;
        mode = g.mode;
        if (g.mode === 'rect') {
            rect = g.box.slice();
            quad = boxCorners(rect);
        } else {
            quad = g.quad.map(p => p.slice());
            rect = boundingBox(quad);
        }
        syncToolbar();
        layout();
    }

    dialog.querySelectorAll('[data-crop-mode]').forEach(button => {
        button.addEventListener('click', () => {
            const next = button.dataset.cropMode;
            if (next === mode) return;
            if (next === 'quad') {
                quad = boxCorners(rect);                     // seeded from the rectangle
            } else {
                if (!isRectangle(quad) && !window.confirm('Back to Crop? The slanted shape becomes its bounding rectangle.')) return;
                rect = boundingBox(quad);
            }
            mode = next;
            syncToolbar();
            draw();
        });
    });

    dialog.querySelectorAll('[data-crop-rotate]').forEach(button => {
        button.addEventListener('click', () => {
            setGeometry(rotateGeometry(geometry(), Number(button.dataset.cropRotate)));
        });
    });

    function applyRatio() {
        syncToolbar();
        const ratio = selectedRatio();
        if (mode === 'rect' && ratio) {
            const [w, h] = rotatedSize();
            rect = fitRatio(rect, fractionalRatio(ratio, w, h));
        }
        draw();
    }

    dialog.querySelectorAll('[data-crop-ratio]').forEach(button => {
        button.addEventListener('click', () => {
            ratioChoice = button.dataset.cropRatio;
            applyRatio();
        });
    });
    dialog.querySelectorAll('[data-crop-orient]').forEach(button => {
        button.addEventListener('click', () => {
            landscape = button.dataset.cropOrient === 'landscape';
            applyRatio();
        });
    });

    $('crop-reset').addEventListener('click', () => {
        setGeometry(mode === 'rect'
            ? { v: 1, rotate: 0, mode, box: [0, 0, 1, 1] }
            : { v: 1, rotate: 0, mode, quad: boxCorners([0, 0, 1, 1]), aspect: null });
    });

    // --- Crop, Undo, Cancel, Save ------------------------------------------------------

    function showResult(entry) {
        // Roomy screens show it in the panel, small ones as a thumbnail in the
        // stage (CSS picks); both are kept current
        dialog.classList.toggle('has-result', !!entry);
        if (!entry) dialog.classList.remove('crop-compare');
        thumb.hidden = !entry;
        if (entry) {
            $('crop-result-img').src = entry.url;
            $('crop-thumb-img').src = entry.url;
        } else {
            $('crop-result-img').removeAttribute('src');
            $('crop-thumb-img').removeAttribute('src');
        }
        $('crop-undo').hidden = !entry;
        $('crop-save').hidden = !entry;
    }

    // Render the current shape on the server and show it. Resolves true when
    // the result on screen is for the current shape.
    async function doCrop() {
        if (!image || busy) return false;
        const geom = geometry();
        const key = JSON.stringify(geom);
        const top = history[history.length - 1];
        if (top && top.key === key) return true;

        const mine = ++requestId;
        busy = true;
        const button = $('crop-do');
        button.disabled = true;
        button.textContent = 'Cropping...';
        try {
            const response = await fetch('/covers/crop/preview', {
                method: 'POST',
                headers: getCSRFHeaders(),
                body: JSON.stringify({ source, geometry: geom }),
            });
            if (!response.ok) {
                const data = await response.json().catch(() => ({}));
                announce(data.error || "Couldn't render the crop.");
                setBusyText(data.error || "Couldn't render the crop.");
                setTimeout(() => setBusyText(''), 3000);
                return false;
            }
            const blob = await response.blob();
            if (mine !== requestId) return false;           // a newer press superseded this one
            const entry = { key, geom, blob, url: URL.createObjectURL(blob) };
            history.push(entry);
            showResult(entry);
            announce('Cropped');
            return true;
        } catch (err) {
            console.error('Crop preview failed', err);
            announce("Couldn't render the crop.");
            return false;
        } finally {
            busy = false;
            button.disabled = false;
            button.textContent = 'Crop';
        }
    }

    function undo() {
        if (!history.length) return;
        URL.revokeObjectURL(history.pop().url);
        const top = history[history.length - 1];
        if (top) {
            setGeometry(top.geom);
            showResult(top);
        } else {
            setGeometry({ v: 1, rotate: 0, mode: 'rect', box: [0, 0, 1, 1] });
            showResult(null);
        }
        announce('Undone');
    }

    async function save() {
        if (!await doCrop()) return;                        // crop first if the handles moved on
        const top = history[history.length - 1];
        sourceInput.value = source;
        cropInput.value = JSON.stringify(top.geom);

        // Show the result in the form's cover preview (a fresh blob URL: the
        // dialog's own are revoked when it closes)
        if (originalPreview === null) originalPreview = preview.innerHTML;
        if (savedUrl) URL.revokeObjectURL(savedUrl);
        savedUrl = URL.createObjectURL(top.blob);
        const img = document.createElement('img');
        img.src = savedUrl;
        img.alt = 'Cover';
        img.className = 'max-w-[12rem] rounded-lg';
        preview.replaceChildren(img);
        note.classList.remove('hidden');
        announce('Cover cropped. Save the form to keep it.');
        dialog.close();
    }

    function cleanup() {
        history.forEach(entry => URL.revokeObjectURL(entry.url));
        history = [];
        showResult(null);
        endDrag();
        image = null;
        source = null;
        setBusyText('');
        openButton.focus();
    }

    $('crop-do').addEventListener('click', doCrop);
    $('crop-undo').addEventListener('click', undo);
    $('crop-save').addEventListener('click', save);
    $('crop-cancel').addEventListener('click', () => dialog.close());
    dialog.addEventListener('close', cleanup);       // Save, Cancel and Esc all end here
    thumb.addEventListener('click', () => dialog.classList.toggle('crop-compare'));

    new ResizeObserver(() => layout()).observe(stage);

    // --- Opening: find the source ----------------------------------------------------------

    function pickedFile() {
        return $('image')?.files?.[0] || null;
    }

    function hasSource() {
        return !!(pickedFile() || $('existing_cover_url')?.value || openButton.dataset.currentCover);
    }

    // A picked file is uploaded once and remembered per File, so reopening the
    // tool doesn't send it again
    async function stageFile(file) {
        if (stagedFiles.has(file)) return stagedFiles.get(file);
        const body = new FormData();
        body.append('image', file);
        const response = await fetch('/covers/crop/source', {
            method: 'POST',
            headers: { 'X-CSRFToken': getCSRFToken() },
            body,
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok || !data.success) throw new Error(data.error || "Couldn't prepare that image.");
        stagedFiles.set(file, data.source);
        return data.source;
    }

    async function resolveSource() {
        const file = pickedFile();
        if (file) return stageFile(file);
        return $('existing_cover_url')?.value || openButton.dataset.currentCover || null;
    }

    function loadImage(path) {
        return new Promise((resolve, reject) => {
            const img = new Image();
            img.onload = () => resolve(img);
            img.onerror = () => reject(new Error("Couldn't load that cover."));
            img.src = `/static/${encodeURI(path)}`;
        });
    }

    async function openTool() {
        if (!hasSource()) return;
        history = [];
        showResult(null);
        rotate = 0;
        mode = 'rect';
        ratioChoice = 'free';
        landscape = false;
        rect = [0, 0, 1, 1];
        quad = boxCorners(rect);
        syncToolbar();
        dialog.showModal();
        setBusyText('Preparing image...');
        try {
            source = await resolveSource();
            if (!source) throw new Error("There's no cover to crop yet.");
            const loaded = await loadImage(source);
            image = loaded;
            setBusyText('');
            layout();
            // Reopen with a crop already saved for this source: non-destructive
            if (cropInput.value && sourceInput.value === source) {
                try { setGeometry(JSON.parse(cropInput.value)); await doCrop(); } catch (err) { console.error(err); }
            }
            handles[0].focus({ preventScroll: true });
        } catch (err) {
            console.error('Crop tool could not open', err);
            setBusyText(err.message);
            image = null;
            setTimeout(() => { if (dialog.open && !image) dialog.close(); }, 2200);
        }
    }

    openButton.addEventListener('click', openTool);

    // --- The form's side ------------------------------------------------------------------------

    function clearCrop(restore) {
        sourceInput.value = '';
        cropInput.value = '';
        note.classList.add('hidden');
        if (savedUrl) { URL.revokeObjectURL(savedUrl); savedUrl = null; }
        if (restore && originalPreview !== null) preview.innerHTML = originalPreview;
        originalPreview = null;
    }

    function refreshButton() {
        openButton.classList.toggle('hidden', !hasSource());
    }

    // A new cover came from somewhere else (picked file, lookup, "Find a better
    // cover"): any pending crop was of the old one
    document.addEventListener('cover-changed', () => {
        if (sourceInput.value) announce('Crop removed');
        clearCrop(false);
        refreshButton();
    });
    $('image')?.addEventListener('change', () => {
        clearCrop(false);
        refreshButton();
    });

    registerActions({
        removeCrop: () => {
            clearCrop(true);
            announce('Crop removed');
        },
    });

    refreshButton();
}

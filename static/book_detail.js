// Book page (templates/book_detail.html): the reading-session form.
// Description and friend-review toggles are in script.js, tags in tags.js.

'use strict';

function sessionForm() {
    return {
        container: document.getElementById('session-form-container'),
        title: document.getElementById('session-form-title'),
        sessionId: document.getElementById('form_session_id'),
        dateStarted: document.getElementById('form_date_started'),
        dateCompleted: document.getElementById('form_date_completed'),
    };
}

// mode: 'add' or 'edit'. The heading's wording ("Reading Session",
// "Listening Session") comes from the template's data-add-title / data-edit-title.
function openSessionForm(mode, sessionId, dateStarted, dateCompleted) {
    const f = sessionForm();
    f.title.textContent = f.title.dataset[mode + 'Title'];
    f.sessionId.value = sessionId;
    f.dateStarted.value = dateStarted;
    f.dateCompleted.value = dateCompleted;
    f.container.classList.remove('hidden');
    f.container.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

registerActions({
    showAddSessionForm: () => openSessionForm('add', '', '', ''),

    hideSessionForm: () => sessionForm().container.classList.add('hidden'),

    // A session with no dates is allowed (books read long ago) but asked
    // first, so a stray Save doesn't add an empty one (ROADMAP 14c). The
    // server only saves an undated session with undated=1.
    saveSession: async (form, event) => {
        const f = sessionForm();
        if (f.dateStarted.value || f.dateCompleted.value) return;   // submits as usual
        event.preventDefault();
        const message = f.sessionId.value ? form.dataset.undatedEdit : form.dataset.undatedAdd;
        if (!await confirmDialog(message, { ok: 'Save without dates', danger: false })) return;
        document.getElementById('form_undated').value = '1';
        form.submit();
    },

    // data-session-id, data-date-started, data-date-completed
    editSession: el => openSessionForm('edit', el.dataset.sessionId,
                                       el.dataset.dateStarted, el.dataset.dateCompleted),

    // data-session-id, data-book-id; comes back to this page afterwards
    deleteSession: async el => {
        if (!await confirmDialog('Delete this reading session?', { ok: 'Delete' })) return;
        postForm('/read/delete_reading_session/' + encodeURIComponent(el.dataset.sessionId), {
            book_id: el.dataset.bookId,
            redirect_to: 'book_detail',
        });
    },
});

// More photos (#photo-gallery, ROADMAP 16.0a): one slide at a time.
// Previous / next wrap around; the arrow keys and a sideways swipe do the
// same. Opens on the first photo after the cover (data-start), since the
// cover is already on the page; Previous goes back to it.
const gallery = {
    dialog: () => document.getElementById('photo-gallery'),
    slides: () => Array.from(document.querySelectorAll('#photo-gallery [data-slide]')),
    index: 0,
    show(i) {
        const slides = this.slides();
        if (!slides.length) return;
        this.index = (i + slides.length) % slides.length;
        slides.forEach((s, n) => { s.hidden = n !== this.index; });
    },
};

registerActions({
    openGallery: el => {
        gallery.show(Number(el.dataset.start || 0));
        gallery.dialog()?.showModal();
    },
    galleryStep: el => gallery.show(gallery.index + Number(el.dataset.step)),
});

document.addEventListener('keydown', event => {
    if (!gallery.dialog()?.open) return;
    if (event.key === 'ArrowLeft') gallery.show(gallery.index - 1);
    if (event.key === 'ArrowRight') gallery.show(gallery.index + 1);
});

// A swipe: mostly sideways, at least 40px. A tap still closes (the photo
// is the dialog's close button), so only a real swipe changes slides.
let swipeStart = null;
document.addEventListener('touchstart', event => {
    if (!gallery.dialog()?.open) return;
    const t = event.touches[0];
    swipeStart = { x: t.clientX, y: t.clientY };
}, { passive: true });
document.addEventListener('touchend', event => {
    if (!swipeStart || !gallery.dialog()?.open) return;
    const t = event.changedTouches[0];
    const dx = t.clientX - swipeStart.x;
    const dy = t.clientY - swipeStart.y;
    swipeStart = null;
    if (Math.abs(dx) > 40 && Math.abs(dx) > Math.abs(dy) * 1.5) {
        event.preventDefault();          // no close-click after a swipe
        gallery.show(gallery.index + (dx < 0 ? 1 : -1));
    }
});

// --- The item in 3D (#item-3d, ROADMAP 16.0a; Shelf style only) -------------
// The cover opens a box with the item's photos on its faces (_item3d.html),
// turned by dragging (with a little momentum), the arrow keys or the Front /
// Spine / Back buttons. Pure CSS 3D: the box's proportions come from the
// server (--a, --dr) and its size from CSS; this sets the turn (--rx, --ry)
// and each face's light (--shade). The dialog is only on the page when the
// item has every photo its shape needs; otherwise the cover opens the
// gallery (when there are more photos) or the zoom.

// A face's normal after the box's turn, dotted with the light: how lit it
// is (CSS: transform rotateX(rx) rotateY(ry), x right, y down, z to you).
function faceLight(normal, rxDeg, ryDeg) {
    const rx = rxDeg * Math.PI / 180, ry = ryDeg * Math.PI / 180;
    const [x, y, z] = normal;
    // rotateY, then rotateX
    const x1 = x * Math.cos(ry) + z * Math.sin(ry);
    const z1 = -x * Math.sin(ry) + z * Math.cos(ry);
    const y2 = y * Math.cos(rx) - z1 * Math.sin(rx);
    const z2 = y * Math.sin(rx) + z1 * Math.cos(rx);
    const L = [-0.35, -0.55, 1];
    const len = Math.hypot(...L);
    return (x1 * L[0] + y2 * L[1] + z2 * L[2]) / len;
}

// spine is the left side, side the right
const ITEM3D_FACES = {
    front: [0, 0, 1], back: [0, 0, -1], spine: [-1, 0, 0],
    side: [1, 0, 0], top: [0, -1, 0], bottom: [0, 1, 0],
};

const item3d = {
    rx: -8, ry: 28, vx: 0, vy: 0, target: null, frame: null, ready: false,
    reduced: () => window.matchMedia('(prefers-reduced-motion: reduce)').matches,
    dialog: () => document.getElementById('item-3d'),
    box: () => document.querySelector('#item-3d [data-item3d-box]'),

    // A record sleeve's four edges are card in the cover's own colour: the
    // average of the cover's outer rows and columns (--edge; styles.css has
    // a plain card colour for a cover the canvas can't read).
    colour() {
        const box = this.box();
        const cover = box.querySelector('[data-item3d-cover]');
        if (!box.classList.contains('item3d-sleeve') || !cover?.naturalWidth) return;
        try {
            const c = document.createElement('canvas');
            c.width = c.height = 24;
            const ctx = c.getContext('2d');
            ctx.drawImage(cover, 0, 0, c.width, c.height);
            const px = ctx.getImageData(0, 0, c.width, c.height).data;
            let r = 0, g = 0, b = 0, n = 0;
            for (let y = 0; y < c.height; y++) {
                for (let x = 0; x < c.width; x++) {
                    if (x > 0 && x < c.width - 1 && y > 0 && y < c.height - 1) continue;
                    const i = (y * c.width + x) * 4;
                    r += px[i]; g += px[i + 1]; b += px[i + 2]; n++;
                }
            }
            box.style.setProperty('--edge', `${r / n | 0} ${g / n | 0} ${b / n | 0}`);
        } catch { /* keeps the plain card */ }
    },

    render() {
        const box = this.box();
        box.style.setProperty('--rx', `${this.rx}deg`);
        box.style.setProperty('--ry', `${this.ry}deg`);
        for (const [face, normal] of Object.entries(ITEM3D_FACES)) {
            const lit = Math.max(0, faceLight(normal, this.rx, this.ry));
            box.querySelector(`.item3d-${face}`).style.setProperty('--shade', (1 - (0.35 + 0.65 * lit)).toFixed(3));
        }
    },

    // Momentum after a drag, or easing to a Front / Spine / Back target
    tick() {
        this.frame = null;
        if (this.target !== null) {
            const gap = this.target - this.ry;
            const rgap = -6 - this.rx;
            if (Math.abs(gap) < 0.3 && Math.abs(rgap) < 0.3) {
                this.ry = this.target; this.target = null;
            } else {
                this.ry += gap * 0.14; this.rx += rgap * 0.14;
            }
        } else {
            this.ry += this.vy; this.rx = Math.max(-45, Math.min(45, this.rx + this.vx));
            this.vy *= 0.94; this.vx *= 0.9;
            if (Math.abs(this.vy) < 0.02 && Math.abs(this.vx) < 0.02) { this.vy = this.vx = 0; }
        }
        this.render();
        if (this.target !== null || this.vy || this.vx) this.frame = requestAnimationFrame(() => this.tick());
    },
    run() { if (!this.frame) this.frame = requestAnimationFrame(() => this.tick()); },

    turnTo(angle) {
        // The nearest way round to that face
        const target = angle + 360 * Math.round((this.ry - angle) / 360);
        this.vx = this.vy = 0;
        if (this.reduced()) { this.ry = target; this.rx = -6; this.render(); return; }
        this.target = target;
        this.run();
    },

    open() {
        const dialog = this.dialog();
        if (!this.ready) { this.setup(); this.ready = true; }
        this.colour();
        this.rx = -8; this.ry = 28;
        this.render();
        dialog.showModal();
        if (!this.reduced()) {        // a short turn to say "I move"
            this.ry = 70; this.render();
            this.turnTo(28);
        }
    },

    setup() {
        const dialog = this.dialog();
        const stage = dialog.querySelector('[data-item3d-stage]');
        let last = null, moved = 0;
        stage.addEventListener('pointerdown', event => {
            stage.setPointerCapture(event.pointerId);
            stage.classList.add('dragging');
            last = { x: event.clientX, y: event.clientY, t: performance.now() };
            moved = 0;
            this.target = null; this.vx = this.vy = 0;
        });
        stage.addEventListener('pointermove', event => {
            if (!last) return;
            const dx = event.clientX - last.x, dy = event.clientY - last.y;
            const dt = Math.max(1, performance.now() - last.t);
            moved += Math.abs(dx) + Math.abs(dy);
            this.ry += dx * 0.45;
            this.rx = Math.max(-45, Math.min(45, this.rx - dy * 0.3));
            // Speed in degrees per frame (~16 ms), for the momentum
            this.vy = dx * 0.45 * 16 / dt;
            this.vx = -dy * 0.3 * 16 / dt;
            last = { x: event.clientX, y: event.clientY, t: performance.now() };
            this.render();
        });
        const release = () => {
            if (!last) return;
            stage.classList.remove('dragging');
            // A pause before letting go means no fling
            if (performance.now() - last.t > 80 || this.reduced()) this.vx = this.vy = 0;
            last = null;
            this.run();
        };
        stage.addEventListener('pointerup', release);
        stage.addEventListener('pointercancel', release);
        // A click on the empty sheet (not a drag, not the box) closes it
        dialog.addEventListener('click', event => {
            if (event.target === stage && moved < 4) dialog.close();
        });
        document.addEventListener('keydown', event => {
            if (!dialog.open) return;
            const step = { ArrowLeft: [0, -15], ArrowRight: [0, 15], ArrowUp: [10, 0], ArrowDown: [-10, 0] }[event.key];
            if (!step) return;
            event.preventDefault();
            this.target = null;
            this.rx = Math.max(-45, Math.min(45, this.rx + step[0]));
            this.ry += step[1];
            this.render();
        });
    },
};

registerActions({
    // The cover: in the Shelf style the item in 3D, when it has the photos
    // for it; else the gallery from the cover, when there are more photos;
    // else the cover alone, bigger.
    openCover: el => {
        const shelf = document.documentElement.dataset.style === 'shelf';
        if (shelf && item3d.dialog()) { item3d.open(); return; }
        if (gallery.dialog()) { gallery.show(0); gallery.dialog().showModal(); return; }
        document.getElementById(el.dataset.target)?.showModal();
    },
    item3dTurn: el => item3d.turnTo(Number(el.dataset.angle)),
});

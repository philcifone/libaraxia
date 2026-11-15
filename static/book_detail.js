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

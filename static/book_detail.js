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

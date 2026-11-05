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

function openSessionForm(title, sessionId, dateStarted, dateCompleted) {
    const f = sessionForm();
    f.title.textContent = title;
    f.sessionId.value = sessionId;
    f.dateStarted.value = dateStarted;
    f.dateCompleted.value = dateCompleted;
    f.container.classList.remove('hidden');
    f.container.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

registerActions({
    showAddSessionForm: () => openSessionForm('Add New Reading Session', '', '', ''),

    hideSessionForm: () => sessionForm().container.classList.add('hidden'),

    // data-session-id, data-date-started, data-date-completed
    editSession: el => openSessionForm('Edit Reading Session', el.dataset.sessionId,
                                       el.dataset.dateStarted, el.dataset.dateCompleted),

    // data-session-id, data-book-id; comes back to this page afterwards
    deleteSession: el => {
        if (!confirm('Are you sure you want to delete this reading session?')) return;
        postForm('/read/delete_reading_session/' + encodeURIComponent(el.dataset.sessionId), {
            book_id: el.dataset.bookId,
            redirect_to: 'book_detail',
        });
    },
});

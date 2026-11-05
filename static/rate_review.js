// Rate & review page (templates/rate_review.html): the inline reading-session
// form. The star rating itself is initRatingSystem in script.js.

'use strict';

let currentEditingSessionId = null;   // null while adding a new session

function openInlineSessionForm(title, sessionId, dateStarted, dateCompleted) {
    currentEditingSessionId = sessionId;
    document.getElementById('inline-session-form-title').textContent = title;
    document.getElementById('inline_date_started').value = dateStarted;
    document.getElementById('inline_date_completed').value = dateCompleted;
    const container = document.getElementById('session-form-inline');
    container.classList.remove('hidden');
    container.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

registerActions({
    showAddSessionForm: () => openInlineSessionForm('Add New Reading Session', null, '', ''),

    hideInlineSessionForm: () => {
        document.getElementById('session-form-inline').classList.add('hidden');
        currentEditingSessionId = null;
    },

    // data-session-id, data-date-started, data-date-completed
    editInlineSession: el => openInlineSessionForm('Edit Reading Session', el.dataset.sessionId,
                                                   el.dataset.dateStarted, el.dataset.dateCompleted),

    // data-book-id. Posted as its own form so the review form isn't submitted.
    saveInlineSession: el => {
        const dateStarted = document.getElementById('inline_date_started').value;
        const dateCompleted = document.getElementById('inline_date_completed').value;
        if (dateStarted && dateCompleted && new Date(dateStarted) > new Date(dateCompleted)) {
            showFlashMessage('error', 'Start date cannot be after completion date.');
            return;
        }
        const fields = { date_started: dateStarted, date_completed: dateCompleted, redirect_to: 'rate_review' };
        if (currentEditingSessionId) fields.session_id = currentEditingSessionId;
        postForm('/read/manage_session/' + encodeURIComponent(el.dataset.bookId), fields);
    },

    // data-session-id, data-book-id
    deleteSession: async el => {
        if (!await confirmDialog('Delete this reading session?', { ok: 'Delete' })) return;
        postForm('/read/delete_reading_session/' + encodeURIComponent(el.dataset.sessionId),
                 { book_id: el.dataset.bookId });
    },
});

// Admin -> orphaned images (templates/admin/orphaned_images.html).

'use strict';

function setAllOrphans(checked) {
    document.querySelectorAll('.orphan-checkbox').forEach(checkbox => { checkbox.checked = checked; });
    updateSelectedCount();
}

function updateSelectedCount() {
    const count = document.querySelectorAll('.orphan-checkbox:checked').length;
    const label = document.getElementById('selected-count');
    if (label) label.textContent = count;
}

registerActions({
    selectAll: () => setAllOrphans(true),
    deselectAll: () => setAllOrphans(false),
    updateSelectedCount,

    // data-submit on the delete form: refuse an empty selection, then confirm.
    confirmDeletion: (form, event) => {
        const count = document.querySelectorAll('.orphan-checkbox:checked').length;
        if (count === 0) {
            event.preventDefault();
            showFlashMessage('error', 'Select at least one file to delete.');
            return;
        }
        confirmSubmit(form, event, `Delete ${count} orphaned image file(s)? This cannot be undone.`, { ok: 'Delete' });
    },
});

document.addEventListener('DOMContentLoaded', updateSelectedCount);

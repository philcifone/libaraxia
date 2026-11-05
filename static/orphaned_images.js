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
            alert('Please select at least one file to delete.');
            event.preventDefault();
        } else if (!confirm(`Are you sure you want to delete ${count} orphaned image file(s)? This action cannot be undone.`)) {
            event.preventDefault();
        }
    },
});

document.addEventListener('DOMContentLoaded', updateSelectedCount);

// Edit Book (templates/edit_book.html, fields from _item_fields.html): the
// preview of an uploaded cover. "Find a better cover" is cover_finder.js.
// Shared helpers (escapeHtml) are in common.js.

'use strict';

document.addEventListener('DOMContentLoaded', () => {
    const $ = id => document.getElementById(id);
    const preview = $('cover-preview');

    function showCover(src) {
        preview.innerHTML = `<img src="${escapeHtml(src)}" alt="Cover" data-fallback-src="/static/no-cover.svg" class="max-w-[12rem] rounded-lg">`;
    }

    // Preview an uploaded file (it replaces any picked cover on save)
    $('image')?.addEventListener('change', event => {
        const file = event.target.files[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = e => {
            showCover(e.target.result);
            document.dispatchEvent(new CustomEvent('cover-changed'));   // cover_crop.js
        };
        reader.readAsDataURL(file);
    });
});

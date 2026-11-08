// Edit Book (templates/edit_book.html, fields from _item_fields.html).
// Shared helpers (getCSRFHeaders, escapeHtml, showFlashMessage) are in common.js.
//
// "Find a better cover": /books/fetch_cover downloads candidate covers for
// the ISBN/title into static/uploads and lists them; picking one shows it
// as the cover and puts its path in existing_cover_url, which edit_book
// checks (is_safe_upload_path) and saves. An uploaded file still wins.

'use strict';

document.addEventListener('DOMContentLoaded', () => {
    const $ = id => document.getElementById(id);
    const button = $('fetch-cover-btn');
    const status = $('cover-status');
    const options = $('cover-options');
    const hidden = $('existing_cover_url');
    const preview = $('cover-preview');

    function showCover(src) {
        preview.innerHTML = `<img src="${escapeHtml(src)}" alt="Cover" data-fallback-src="/static/no-cover.svg" class="max-w-[12rem] rounded-lg">`;
    }

    button?.addEventListener('click', async () => {
        const isbn = $('isbn').value.trim();
        const title = $('title').value.trim();
        if (!isbn && !title) {
            status.textContent = 'Give an ISBN or a title first.';
            return;
        }
        button.disabled = true;
        status.textContent = 'Looking for covers...';
        options.classList.add('hidden');
        try {
            const response = await fetch('/books/fetch_cover', {
                method: 'POST',
                headers: getCSRFHeaders(),
                body: JSON.stringify({ isbn, title, author: $('author').value.trim() }),
            });
            const data = await response.json();
            if (!data.success || !(data.covers || []).length) {
                status.textContent = data.error || 'No covers found.';
                return;
            }
            status.textContent = `Found ${data.covers.length} cover${data.covers.length === 1 ? '' : 's'}: pick one.`;
            options.innerHTML = data.covers.map((cover, i) => `
                <button type="button" data-cover="${i}"
                        class="p-2 bg-primary-bg border-2 border-card hover:border-accent rounded-lg text-left">
                    <img src="/static/${escapeHtml(encodeURI(cover.url))}" alt="Cover from ${escapeHtml(cover.source)}"
                         class="w-full h-48 object-contain" loading="lazy">
                    <span class="block mt-1 text-xs text-content-secondary text-center">${escapeHtml(cover.source)}</span>
                </button>`).join('');
            options.classList.remove('hidden');
            options.onclick = event => {
                const pick = event.target.closest('[data-cover]');
                if (!pick) return;
                const cover = data.covers[Number(pick.dataset.cover)];
                hidden.value = cover.url;
                showCover(`/static/${encodeURI(cover.url)}`);
                options.classList.add('hidden');
                status.textContent = `Cover from ${cover.source} picked. Save to keep it.`;
            };
        } catch (err) {
            console.error('Cover fetch failed', err);
            status.textContent = 'The cover search failed. Try again, or upload one.';
        } finally {
            button.disabled = false;
        }
    });

    // Preview an uploaded file (it replaces any picked cover on save)
    $('image')?.addEventListener('change', event => {
        const file = event.target.files[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = e => showCover(e.target.result);
        reader.readAsDataURL(file);
    });
});

// "Find a better cover", on Edit Book and Add Book (books only; the button
// is in _item_fields.html when the page passes cover_fetch).
// Shared helpers (getCSRFHeaders, escapeHtml) are in common.js.
//
// /books/fetch_cover asks each cover source for the ISBN/title, downloads
// what they offer into static/uploads, and streams its progress as it goes
// (NDJSON: one JSON object per line, see the route). The bar fills over the
// search (first 40%) and the downloads (the rest), and each cover shows up
// as soon as it's downloaded. Picking one shows it as the cover and puts its
// path in existing_cover_url, which the save route checks
// (is_safe_upload_path). An uploaded file still wins. On Add Book a picked
// cover also counts as yours: a later lookup won't replace it (add_item.js).

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

    const progress = $('cover-progress');
    const bar = progress?.firstElementChild;
    let covers = [];

    function setProgress(pct) {
        if (!progress) return;
        bar.style.width = `${pct}%`;
        progress.setAttribute('aria-valuenow', String(Math.round(pct)));
    }

    function addCover(cover) {
        const i = covers.push(cover) - 1;
        options.insertAdjacentHTML('beforeend', `
            <button type="button" data-cover="${i}"
                    class="p-2 bg-primary-bg border-2 border-card hover:border-accent rounded-lg text-left">
                <img src="/static/${escapeHtml(encodeURI(cover.url))}" alt="Cover from ${escapeHtml(cover.source)}"
                     class="w-full h-48 object-contain" loading="lazy">
                <span class="block mt-1 text-xs text-content-secondary text-center">${escapeHtml(cover.source)}</span>
            </button>`);
        options.classList.remove('hidden');
    }

    // One line of the stream
    function handle(event) {
        if (event.type === 'step') {
            const share = event.total ? event.done / event.total : 1;
            if (event.phase === 'search') {
                setProgress(share * 40);
                status.textContent = `Asking ${event.label}...`;
            } else {
                setProgress(40 + share * 60);
                status.textContent = `Downloading ${event.done + 1} of ${event.total} (${event.label})` +
                    (covers.length ? `, ${covers.length} so far` : '') + '...';
            }
        } else if (event.type === 'cover') {
            addCover(event);
        } else if (event.type === 'done') {
            setProgress(100);
            status.textContent = event.error ||
                `Found ${event.count} cover${event.count === 1 ? '' : 's'}: pick one.`;
        }
    }

    // Picking a cover (the buttons are added as they arrive)
    options?.addEventListener('click', event => {
        const pick = event.target.closest('[data-cover]');
        if (!pick) return;
        const cover = covers[Number(pick.dataset.cover)];
        hidden.value = cover.url;
        showCover(`/static/${encodeURI(cover.url)}`);
        options.classList.add('hidden');
        status.textContent = `Cover from ${cover.source} picked. Save to keep it.`;
    });

    button?.addEventListener('click', async () => {
        const isbn = $('isbn').value.trim();
        const title = $('title').value.trim();
        if (!isbn && !title) {
            status.textContent = 'Give an ISBN or a title first.';
            return;
        }
        button.disabled = true;
        covers = [];
        options.innerHTML = '';
        options.classList.add('hidden');
        setProgress(0);
        progress?.classList.remove('hidden');
        status.textContent = 'Looking for covers...';
        try {
            const response = await fetch('/books/fetch_cover', {
                method: 'POST',
                headers: getCSRFHeaders(),
                body: JSON.stringify({ isbn, title, author: $('author').value.trim() }),
            });
            if (!response.ok || !response.body) throw new Error(`HTTP ${response.status}`);

            // Read the stream line by line; a chunk can end mid-line, so the
            // unfinished tail waits in `buffer` for the next chunk
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            for (;;) {
                const { value, done } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop();
                lines.filter(Boolean).forEach(l => handle(JSON.parse(l)));
            }
            if (buffer.trim()) handle(JSON.parse(buffer));
        } catch (err) {
            console.error('Cover fetch failed', err);
            status.textContent = covers.length
                ? 'The search stopped early: pick one of these, or try again.'
                : 'The cover search failed. Try again, or upload one.';
        } finally {
            button.disabled = false;
            progress?.classList.add('hidden');
        }
    });

});

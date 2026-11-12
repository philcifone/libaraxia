// Do I have this? (templates/have.html): the camera. A confirmed read
// (scanner.js) reloads the page with the code, and the server answers;
// typing works the same way through the plain GET form.
document.addEventListener('DOMContentLoaded', () => {
    const root = document.getElementById('have');
    const view = document.getElementById('interactive');
    const button = document.getElementById('toggle-scanner');
    if (!root || !view || !button || typeof createBarcodeScanner !== 'function') return;

    // The camera box only takes space while the camera is on
    // (and only where a camera can work: scanner.js says why otherwise)
    button.addEventListener('click', () => {
        if (!window.isSecureContext || !navigator.mediaDevices) return;
        view.classList.remove('hidden');
        view.classList.add('flex');
    }, { capture: true });

    createBarcodeScanner({
        container: view,
        button,
        cameraSelect: document.getElementById('camera-select'),
        onCode: ({ code }) => {
            document.getElementById('scan-status').textContent = `Read ${code}, checking...`;
            const url = new URL(root.dataset.checkUrl, window.location.origin);
            url.searchParams.set('q', code);
            window.location.assign(url.pathname + url.search);
        },
    });
});

// "Not here" (ROADMAP 13b): what it most likely is. The page is already
// answered; this asks /have/online (Google Books / Open Library, TMDb,
// Discogs or MusicBrainz, all at once on the server) and shows the best
// candidate on top with its type, then the rest by type. Each candidate's
// buttons open its type's add page with its id, which the page looks up
// on load (add_item.js). A slow or busy source is simply missing.
document.addEventListener('DOMContentLoaded', async () => {
    const box = document.getElementById('have-online');
    if (!box) return;
    const status = box.querySelector('[data-online-status]');
    const fallback = document.getElementById('have-add-links');

    let data = {};
    try {
        const response = await fetch(box.dataset.onlineUrl, { headers: { Accept: 'application/json' } });
        data = await response.json();
        if (!response.ok && !data.error) data.error = 'error';
    } catch (e) {
        data = { error: 'error' };
    }
    if (data.error || !data.best) {
        status.textContent = data.error
            ? "Couldn't look it up online right now. Add it by hand:"
            : 'Nothing found online either. Add it by hand:';
        return;
    }

    const cover = (c, size) => `<img src="${escapeHtml(coverSrc(c.thumb))}" alt="" loading="lazy"
        data-fallback-src="/static/no-cover.svg" class="${size} object-cover rounded shrink-0">`;
    const line = c => [c.creator, c.year, c.detail].filter(Boolean).map(escapeHtml).join(' &middot; ');
    const buttons = (c, small) => {
        const pad = small ? 'px-3 py-1.5 text-sm' : 'px-4 py-2';
        return `<div class="mt-2 flex flex-wrap gap-2">
            <a href="${escapeHtml(c.wishlist_url)}" class="${pad} rounded-lg btn bg-accent hover:bg-accent-hover text-on-accent">Add to wishlist</a>
            <a href="${escapeHtml(c.shelf_url)}" class="${pad} rounded-lg btn bg-primary hover:bg-primary-hover text-content-primary border border-rule-strong">Add to shelf</a>
        </div>`;
    };
    const badge = c => `<span class="px-2 py-0.5 text-xs rounded-pill bg-accent text-on-accent align-middle">${escapeHtml(c.type_label)}</span>`;

    const best = data.best;
    let html = `<p class="text-sm font-semibold text-content-secondary">Most likely</p>
        <div class="mt-2 flex gap-4 bg-primary border border-card rounded-lg p-3 sm:p-4">
            ${cover(best, 'w-20 h-28')}
            <div class="min-w-0 flex-1">
                <p class="font-display text-lg text-content-primary">${escapeHtml(best.title)} ${badge(best)}</p>
                <p class="text-sm text-content-secondary">${line(best)}</p>
                ${buttons(best, false)}
            </div>
        </div>`;

    for (const group of data.groups || []) {
        // The server words it ("Other movies and shows", "Albums")
        const heading = group.heading;
        html += `<p class="mt-5 text-sm font-semibold text-content-secondary">${escapeHtml(heading)}</p>
            <ul class="mt-2 space-y-2">${group.items.map(c => `
                <li class="flex gap-3 bg-primary border border-card rounded-lg p-3">
                    ${cover(c, 'w-12 h-16')}
                    <div class="min-w-0 flex-1">
                        <p class="font-semibold text-content-primary line-clamp-2">${escapeHtml(c.title)}</p>
                        <p class="text-sm text-content-secondary truncate">${line(c)}</p>
                        ${buttons(c, true)}
                    </div>
                </li>`).join('')}
            </ul>`;
    }

    // Fixed markup, no data: TMDb's and Discogs' terms ask for these
    const credits = {
        tmdb: 'This product uses the <a class="underline hover:text-accent" href="https://www.themoviedb.org/" rel="noopener">TMDB</a> API but is not endorsed or certified by TMDB.',
        discogs: 'Data provided by <a class="underline hover:text-accent" href="https://www.discogs.com/" rel="noopener">Discogs</a>.',
    };
    const lines = (data.credits || []).filter(k => credits[k]).map(k => `<p>${credits[k]}</p>`).join('');
    if (lines) html += `<div class="mt-4 text-xs text-content-secondary">${lines}</div>`;
    box.innerHTML = html;

    // A barcode someone recognised needs no movie-or-album guess; a title
    // keeps the by-hand links, in case none of these is it
    if (fallback) {
        if (box.dataset.kind === 'barcode') fallback.remove();
        else fallback.insertAdjacentHTML('afterbegin', '<p class="text-sm text-content-secondary">None of these? Add it by hand:</p>');
    }
});

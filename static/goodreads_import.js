// Goodreads CSV import page (templates/goodreads_import.html): uploads the
// file, renders the per-row report, and starts the background cover fetch.

'use strict';

// URLs come from data- attributes on the file input (Jinja can't run in here).
const importInput = () => document.getElementById('goodreads-import');

const esc = escapeHtml;
const plural = (n, one, many = one + 's') => `${n} ${n === 1 ? one : many}`;

function setImportButton(enabled) {
    const button = document.querySelector('label[for="goodreads-import"]');
    if (!button) return;
    button.classList.toggle('opacity-50', !enabled);
    button.classList.toggle('cursor-not-allowed', !enabled);
    button.style.pointerEvents = enabled ? 'auto' : 'none';
}

function handleGoodreadsImport(input, event) {
    const file = event.target.files[0];
    if (!file) return;
    if (!file.name.toLowerCase().endsWith('.csv')) {
        alert('Please select a CSV file');
        event.target.value = '';
        return;
    }

    const progressDiv = document.getElementById('import-progress');
    const resultDiv = document.getElementById('import-result');
    const messageP = document.getElementById('import-message');
    document.getElementById('import-status').classList.remove('hidden');
    progressDiv.classList.remove('hidden');
    resultDiv.classList.add('hidden');
    setImportButton(false);

    const formData = new FormData();
    formData.append('goodreads_csv', file);
    addCSRFToFormData(formData);

    fetch(input.dataset.importUrl, {method: 'POST', body: formData})
        .then(response => response.json().catch(() => ({success: false, message: `Server error (${response.status})`})))
        .then(data => {
            messageP.innerHTML = data.success ? renderReport(data) : `
                <p class="text-red-400">Import failed: ${esc(data.message)}</p>`;
        })
        .catch(error => {
            messageP.innerHTML = `<p class="text-red-400">Error: ${esc(error.message)}</p>
                <p class="text-sm text-content-secondary mt-2">Please try again.</p>`;
        })
        .finally(() => {
            progressDiv.classList.add('hidden');
            resultDiv.classList.remove('hidden');
            setImportButton(true);
            event.target.value = '';
        });
}

// Every row of the file has exactly one outcome; list each group so
// the counts can be checked against the file.
function renderReport(data) {
    const groups = data.outcome_labels.map(([key, label]) => {
        const rows = data.rows.filter(r => r.outcome === key);
        if (!rows.length) return '';
        const tone = key === 'error' ? 'text-red-400' : (key === 'already' || key === 'skipped') ? 'text-content-secondary' : 'text-content-primary';
        const items = rows.map(r => `
            <li><span class="font-mono text-xs text-content-secondary">line ${r.line}</span>
                ${esc(r.title || '(no title)')}${r.author ? ` <span class="text-content-secondary">by ${esc(r.author)}</span>` : ''}
                ${r.detail ? ` <span class="text-content-secondary italic">(${esc(r.detail)})</span>` : ''}</li>`).join('');
        return `
            <details class="border border-card rounded p-2" ${key === 'error' ? 'open' : ''}>
                <summary class="cursor-pointer ${tone}"><strong>${rows.length}</strong> ${esc(label)}</summary>
                <ul class="mt-2 ml-4 space-y-1 text-sm max-h-96 overflow-y-auto">${items}</ul>
            </details>`;
    }).join('');

    const t = data.totals;
    const created = data.collections_created.length
        ? `<p>New collections: ${data.collections_created.map(esc).join(', ')}</p>` : '';
    const notes = t.private_notes_not_imported
        ? `<p class="text-yellow-400">${plural(t.private_notes_not_imported, 'private note')} on library books not imported (there's nowhere to keep them yet).</p>` : '';
    const encoding = data.encoding !== 'utf-8-sig'
        ? `<p class="text-yellow-400">The file wasn't UTF-8; it was read as ${esc(data.encoding)}. Check accented titles.</p>` : '';
    const covers = data.covers_missing ? `
        <div id="cover-fetch" class="mt-4 p-3 border border-card rounded">
            <p class="text-sm text-content-secondary mb-2">${plural(data.covers_missing, 'book')} of yours ha${data.covers_missing === 1 ? 's' : 've'} an ISBN but no cover.
                Fetching runs in the background (a second or two per book); you can leave this page and follow it in the corner.</p>
            <button type="button" data-click="startCoverFetch"
                    class="px-4 py-2 bg-accent rounded-lg text-on-accent hover:bg-accent-hover transition-colors">
                Fetch covers
            </button>
            <p id="cover-start-message" class="text-sm text-content-secondary mt-2"></p>
        </div>` : '';

    return `
        <div class="space-y-3">
            <p class="text-green-400 font-semibold">Import finished: ${plural(data.total_rows, 'row')} in the file, all accounted for below.</p>
            ${encoding}
            <div class="space-y-2">${groups}</div>
            <div class="text-sm text-content-secondary space-y-1">
                <p>${plural(t.books_created, 'new book')}, ${plural(t.statuses, 'reading status', 'reading statuses')}, ${plural(t.wishlist, 'wishlist entry', 'wishlist entries')}</p>
                <p>${plural(t.ratings, 'rating')}, ${plural(t.reviews, 'review')}, ${plural(t.sessions, 'reading session')}, ${plural(t.collection_entries, 'collection entry', 'collection entries')}</p>
                ${created}
                ${notes}
            </div>
            ${covers}
            <a href="${esc(importInput().dataset.profileUrl)}"
               class="inline-block mt-3 px-4 py-2 bg-accent rounded-lg text-on-accent hover:bg-accent-hover transition-colors">
                Return to Profile
            </a>
        </div>`;
}

// Starts a background job (blueprints/covers.py); its progress shows
// in the floating panel from _sidebar.html on every page.
function startCoverFetch(button) {
    button.disabled = true;
    button.classList.add('opacity-50');
    const form = new FormData();
    addCSRFToFormData(form);
    form.append('scope', 'own');
    fetch(importInput().dataset.coversStartUrl, {method: 'POST', body: form, headers: {'X-Requested-With': 'XMLHttpRequest'}})
        .then(response => response.json())
        .then(data => {
            document.getElementById('cover-start-message').textContent = data.message || '';
            if (data.job && window.coverJobs) window.coverJobs.track(data.job);
        })
        .catch(error => {
            document.getElementById('cover-start-message').textContent = `Couldn't start: ${error.message}`;
            button.disabled = false;
            button.classList.remove('opacity-50');
        });
}

registerActions({ handleGoodreadsImport, startCoverFetch });

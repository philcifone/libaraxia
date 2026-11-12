// The Goodreads import's review page (templates/goodreads_review.html,
// ROADMAP 14b): select rows (click, shift-click, a whole box), choose for
// them, filter, Import, then the result with Undo and the cover fetch.
// Loaded after bulk.js, which lends its pure helpers (fold, rangeBetween);
// its own browser part does nothing on a page without #book-container.

'use strict';

// ---------------------------------------------------------------- pure helpers
// Top-level names start with gr: bulk.js's globals share this scope.

const grFold = typeof fold === 'function' ? fold : require('./bulk.js').fold;
const grRange = typeof rangeBetween === 'function' ? rangeBetween : require('./bulk.js').rangeBetween;

// The choices every selected row allows, in the first row's order. Each
// entry is one row's list. 'ask' is never something the user sets.
function grAllowedChoices(lists) {
    if (!lists.length) return [];
    return lists[0].filter(c => c && c !== 'ask' && lists.every(list => list.includes(c)));
}

// The Import button: "Import 214, leave 12 undecided"
function grImportLabel(willWrite, undecided) {
    return `Import ${willWrite}` + (undecided ? `, leave ${undecided} undecided` : '');
}

function grSelectedLabel(n) { return `${n} selected`; }

// Whether a row passes the filters. row: {box, shelves: [], search};
// filter: {box, shelf, q}, each empty for "any". Search folds as the
// server does (case, accents, punctuation), every word must match.
function grRowMatches(row, filter) {
    if (filter.box && row.box !== filter.box) return false;
    if (filter.shelf && !row.shelves.includes(filter.shelf)) return false;
    const words = String(filter.q || '').split(/\s+/).map(grFold).filter(Boolean);
    const text = grFold(row.search);
    return words.every(w => text.includes(w));
}

// ---------------------------------------------------------------- the page

(function () {
    if (typeof document === 'undefined') return;

    const $ = id => document.getElementById(id);
    const page = () => $('gr-review');
    const selected = new Set();          // line numbers
    let anchor = -1;                     // index in visibleRows() of the last click, for shift-click
    const expanded = new Set();          // boxes showing all their rows
    let labels = {};

    const allRows = () => Array.from(document.querySelectorAll('.gr-row'));
    const visibleRows = () => allRows().filter(r => !r.hidden);
    const lineOf = row => Number(row.dataset.line);
    const rowByLine = line => document.querySelector(`.gr-row[data-line="${line}"]`);
    const choicesOf = row => (row.dataset.choices || '').split(',').filter(Boolean);

    // ---- selection ------------------------------------------------------

    function setSelected(row, on) {
        const line = lineOf(row);
        if (on) selected.add(line); else selected.delete(line);
        row.classList.toggle('is-selected', on);
        row.querySelector('.gr-tick').checked = on;
    }

    function clearSelection() {
        allRows().forEach(r => setSelected(r, false));
        anchor = -1;
        refreshBar();
    }

    function onTick(row, event) {
        const on = row.querySelector('.gr-tick').checked;
        const rows = visibleRows();
        const index = rows.indexOf(row);
        if (event.shiftKey && anchor >= 0 && anchor < rows.length) {
            grRange(anchor, index).forEach(i => setSelected(rows[i], on));
        } else {
            setSelected(row, on);
        }
        anchor = index;
        refreshBar();
    }

    function selectBox(button) {
        const box = button.dataset.box;
        const filter = currentFilter();
        allRows().filter(r => r.dataset.box === box && grRowMatches(rowData(r), filter))
            .forEach(r => setSelected(r, true));
        refreshBar();
    }

    function refreshBar() {
        const bar = $('gr-bar');
        const actions = $('gr-actions');
        const hint = $('gr-bar-hint');
        bar.classList.toggle('hidden', selected.size === 0);
        document.documentElement.dataset.grBar = selected.size ? 'on' : 'off';
        $('gr-count').textContent = grSelectedLabel(selected.size);
        const allowed = grAllowedChoices([...selected].map(l => choicesOf(rowByLine(l))));
        actions.replaceChildren(...allowed.map(choice => {
            const b = document.createElement('button');
            b.type = 'button';
            b.className = 'btn rounded-lg bg-accent hover:bg-accent-hover text-on-accent px-3 py-1.5 text-sm font-bold';
            b.textContent = labels[choice] || choice;
            b.dataset.click = 'grChooseSelected';
            b.dataset.choice = choice;
            return b;
        }));
        const nothing = selected.size && !allowed.length;
        hint.classList.toggle('hidden', !nothing);
        hint.textContent = nothing ? 'No one choice fits every selected row. Select rows from one box, or fewer.' : '';
    }

    // ---- choices --------------------------------------------------------

    function updateCounts(data) {
        page().dataset.fingerprint = data.fingerprint;
        document.querySelectorAll('[data-gr-import]').forEach(b => {
            b.textContent = grImportLabel(data.will_write, data.undecided);
        });
    }

    function showRow(line, info) {
        const row = rowByLine(line);
        if (!row) return;
        const select = row.querySelector('.gr-choice');
        if (select) {
            select.querySelector('option[value="ask"]')?.remove();
            select.value = info.choice;
            select.dataset.was = info.choice;
        }
        const adds = row.querySelector('.gr-adds');
        adds.hidden = !info.adds.length;
        adds.querySelector('[data-gr-adds]').textContent = info.adds.join(', ');
        const preview = row.querySelector('.gr-preview');
        preview.hidden = !info.preview;
        preview.querySelector('[data-gr-preview]').textContent = info.preview || '';
    }

    async function choose(lines, choice) {
        let data;
        try {
            const response = await fetch(page().dataset.chooseUrl, {
                method: 'POST', headers: getCSRFHeaders(), body: JSON.stringify({ lines, choice }),
            });
            data = await response.json().catch(() => ({ success: false }));
        } catch (e) {
            data = { success: false };
        }
        if (!data.success) {
            showFlashMessage('error', data.error || 'That choice could not be saved.');
            return null;
        }
        Object.entries(data.rows).forEach(([line, info]) => showRow(line, info));
        updateCounts(data);
        if (data.refused.length) {
            showFlashMessage('warning', `${data.refused.length} row${data.refused.length === 1 ? '' : 's'} kept ` +
                             `${data.refused.length === 1 ? 'its' : 'their'} choice: ${data.refused[0].error}`);
        }
        return data;
    }

    // One row's select: optimistic; on failure it goes back to what it was
    async function chooseOne(select) {
        const row = select.closest('.gr-row');
        const was = select.dataset.was;
        const data = await choose([lineOf(row)], select.value);
        if (!data || !data.saved.length) select.value = was;
    }

    async function chooseSelected(button) {
        const data = await choose([...selected], button.dataset.choice);
        if (data) {
            showFlashMessage('success', `${data.saved.length} row${data.saved.length === 1 ? '' : 's'} set to ` +
                             `${labels[button.dataset.choice]}.`);
        }
    }

    // ---- show all, filters ----------------------------------------------

    function rowData(row) {
        return { box: row.dataset.box, shelves: (row.dataset.shelves || '').split(','), search: row.dataset.search };
    }

    function currentFilter() {
        return { box: $('gr-filter-box').value, shelf: $('gr-filter-shelf').value, q: $('gr-filter-q').value };
    }

    function applyFilter() {
        const filter = currentFilter();
        const active = Boolean(filter.box || filter.shelf || filter.q.trim());
        let shown = 0;
        allRows().forEach(row => {
            const matches = grRowMatches(rowData(row), filter);
            // A collapsed box shows its first rows; a filter shows every match
            const collapsed = row.hasAttribute('data-more') && !expanded.has(row.dataset.box) && !active;
            row.hidden = !matches || collapsed;
            if (matches) shown += 1;
            if (!matches && selected.has(lineOf(row))) setSelected(row, false);
        });
        document.querySelectorAll('.gr-box').forEach(box => {
            const any = Array.from(box.querySelectorAll('.gr-row'))
                .some(r => grRowMatches(rowData(r), filter));
            box.hidden = !any;
        });
        const count = $('gr-filter-count');
        count.classList.toggle('hidden', !active);
        count.textContent = active ? `${shown} row${shown === 1 ? '' : 's'} match.` : '';
        anchor = -1;
        refreshBar();
    }

    function showAll(button) {
        const box = button.dataset.box;
        const open = !expanded.has(box);
        if (open) expanded.add(box); else expanded.delete(box);
        button.setAttribute('aria-expanded', String(open));
        // A summary box (Nothing to do) starts with every row hidden
        const total = button.closest('.gr-box').querySelectorAll('.gr-row').length;
        const summary = button.hasAttribute('data-summary');
        button.textContent = open ? (summary ? 'Hide' : 'Show fewer') : (summary ? 'Show' : `Show all ${total}`);
        applyFilter();
    }

    // ---- import and the result -----------------------------------------

    function setImporting(on) {
        document.querySelectorAll('[data-gr-import]').forEach(b => {
            b.disabled = on;
            b.classList.toggle('opacity-50', on);
            if (on) b.textContent = 'Importing...';
        });
    }

    async function runImport() {
        setImporting(true);
        let response, data;
        try {
            response = await fetch(page().dataset.applyUrl, {
                method: 'POST', headers: getCSRFHeaders(),
                body: JSON.stringify({ fingerprint: page().dataset.fingerprint }),
            });
            data = await response.json().catch(() => ({ success: false }));
        } catch (e) {
            data = { success: false };
        }
        if (data.stale) {
            // The server flashed why; the page re-reads every row, choices kept
            window.location.reload();
            return;
        }
        if (!data.success) {
            showFlashMessage('error', data.error || 'The import failed. Nothing was saved.');
            window.location.reload();
            return;
        }
        clearSelection();
        $('gr-boxes').hidden = true;
        renderResult(data);
    }

    const plural = (n, one, many = one + 's') => `${n} ${n === 1 ? one : many}`;

    function renderResult(data) {
        const result = $('gr-result');
        const groups = data.outcome_labels.map(([key, label]) => {
            const rows = data.rows.filter(r => r.outcome === key);
            if (!rows.length) return '';
            const items = rows.map(r => `
                <li><span class="text-xs text-content-secondary">line ${r.line}</span>
                    ${escapeHtml(r.title || '(no title)')}${r.author ? ` <span class="text-content-secondary">· ${escapeHtml(r.author)}</span>` : ''}
                    ${r.detail ? ` <span class="text-content-secondary">(${escapeHtml(r.detail)})</span>` : ''}</li>`).join('');
            return `
                <details class="bulk-group"${key === 'error' ? ' open' : ''}>
                    <summary class="bulk-group-head">
                        <span class="bulk-group-label">${escapeHtml(label)}</span>
                        <span class="bulk-group-count">${rows.length}</span>
                        <span class="bulk-link bulk-show" aria-hidden="true"></span>
                    </summary>
                    <ul class="px-3 pb-3 space-y-1 text-sm max-h-96 overflow-y-auto">${items}</ul>
                </details>`;
        }).join('');

        const undo = data.edit_id ? `
            <div class="flex flex-wrap items-center gap-3">
                <button type="button" data-click="grUndo" data-edit-id="${Number(data.edit_id)}"
                        class="btn btn-outline rounded-lg bg-primary hover:bg-primary-hover text-content-primary px-4 py-2">Undo this import</button>
                <p id="gr-undo-message" class="text-sm text-content-secondary">Undo is here and in Profile, Recent bulk edits, for 30 days.</p>
            </div>` : '';
        const covers = data.covers_missing ? `
            <div class="p-3 border border-card">
                <p class="text-sm text-content-secondary mb-2">${plural(data.covers_missing, 'book')} of yours ha${data.covers_missing === 1 ? 's' : 've'} an ISBN but no cover.
                    Fetching runs in the background (a second or two per book); you can leave this page and follow it in the corner.</p>
                <button type="button" data-click="grFetchCovers"
                        class="btn rounded-lg bg-accent hover:bg-accent-hover text-on-accent px-4 py-2">Fetch covers for ${plural(data.covers_missing, 'book')}</button>
                <p id="gr-cover-message" class="text-sm text-content-secondary mt-2"></p>
            </div>` : '';

        result.innerHTML = `
            <h2 class="text-xl font-display text-content-primary">Import finished</h2>
            <p class="text-content-primary">${plural(data.total_rows, 'row')} in the file, each accounted for below.</p>
            <div class="space-y-2">${groups}</div>
            ${undo}
            ${covers}
            <p><a href="${escapeHtml(page().dataset.booksUrl)}" class="text-accent underline">Books from Goodreads</a>
               <span class="text-sm text-content-secondary">(every book this import matched or added, owned or not)</span></p>`;
        result.hidden = false;
        result.focus();
    }

    async function undoImport(button) {
        button.disabled = true;
        button.classList.add('opacity-50');
        const url = page().dataset.undoUrl.replace('/0/undo', `/${Number(button.dataset.editId)}/undo`);
        let data;
        try {
            const response = await fetch(url, { method: 'POST', headers: getCSRFHeaders(),
                                                body: JSON.stringify({ banner: false }) });
            data = await response.json().catch(() => ({ success: false }));
        } catch (e) {
            data = { success: false };
        }
        $('gr-undo-message').textContent = data.success ? data.summary : (data.error || 'Could not undo the import.');
        if (!data.success) {
            button.disabled = false;
            button.classList.remove('opacity-50');
        }
    }

    // Starts the background job (blueprints/covers.py); progress shows in
    // the corner panel from _sidebar.html on every page
    async function fetchCovers(button) {
        button.disabled = true;
        button.classList.add('opacity-50');
        const form = addCSRFToFormData(new FormData());
        form.append('scope', 'own');
        try {
            const response = await fetch(page().dataset.coversStartUrl,
                                         { method: 'POST', body: form, headers: { 'X-Requested-With': 'XMLHttpRequest' } });
            const data = await response.json();
            $('gr-cover-message').textContent = data.message || '';
            if (data.job && window.coverJobs) window.coverJobs.track(data.job);
        } catch (e) {
            $('gr-cover-message').textContent = "Couldn't start the cover fetch.";
            button.disabled = false;
            button.classList.remove('opacity-50');
        }
    }

    // ---- wiring ---------------------------------------------------------

    registerActions({
        grChoose: chooseOne,
        grChooseSelected: chooseSelected,
        grSelectBox: selectBox,
        grShowAll: showAll,
        grClear: clearSelection,
        grFilter: applyFilter,
        grImport: runImport,
        grUndo: undoImport,
        grFetchCovers: fetchCovers,
    });

    document.addEventListener('DOMContentLoaded', () => {
        if (!page()) return;
        try {
            labels = JSON.parse(page().dataset.choiceLabels || '{}');
        } catch (e) {
            labels = {};
        }
        document.querySelectorAll('img[data-remote-cover]').forEach(img => {
            img.src = coverSrc(img.dataset.remoteCover);
        });
        $('gr-filter-q').addEventListener('input', applyFilter);

        const boxes = $('gr-boxes');
        boxes.addEventListener('click', e => {
            const row = e.target.closest('.gr-row');
            if (!row) return;
            if (e.target.classList.contains('gr-tick')) {
                onTick(row, e);
                return;
            }
            // A click on the row (not its link, select or preview) ticks it
            if (e.target.closest('a, select, option, summary, details, button, input')) return;
            const tick = row.querySelector('.gr-tick');
            tick.checked = !tick.checked;
            onTick(row, e);
        });
        // Shift-click on text would select it; the range is what's meant
        boxes.addEventListener('mousedown', e => {
            if (e.shiftKey && e.target.closest('.gr-row')) e.preventDefault();
        });
        document.addEventListener('keydown', e => {
            if (e.key === 'Escape' && selected.size && !e.target.closest('select')) clearSelection();
        });
    });
})();

// Node (tests) gets the pure helpers
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { grAllowedChoices, grImportLabel, grSelectedLabel, grRowMatches };
}

// Bulk edit (ROADMAP 14, docs/BULK-EDIT-SPEC.md): select mode on the grids,
// the selection bar, and the choose / review sheet. The rules (who may edit
// what, what changes) are the server's: this file collects ids and a value,
// asks POST /bulk/plan what would happen, shows it and posts what was ticked.
//
// The pure helpers come first so node can test them (tests/test_bulk_js.py);
// the browser part at the bottom only runs where there is a document.
'use strict';

const DEFAULT_TICKED = true;   // spec section 13.1: change groups start ticked
const MAX_ITEMS = 500;         // the server's cap; the bar says so before it refuses
const OPEN_ALL_UP_TO = 12;     // a plan this small starts with its groups open
const GROUP_PREVIEW = 50;      // items shown per open group before "Show all"
const MAX_GENRE = 80;

// ---------------------------------------------------------------- pure helpers

// Same folding as utils/search.py: case, accents and punctuation ignored.
function fold(text) {
    return String(text ?? '').normalize('NFKD').replace(/\p{M}/gu, '').replace(/[^\p{L}\p{N}]/gu, '').toLowerCase();
}

// Indexes from a to b inclusive, whichever way round (shift-click's range).
function rangeBetween(a, b) {
    const lo = Math.min(a, b), hi = Math.max(a, b);
    return Array.from({ length: hi - lo + 1 }, (_, i) => lo + i);
}

// How many cards sit in the first row, from each card's top edge in page
// order: the column count Up and Down move by.
function columnCount(tops) {
    if (!tops.length) return 1;
    let n = 1;
    while (n < tops.length && Math.abs(tops[n] - tops[0]) < 2) n++;
    return n;
}

// Where an arrow key moves the focus, or null when it stays (an edge).
function nextIndex(index, key, cols, count) {
    const step = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -cols, ArrowDown: cols }[key];
    if (key === 'Home') return 0;
    if (key === 'End') return count - 1;
    if (step === undefined) return null;
    const to = index + step;
    return to < 0 || to >= count ? null : to;
}

// 'all', 'some' or 'none' of a group's ids are ticked (excluded is a Set).
function groupTickState(ids, excluded) {
    const out = ids.filter(id => excluded.has(id)).length;
    return out === 0 ? 'all' : out === ids.length ? 'none' : 'some';
}

// How many changes will be written: the plan's, minus the unticked.
function applyCount(plan, excluded) {
    return plan.groups.reduce((n, g) => n + g.items.filter(i => !excluded.has(i.id)).length, 0);
}

// "44 will change · 1 already set · 2 skipped": words first, never colour alone.
function summaryLine(changes, same, skipped) {
    const parts = [`${changes} will change`];
    if (same) parts.push(`${same} already set`);
    if (skipped) parts.push(`${skipped} skipped`);
    return parts.join(' · ');
}

function itemsWord(n) { return `${n} item${n === 1 ? '' : 's'}`; }

function applyLabel(n) { return `Apply to ${itemsWord(n)}`; }

function selectedLabel(n) { return `${n} selected`; }

// The genre field's state: what would be sent, and the line under the box.
// `genres` is [{value, count}] from /bulk/genres. A typed value that folds
// equal to an existing genre snaps to that spelling (the server writes
// exactly what it is sent, so this is where near-duplicates are stopped).
function matchGenre(typed, genres, cleared = false) {
    if (cleared) return { value: null, hint: 'The genre will be cleared.', valid: true };
    const text = String(typed ?? '').replace(/\s+/g, ' ').trim();
    if (!text) return { value: undefined, hint: '', valid: false };
    if (text.length > MAX_GENRE) return { value: undefined, hint: `Keep it to ${MAX_GENRE} characters or fewer.`, valid: false };
    const existing = genres.find(g => fold(g.value) === fold(text));
    if (!existing) return { value: text, hint: 'New genre', valid: true };
    const hint = existing.value === text ? 'Existing genre' : `Using existing spelling “${existing.value}”`;
    return { value: existing.value, hint, valid: true };
}

// The picker's list for what is typed: your genres whose folded form contains it.
function filterGenres(genres, typed) {
    const needle = fold(typed);
    return needle ? genres.filter(g => fold(g.value).includes(needle)) : genres.slice();
}

// After a 409 the sheet shows the new plan; the user's choices carry over.
// A group unticked as a whole stays unticked by its before value; single
// unticked items stay unticked by id where they are still in the plan.
function carryExclusions(oldPlan, oldExcluded, newPlan) {
    const groupsOff = new Set(oldPlan.groups
        .filter(g => g.items.length && g.items.every(i => oldExcluded.has(i.id))).map(g => g.before));
    const next = new Set();
    for (const g of newPlan.groups) {
        for (const item of g.items) {
            if (groupsOff.has(g.before) || oldExcluded.has(item.id)) next.add(item.id);
        }
    }
    return next;
}

// The id in a card's link: /books/book/12, /videos/12, /records/12.
function idFromHref(href) {
    const m = /\/(\d+)(?:[/?#].*)?$/.exec(href || '');
    return m ? Number(m[1]) : null;
}

// ------------------------------------------------------------------ the page

(function () {
    if (typeof document === 'undefined') return;

    const selected = new Set();
    let selecting = false;
    let anchor = -1;               // card index of the last click, where a range starts
    let container = null;
    let opener = null;             // the bar button that opened the sheet, for focus

    const $ = id => document.getElementById(id);
    const cards = () => container ? Array.from(container.querySelectorAll('.book-item')) : [];
    const cardId = card => {
        if (!card.dataset.bookId) card.dataset.bookId = idFromHref(card.querySelector('.book-link')?.getAttribute('href')) ?? '';
        return Number(card.dataset.bookId);
    };

    // ---- select mode ----------------------------------------------------

    function decorate(card) {
        card.setAttribute('role', 'option');
        card.setAttribute('aria-selected', String(selected.has(cardId(card))));
        card.tabIndex = -1;
        card.querySelector('.book-link')?.setAttribute('tabindex', '-1');
        const cover = card.querySelector('.book-cover');
        if (cover && !cover.querySelector('.bulk-check')) {
            const box = document.createElement('span');
            box.className = 'bulk-check';
            box.setAttribute('aria-hidden', 'true');
            box.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3.5" stroke-linecap="square"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>';
            cover.prepend(box);
        }
    }

    function undecorate(card) {
        for (const attr of ['role', 'aria-selected', 'tabindex']) card.removeAttribute(attr);
        card.querySelector('.book-link')?.removeAttribute('tabindex');
        card.querySelector('.bulk-check')?.remove();
    }

    function enterSelect() {
        container = $('book-container');
        if (!container) return;
        selecting = true;
        container.dataset.select = 'on';
        container.setAttribute('role', 'listbox');
        container.setAttribute('aria-multiselectable', 'true');
        container.setAttribute('aria-label', 'Items to edit');
        document.documentElement.dataset.bulk = 'on';
        cards().forEach(decorate);
        const first = cards()[0];
        if (first) first.tabIndex = 0;
        $('bulk-bar').classList.remove('hidden');
        syncButton();
        refresh();
    }

    function exitSelect() {
        selecting = false;
        selected.clear();
        anchor = -1;
        if (container) {
            delete container.dataset.select;
            for (const attr of ['role', 'aria-multiselectable', 'aria-label']) container.removeAttribute(attr);
            cards().forEach(undecorate);
        }
        delete document.documentElement.dataset.bulk;
        $('bulk-bar').classList.add('hidden');
        syncButton();
    }

    function syncButton() {
        const btn = $('bulk-select-btn');
        if (!btn) return;
        btn.setAttribute('aria-pressed', String(selecting));
        btn.querySelector('[data-bulk-label]').textContent = selecting ? 'Done' : 'Select';
        btn.setAttribute('aria-label', selecting ? 'Done selecting' : 'Select');
    }

    // The bar, the cards' aria-selected and the Select all / Clear toggle
    function refresh() {
        const list = cards();
        list.forEach(card => card.setAttribute('aria-selected', String(selected.has(cardId(card)))));
        const n = selected.size;
        const tooMany = n > MAX_ITEMS;
        $('bulk-count').textContent = tooMany
            ? `Too many for one edit (${n}). Narrow the view.` : selectedLabel(n);
        $('bulk-all').classList.toggle('hidden', n > 0);
        $('bulk-clear').classList.toggle('hidden', n === 0);
        document.querySelectorAll('[data-bulk-action]').forEach(btn => {
            const off = n === 0 || tooMany;
            btn.disabled = off;
            btn.title = n === 0 ? 'Select something first' : tooMany ? 'Select 500 or fewer' : '';
        });
        // More of the view than the page has loaded: say so rather than let
        // "all" mean fewer than it sounds
        const total = Number(container?.parentElement?.dataset.totalCount) || 0;
        const hint = $('bulk-hint');
        const partial = n > 0 && n === list.length && total > list.length;
        hint.classList.toggle('hidden', !partial);
        hint.textContent = partial ? `Selected the ${list.length} loaded of ${total}. Scroll down to load more.` : '';
    }

    function setSelected(card, on) {
        const id = cardId(card);
        if (on) selected.add(id); else selected.delete(id);
    }

    // Click, Space or a key: toggle one card, or select the range from the anchor
    function activate(card, range) {
        const list = cards();
        const index = list.indexOf(card);
        if (range && anchor >= 0) {
            rangeBetween(anchor, index).forEach(i => setSelected(list[i], true));
        } else {
            setSelected(card, !selected.has(cardId(card)));
            anchor = index;
        }
        refresh();
    }

    function focusCard(index) {
        const list = cards();
        if (!list[index]) return;
        list.forEach(c => { c.tabIndex = -1; });
        list[index].tabIndex = 0;
        list[index].focus();
    }

    // Long-press on a cover (touch or pen) starts select mode with that item
    // ticked. The button stays: this is a shortcut, not the only way in.
    const LONG_PRESS_MS = 500;
    const MOVE_LIMIT = 10;          // px; more than that is a scroll, not a press
    let press = null;               // {timer, x, y} while a finger is down
    let ignoreClickUntil = 0;       // the click that ends a long press must not toggle it back

    function cancelPress() {
        if (press) clearTimeout(press.timer);
        press = null;
    }

    function onPressStart(e) {
        if (selecting || e.pointerType === 'mouse' || !e.isPrimary) return;
        const card = e.target.closest('.book-item');
        if (!card) return;
        cancelPress();
        press = {
            x: e.clientX, y: e.clientY,
            timer: setTimeout(() => {
                press = null;
                ignoreClickUntil = Date.now() + 800;
                enterSelect();
                activate(card, false);
                focusCard(cards().indexOf(card));
                navigator.vibrate?.(15);       // a small tick where supported
            }, LONG_PRESS_MS),
        };
    }

    function onPressMove(e) {
        if (press && Math.hypot(e.clientX - press.x, e.clientY - press.y) > MOVE_LIMIT) cancelPress();
    }

    function onGridClick(e) {
        if (Date.now() < ignoreClickUntil) {       // the end of a long press
            e.preventDefault();
            e.stopPropagation();
            return;
        }
        if (!selecting) return;
        const card = e.target.closest('.book-item');
        if (!card || !container.contains(card)) return;
        // Links and menus on the card are inert here: a mis-tap can't navigate
        // away and lose the selection
        e.preventDefault();
        e.stopPropagation();
        activate(card, e.shiftKey);
        focusCard(cards().indexOf(card));
    }

    function onGridKey(e) {
        if (!selecting) return;
        const card = e.target.closest?.('.book-item');
        if (!card) return;
        const list = cards();
        const index = list.indexOf(card);
        if (e.key === ' ' || e.key === 'Enter') {
            e.preventDefault();
            activate(card, e.shiftKey);
            return;
        }
        const cols = columnCount(list.map(c => c.offsetTop));
        const to = nextIndex(index, e.key, cols, list.length);
        if (to === null) return;
        e.preventDefault();
        if (e.shiftKey) {
            if (anchor < 0) anchor = index;
            rangeBetween(anchor, to).forEach(i => setSelected(list[i], true));
            refresh();
        }
        focusCard(to);
    }

    function selectAll() {
        cards().forEach(card => setSelected(card, true));
        refresh();
    }

    function clearSelection() {
        selected.clear();
        anchor = -1;
        refresh();
    }

    function ids() {
        // In page order, so the plan and the review read as the grid does
        return cards().map(cardId).filter(id => selected.has(id));
    }

    // ---- the sheet ------------------------------------------------------

    const sheet = { action: null, params: null, ids: [], plan: null, excluded: new Set(), stage: 'choose' };
    const genre = { list: [], cleared: false, active: -1 };

    function showStage(stage) {
        sheet.stage = stage;
        $('bulk-choose').classList.toggle('hidden', stage !== 'choose');
        $('bulk-review').classList.toggle('hidden', stage !== 'review');
        $('bulk-title').textContent = stage === 'choose' ? 'Set genre' : 'Review';
        setError('');
        if (stage === 'choose') {
            $('bulk-go').textContent = 'Review';
            syncGenre();
        }
    }

    function setError(message) {
        const el = $('bulk-error');
        el.textContent = message;
        el.classList.toggle('hidden', !message);
    }

    async function api(url, body) {
        const res = await fetch(url, { method: body ? 'POST' : 'GET', headers: getCSRFHeaders(),
                                       body: body ? JSON.stringify(body) : undefined });
        let data = null;
        try { data = await res.json(); } catch { /* not JSON: a proxy error page */ }
        return { status: res.status, data };
    }

    async function openSheet(action, button) {
        sheet.action = action;
        sheet.ids = ids();
        if (!sheet.ids.length) return;
        opener = button;
        genre.cleared = false;
        genre.active = -1;
        $('bulk-genre-input').value = '';
        $('bulk-choose-count').textContent = itemsWord(sheet.ids.length);
        showStage('choose');
        $('bulk-sheet').showModal();
        $('bulk-genre-input').focus();
        // Your genres for this section, most used first; the box works while it loads
        const res = await api('/bulk/genres?type=' + encodeURIComponent(container.dataset.media || 'book'));
        genre.list = res.data?.success ? res.data.genres : [];
        renderGenreList();
        syncGenre();
    }

    function closeSheet() {
        const dialog = $('bulk-sheet');
        if (dialog.open) dialog.close();
        (opener || $('bulk-select-btn'))?.focus();
    }

    // ---- genre picker (a combobox, not a datalist: it shows counts) ----

    function renderGenreList() {
        const list = $('bulk-genre-list');
        const typed = $('bulk-genre-input').value;
        const shown = filterGenres(genre.list, typed);
        list.replaceChildren();
        shown.forEach((g, i) => {
            const li = document.createElement('li');
            li.id = `bulk-genre-opt-${i}`;
            li.setAttribute('role', 'option');
            li.className = 'bulk-opt';
            li.dataset.value = g.value;
            const name = document.createElement('span');
            name.textContent = g.value;
            const count = document.createElement('span');
            count.className = 'bulk-opt-count';
            count.textContent = g.count;
            li.append(name, count);
            list.append(li);
        });
        // "(no genre)" clears: last, so the real genres lead
        const none = document.createElement('li');
        none.id = 'bulk-genre-opt-none';
        none.setAttribute('role', 'option');
        none.className = 'bulk-opt bulk-opt-none';
        none.dataset.clear = '1';
        none.textContent = '(no genre)';
        list.append(none);
        genre.active = -1;
        $('bulk-genre-input').removeAttribute('aria-activedescendant');
    }

    function openList(open) {
        $('bulk-genre-list').classList.toggle('hidden', !open);
        $('bulk-genre-input').setAttribute('aria-expanded', String(open));
    }

    function setActive(i) {
        const opts = Array.from($('bulk-genre-list').children);
        opts.forEach(o => o.setAttribute('aria-selected', 'false'));
        genre.active = (i + opts.length) % opts.length;
        const opt = opts[genre.active];
        opt.setAttribute('aria-selected', 'true');
        opt.scrollIntoView({ block: 'nearest' });
        $('bulk-genre-input').setAttribute('aria-activedescendant', opt.id);
    }

    function chooseOption(opt) {
        genre.cleared = !!opt.dataset.clear;
        $('bulk-genre-input').value = genre.cleared ? '(no genre)' : opt.dataset.value;
        openList(false);
        syncGenre();
    }

    function currentGenre() {
        return matchGenre($('bulk-genre-input').value, genre.list, genre.cleared);
    }

    function syncGenre() {
        const state = currentGenre();
        $('bulk-genre-hint').textContent = state.hint;
        $('bulk-go').disabled = sheet.stage === 'choose' && !state.valid;
    }

    function onGenreInput() {
        genre.cleared = false;      // typing again leaves "(no genre)"
        renderGenreList();
        openList(true);
        syncGenre();
    }

    function onGenreKey(e) {
        const listOpen = !$('bulk-genre-list').classList.contains('hidden');
        if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
            e.preventDefault();
            if (!listOpen) { openList(true); }
            setActive(genre.active + (e.key === 'ArrowDown' ? 1 : -1));
        } else if (e.key === 'Enter') {
            e.preventDefault();
            const opt = listOpen && genre.active >= 0 ? $('bulk-genre-list').children[genre.active] : null;
            if (opt) chooseOption(opt);
            else if (currentGenre().valid) goReview();
        } else if (e.key === 'Escape' && listOpen) {
            // The first Escape closes the list; the sheet stays
            e.preventDefault();
            e.stopPropagation();
            openList(false);
        }
    }

    // ---- review ---------------------------------------------------------

    async function goReview() {
        const state = currentGenre();
        if (!state.valid) return;
        sheet.params = { genre: state.value };
        $('bulk-go').disabled = true;
        const res = await api('/bulk/plan', { action: sheet.action, params: sheet.params, ids: sheet.ids });
        if (!res.data?.success) {
            setError(res.data?.error || 'Could not work that out. Try again.');
            syncGenre();
            return;
        }
        sheet.plan = res.data.plan;
        sheet.excluded = new Set();
        if (!DEFAULT_TICKED) sheet.plan.groups.forEach(g => g.items.forEach(i => sheet.excluded.add(i.id)));
        showStage('review');
        $('bulk-stale').classList.add('hidden');
        renderReview(true);
    }

    function line(text, cls) {
        const p = document.createElement('p');
        p.className = cls;
        p.textContent = text;
        return p;
    }

    function renderReview(initial, openGroups = null) {
        const plan = sheet.plan;
        // Rebuilding the list on every tick must not move the user's place
        const body = document.querySelector('.bulk-sheet-body');
        const scrollTop = body.scrollTop;
        const ticks = Array.from($('bulk-review').querySelectorAll('.bulk-tick'));
        const focused = ticks.indexOf(document.activeElement);
        const skipped = plan.skipped.reduce((n, s) => n + s.count, 0);
        $('bulk-describe').textContent = plan.describe;
        const groups = $('bulk-groups');
        const wasOpen = openGroups || new Set(Array.from(groups.querySelectorAll('details[open]')).map(d => d.dataset.key));
        groups.replaceChildren();

        const startOpen = plan.changes <= OPEN_ALL_UP_TO;
        plan.groups.forEach((g, gi) => {
            const key = String(g.before);
            const ids = g.items.map(i => i.id);
            const box = document.createElement('details');
            box.className = 'bulk-group';
            box.dataset.key = key;
            if (initial ? startOpen : wasOpen.has(key)) box.open = true;

            const head = document.createElement('summary');
            head.className = 'bulk-group-head';
            const check = document.createElement('input');
            check.type = 'checkbox';
            check.className = 'bulk-tick';
            const state = groupTickState(ids, sheet.excluded);
            check.checked = state === 'all';
            check.indeterminate = state === 'some';
            check.setAttribute('aria-label', `${g.before || '(no genre)'} to ${g.after || '(no genre)'}, ${g.count} items`);
            // The checkbox sits in the <summary>: don't let a tick toggle the group open
            check.addEventListener('click', e => e.stopPropagation());
            check.addEventListener('change', () => {
                ids.forEach(id => check.checked ? sheet.excluded.delete(id) : sheet.excluded.add(id));
                renderReview(false);
            });
            const label = document.createElement('span');
            label.className = 'bulk-group-label';
            label.textContent = `${g.before || '(no genre)'} → ${g.after || '(no genre)'}`;
            const count = document.createElement('span');
            count.className = 'bulk-group-count';
            count.textContent = g.count;
            const show = document.createElement('span');
            show.className = 'bulk-link bulk-show';
            show.setAttribute('aria-hidden', 'true');
            head.append(check, label, count, show);
            box.append(head);

            const items = document.createElement('ul');
            items.className = 'bulk-items';
            const cap = GROUP_PREVIEW;
            g.items.slice(0, cap).forEach(item => items.append(itemRow(item)));
            if (g.items.length > cap) {
                const more = document.createElement('li');
                const btn = document.createElement('button');
                btn.type = 'button';
                btn.className = 'bulk-link';
                btn.textContent = `Show all ${g.items.length}`;
                btn.addEventListener('click', () => {
                    g.items.slice(cap).forEach(item => items.insertBefore(itemRow(item), more));
                    more.remove();
                });
                more.append(btn);
                items.append(more);
            }
            box.append(items);
            groups.append(box);
        });

        const quiet = $('bulk-quiet');
        quiet.replaceChildren();
        if (plan.same) quiet.append(li(`Already “${plan.params.genre ?? '(no genre)'}” (${plan.same})`));
        plan.skipped.forEach(s => quiet.append(li(`Skipped: ${s.reason.toLowerCase()} (${s.count})`)));
        plan.notes.forEach(n => quiet.append(li(n)));

        $('bulk-summary').textContent = summaryLine(plan.changes, plan.same, skipped);
        const n = applyCount(plan, sheet.excluded);
        const go = $('bulk-go');
        go.textContent = applyLabel(n);
        go.disabled = n === 0;

        body.scrollTop = scrollTop;
        if (focused >= 0) $('bulk-review').querySelectorAll('.bulk-tick')[focused]?.focus({ preventScroll: true });
    }

    function li(text) {
        const el = document.createElement('li');
        el.textContent = text;
        return el;
    }

    function itemRow(item) {
        const row = document.createElement('li');
        row.className = 'bulk-item';
        const check = document.createElement('input');
        check.type = 'checkbox';
        check.className = 'bulk-tick';
        check.checked = !sheet.excluded.has(item.id);
        check.setAttribute('aria-label', item.title || 'Item');
        check.addEventListener('change', () => {
            if (check.checked) sheet.excluded.delete(item.id); else sheet.excluded.add(item.id);
            renderReview(false);
        });
        const img = document.createElement('img');
        img.className = 'bulk-thumb';
        img.alt = '';
        img.loading = 'lazy';
        if (item.cover) img.src = '/static/' + item.cover; else img.classList.add('bulk-thumb-none');
        const text = document.createElement('span');
        text.className = 'bulk-item-text';
        const title = document.createElement('span');
        title.className = 'bulk-item-title';
        title.textContent = item.title;
        const creator = document.createElement('span');
        creator.className = 'bulk-item-creator';
        creator.textContent = item.creator || '';
        text.append(title, creator);
        row.append(check, img, text);
        return row;
    }

    async function goApply() {
        const go = $('bulk-go');
        go.disabled = true;
        setError('');
        const res = await api('/bulk/apply', {
            action: sheet.action, params: sheet.params, ids: sheet.ids,
            fingerprint: sheet.plan.fingerprint, excluded_ids: Array.from(sheet.excluded),
        });
        if (res.status === 409 && res.data?.stale) {
            // The data moved: show the new plan in place, keep the user's choices, write nothing
            const open = new Set(Array.from($('bulk-groups').querySelectorAll('details[open]')).map(d => d.dataset.key));
            sheet.excluded = carryExclusions(sheet.plan, sheet.excluded, res.data.plan);
            sheet.plan = res.data.plan;
            $('bulk-stale').classList.remove('hidden');
            renderReview(false, open);
            return;
        }
        if (!res.data?.success) {
            setError(res.data?.error || 'Could not apply that. Nothing was changed.');
            go.disabled = false;
            return;
        }
        // The server has put the result in the session; the page shows it as a banner
        window.location.reload();
    }

    function goBack() {
        showStage('choose');
        $('bulk-genre-input').focus();
    }

    // ---- banner ---------------------------------------------------------

    async function undoEdit(button) {
        button.disabled = true;
        const res = await api(`/bulk/${encodeURIComponent(button.dataset.editId)}/undo`, {});
        if (res.data?.success) { window.location.reload(); return; }
        button.disabled = false;
        showFlashMessage('error', res.data?.error || 'Could not undo that.');
    }

    // ---- wiring ---------------------------------------------------------

    registerActions({
        bulkToggleSelect: () => (selecting ? exitSelect() : enterSelect()),
        bulkSelectAll: selectAll,
        bulkClear: clearSelection,
        bulkOpen: el => openSheet(el.dataset.action, el),
        bulkGo: () => (sheet.stage === 'choose' ? goReview() : goApply()),
        bulkChange: goBack,
        bulkCancel: closeSheet,
        bulkUndo: undoEdit,
        bulkDismiss: el => el.closest('[data-bulk-banner]')?.remove(),
    });

    document.addEventListener('DOMContentLoaded', () => {
        const grid = $('book-container');
        if (!grid || !$('bulk-bar')) return;
        grid.addEventListener('click', e => { container = grid; onGridClick(e); }, true);
        grid.addEventListener('keydown', e => { container = grid; onGridKey(e); });
        if (grid.hasAttribute('data-bulkable')) {
            grid.addEventListener('pointerdown', onPressStart);
            grid.addEventListener('pointermove', onPressMove);
            for (const type of ['pointerup', 'pointercancel', 'pointerleave']) grid.addEventListener(type, cancelPress);
            // Android's long-press menu (and iOS's, with the CSS) would fight it
            grid.addEventListener('contextmenu', e => {
                if (press || selecting || Date.now() < ignoreClickUntil) e.preventDefault();
            });
        }

        const input = $('bulk-genre-input');
        input.addEventListener('input', onGenreInput);
        input.addEventListener('keydown', onGenreKey);
        input.addEventListener('focus', () => { renderGenreList(); openList(true); });
        // pointerdown, not click: the input would blur and hide the list first
        $('bulk-genre-list').addEventListener('pointerdown', e => {
            const opt = e.target.closest('[role="option"]');
            if (opt) { e.preventDefault(); chooseOption(opt); }
        });
        // Click elsewhere in the sheet closes the list
        $('bulk-sheet').addEventListener('click', e => {
            if (!e.target.closest('#bulk-genre-input, #bulk-genre-list')) openList(false);
        });
        // Esc, however the dialog closed, sends focus back to the button that opened it
        $('bulk-sheet').addEventListener('close', () => (opener || $('bulk-select-btn'))?.focus());
    });

    document.addEventListener('cards-added', e => {
        if (!selecting || e.detail?.container !== container) return;
        cards().filter(c => !c.hasAttribute('role')).forEach(decorate);
        refresh();
    });

    document.addEventListener('keydown', e => {
        if (!selecting || $('bulk-sheet').open) return;     // an open sheet takes its own Escape
        if (e.key === 'Escape') {
            exitSelect();
        } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'a'
                   && !/^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)) {
            e.preventDefault();
            selectAll();
        }
    });
})();

// Node (tests) gets the pure helpers; browsers just see the globals above.
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        fold, rangeBetween, columnCount, nextIndex, groupTickState, applyCount, summaryLine, applyLabel,
        selectedLabel, matchGenre, filterGenres, carryExclusions, idFromHref,
    };
}

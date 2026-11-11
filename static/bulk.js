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

// The review's primary button: the verb and the live count.
function applyLabel(n, action = '', shelfName = '') {
    if (action === 'remove') return `Remove ${n} from library`;
    if (action === 'restore') return `Put ${itemsWord(n)} back`;
    if (action === 'shelf_add') return `Add ${n} to ${shelfName}`;
    if (action === 'shelf_remove') return `Remove ${n} from ${shelfName}`;
    return `Apply to ${itemsWord(n)}`;
}

function selectedLabel(n) { return `${n} selected`; }

// The bar's count for a view selection ("Select all 57 in this view"):
// past the cap it says so, and the actions are off.
function viewLabel(total) {
    return total > MAX_ITEMS ? `Too many for one edit (${total}). Narrow the view.` : `All ${total} in this view`;
}

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
        .filter(g => g.items.length && g.items.every(i => oldExcluded.has(i.id))).map(g => g.key));
    const next = new Set();
    for (const g of newPlan.groups) {
        for (const item of g.items) {
            if (groupsOff.has(g.key) || oldExcluded.has(item.id)) next.add(item.id);
        }
    }
    return next;
}

// What the sheet sends for an action, from the raw values of its inputs:
// {action, params, valid}. `kind` is the sheet's panel ('shelf' and 'tag'
// choose between add and remove with v.mode). Server rules decide the rest;
// this only keeps Review disabled until there is something to send.
function buildParams(kind, v) {
    const text = String(v.text ?? '').trim();
    switch (kind) {
        case 'genre': {
            const g = matchGenre(v.text, v.genres || [], !!v.cleared);
            return { action: 'genre', params: { genre: g.value }, valid: g.valid };
        }
        case 'status':
            return { action: 'status', params: { status: v.value }, valid: !!v.value };
        case 'format':
            return { action: 'format', params: { format: v.value }, valid: !!v.value };
        case 'owned':
            return { action: 'owned', params: { owned: v.value }, valid: v.value === '1' || v.value === '0' };
        case 'remove':
            return { action: 'remove', params: { note: text || null }, valid: true };
        case 'restore':
            return { action: 'restore', params: {}, valid: true };
        case 'shelf': {
            const action = v.mode === 'remove' ? 'shelf_remove' : 'shelf_add';
            if (v.shelf === '__new__' && action === 'shelf_add') {
                const name = String(v.newName ?? '').trim();
                return { action, params: { media_type: v.mediaType, new_shelf: name }, valid: !!name && name.length <= 60 };
            }
            const id = Number(v.shelf);
            return { action, params: { media_type: v.mediaType, shelf_id: id }, valid: Number.isInteger(id) && id > 0 };
        }
        case 'tag': {
            const tag = text.toLowerCase();
            return { action: v.mode === 'remove' ? 'tag_remove' : 'tag_add', params: { tag },
                     valid: !!tag && tag.length <= 50 };
        }
        default:
            return { action: '', params: {}, valid: false };
    }
}

// The line under the tag box: tags are kept lower case, as everywhere else.
function tagHint(typed) {
    const text = String(typed ?? '').trim();
    if (!text) return '';
    if (text.length > 50) return 'Keep it to 50 characters or fewer.';
    return text === text.toLowerCase() ? '' : `Saved as \u201c${text.toLowerCase()}\u201d`;
}

// What a selected item has now, for the action in hand: the line under its
// title in the choose step. `item` is one row of POST /bulk/selection.
const OWNER_ONLY = new Set(['genre', 'format', 'owned', 'remove', 'restore']);
function nowText(kind, item) {
    if (OWNER_ONLY.has(kind) && !item.yours) return 'Not yours, will be skipped';
    switch (kind) {
        case 'genre': return item.genre || '(no genre)';
        case 'status': return item.status;
        case 'format': return item.format || '(no format)';
        case 'owned': return item.owned ? 'Owned' : 'Not owned';
        case 'remove':
        case 'restore': return item.removed ? 'Removed' : 'On the shelf';
        case 'shelf': return item.shelves.length ? 'In ' + item.shelves.join(', ') : 'In no collections';
        case 'tag': return item.tags.length ? item.tags.join(', ') : 'No tags';
        default: return '';
    }
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
    // A view selection: every item of the grid's view, not just the loaded
    // cards ({key, args, total}). The server resolves it at plan time. Cards
    // can't be toggled one by one while it's on; the review leaves things out.
    let viewAll = null;

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
        viewAll = null;
        selected.clear();
        anchor = -1;
        if (container) {
            delete container.dataset.select;
            for (const attr of ['role', 'aria-multiselectable', 'aria-label']) container.removeAttribute(attr);
            cards().forEach(undecorate);
        }
        delete document.documentElement.dataset.bulk;
        $('bulk-bar').classList.add('hidden');
        $('bulk-menu')?.classList.add('hidden');
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
        list.forEach(card => card.setAttribute('aria-selected', String(!!viewAll || selected.has(cardId(card)))));
        const hint = $('bulk-hint');
        if (viewAll) {
            const over = viewAll.total > MAX_ITEMS;
            $('bulk-count').textContent = viewLabel(viewAll.total);
            $('bulk-all').classList.add('hidden');
            $('bulk-clear').classList.remove('hidden');
            document.querySelectorAll('[data-bulk-action]').forEach(btn => {
                btn.disabled = over;
                btn.title = over ? `Select ${MAX_ITEMS} or fewer` : '';
            });
            hint.classList.add('hidden');
            return;
        }
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
        // Paged grids (Books, Household books, Search) can take the whole view.
        // The offer stays while anything is selected, also once scrolling has
        // loaded cards that aren't (Phil, 2026-11-11).
        const offerView = !!container?.dataset.bulkView && n > 0 && total > n;
        const partial = n > 0 && n === list.length && total > list.length;
        hint.classList.toggle('hidden', !(offerView || partial));
        hint.replaceChildren();
        if (offerView) {
            const more = document.createElement('button');
            more.type = 'button';
            more.className = 'bulk-link';
            more.dataset.click = 'bulkSelectView';
            more.textContent = `Select all ${total} in this view`;
            hint.append(n === list.length ? `All ${n} loaded are selected. ` : `${n} of ${total} selected. `, more);
        } else if (partial) {
            hint.textContent = `Selected the ${list.length} loaded of ${total}. Scroll down to load more.`;
        }
    }

    function selectView() {
        const total = Number(container?.parentElement?.dataset.totalCount) || 0;
        if (!container?.dataset.bulkView || !total) return;
        viewAll = { key: container.dataset.bulkView, args: window.location.search.replace(/^\?/, ''), total,
                    drop: new Set() };       // items taken out from the sheet's list
        refresh();
        $('bulk-clear').focus();
    }

    function setSelected(card, on) {
        const id = cardId(card);
        if (on) selected.add(id); else selected.delete(id);
    }

    // Click, Space or a key: toggle one card, or select the range from the anchor
    function activate(card, range) {
        if (viewAll) return;              // the whole view: leave items out in the review
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
        if (e.shiftKey && !viewAll) {
            if (anchor < 0) anchor = index;
            rangeBetween(anchor, to).forEach(i => setSelected(list[i], true));
            refresh();
        }
        focusCard(to);
    }

    function selectAll() {
        if (viewAll) return;
        cards().forEach(card => setSelected(card, true));
        refresh();
    }

    function clearSelection() {
        viewAll = null;
        selected.clear();
        anchor = -1;
        refresh();
    }

    function ids() {
        // In page order, so the plan and the review read as the grid does
        return cards().map(cardId).filter(id => selected.has(id));
    }

    // ---- the sheet ------------------------------------------------------

    // Each bar action opens the same dialog with its own inputs (a panel in
    // _bulk_sheet.html). `kind` is the panel; the server action key (shelf and
    // tag choose add or remove) comes from buildParams.
    const KINDS = {
        genre:   { title: 'Set genre' },
        status:  { title: 'Set status' },
        format:  { title: 'Set format' },
        owned:   { title: 'Owned or not' },
        remove:  { title: 'Remove from library', danger: true },
        restore: { title: 'Put back on the shelf' },
        shelf:   { title: 'Collections' },   // custom collections; code says shelf
        tag:     { title: 'Tags' },
    };
    const sheet = { kind: null, action: null, params: null, ids: [], view: null, plan: null, excluded: new Set(), stage: 'choose' };
    const genre = { list: [], cleared: false, active: -1, filter: '' };
    const picked = { key: '', items: null };   // /bulk/selection for the ids in the sheet
    let options = null;             // /bulk/options for this section, fetched once

    const radio = name => document.querySelector(`input[name="${name}"]:checked`)?.value;
    const mediaType = () => container?.dataset.media || 'book';

    function showStage(stage) {
        sheet.stage = stage;
        $('bulk-choose').classList.toggle('hidden', stage !== 'choose');
        $('bulk-review').classList.toggle('hidden', stage !== 'review');
        $('bulk-title').textContent = stage === 'choose' ? KINDS[sheet.kind].title : 'Review';
        setError('');
        if (stage === 'choose') {
            const go = $('bulk-go');
            go.textContent = 'Review';
            styleGo(false);
            syncChoose();
        }
    }

    // The remove action's button is the danger colour, as the spec asks
    function styleGo(danger) {
        const go = $('bulk-go');
        go.classList.toggle('bg-red-600', danger);
        go.classList.toggle('hover:bg-red-700', danger);
        go.classList.toggle('bg-accent', !danger);
        go.classList.toggle('hover:bg-accent-hover', !danger);
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

    function fillSelect(select, items, placeholder) {
        select.replaceChildren();
        if (placeholder) {
            const first = document.createElement('option');
            first.value = '';
            first.textContent = placeholder;
            select.append(first);
        }
        for (const [value, label] of items) {
            const opt = document.createElement('option');
            opt.value = value;
            opt.textContent = label;
            select.append(opt);
        }
    }

    // Put the pickers' choices in the panels (statuses, formats, shelves, tags)
    function fillPanels() {
        if (!options) return;
        fillSelect($('bulk-status'), options.statuses.map(s =>
            [s.value, s.value === 'untracked' ? `${s.label} (clears the status)` : s.label]), 'Choose a status');
        fillSelect($('bulk-format'), options.formats.map(f => [f.value, f.label]), 'Choose a format');
        fillShelves();
        const tags = $('bulk-tag-list');
        tags.replaceChildren();
        for (const t of options.tags) {
            const opt = document.createElement('option');
            opt.value = t.value;
            tags.append(opt);
        }
    }

    // "New shelf..." only makes sense when adding
    function fillShelves() {
        if (!options) return;
        const adding = radio('bulk-shelf-mode') !== 'remove';
        const items = options.shelves.map(s => [String(s.id), `${s.name} (${s.count})`]);
        if (adding) items.push(['__new__', 'New collection…']);
        const select = $('bulk-shelf');
        const was = select.value;
        fillSelect(select, items, items.length ? 'Choose a collection' : 'You have no collections here yet');
        if (items.some(([v]) => v === was)) select.value = was;
        else if (adding && !options.shelves.length) select.value = '__new__';
        $('bulk-shelf-new-row').classList.toggle('hidden', select.value !== '__new__');
    }

    function resetInputs() {
        genre.cleared = false;
        genre.active = -1;
        genre.filter = '';
        $('bulk-genre-input').value = '';
        $('bulk-status').value = '';
        $('bulk-format').value = '';
        document.querySelectorAll('input[name="bulk-owned"]').forEach(r => { r.checked = false; });
        $('bulk-note').value = '';
        $('bulk-shelf-new').value = '';
        $('bulk-tag-input').value = '';
        document.querySelectorAll('input[name="bulk-shelf-mode"], input[name="bulk-tag-mode"]')
            .forEach(r => { r.checked = r.value === 'add'; });
    }

    // What the open panel would send, or null before any panel is open
    function readChoice() {
        const kind = sheet.kind;
        const v = {
            genre: () => ({ text: $('bulk-genre-input').value, genres: genre.list, cleared: genre.cleared }),
            status: () => ({ value: $('bulk-status').value }),
            format: () => ({ value: $('bulk-format').value }),
            owned: () => ({ value: radio('bulk-owned') }),
            remove: () => ({ text: $('bulk-note').value }),
            restore: () => ({}),
            shelf: () => ({ mode: radio('bulk-shelf-mode'), shelf: $('bulk-shelf').value,
                            newName: $('bulk-shelf-new').value, mediaType: mediaType() }),
            tag: () => ({ mode: radio('bulk-tag-mode'), text: $('bulk-tag-input').value }),
        }[kind];
        return v ? buildParams(kind, v()) : null;
    }

    function syncChoose() {
        if (!sheet.kind) return;
        const choice = readChoice();
        if (sheet.kind === 'genre') $('bulk-genre-hint').textContent = matchGenre(
            $('bulk-genre-input').value, genre.list, genre.cleared).hint;
        if (sheet.kind === 'tag') $('bulk-tag-hint').textContent = tagHint($('bulk-tag-input').value);
        $('bulk-go').disabled = sheet.stage === 'choose' && !(choice && choice.valid && sheetCount() > 0);
    }

    async function openSheet(kind, button) {
        if (!KINDS[kind]) return;
        sheet.kind = kind;
        // A view selection is resolved by the server: the plan brings its ids
        sheet.view = viewAll ? { view: viewAll.key, args: viewAll.args } : null;
        sheet.ids = viewAll ? [] : ids();
        const count = viewAll ? viewAll.total : sheet.ids.length;
        if (!count) return;
        opener = button;
        resetInputs();
        for (const key of Object.keys(KINDS)) $(`bulk-in-${key}`).classList.toggle('hidden', key !== kind);
        setCounts();
        fillPanels();
        showStage('choose');
        $('bulk-sheet').showModal();
        // On a touch screen focusing a text box opens the keyboard over the
        // lists, so focus goes to the heading there and you tap what you want
        if (window.matchMedia('(pointer: fine)').matches) {
            $(`bulk-in-${kind}`).querySelector('input:not([type="radio"]), select, input[type="radio"]')?.focus();
        } else {
            $('bulk-title').focus();
        }
        renderGenreList();
        loadSelection();
        // Your genres and the pickers' choices for this section; the sheet works while they load
        const type = encodeURIComponent(mediaType());
        if (kind === 'genre' && !genre.list.length) {
            const res = await api('/bulk/genres?type=' + type);
            genre.list = res.data?.success ? res.data.genres : [];
            renderGenreList();
        }
        if (!options && ['status', 'format', 'shelf', 'tag'].includes(kind)) {
            const res = await api('/bulk/options?type=' + type);
            if (res.data?.success) { options = res.data; fillPanels(); }
        }
        syncChoose();
    }

    // ---- the selected items, with what each has now ----

    // What the sheet's list was loaded for: the ids, or the view less what was taken out
    function selectionKey() {
        return sheet.view ? `view:${sheet.view.view}?${sheet.view.args}|${Array.from(viewAll?.drop || []).join(',')}`
                          : sheet.ids.join(',');
    }

    // How many the sheet is about, for its "for N items" lines
    function sheetCount() {
        if (picked.items && picked.key === selectionKey()) return picked.items.length;
        return sheet.view ? viewAll.total - viewAll.drop.size : sheet.ids.length;
    }

    function setCounts() {
        const words = itemsWord(sheetCount());
        $('bulk-choose-count').textContent = words;
        document.querySelectorAll('[data-bulk-count]').forEach(el => { el.textContent = words; });
    }

    // The X on a row of the sheet's list: out of the selection, card and all
    function dropItem(id) {
        if (sheet.view) {
            viewAll.drop.add(id);
        } else {
            sheet.ids = sheet.ids.filter(x => x !== id);
            const card = cards().find(c => cardId(c) === id);
            if (card) setSelected(card, false); else selected.delete(id);
            refresh();
        }
        picked.items = picked.items.filter(item => item.id !== id);
        picked.key = selectionKey();
        setCounts();
        renderSelection();
        syncChoose();
        // Keep focus in the list: the next row's X, else the heading
        const next = $('bulk-selected-list').querySelector('.bulk-drop');
        (next || $('bulk-title')).focus();
    }

    async function loadSelection() {
        const key = selectionKey();
        if (picked.key !== key) {
            picked.key = key;
            picked.items = null;
            renderSelection();
            const res = await api('/bulk/selection', target());
            if (picked.key !== key) return;          // the sheet moved on meanwhile
            picked.items = res.data?.success ? res.data.items : [];
        }
        setCounts();           // the list is the true count: items you can't see aren't in it
        renderSelection();
        syncChoose();
    }

    function renderSelection() {
        const box = $('bulk-selected');
        const items = picked.items;
        box.classList.toggle('hidden', !items || !items.length);
        if (!items) return;
        $('bulk-selected-head').textContent = `Selected (${items.length})`;
        $('bulk-selected-list').replaceChildren(...items.map(item => {
            const row = itemRow(item, false);
            const now = document.createElement('span');
            now.className = 'bulk-item-now';
            now.textContent = nowText(sheet.kind, item);
            row.querySelector('.bulk-item-text').append(now);
            row.append(dropButton(item));
            return row;
        }));
    }

    // An X (Lucide "x"), not a bin: it takes the item out of this edit and
    // deletes nothing
    function dropButton(item) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'bulk-drop';
        button.setAttribute('aria-label', `Leave ${item.title || 'this item'} out`);
        button.title = 'Leave out of this edit';
        const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        for (const [k, v] of Object.entries({ viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor',
                                              'stroke-width': '2', 'stroke-linecap': 'round', 'aria-hidden': 'true' })) {
            svg.setAttribute(k, v);
        }
        for (const d of ['M18 6 6 18', 'm6 6 12 12']) {
            const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
            path.setAttribute('d', d);
            svg.append(path);
        }
        button.append(svg);
        button.addEventListener('click', () => dropItem(item.id));
        return button;
    }

    function closeSheet() {
        const dialog = $('bulk-sheet');
        if (dialog.open) dialog.close();
        (opener || $('bulk-select-btn'))?.focus();
    }

    // ---- genre picker (a combobox, not a datalist: it shows counts) ----

    function renderGenreList() {
        const list = $('bulk-genre-list');
        const shown = filterGenres(genre.list, genre.filter);
        const value = fold($('bulk-genre-input').value);
        list.replaceChildren();
        shown.forEach((g, i) => {
            const li = document.createElement('li');
            li.id = `bulk-genre-opt-${i}`;
            li.setAttribute('role', 'option');
            li.className = 'bulk-opt';
            li.dataset.value = g.value;
            if (!genre.cleared && value && fold(g.value) === value) li.dataset.chosen = '';
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
        if (genre.cleared) none.dataset.chosen = '';
        list.append(none);
        genre.active = -1;
        $('bulk-genre-input').removeAttribute('aria-activedescendant');
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
        genre.filter = '';          // the whole list again, the choice marked
        renderGenreList();
        syncChoose();
    }

    function onGenreInput() {
        genre.cleared = false;      // typing again leaves "(no genre)"
        genre.filter = $('bulk-genre-input').value;
        renderGenreList();
        syncChoose();
    }

    function onGenreKey(e) {
        if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
            e.preventDefault();
            setActive(genre.active + (e.key === 'ArrowDown' ? 1 : -1));
        } else if (e.key === 'Enter') {
            e.preventDefault();
            const opt = genre.active >= 0 ? $('bulk-genre-list').children[genre.active] : null;
            if (opt) chooseOption(opt);
            else if (readChoice()?.valid) goReview();
        }
    }

    // Enter in any other text box goes to Review as well
    function onChooseKey(e) {
        if (e.key === 'Enter' && e.target.tagName === 'INPUT' && e.target.type === 'text'
            && e.target.id !== 'bulk-genre-input') {
            e.preventDefault();
            if (readChoice()?.valid) goReview();
        }
    }

    // ---- review ---------------------------------------------------------

    // What the sheet is about, as /bulk/plan and /bulk/selection take it
    function target() {
        return sheet.view ? { ...sheet.view, drop_ids: Array.from(viewAll?.drop || []) } : { ids: sheet.ids };
    }

    async function goReview() {
        const choice = readChoice();
        if (!choice || !choice.valid) return;
        sheet.action = choice.action;
        sheet.params = choice.params;
        $('bulk-go').disabled = true;
        const res = await api('/bulk/plan', { action: sheet.action, params: sheet.params, ...target() });
        if (!res.data?.success) {
            setError(res.data?.error || 'Could not work that out. Try again.');
            syncChoose();
            return;
        }
        sheet.plan = res.data.plan;
        // Apply writes to exactly what was reviewed, even if the view has grown since
        if (sheet.view) sheet.ids = sheet.plan.ids;
        sheet.excluded = new Set();
        if (!DEFAULT_TICKED) sheet.plan.groups.forEach(g => g.items.forEach(i => sheet.excluded.add(i.id)));
        showStage('review');
        $('bulk-stale').classList.add('hidden');
        renderReview(true);
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
        plan.groups.forEach(g => {
            const key = String(g.key);
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
            check.setAttribute('aria-label', `${g.label}, ${g.count} items`);
            // The checkbox sits in the <summary>: don't let a tick toggle the group open
            check.addEventListener('click', e => e.stopPropagation());
            check.addEventListener('change', () => {
                ids.forEach(id => check.checked ? sheet.excluded.delete(id) : sheet.excluded.add(id));
                renderReview(false);
            });
            const label = document.createElement('span');
            label.className = 'bulk-group-label';
            label.textContent = g.label;
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
        if (plan.same) quiet.append(li(`${plan.same_text} (${plan.same})`));
        plan.skipped.forEach(s => quiet.append(li(`Skipped: ${s.reason.toLowerCase()} (${s.count})`)));
        plan.notes.forEach(n => quiet.append(li(n)));

        $('bulk-summary').textContent = summaryLine(plan.changes, plan.same, skipped);
        const n = applyCount(plan, sheet.excluded);
        const go = $('bulk-go');
        go.textContent = applyLabel(n, plan.action, plan.params.shelf_name);
        go.disabled = n === 0;
        styleGo(!!KINDS[sheet.kind].danger);

        body.scrollTop = scrollTop;
        if (focused >= 0) $('bulk-review').querySelectorAll('.bulk-tick')[focused]?.focus({ preventScroll: true });
    }

    function li(text) {
        const el = document.createElement('li');
        el.textContent = text;
        return el;
    }

    // One item: cover, title, creator. In the review it has a tick box that
    // leaves it out; in the choose step's list it doesn't.
    function itemRow(item, withTick = true) {
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
        if (withTick) row.append(check);
        row.append(img, text);
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
        $(`bulk-in-${sheet.kind}`).querySelector('input:not([type="radio"]), select')?.focus();
    }

    // ---- the actions menu (More on a wide screen, Actions on a phone) ----

    const menuOpen = () => !$('bulk-menu').classList.contains('hidden');

    function toggleMenu(open = !menuOpen()) {
        $('bulk-menu').classList.toggle('hidden', !open);
        $('bulk-more').setAttribute('aria-expanded', String(open));
        if (open) {
            // Restore only makes sense where removed items are in view (Show: removed or everything)
            const show = new URLSearchParams(window.location.search);
            $('bulk-restore-item').hidden = !(['removed', 'all'].includes(show.get('show')) || show.get('show_removed'));
            Array.from($('bulk-menu').querySelectorAll('button:not([hidden])')).find(b => b.offsetParent)?.focus();
        }
    }

    function onMenuKey(e) {
        const items = Array.from($('bulk-menu').querySelectorAll('button')).filter(b => !b.hidden && b.offsetParent);
        const at = items.indexOf(document.activeElement);
        if (e.key === 'ArrowDown') { e.preventDefault(); items[(at + 1) % items.length]?.focus(); }
        else if (e.key === 'ArrowUp') { e.preventDefault(); items[(at - 1 + items.length) % items.length]?.focus(); }
        else if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); toggleMenu(false); $('bulk-more').focus(); }
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
        bulkSelectView: selectView,
        bulkOpen: el => { toggleMenu(false); openSheet(el.dataset.action, el.closest('#bulk-menu') ? $('bulk-more') : el); },
        bulkMenu: () => toggleMenu(),
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
        // Any other input in the sheet re-checks whether Review can be pressed
        const choose = $('bulk-choose');
        choose.addEventListener('input', syncChoose);
        choose.addEventListener('change', e => {
            if (e.target.name === 'bulk-shelf-mode') fillShelves();
            if (e.target.id === 'bulk-shelf') {
                $('bulk-shelf-new-row').classList.toggle('hidden', e.target.value !== '__new__');
                if (e.target.value === '__new__') $('bulk-shelf-new').focus();
            }
            syncChoose();
        });
        choose.addEventListener('keydown', onChooseKey);
        $('bulk-menu').addEventListener('keydown', onMenuKey);
        // A click outside the menu closes it
        document.addEventListener('click', e => {
            if (menuOpen() && !e.target.closest('#bulk-menu, #bulk-more')) toggleMenu(false);
        });
        // click, not pointerdown: a finger that starts on an option may be scrolling the list
        $('bulk-genre-list').addEventListener('click', e => {
            const opt = e.target.closest('[role="option"]');
            if (opt) chooseOption(opt);
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
            if (menuOpen()) { toggleMenu(false); return; }   // the menu closes first
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
        selectedLabel, viewLabel, matchGenre, filterGenres, carryExclusions, idFromHref, buildParams, tagHint, nowText,
    };
}

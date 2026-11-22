// Header bar and sidebar (templates/_sidebar.html): the hamburger menu, and
// Escape / click-outside to close it. Loaded by _sidebar.html, so every page
// with a sidebar gets it.

'use strict';

document.addEventListener("DOMContentLoaded", () => {
    const hamburger = document.getElementById("hamburger");
    const sidebar = document.getElementById("sidebar");

    // One place sets the open/closed state. The sidebar slides with a class;
    // the hamburger icon (bars <-> X) follows aria-expanded in styles.css, so
    // the two can't drift apart the way separately toggled classes could.
    // Closed, it's inert: only slid off-screen, its links would still take
    // Tab stops and be read out. If focus was inside when it closes
    // (Escape), it goes back to the hamburger rather than being lost.
    const setSidebarOpen = (open) => {
        if (!open && sidebar.contains(document.activeElement)) hamburger.focus();
        sidebar.classList.toggle("-translate-x-full", !open);
        sidebar.inert = !open;
        hamburger.setAttribute("aria-expanded", String(open));
    };
    const sidebarIsOpen = () => hamburger.getAttribute("aria-expanded") === "true";

    // Toggle sidebar
    hamburger.addEventListener("click", (event) => {
        setSidebarOpen(!sidebarIsOpen());
        event.stopPropagation();
    });
    // Close sidebar when clicking outside
    document.addEventListener("click", (event) => {
        if (!sidebar.contains(event.target) && !hamburger.contains(event.target)) {
            setSidebarOpen(false);
        }
    });
    // A page restored from the back/forward cache keeps its old DOM, so a
    // sidebar left open when you followed a link would come back open.
    window.addEventListener("pageshow", (event) => {
        if (event.persisted) setSidebarOpen(false);
    });
    // Handle escape key
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            setSidebarOpen(false);
        }
    });
});

// ---- Appearance: Settings -> Account -> Appearance and the sidebar ----------
// Appearance is a dropdown per setting (select[data-kind]) plus the accent
// swatches (.theme-opt buttons). Mode 'system' (the default) follows the
// device; the sidebar's sun/moon reads the mode in effect from darkQuery.
const darkQuery = window.matchMedia('(prefers-color-scheme: dark)');

// Show a choice on every picker for that setting: the pressed swatch, the
// dropdown's value (a select's data-value also sets a font dropdown's face, .font-opt)
function showChoice(kind, value) {
    document.querySelectorAll(`.theme-opt[data-kind="${kind}"]`)
        .forEach(b => b.setAttribute('aria-pressed', String(b.dataset.value === value)));
    document.querySelectorAll(`select[data-kind="${kind}"]`).forEach(s => {
        s.value = value;
        s.dataset.value = value;
    });
}

// Apply appearance settings instantly (data-style / data-mode / ... on
// <html>), then save them; revert if the save fails. Every picker on the
// page is kept in step. One setting is setAppearance('font', 'jost');
// several at once pass an object, setAppearance({font: 'jost', heading: 'jost'}).
// Keys: 'style', 'mode', 'accent', 'font' (text), 'heading' or 'palette'.
async function setAppearance(kindOrChanges, value) {
    const root = document.documentElement;
    const wanted = typeof kindOrChanges === 'string' ? { [kindOrChanges]: value } : kindOrChanges;
    const changes = {};
    const previous = {};
    for (const [kind, v] of Object.entries(wanted)) {
        if (root.dataset[kind] !== v) {
            changes[kind] = v;
            previous[kind] = root.dataset[kind];
        }
    }
    if (!Object.keys(changes).length) return false;
    const show = settings => {
        Object.entries(settings).forEach(([kind, v]) => {
            root.dataset[kind] = v;
            showChoice(kind, v);
        });
        syncThemeColor();               // the status bar follows (common.js)
    };
    show(changes);

    try {
        const response = await fetch('/user/update_theme', {
            method: 'POST',
            headers: getCSRFHeaders(),
            body: JSON.stringify(changes)
        });
        const data = await response.json();
        if (!response.ok || !data.success) throw new Error(data.message);
        // A shelf page's catalog cabinet is laid out by the server for the
        // Shelf style (Filters in the bottom row, Batch; _view_bar.html), so
        // switching into or out of Shelf there reloads it, once saved. Only
        // there: every tab row is a cabinet too (tab_row), drawn by CSS alone
        if ('style' in changes && (changes.style === 'shelf') !== (previous.style === 'shelf')
                && document.querySelector('.view-bar.cabinet-part')) {
            location.reload();
        }
        return true;
    } catch (err) {
        show(previous);
        showFlashMessage('error', 'Could not save appearance settings.');
        return false;
    }
}

// Settings -> Account -> Appearance: the swatches and the dropdowns.
// Choosing Cyberpunk here (from another style, once saved) plays its boot
// screen on the spot (cyberpunk.js), which counts as this login's boot.
async function pickAppearance(kind, value) {
    const saved = await setAppearance(kind, value);
    if (saved && kind === 'style' && value === 'cyberpunk') window.cyberpunkStart?.();
}
document.addEventListener('click', event => {
    const btn = event.target.closest('[data-theme-picker] .theme-opt');
    if (btn) pickAppearance(btn.dataset.kind, btn.dataset.value);
});
document.addEventListener('change', event => {
    const select = event.target.closest('[data-theme-picker] select[data-kind]');
    if (select) pickAppearance(select.dataset.kind, select.value);
});

// The sidebar's sun/moon: the other mode from the one in effect (while
// following the system, the device's), stored as a choice like the buttons
document.addEventListener('click', event => {
    if (!event.target.closest('[data-mode-toggle]')) return;
    const mode = document.documentElement.dataset.mode;
    const effective = mode === 'system' ? (darkQuery.matches ? 'dark' : 'light') : mode;
    setAppearance('mode', effective === 'dark' ? 'light' : 'dark');
});

// ---- Header cyclers (ROADMAP 14c): style, accent, font -----------------------
// Each button steps to the next choice after the one in effect and saves it
// through setAppearance, the same as Settings -> Account -> Appearance. Its title names
// what's on now, and a status line announces it to screen readers.
// data-cycle-skip lists choices it names but never steps to: Cyberpunk,
// only found in Appearance (Phil, 2026-11-21). From one of those it steps
// to the first choice.
function cycleLabel(button) {
    const values = button.dataset.cycleValues.split(',');
    const names = button.dataset.cycleNames.split(',');
    const current = document.documentElement.dataset[button.dataset.cycle];
    const now = names[values.indexOf(current)] || names[0];
    const label = `${button.dataset.cycleWhat}: ${now}. Click for the next one`;
    button.title = label;
    button.setAttribute('aria-label', label);
    return now;
}

document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('[data-cycle]').forEach(cycleLabel);
});

document.addEventListener('click', async event => {
    const button = event.target.closest('[data-cycle]');
    if (!button) return;
    const kind = button.dataset.cycle;
    const skip = (button.dataset.cycleSkip || '').split(',');
    const values = button.dataset.cycleValues.split(',').filter(v => !skip.includes(v));
    const current = document.documentElement.dataset[kind];
    const next = values[(values.indexOf(current) + 1) % values.length];
    // The font cycler steps through the text fonts and sets the headings to
    // the same, as one font for the page; Appearance sets them apart
    await setAppearance(kind === 'font' ? { font: next, heading: next } : { [kind]: next });
    const now = cycleLabel(button);
    let status = document.getElementById('cycle-status');
    if (!status) {
        status = document.createElement('p');
        status.id = 'cycle-status';
        status.className = 'sr-only';
        status.setAttribute('aria-live', 'polite');
        document.body.appendChild(status);
    }
    status.textContent = `${button.dataset.cycleWhat}: ${now}`;
});

// The cycler row is hidden until the sliders button (right of the mode
// toggle) opens it. Open or closed is remembered per browser; storage can
// be missing or blocked, and then the row just starts closed.
const CYCLERS_KEY = 'sidebarCyclersOpen';

function setCyclersOpen(toggle, open) {
    const row = document.getElementById(toggle.getAttribute('aria-controls'));
    if (!row) return;
    row.hidden = !open;
    toggle.setAttribute('aria-expanded', String(open));
    toggle.setAttribute('aria-label', `${open ? 'Hide' : 'Show'} quick appearance buttons`);
    toggle.classList.toggle('is-active', open);
}

document.addEventListener('DOMContentLoaded', () => {
    const toggle = document.querySelector('[data-cyclers-toggle]');
    if (!toggle) return;
    let open = false;
    try { open = localStorage.getItem(CYCLERS_KEY) === '1'; } catch (e) { /* storage blocked */ }
    setCyclersOpen(toggle, open);
    toggle.addEventListener('click', () => {
        const nowOpen = toggle.getAttribute('aria-expanded') !== 'true';
        setCyclersOpen(toggle, nowOpen);
        try { localStorage.setItem(CYCLERS_KEY, nowOpen ? '1' : '0'); } catch (e) { /* storage blocked */ }
    });
});

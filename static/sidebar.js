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
    const setSidebarOpen = (open) => {
        sidebar.classList.toggle("-translate-x-full", !open);
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

// ---- Appearance: style and mode pickers ------------------------------------
// Mode is Light | Dark (12.4). Following the system (data-mode="system", the
// default), the button for the mode in effect shows pressed, and changes
// with the device; "Follow system" (.follow-system) goes back to that.
const darkQuery = window.matchMedia('(prefers-color-scheme: dark)');
function syncModeButtons() {
    const mode = document.documentElement.dataset.mode;
    const effective = mode === 'system' ? (darkQuery.matches ? 'dark' : 'light') : mode;
    document.querySelectorAll('.theme-opt[data-kind="mode"]:not(.follow-system)')
        .forEach(b => b.setAttribute('aria-pressed', String(b.dataset.value === effective)));
}
document.addEventListener('DOMContentLoaded', syncModeButtons);
darkQuery.addEventListener('change', syncModeButtons);

// Apply an appearance setting instantly (data-style / data-mode / ... on
// <html>), then save it; revert if the save fails. Every picker on the page
// is kept in step.
async function setAppearance(kind, value) {     // kind: 'style', 'mode', 'accent' or 'font'
    const root = document.documentElement;
    const previous = root.dataset[kind];
    const press = value => kind === 'mode' ? syncModeButtons()
        : document.querySelectorAll(`.theme-opt[data-kind="${kind}"]`)
            .forEach(b => b.setAttribute('aria-pressed', String(b.dataset.value === value)));

    if (value === previous) return;
    root.dataset[kind] = value;
    press(value);

    try {
        const response = await fetch('/user/update_theme', {
            method: 'POST',
            headers: getCSRFHeaders(),
            body: JSON.stringify({ [kind]: value })
        });
        const data = await response.json();
        if (!response.ok || !data.success) throw new Error(data.message);
    } catch (err) {
        root.dataset[kind] = previous;
        press(previous);
        showFlashMessage('error', 'Could not save appearance settings.');
    }
}

// Any [data-theme-picker] group of .theme-opt buttons (Profile -> Appearance)
document.addEventListener('click', event => {
    const btn = event.target.closest('[data-theme-picker] .theme-opt');
    if (btn) setAppearance(btn.dataset.kind, btn.dataset.value);
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
// through setAppearance, the same as Profile -> Appearance. Its title names
// what's on now, and a status line announces it to screen readers.
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
    const values = button.dataset.cycleValues.split(',');
    const current = document.documentElement.dataset[kind];
    const next = values[(values.indexOf(current) + 1) % values.length];
    await setAppearance(kind, next);
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

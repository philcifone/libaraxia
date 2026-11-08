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
// Any [data-theme-picker] group of .theme-opt buttons (Profile -> Appearance,
// the sidebar's Mode shortcut). Applies instantly by setting data-style /
// data-mode on <html>, then saves; reverts if the save fails. Every picker on
// the page is kept in step.
document.addEventListener('click', async event => {
    const btn = event.target.closest('[data-theme-picker] .theme-opt');
    if (!btn) return;
    const kind = btn.dataset.kind;              // 'style' or 'mode'
    const root = document.documentElement;
    const previous = root.dataset[kind];
    const press = value => document.querySelectorAll(`.theme-opt[data-kind="${kind}"]`)
        .forEach(b => b.setAttribute('aria-pressed', String(b.dataset.value === value)));

    if (btn.dataset.value === previous) return;
    root.dataset[kind] = btn.dataset.value;
    press(btn.dataset.value);

    try {
        const response = await fetch('/user/update_theme', {
            method: 'POST',
            headers: getCSRFHeaders(),
            body: JSON.stringify({ [kind]: btn.dataset.value })
        });
        const data = await response.json();
        if (!response.ok || !data.success) throw new Error(data.message);
    } catch (err) {
        root.dataset[kind] = previous;
        press(previous);
        showFlashMessage('error', 'Could not save appearance settings.');
    }
});

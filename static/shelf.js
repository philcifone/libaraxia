// The Shelf style's video-store rack: an easter egg on the Movies grid (the egg
// button in _view_bar.html, Shelf style only). On, <html data-rack="store">
// turns the wooden bookcase into the white rack with boxed movies
// (styles.css, "the movie rack"). Remembered per browser, like grid/list.
// Loaded in <head> without defer so the attribute is set before the first
// paint.
(() => {
    const KEY = 'shelfRack';
    const root = document.documentElement;
    const read = () => { try { return localStorage.getItem(KEY) === 'store'; } catch { return false; } };
    const apply = on => {
        if (on) root.dataset.rack = 'store'; else delete root.dataset.rack;
        document.querySelectorAll('[data-click="toggleRack"]')
            .forEach(btn => btn.setAttribute('aria-pressed', on ? 'true' : 'false'));
    };
    let on = read();
    apply(on);
    document.addEventListener('DOMContentLoaded', () => apply(on));   // the button exists now
    registerActions({
        toggleRack: () => {
            on = !on;
            try { localStorage.setItem(KEY, on ? 'store' : 'shelf'); } catch { /* storage blocked: this page only */ }
            apply(on);
        },
    });
})();

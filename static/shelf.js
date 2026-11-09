// Shelf style on touch screens (ROADMAP 10.1): the bookcase shows covers
// only, with the title on hover, and a phone can't hover. So the first tap
// on a cover shows its label ("peek") and a second tap on the same cover
// within 5 s opens it; tapping elsewhere, or waiting, puts the label away.
// Mouse and keyboard are unchanged (hover and focus show the label).
//
// Also the video-store rack: an easter egg on the Movies grid (the egg
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

(() => {
    const PEEK_MS = 5000;
    const noHover = window.matchMedia('(hover: none)');
    let peeked = null;
    let timer = null;

    const clear = () => {
        if (peeked) peeked.classList.remove('peek');
        peeked = null;
        clearTimeout(timer);
    };

    document.addEventListener('click', event => {
        if (document.documentElement.dataset.style !== 'shelf' || !noHover.matches) return;
        const link = event.target.closest('.shelf-grid.grid .book-link');
        if (!link) { clear(); return; }
        if (link === peeked) { clear(); return; }   // second tap: let it open
        event.preventDefault();
        clear();
        peeked = link;
        link.classList.add('peek');
        timer = setTimeout(clear, PEEK_MS);
    });
})();

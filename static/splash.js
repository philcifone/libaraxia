// The launch splash of the home-screen app (Phil, 2026-11-22): the app icon's
// glyph and "Libaraxia" in Young Serif, in the style's own colours, for under
// a second each time the installed app opens. Never in a browser tab, where
// it would only be a delay, and never in Cyberpunk, whose boot screen
// (cyberpunk.js) plays at login instead.
//
// Loaded in <head> without defer, like cyberpunk.js, so the cover is up
// before the first paint: it sets <html data-splash="on"> at once, which CSS
// turns into a plain cover in the page's background colour (::before). When
// the body exists it mounts the splash itself (.app-splash, built here with
// DOM calls) and switches to data-splash="run". A tap or key skips it.
//
// Once per launch: sessionStorage lives as long as the app is open, so pages
// within it don't splash again, and a fresh launch (the app closed or
// reclaimed by the phone) starts empty. With storage blocked it never shows.
(() => {
    const root = document.documentElement;
    if (root.dataset.style === 'cyberpunk') return;
    const installed = window.matchMedia('(display-mode: standalone)').matches
        || window.navigator.standalone === true;          // older iOS
    if (!installed) return;
    const KEY = 'appSplash';
    try {
        if (sessionStorage.getItem(KEY)) return;
        sessionStorage.setItem(KEY, '1');
    } catch {
        return;
    }

    // The timing, in ms: the splash holds this long once the page has parsed,
    // then fades. Short on purpose: a splash covers a launch, it shouldn't
    // add to it. Reduced motion drops the fade (CSS), not the splash.
    const HOLD = 600;
    const FADE = 250;           // matches .app-splash's transition in styles.css

    // Ask for Young Serif now, so the word is in it by the time it shows
    document.fonts?.load('1em "Young Serif"').catch(() => {});

    root.dataset.splash = 'on';
    let splash = null;
    let timer = null;

    const done = () => {
        clearTimeout(timer);
        document.removeEventListener('pointerdown', skip, true);
        document.removeEventListener('keydown', skip, true);
        if (!splash) {                      // skipped before it mounted
            delete root.dataset.splash;
            return;
        }
        root.dataset.splash = 'out';        // CSS fades it
        setTimeout(() => {
            splash.remove();
            delete root.dataset.splash;
        }, FADE);
    };
    // The splash covers the page, so a skipping tap lands on it, not a link
    const skip = event => {
        event.preventDefault();
        event.stopPropagation();
        done();
    };
    document.addEventListener('pointerdown', skip, true);
    document.addEventListener('keydown', skip, true);

    // The library-house glyph (_icons.html, static/icons/icon.svg): the
    // house in the text colour, the books in the accent (CSS)
    const SVG = 'http://www.w3.org/2000/svg';
    const glyph = () => {
        const svg = document.createElementNS(SVG, 'svg');
        svg.setAttribute('viewBox', '0 0 24 24');
        svg.setAttribute('class', 'app-splash-icon');
        const path = (d, cls) => {
            const p = document.createElementNS(SVG, 'path');
            p.setAttribute('d', d);
            if (cls) p.setAttribute('class', cls);
            svg.append(p);
        };
        path('M3 10a2 2 0 0 1 .709-1.528l7-5.999a2 2 0 0 1 2.582 0l7 5.999A2 2 0 0 1 21 10v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z', 'app-splash-house');
        ['M7.5 9.5v9', 'M10.5 11v7.5', 'M13.5 11v7.5', 'm15.5 11 2.25 7.5'].forEach(d => path(d, 'app-splash-book'));
        return svg;
    };

    document.addEventListener('DOMContentLoaded', () => {
        if (root.dataset.splash !== 'on') return;      // skipped already
        splash = document.createElement('div');
        splash.className = 'app-splash';
        splash.setAttribute('aria-hidden', 'true');
        const word = document.createElement('p');
        word.className = 'app-splash-word';
        word.textContent = 'Libaraxia';
        splash.append(glyph(), word);
        document.body.append(splash);
        root.dataset.splash = 'run';
        timer = setTimeout(done, HOLD);
    });
})();

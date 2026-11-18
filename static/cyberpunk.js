// The Cyberpunk style's boot screen: five seconds of terminal start-up,
// once per login (Phil, 2026-11-18). Typed a character at a time, each
// status line's OK a beat after its dots, then "ENTERING LIBARAXIA" with a
// blinking two-character block cursor, a flash, and the app.
//
// Loaded in <head> without defer, like shelf.js: it sets <html data-boot="on">
// at once, which CSS turns into a plain cover (html::before) before the
// first paint, so the page never flashes in first. When the body exists it
// mounts the screen (.cp-boot, built here with textContent) and switches to
// data-boot="run"; the screen then covers the page itself. The timing is
// all here: each piece gets its start (--d), length (--dur) and character
// count (--n) as custom properties, and the CSS ("Cyberpunk finishing
// touches") animates them.
//
// Once per login, not per tab: <meta name="login-mark"> is the seed drawn at
// each login (session['heading_seed']), remembered here once booted, so new
// tabs and later pages don't boot again. Never with reduced motion, and never
// when storage is blocked (it would boot on every page). Any click or key
// skips it.
(() => {
    const KEY = 'cyberpunkBoot';
    const root = document.documentElement;
    if (root.dataset.style !== 'cyberpunk') return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const mark = document.querySelector('meta[name="login-mark"]')?.content;
    if (!mark) return;
    try {
        if (localStorage.getItem(KEY) === mark) return;
        localStorage.setItem(KEY, mark);
    } catch {
        return;
    }

    // The script. ok: a word that appears after the line is typed;
    // cursor: the blinking block at the end. An empty line is a blank row.
    const LINES = [
        { text: 'LIBARAXIA // CATALOG TERMINAL', head: true },
        { text: '' },
        { text: '> MOUNTING SHELVES ........ ', ok: 'OK' },
        { text: '> INDEXING COLLECTIONS .... ', ok: 'OK' },
        { text: '> LINKING FRIENDS ......... ', ok: 'OK' },
        { text: '' },
        { text: '> ENTERING LIBARAXIA ', cursor: true },
    ];
    // The schedule, in ms. Typing speed is whatever fills the time left
    // between START and the cursor's blinking, so the whole runs END ms.
    const END = 5000;       // the app is showing
    const OUT = 150;        // the cut to the app: a short fade
    const FLASH = 120;      // the bright flash just before it
    const BLINK = 1000;     // the finished last line, cursor blinking
    const START = 120;      // the first character
    const GAP = 110;        // between lines
    const OK_WAIT = 170;    // dots typed, then the OK
    const typeEnd = END - OUT - FLASH - BLINK;
    const typed = LINES.filter(l => l.text);
    const chars = typed.reduce((sum, l) => sum + l.text.length, 0);
    const pauses = GAP * (typed.length - 1) + OK_WAIT * LINES.filter(l => l.ok).length;
    const perChar = (typeEnd - START - pauses) / chars;

    let screen = null;
    let timer = null;
    const done = () => {
        clearTimeout(timer);
        screen?.remove();
        delete root.dataset.boot;
        document.removeEventListener('pointerdown', done, true);
        document.removeEventListener('keydown', done, true);
    };
    root.dataset.boot = 'on';
    // The screen covers the page, so a skipping click lands on it, not a link
    document.addEventListener('pointerdown', done, true);
    document.addEventListener('keydown', done, true);

    const timed = (el, start, length, steps) => {
        el.style.setProperty('--d', `${Math.round(start)}ms`);
        el.style.setProperty('--dur', `${Math.max(1, Math.round(length))}ms`);
        if (steps) el.style.setProperty('--n', steps);
        return el;
    };
    const mount = () => {
        if (root.dataset.boot !== 'on') return;      // skipped already
        screen = document.createElement('div');
        screen.className = 'cp-boot';
        screen.setAttribute('aria-hidden', 'true');
        timed(screen, END - OUT - FLASH, FLASH);
        screen.style.setProperty('--out', `${END - OUT}ms`);
        screen.style.setProperty('--out-dur', `${OUT}ms`);
        let t = START;
        for (const line of LINES) {
            const row = document.createElement('div');
            row.className = 'cp-boot-row';
            if (line.head) row.classList.add('cp-boot-head');
            screen.append(row);
            if (!line.text) { row.textContent = ' '; continue; }
            const text = document.createElement('span');
            text.className = 'cp-boot-type';
            text.textContent = line.text;
            const length = line.text.length * perChar;
            row.append(timed(text, t, length, line.text.length));
            t += length;
            if (line.ok) {
                t += OK_WAIT;
                const ok = document.createElement('span');
                ok.className = 'cp-boot-ok';
                ok.textContent = line.ok;
                row.append(timed(ok, t, 1));
            }
            if (line.cursor) {
                const cursor = document.createElement('span');
                cursor.className = 'cp-boot-cursor';
                row.append(timed(cursor, t, BLINK));
            }
            t += GAP;
        }
        document.body.append(screen);
        root.dataset.boot = 'run';
        timer = setTimeout(done, END + 50);
    };
    document.addEventListener('DOMContentLoaded', mount);
})();

// The Cyberpunk style's motion: the boot screen once per login, and the
// glitch (Phil, 2026-11-18). Both are off with reduced motion.
//
// Loaded in <head> without defer, like shelf.js, so the boot screen can be
// up before the first paint.
(() => {
    const root = document.documentElement;
    if (root.dataset.style !== 'cyberpunk') return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

    const booting = boot();
    glitch(booting);

    // ---- The boot screen ----------------------------------------------------
    // Five seconds of terminal start-up. Typed a character at a time, each
    // status line's readout a beat after its dots, then "ENTERING LIBARAXIA"
    // with a blinking two-character block cursor, a flash, and the app.
    //
    // It sets <html data-boot="on"> at once, which CSS turns into a plain
    // cover (html::before) before the first paint, so the page never flashes
    // in first. When the body exists it mounts the screen (.cp-boot, built
    // here with textContent) and switches to data-boot="run"; the screen
    // then covers the page itself. The timing is all here: each piece gets
    // its start (--d), length (--dur) and character count (--n) as custom
    // properties, and the CSS ("Cyberpunk finishing touches") animates them.
    //
    // Once per login, not per tab: <meta name="login-mark"> is the seed drawn
    // at each login (session['heading_seed']), remembered here once booted,
    // so new tabs and later pages don't boot again. Never when storage is
    // blocked (it would boot on every page). Any click or key skips it.
    //
    // The readouts (user, item, collection and friend counts) come from
    // <meta name="boot-stats">, which the first page after login carries
    // (app.boot_stats). Without it (a later page, the style switched on
    // mid-session) the lines just say OK.
    //
    // Returns the time in ms until the app shows, or null when not booting.
    function boot() {
        const KEY = 'cyberpunkBoot';
        const mark = document.querySelector('meta[name="login-mark"]')?.content;
        if (!mark) return null;
        try {
            if (localStorage.getItem(KEY) === mark) return null;
            localStorage.setItem(KEY, mark);
        } catch {
            return null;
        }

        // The counts, as text; null when the page didn't bring them
        const stats = document.querySelector('meta[name="boot-stats"]')?.dataset;
        const readout = (n, unit) => (stats ? `${n} ${unit}` : 'OK');
        const user = (stats?.user || '').toUpperCase();

        // The script. Each status label is padded with dots to one width, so
        // the readouts line up. ok: shown after the line is typed; cursor:
        // the blinking block at the end. An empty line is a blank row.
        const status = label => `> ${label} `.padEnd(27, '.') + ' ';
        const LINES = [
            { text: 'LIBARAXIA // CATALOG TERMINAL', head: true },
            { text: '' },
            // A long name is cut, so the column stays narrow on a phone
            ...(user ? [{ text: status('OPERATOR'), ok: user.slice(0, 12) }] : []),
            { text: status('MOUNTING SHELVES'), ok: readout(stats?.items, 'ITEMS') },
            { text: status('INDEXING COLLECTIONS'), ok: readout(stats?.lists, 'LISTS') },
            { text: status('LINKING FRIENDS'), ok: readout(stats?.friends, 'LINKED') },
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
        const OK_WAIT = 170;    // dots typed, then the readout
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
            // The login's messages ("Welcome", unread notifications) waited
            // behind the screen: slide them in now, and start their 5 s
            // (scheduleFlashDismiss in common.js listens for this)
            document.querySelectorAll('.flash-message').forEach(m => {
                m.classList.remove('animate-slide-in');
                void m.offsetWidth;                     // restart the animation
                m.classList.add('animate-slide-in');
            });
            document.dispatchEvent(new Event('cyberpunk:booted'));
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
                if (!line.text) { row.textContent = ' '; continue; }
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
        return END;
    }

    // ---- The glitch ---------------------------------------------------------
    // A short digital stutter (class cp-glitch, CSS "Cyberpunk glitch"): the
    // page title once as the page loads, then every 10 s one thing on screen
    // picked at random, a cover or a heading. On a timer, not on hover, so it
    // works the same on a phone; never on a tap. Skipped while the tab is
    // hidden, so a tab left open doesn't queue them up.
    function glitch(bootMs) {
        const FIRST = 500;          // after the page (or the boot screen) is up
        const EVERY = 10000;      // Phil, 2026-11-18 (was 30 s)
        const LENGTH = 450;         // the animation's length in the CSS
        const POOL = '.book-cover, .detail-cover, .page-title, .card h2.font-display, .site-title';

        const run = el => {
            if (!el || el.classList.contains('cp-glitch')) return;
            el.classList.add('cp-glitch');
            setTimeout(() => el.classList.remove('cp-glitch'), LENGTH + 50);
        };
        // On screen: has a size and at least half of it is in the window
        const onScreen = el => {
            const r = el.getBoundingClientRect();
            if (!r.width || !r.height) return false;
            const seen = Math.min(r.bottom, window.innerHeight) - Math.max(r.top, 0);
            return seen >= r.height / 2;
        };
        const random = () => {
            if (document.hidden) return;
            const seen = [...document.querySelectorAll(POOL)].filter(onScreen);
            run(seen[Math.floor(Math.random() * seen.length)]);
        };
        document.addEventListener('DOMContentLoaded', () => {
            setTimeout(() => {
                run(document.querySelector('.page-title') || document.querySelector('.site-title'));
                setInterval(random, EVERY);
            }, (bootMs || 0) + FIRST);
        });
    }
})();

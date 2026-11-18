// The Cyberpunk style's boot screen: a second of terminal start-up text,
// once per login (Phil, 2026-11-18). The screen itself is CSS (html::before
// and ::after in styles.css, "Cyberpunk finishing touches"), shown while
// <html data-boot> is set; this only decides whether to set it.
// Loaded in <head> without defer, like shelf.js, so the screen is up before
// the first paint and the page doesn't flash in first.
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

    root.dataset.boot = 'on';
    const done = () => {
        delete root.dataset.boot;
        document.removeEventListener('pointerdown', done, true);
        document.removeEventListener('keydown', done, true);
    };
    // The screen covers the page, so a skipping click lands on <html>, not a link
    document.addEventListener('pointerdown', done, true);
    document.addEventListener('keydown', done, true);
    setTimeout(done, 1100);     // the CSS fades it out by then anyway
})();

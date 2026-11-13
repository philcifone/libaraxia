// Shelf: the tilt glare (ROADMAP 16.0 step 12). The covers' static sheen
// (.cover-sheen in styles.css) reads --sheen-shift for where its band of
// light sits; with Tilt on, this slides the band as the phone tilts, the
// way the light moves on a real cover in your hand.
//
// - On or off per device (localStorage), like the rental rack: tilt only
//   means anything on a phone, and iPhone permission is per device anyway.
//   The switch is Settings -> Account -> Appearance -> Tilt (Shelf only).
// - iPhone Safari sends orientation only after DeviceOrientationEvent.
//   requestPermission(), called from a tap, and only over HTTPS. Turning
//   Tilt on asks; on later pages the first tap asks again, which Safari
//   answers without a prompt once it has been allowed.
// - Never runs under prefers-reduced-motion, and does nothing outside the
//   Shelf style (the cycler can switch styles live, so it checks per event).
// - The band follows the phone's pose relative to how you were holding it
//   when the page opened, and that rest pose drifts slowly after you, so
//   lying down or sitting up doesn't park the light off the covers.
//
// The pure maths (tiltAxes, tiltShift) is tested under node
// (tests/test_tilt_js.py).

const TILT_KEY = 'shelfTilt';
const TILT_RANGE = 30;      // the band moves at most this many % either way
const TILT_GAIN = 1.2;      // % per degree of tilt
const TILT_DRIFT = 0.01;    // share of the gap to the rest pose closed per event (~60/s)

// The device's beta (front-back) and gamma (left-right) in degrees, turned
// into screen axes for the current orientation (0, 90, 180 or 270):
// [x, y] = tilt toward the screen's right edge, toward its bottom edge.
function tiltAxes(beta, gamma, angle) {
    switch (((angle % 360) + 360) % 360) {
        case 90:  return [beta, -gamma];
        case 180: return [-gamma, -beta];
        case 270: return [-beta, gamma];
        default:  return [gamma, beta];
    }
}

// How far (%) to slide the band for a pose [x, y] against the rest pose.
// The band runs top-left to bottom-right, so both axes move it; tilting
// right or toward you slides the reflection the other way, as a mirror does.
function tiltShift(pose, rest) {
    const dx = pose[0] - rest[0];
    const dy = pose[1] - rest[1];
    const shift = -TILT_GAIN * (0.7 * dx + 0.5 * dy);
    return Math.max(-TILT_RANGE, Math.min(TILT_RANGE, shift));
}

if (typeof window !== 'undefined') (() => {
    const root = document.documentElement;
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
    const Orientation = window.DeviceOrientationEvent;
    const needsPermission = !!Orientation && typeof Orientation.requestPermission === 'function';

    const read = () => { try { return localStorage.getItem(TILT_KEY) === 'on'; } catch { return false; } };
    const save = on => { try { localStorage.setItem(TILT_KEY, on ? 'on' : 'off'); } catch { /* this page only */ } };

    let on = read();
    let listening = false;
    let heard = false;          // an event has arrived, so permission is in hand
    let rest = null;            // the rest pose, [x, y]
    let shift = 0;
    let frame = 0;

    function onTilt(event) {
        if (event.beta == null || event.gamma == null) return;
        heard = true;
        if (root.dataset.style !== 'shelf' || reduced.matches) return;
        const angle = (screen.orientation && screen.orientation.angle) || window.orientation || 0;
        const pose = tiltAxes(event.beta, event.gamma, angle);
        if (!rest) rest = pose;
        rest = [rest[0] + (pose[0] - rest[0]) * TILT_DRIFT, rest[1] + (pose[1] - rest[1]) * TILT_DRIFT];
        shift = tiltShift(pose, rest);
        // Events can outrun the screen: write at most once a frame
        if (!frame) frame = requestAnimationFrame(() => {
            frame = 0;
            root.style.setProperty('--sheen-shift', shift.toFixed(1) + '%');
        });
    }

    function start() {
        if (listening || !Orientation || reduced.matches) return;
        window.addEventListener('deviceorientation', onTilt);
        listening = true;
    }

    function stop() {
        window.removeEventListener('deviceorientation', onTilt);
        listening = false;
        rest = null;
        root.style.removeProperty('--sheen-shift');
    }

    // Must be called inside a tap's handler, before any await
    function askPermission() {
        if (!needsPermission) return Promise.resolve(true);
        return Orientation.requestPermission().then(r => r === 'granted').catch(() => false);
    }

    // The Appearance row: the pressed button, and a line saying why Tilt
    // can't run here when it can't
    function why() {
        if (!Orientation) return 'This browser has no tilt sensor.';
        if (!window.isSecureContext) return 'Tilt needs the site over HTTPS.';
        if (reduced.matches) return 'Off while your device asks for reduced motion.';
        return '';
    }
    function sync() {
        document.querySelectorAll('[data-click="setTilt"]')
            .forEach(b => b.setAttribute('aria-pressed', String((b.dataset.value === 'on') === on)));
        document.querySelectorAll('[data-tilt-note]').forEach(p => {
            p.textContent = why();
            p.hidden = !p.textContent;
        });
    }

    registerActions({
        setTilt: button => {
            const want = button.dataset.value === 'on';
            if (want === on) return;
            if (!want) { on = false; save(false); stop(); sync(); return; }
            askPermission().then(granted => {
                if (!granted) {
                    showFlashMessage('error', 'Tilt was blocked. To allow it, turn on Motion & Orientation Access for this site in Safari\'s settings, then try again.');
                    return;
                }
                on = true; save(true); start(); sync();
            });
        },
    });

    if (on) {
        start();
        // iPhone: the first tap on a page asks again (silently once allowed),
        // unless the sensor is already talking
        if (needsPermission) {
            const ask = () => { if (!heard) askPermission(); };
            document.addEventListener('click', ask, { once: true, capture: true });
        }
    }
    reduced.addEventListener('change', () => { if (reduced.matches) stop(); else if (on) start(); sync(); });
    document.addEventListener('DOMContentLoaded', sync);
})();

if (typeof module !== 'undefined' && module.exports) {
    module.exports = { tiltAxes, tiltShift, TILT_RANGE };
}

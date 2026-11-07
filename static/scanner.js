// Barcode scanner shared by the add-book and wishlist pages.
//
// Loaded after static/vendor/quagga2-*.min.js and before the page script.
// The page gives it a container for the camera view, a start/stop button,
// an optional <select> for the camera picker, and a callback:
//
//   const scanner = createBarcodeScanner({
//       container: document.getElementById('interactive'),
//       button: document.getElementById('toggle-scanner'),
//       cameraSelect: document.getElementById('camera-select'),
//       onCode: ({ code, raw, format }) => { ... },   // called once, camera already off
//   });
//   scanner.stop();   // e.g. when the user switches tabs
//
// How a read is accepted:
//   1. Only the area inside the visible target box is decoded.
//   2. A read must pass its check digit (EAN-13, UPC-A); misreads usually don't.
//   3. The same code must come back on CONFIRM_READS reads in a row. A
//      different code starts the count again.
//
// Codes are handed over as 13 digits: a 12-digit UPC-A gets a leading 0,
// which is how EAN-13 defines it. `raw` is the code as decoded.
//
// The camera is ours, not the decoder's: we open the stream, show it in a
// <video>, copy the target area to a canvas and give that to the decoder.
// So the decoder is only a function from canvas to code (see quaggaDecoder),
// and another one can be dropped in without touching the camera code or the
// pages. Every exit path (code found, Stop, error, tab hidden, page left)
// goes through stop(), which stops every track of the stream.

'use strict';

// --- Check digits -------------------------------------------------------------
// Pure functions; tests/test_scanner_js.py runs them under node.

// EAN-13 (and UPC-A, which is EAN-13 with a leading 0): weights 1,3,1,3,...
// from the left over the first 12 digits; the check digit brings the sum up
// to a multiple of 10.
function isValidEan13(code) {
    if (!/^\d{13}$/.test(code)) return false;
    let sum = 0;
    for (let i = 0; i < 12; i++) sum += Number(code[i]) * (i % 2 ? 3 : 1);
    return (10 - (sum % 10)) % 10 === Number(code[12]);
}

function isValidUpcA(code) {
    return /^\d{12}$/.test(code) && isValidEan13('0' + code);
}

// ISBN-10: weights 10..1, the sum must be a multiple of 11; the last
// character may be X (= 10). Books print their ISBN as an EAN-13 barcode, so
// this is for typed codes, not scans.
function isValidIsbn10(code) {
    const s = String(code).toUpperCase();
    if (!/^\d{9}[\dX]$/.test(s)) return false;
    let sum = 0;
    for (let i = 0; i < 10; i++) sum += (s[i] === 'X' ? 10 : Number(s[i])) * (10 - i);
    return sum % 11 === 0;
}

// A decoded barcode as 13 digits, or null if it isn't a valid EAN-13/UPC-A.
function normalizeScannedCode(raw) {
    const code = String(raw ?? '').trim();
    if (isValidEan13(code)) return code;
    if (isValidUpcA(code)) return '0' + code;
    return null;
}

// Counts identical reads in a row. push(code) returns the code once it has
// been seen `needed` times running, otherwise null. A read older than
// maxGapMs (the barcode left the box for a while) doesn't count towards the
// next one.
function createReadConfirmer(needed, maxGapMs = 1500, now = () => Date.now()) {
    let last = null;
    let count = 0;
    let lastAt = 0;
    return {
        push(code) {
            const t = now();
            if (code === last && t - lastAt <= maxGapMs) count++;
            else { last = code; count = 1; }
            lastAt = t;
            return count >= needed ? code : null;
        },
        reset() { last = null; count = 0; lastAt = 0; },
    };
}

// --- Decoder ------------------------------------------------------------------
// A decoder is { name, available(), decode(canvas) -> Promise<{code, format} | null> }.
// decode() is only ever called once at a time.

const quaggaDecoder = {
    name: 'quagga2',

    available() {
        return typeof window !== 'undefined' && !!window.Quagga;
    },

    // Quagga puts its working canvas into a "viewport" element, by default
    // the first #interactive.viewport on the page, which is our camera
    // view. Give it a detached element instead, emptied after every decode
    // so the canvases don't pile up.
    sink: typeof document !== 'undefined' ? document.createElement('div') : null,

    async decode(canvas) {
        try {
            // decodeSingle takes an image URL. The canvas is only the target
            // box, so this is a small JPEG; data: URLs are allowed by img-src.
            const result = await window.Quagga.decodeSingle({
                src: canvas.toDataURL('image/jpeg', 0.92),
                numOfWorkers: 0,
                locate: true,
                inputStream: { size: 800, target: this.sink },
                canvas: { createOverlay: false },
                locator: { patchSize: 'medium', halfSample: false },
                // Books are EAN-13, VHS tapes UPC-A. EAN-8 and UPC-E are left
                // out: they don't occur on either, and a short reader matching
                // part of a longer barcode is a classic source of wrong codes.
                decoder: { readers: ['ean_reader', 'upc_reader'] },
            });
            const cr = result && result.codeResult;
            return cr && cr.code ? { code: cr.code, format: cr.format } : null;
        } finally {
            this.sink.replaceChildren();
        }
    },
};

// --- Camera choice --------------------------------------------------------------

const CAMERA_STORAGE_KEY = 'libaraxia.scannerCamera';
const CONFIRM_READS = 3;        // identical reads needed before a code is accepted
const DECODE_INTERVAL_MS = 120; // pause between decode attempts

// localStorage can throw (private mode, blocked storage); the picker then
// just doesn't remember.
function loadCameraChoice() {
    try { return localStorage.getItem(CAMERA_STORAGE_KEY) || null; } catch (e) { return null; }
}

function saveCameraChoice(deviceId) {
    try {
        if (deviceId) localStorage.setItem(CAMERA_STORAGE_KEY, deviceId);
        else localStorage.removeItem(CAMERA_STORAGE_KEY);
    } catch (e) { /* not remembered, that's all */ }
}

// The camera to use when the user hasn't picked one.
//
// iPhones list several back cameras: "Back Camera" (main wide), "Back Ultra
// Wide Camera", "Back Telephoto Camera", and virtual "Back Dual Wide /
// Triple Camera" devices. On Pro iPhones the main camera can't focus closer
// than about 20 cm, so a barcode held at scanning distance stays blurred;
// the Ultra Wide is the lens with macro autofocus (it's what the Camera
// app's macro mode switches to). Tested on an iPhone 17 Pro Max: only the
// Ultra Wide read barcodes. So on iOS prefer it, then the plain back camera.
//
// The iOS label is matched exactly: on Android an ultra-wide is often
// fixed-focus, so there the plain back camera ("camera2 0, facing back")
// stays the default. Older non-Pro iPhones may have a fixed-focus Ultra
// Wide too; the camera picker (remembered) covers those.
//
// Returns a deviceId, or null to keep whatever the browser chose (laptops
// with only a front camera end up here).
function preferredBackCamera(devices) {
    const label = d => d.label.trim();
    const iosUltraWide = devices.find(d => /^back ultra wide camera$/i.test(label(d)));
    if (iosUltraWide) return iosUltraWide.deviceId;
    const back = devices.filter(d => /\b(back|rear|environment)\b/i.test(label(d)));
    const plain = back.filter(d => !/ultra|tele|dual|triple|macro|wide angle/i.test(label(d)));
    const exact = plain.find(d => /^back camera$/i.test(label(d)));
    return (exact || plain[0] || null)?.deviceId ?? null;
}

// --- The scanner ------------------------------------------------------------------

function createBarcodeScanner({ container, button, cameraSelect = null, onCode,
                                decoder = quaggaDecoder }) {
    let stream = null;
    let running = false;
    let session = 0;          // bumped on every start/stop, so stale async work bails out
    let video = null;
    let box = null;
    let timer = null;
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d', { willReadFrequently: true });
    const confirmer = createReadConfirmer(CONFIRM_READS);

    function setButton(on) {
        if (!button) return;
        // Keep the icon: only the text node changes.
        const label = [...button.childNodes].reverse().find(n => n.nodeType === Node.TEXT_NODE && n.textContent.trim());
        if (label) label.textContent = on ? ' Stop Scanner ' : ' Start Scanner ';
        button.setAttribute('aria-pressed', String(on));
    }

    // The camera view: the video fills the container (object-fit: cover,
    // so there are no bars), with the target box on top.
    function buildView() {
        video = document.createElement('video');
        video.className = 'scanner-video';
        video.muted = true;
        video.playsInline = true;            // iOS: play in place, not fullscreen
        video.setAttribute('playsinline', '');
        video.setAttribute('aria-label', 'Camera view');
        box = document.createElement('div');
        box.className = 'scanner-box';
        box.setAttribute('aria-hidden', 'true');
        container.replaceChildren(video, box);
        container.classList.add('scanner-live');
    }

    function constraintsFor(deviceId) {
        const v = { width: { ideal: 1280 }, height: { ideal: 720 } };
        if (deviceId) v.deviceId = { exact: deviceId };
        else v.facingMode = { ideal: 'environment' };
        return { audio: false, video: v };
    }

    // Continuous autofocus where the camera offers it (Chrome/Android,
    // recent Safari). Firefox has no getCapabilities; it just isn't asked.
    async function enableAutofocus(track) {
        try {
            const caps = track.getCapabilities ? track.getCapabilities() : {};
            if (caps.focusMode && caps.focusMode.includes('continuous')) {
                await track.applyConstraints({ advanced: [{ focusMode: 'continuous' }] });
            }
        } catch (e) {
            console.debug('Autofocus not applied:', e);
        }
    }

    async function openStream(deviceId) {
        try {
            return await navigator.mediaDevices.getUserMedia(constraintsFor(deviceId));
        } catch (err) {
            // A remembered camera that's gone (other device, unplugged webcam):
            // forget it and let the browser pick.
            if (deviceId && (err.name === 'OverconstrainedError' || err.name === 'NotFoundError')) {
                saveCameraChoice(null);
                return navigator.mediaDevices.getUserMedia(constraintsFor(null));
            }
            throw err;
        }
    }

    // Fill the picker. Labels are only readable once permission is granted,
    // which is why this runs after the stream is open. One camera: no picker.
    async function fillPicker(currentId) {
        if (!cameraSelect) return [];
        const devices = (await navigator.mediaDevices.enumerateDevices())
            .filter(d => d.kind === 'videoinput');
        cameraSelect.replaceChildren(...devices.map((d, i) => {
            const option = document.createElement('option');
            option.value = d.deviceId;
            option.textContent = d.label || `Camera ${i + 1}`;
            option.selected = d.deviceId === currentId;
            return option;
        }));
        const wrapper = cameraSelect.closest('[data-camera-picker]') || cameraSelect;
        wrapper.hidden = devices.length < 2;
        return devices;
    }

    async function start() {
        if (running) return;
        const reason = cameraUnavailableReason();
        if (reason) { showFlashMessage('error', reason); return; }
        if (!decoder.available()) {
            showFlashMessage('error', 'The barcode reader failed to load. Reload the page and try again.');
            return;
        }

        running = true;
        const mySession = ++session;
        setButton(true);
        confirmer.reset();
        buildView();

        try {
            let deviceId = loadCameraChoice();
            stream = await openStream(deviceId);
            if (mySession !== session) { stopTracks(); return; }

            // No saved choice: once labels are readable, switch to the main
            // back camera if the browser opened a different one, and
            // remember it so the next scan opens it straight away.
            const currentId = () => stream.getVideoTracks()[0]?.getSettings().deviceId;
            const devices = await fillPicker(currentId());
            if (mySession !== session) { stopTracks(); return; }
            if (!deviceId) {
                const preferred = preferredBackCamera(devices);
                if (preferred) {
                    saveCameraChoice(preferred);
                    if (preferred !== currentId()) {
                        stopTracks();
                        stream = await openStream(preferred);
                        if (mySession !== session) { stopTracks(); return; }
                    }
                    if (cameraSelect) cameraSelect.value = preferred;
                }
            }

            await enableAutofocus(stream.getVideoTracks()[0]);
            video.srcObject = stream;
            await video.play();
            if (mySession !== session) return;
            scheduleDecode(mySession);
        } catch (err) {
            if (mySession !== session) return;
            console.error('Scanner start failed:', err);
            stop();
            showFlashMessage('error', cameraErrorMessage(err));
        }
    }

    function cameraErrorMessage(err) {
        switch (err && err.name) {
            case 'NotAllowedError':
            case 'SecurityError':
                return 'Camera access was denied. Allow it in the browser settings and try again.';
            case 'NotFoundError':
            case 'OverconstrainedError':
                return 'No camera was found.';
            case 'NotReadableError':
            case 'AbortError':
                return 'The camera is in use by another app.';
            default:
                return 'The camera could not be started.';
        }
    }

    function stopTracks() {
        if (stream) stream.getTracks().forEach(t => t.stop());
        stream = null;
    }

    function stop() {
        session++;
        running = false;
        clearTimeout(timer);
        timer = null;
        stopTracks();
        if (video) {
            video.pause();
            video.srcObject = null;
        }
        container?.classList.remove('scanner-live');
        setButton(false);
    }

    function scheduleDecode(mySession) {
        timer = setTimeout(() => decodeFrame(mySession), DECODE_INTERVAL_MS);
    }

    // Copy the part of the video under the target box onto the canvas.
    // The video is scaled with object-fit: cover, so map the box from page
    // pixels back to video pixels.
    function grabBox() {
        const vw = video.videoWidth, vh = video.videoHeight;
        if (!vw || !vh) return false;
        const view = container.getBoundingClientRect();
        const target = box.getBoundingClientRect();
        const scale = Math.max(view.width / vw, view.height / vh);
        const offsetX = (view.width - vw * scale) / 2;
        const offsetY = (view.height - vh * scale) / 2;
        const sx = Math.max(0, (target.left - view.left - offsetX) / scale);
        const sy = Math.max(0, (target.top - view.top - offsetY) / scale);
        const sw = Math.min(vw - sx, target.width / scale);
        const sh = Math.min(vh - sy, target.height / scale);
        if (sw < 10 || sh < 10) return false;
        canvas.width = Math.round(sw);
        canvas.height = Math.round(sh);
        ctx.drawImage(video, sx, sy, sw, sh, 0, 0, canvas.width, canvas.height);
        return true;
    }

    async function decodeFrame(mySession) {
        if (mySession !== session) return;
        let read = null;
        try {
            if (grabBox()) read = await decoder.decode(canvas);
        } catch (e) {
            console.debug('Decode failed:', e);
        }
        if (mySession !== session) return;

        const code = read && normalizeScannedCode(read.code);
        if (code && confirmer.push(code)) {
            confirmed(code, read);
            return;
        }
        scheduleDecode(mySession);
    }

    function confirmed(code, read) {
        box.classList.add('scanner-box-hit');
        if (navigator.vibrate) navigator.vibrate(80);  // Android; iOS has no vibrate
        stop();
        onCode({ code, raw: read.code, format: read.format });
    }

    // Wiring: button toggles, picker switches camera, and the camera goes
    // off whenever the page is hidden or left.
    if (button) button.addEventListener('click', e => {
        e.preventDefault();
        if (running) stop(); else start();
    });

    if (cameraSelect) cameraSelect.addEventListener('change', () => {
        saveCameraChoice(cameraSelect.value);
        if (running) { stop(); start(); }
    });

    document.addEventListener('visibilitychange', () => {
        if (document.hidden && running) stop();
    });
    window.addEventListener('pagehide', () => { if (running) stop(); });

    return {
        start,
        stop,
        get running() { return running; },
    };
}

// Node (tests) gets the pure helpers; browsers just see the globals above.
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        isValidEan13, isValidUpcA, isValidIsbn10, normalizeScannedCode,
        createReadConfirmer, preferredBackCamera,
    };
}

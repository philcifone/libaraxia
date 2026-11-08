// Do I have this? (templates/have.html): the camera. A confirmed read
// (scanner.js) reloads the page with the code, and the server answers;
// typing works the same way through the plain GET form.
document.addEventListener('DOMContentLoaded', () => {
    const root = document.getElementById('have');
    const view = document.getElementById('interactive');
    const button = document.getElementById('toggle-scanner');
    if (!root || !view || !button || typeof createBarcodeScanner !== 'function') return;

    // The camera box only takes space while the camera is on
    // (and only where a camera can work: scanner.js says why otherwise)
    button.addEventListener('click', () => {
        if (!window.isSecureContext || !navigator.mediaDevices) return;
        view.classList.remove('hidden');
        view.classList.add('flex');
    }, { capture: true });

    createBarcodeScanner({
        container: view,
        button,
        cameraSelect: document.getElementById('camera-select'),
        onCode: ({ code }) => {
            document.getElementById('scan-status').textContent = `Read ${code}, checking...`;
            const url = new URL(root.dataset.checkUrl, window.location.origin);
            url.searchParams.set('q', code);
            window.location.assign(url.pathname + url.search);
        },
    });
});

// Photos on the edit page (templates/_photos_edit.html, ROADMAP 16.0a).
// Picking a file uploads it at once; the gallery's files go one by one, so
// a phone on a slow connection sees "Uploading 2 of 5" rather than one long
// wait, and a bad file stops the run with its reason. Then the page reloads
// at #photos to show them. Without this script each form posts as usual
// (its Upload button, hidden here, does that).

'use strict';

document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('[data-photo-submit]').forEach(b => b.classList.add('hidden'));
});

async function uploadPhotos(input) {
    const form = input.closest('form');
    const status = document.querySelector('[data-photos-status]');
    const files = Array.from(input.files || []);
    if (!files.length) return;

    const say = (text, isError = false) => {
        status.textContent = text;
        status.classList.toggle('text-red-600', isError);
        status.classList.toggle('text-content-secondary', !isError);
    };

    input.disabled = true;
    let added = 0;
    for (const [i, file] of files.entries()) {
        say(files.length > 1 ? `Uploading ${i + 1} of ${files.length}...` : 'Uploading...');
        const body = new FormData();
        body.append('photo', file);
        let data = null;
        try {
            const r = await fetch(form.action, {
                method: 'POST',
                body,
                headers: { 'X-CSRFToken': getCSRFToken(), 'X-Requested-With': 'XMLHttpRequest' },
            });
            data = await r.json().catch(() => null);
            if (!r.ok || !data?.success) {
                say(`${file.name}: ${data?.error || 'the upload failed.'}`, true);
                break;
            }
            added += 1;
        } catch {
            say(`${file.name}: the upload failed (connection).`, true);
            break;
        }
    }
    input.disabled = false;
    input.value = '';
    if (added) {
        // Reload to show them; keep any error on screen a moment first
        const wait = status.classList.contains('text-red-600') ? 2500 : 0;
        setTimeout(() => {
            location.hash = 'photos';
            location.reload();
        }, wait);
    }
}

registerActions({ uploadPhotos });

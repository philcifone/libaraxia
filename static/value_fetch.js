// Fetch value on the edit page (templates/_copy_fields.html, ROADMAP 16.0a).
// Asks /values/fetch with the grade (and Discogs release) now on the form,
// then fills the Value field and its hidden source fields. Nothing is
// stored until Save Changes (utils/copy_fields.py); typing over the value
// makes it yours ("manual") again.

'use strict';

async function fetchValue(button) {
    const $ = id => document.getElementById(id);
    const line = $('value-line');
    const body = new FormData();
    body.append('condition', $('condition')?.value || '');
    if ($('discogs_release')) body.append('discogs_release', $('discogs_release').value);

    button.disabled = true;
    line.textContent = 'Asking...';
    try {
        const r = await fetch(button.dataset.url, {
            method: 'POST', body,
            headers: { 'X-CSRFToken': getCSRFToken(), 'X-Requested-With': 'XMLHttpRequest' },
        });
        const data = await r.json().catch(() => null);
        if (!r.ok || !data?.success) {
            line.textContent = data?.error || 'The fetch failed.';
            return;
        }
        const result = data.result;
        line.textContent = result.message;
        if (result.cents !== null) {
            $('value').value = result.value;
            $('value_source').value = result.source;
            $('value_note').value = result.note;
            $('value_fetched_cents').value = String(result.cents);
            line.textContent += ' Save to keep it.';
        }
        // A release matched by barcode or catalogue number: keep it too
        const release = $('discogs_release');
        if (release && !release.value.trim() && result.release_id) release.value = String(result.release_id);
    } catch {
        line.textContent = 'The fetch failed (connection).';
    } finally {
        button.disabled = false;
    }
}

registerActions({ fetchValue });

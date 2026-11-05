// Helpers shared by every page. Loaded in <head> by templates/base.html,
// before any page script, so everything here is a plain global.
//
//   getCSRFToken()          the page's CSRF token
//   getCSRFHeaders()        fetch headers with the token and a JSON body type
//   addCSRFToFormData(fd)   append the token to a FormData
//   escapeHtml(text)        escape for innerHTML / template literals
//   coverSrc(url)           img src for a cover, remote ones via the server
//   showFlashMessage(category, message, autoDismiss = true)
//   confirmDialog(message, {ok, danger}) -> Promise<boolean>   (styled confirm())
//   confirmSubmit(form, event, message, options)                (confirm in a submit handler)
//   dismissFlash(element)   close the flash message containing element
//   <div data-read-more>    long text clamped with a "Read more" toggle (below)
//   noCoverHtml(title, author, {size, box})  placeholder for a book with no cover

'use strict';

// --- CSRF -------------------------------------------------------------------

// base.html puts the token in <meta name="csrf-token">. A hidden csrf_token
// input is checked first so a form's own token wins if a page has both.
function getCSRFToken() {
    const tokenInput = document.querySelector('input[name="csrf_token"]');
    if (tokenInput) return tokenInput.value;
    const tokenMeta = document.querySelector('meta[name="csrf-token"]');
    if (tokenMeta) return tokenMeta.content;
    console.warn('CSRF token not found');
    return null;
}

function getCSRFHeaders() {
    return {
        'X-CSRFToken': getCSRFToken(),
        'Content-Type': 'application/json',
    };
}

function addCSRFToFormData(formData) {
    const token = getCSRFToken();
    if (token) formData.append('csrf_token', token);
    return formData;
}

// --- Escaping ---------------------------------------------------------------

// Use for anything that goes into innerHTML or a template literal, including
// attribute values (quotes are escaped too).
function escapeHtml(text) {
    return String(text ?? '').replace(/[&<>"']/g, c => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    })[c]);
}

// --- Images -----------------------------------------------------------------

// The src to use for a cover URL. Remote covers (Google Books, Open Library
// search results) go through the server's /books/thumbnail proxy, so the
// browser never contacts those hosts and the CSP can keep img-src 'self'.
function coverSrc(url) {
    if (!url) return '/static/no-cover.svg';
    return /^https?:\/\//i.test(url) ? '/books/thumbnail?url=' + encodeURIComponent(url) : url;
}

// --- Camera -------------------------------------------------------------------

// Why the barcode scanner can't use the camera here, or null if it can.
// Browsers only offer the camera (navigator.mediaDevices) on a secure origin:
// https://, or http://localhost. Plain http:// over the LAN has none, which
// otherwise surfaces as a cryptic "getUserMedia is not defined".
function cameraUnavailableReason() {
    if (!window.isSecureContext) {
        return 'The camera needs a secure connection. Open this site over https:// '
             + '(or on localhost) to scan barcodes, or type the ISBN instead.';
    }
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        return "This browser doesn't offer camera access. Type the ISBN instead.";
    }
    return null;
}

// --- Flash messages ---------------------------------------------------------
// Server-side flashes are rendered by templates/_flash_messages.html; this
// adds the same markup for messages raised from JS, and handles closing.

const FLASH_DISMISS_TIME = 5000; // ms before a message closes itself

function flashBackground(category) {
    // Colours live in styles.css (.flash-*), shared with _flash_messages.html
    if (category === 'success') return 'flash-success';
    if (['danger', 'error', 'warning'].includes(category)) return 'flash-error';
    return 'flash-info';
}

function dismissFlash(element) {
    const flashMessage = element.closest('.flash-message');
    if (!flashMessage) return;
    flashMessage.classList.remove('animate-slide-in');
    flashMessage.classList.add('animate-slide-out');
    setTimeout(() => flashMessage.remove(), 300); // matches the animation
}

function scheduleFlashDismiss(flashMessage) {
    setTimeout(() => {
        if (flashMessage.isConnected) dismissFlash(flashMessage);
    }, FLASH_DISMISS_TIME);
}

function showFlashMessage(category, message, autoDismiss = true) {
    let container = document.getElementById('flash-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'flash-container';
        container.className = 'fixed top-4 inset-x-4 sm:left-auto sm:right-4 z-50 space-y-2 sm:max-w-md';
        document.body.appendChild(container);
    }

    const flashDiv = document.createElement('div');
    flashDiv.className = 'flash-message mb-2 px-4 py-3 rounded-lg '
        + `flex items-start gap-3 animate-slide-in ${flashBackground(category)}`;
    flashDiv.setAttribute('role', 'status');
    flashDiv.innerHTML = `
        <div class="flex-1"></div>
        <button type="button" data-dismiss-flash
                class="flex-shrink-0 opacity-80 hover:opacity-100 transition-opacity"
                aria-label="Close message">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
            </svg>
        </button>`;
    flashDiv.querySelector('.flex-1').textContent = message;
    container.appendChild(flashDiv);

    if (autoDismiss) scheduleFlashDismiss(flashDiv);
}

// One delegated listener instead of an onclick on every close button, so the
// markup needs no inline handlers (a CSP without 'unsafe-inline' forbids them).
document.addEventListener('click', event => {
    const button = event.target.closest('[data-dismiss-flash]');
    if (button) dismissFlash(button);
});

document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.flash-message').forEach(scheduleFlashDismiss);
});

// --- Declarative event handlers -----------------------------------------------
// Replaces inline onclick=/onchange=/onsubmit= attributes, which a
// Content-Security-Policy without 'unsafe-inline' refuses to run.
//
//   <form data-confirm="Delete this?">        ask (styled dialog) before submitting
//   <button data-confirm="Sure?">             ask before the click acts
//     optional data-confirm-ok="Delete" (button label) and
//     data-confirm-danger="true|false" (red button; guessed from the wording)
//   <button data-click="saveBio">             calls the registered saveBio
//   <input data-change="uploadAvatar">        ... on change
//   <form data-submit="startSearch">          ... on submit
//   <img data-fallback-src="/static/x.svg">   swapped in if the image fails
//
// A handler is called as handler(element, event); arguments it needs come from
// the element's data- attributes. Page scripts register their handlers with
// registerActions({ name: fn, ... }). Names are looked up in that registry
// only, never evaluated, so markup can't call arbitrary functions.

const pageActions = Object.create(null);

// Built-in actions any page can use without a script of its own.
//   <button data-click="toggleHidden" data-target="panel-id">
//   <button data-click="showModal" data-target="dialog-id">
pageActions.toggleHidden = el => document.getElementById(el.dataset.target)?.classList.toggle('hidden');
pageActions.showModal = el => document.getElementById(el.dataset.target)?.showModal();

// Submit a POST form built on the fly (for a button that isn't inside a form).
// fields: {name: value}; the CSRF token is added.
function postForm(action, fields = {}) {
    const form = document.createElement('form');
    form.method = 'POST';
    form.action = action;
    for (const [name, value] of Object.entries({ csrf_token: getCSRFToken(), ...fields })) {
        const input = document.createElement('input');
        input.type = 'hidden';
        input.name = name;
        input.value = value ?? '';
        form.appendChild(input);
    }
    document.body.appendChild(form);
    form.submit();
}

function registerActions(actions) {
    Object.assign(pageActions, actions);
}

function runAction(element, attribute, event) {
    const name = element.dataset[attribute];
    const action = pageActions[name];
    if (!action) {
        console.error(`No action registered for data-${attribute}="${name}"`);
        return;
    }
    action(element, event);
}

// --- Styled confirm --------------------------------------------------------------
// A replacement for window.confirm(): a native <dialog> (focus moves into it,
// Esc cancels) styled as a card. Resolves true for OK, false otherwise.
//
//   if (!await confirmDialog('Remove this?')) return;
//
// Destructive wording (delete, remove, leave, ...) gets a red OK button with
// focus on Cancel; pass {danger: false} or {ok: 'Label'} to override.
const DANGER_WORDS = /\b(delete|remove|leave|stop|erase|cannot be undone)\b/i;

function confirmDialog(message, { ok = 'OK', danger = DANGER_WORDS.test(message) } = {}) {
    let dialog = document.getElementById('confirm-dialog');
    if (!dialog) {
        dialog = document.createElement('dialog');
        dialog.id = 'confirm-dialog';
        dialog.className = 'confirm-dialog card bg-secondary text-content-primary rounded-lg';
        dialog.innerHTML = `
            <form method="dialog" class="p-5 space-y-5">
                <p class="confirm-message whitespace-pre-line"></p>
                <div class="flex justify-end gap-3">
                    <button value="cancel" class="confirm-cancel px-4 py-2 bg-primary hover:bg-primary-hover text-content-primary rounded-lg btn btn-outline">Cancel</button>
                    <button value="ok" class="confirm-ok px-4 py-2 text-on-accent rounded-lg btn"></button>
                </div>
            </form>`;
        document.body.appendChild(dialog);
    }
    dialog.querySelector('.confirm-message').textContent = message;
    const okButton = dialog.querySelector('.confirm-ok');
    okButton.textContent = ok;
    okButton.classList.toggle('bg-red-600', danger);
    okButton.classList.toggle('hover:bg-red-700', danger);
    okButton.classList.toggle('bg-accent', !danger);
    okButton.classList.toggle('hover:bg-accent-hover', !danger);

    dialog.returnValue = '';
    dialog.showModal();
    (danger ? dialog.querySelector('.confirm-cancel') : okButton).focus();
    return new Promise(resolve => {
        dialog.addEventListener('close', () => resolve(dialog.returnValue === 'ok'), { once: true });
    });
}

function confirmOptions(el) {
    const options = {};
    if (el.dataset.confirmOk) options.ok = el.dataset.confirmOk;
    if (el.dataset.confirmDanger) options.danger = el.dataset.confirmDanger === 'true';
    return options;
}

// For a submit handler that must ask first. The dialog can't block the way
// confirm() did, so the first submit is stopped; on OK the form is submitted
// again (requestSubmit keeps the clicked button's name/value and runs the
// handlers again), and that second pass is let through. Returns true on the
// second pass, false while asking.
//
//   form.addEventListener('submit', e => { if (!confirmSubmit(form, e, 'Sure?')) return; ... });
function confirmSubmit(form, event, message, options = {}) {
    if (form.dataset.confirmed) {
        delete form.dataset.confirmed;
        return true;
    }
    event.preventDefault();
    event.stopImmediatePropagation();
    const submitter = event.submitter;
    confirmDialog(message, options).then(ok => {
        if (!ok) return;
        form.dataset.confirmed = '1';
        if (submitter && submitter.form === form) form.requestSubmit(submitter);
        else form.requestSubmit();
    });
    return false;
}

// data-confirm runs in the capture phase, before any other click/submit
// handler, so a cancelled confirmation stops everything that would follow.
// A confirmed click is replayed with el.click() and let through.
document.addEventListener('click', event => {
    const el = event.target.closest('[data-confirm]');
    if (!el || el.tagName === 'FORM') return;
    if (el.dataset.confirmed) {
        delete el.dataset.confirmed;
        return;
    }
    event.preventDefault();
    event.stopImmediatePropagation();
    confirmDialog(el.dataset.confirm, confirmOptions(el)).then(ok => {
        if (!ok) return;
        el.dataset.confirmed = '1';
        el.click();
    });
}, true);

document.addEventListener('submit', event => {
    const form = event.target;
    if (form.dataset.confirm === undefined) return;
    confirmSubmit(form, event, form.dataset.confirm, confirmOptions(form));
}, true);

document.addEventListener('click', event => {
    const el = event.target.closest('[data-click]');
    if (el) runAction(el, 'click', event);
});

document.addEventListener('change', event => {
    const el = event.target.closest('[data-change]');
    if (el) runAction(el, 'change', event);
});

document.addEventListener('submit', event => {
    if (event.target.dataset.submit) runAction(event.target, 'submit', event);
});

// Image load errors don't bubble, but they can be caught on the way down.
document.addEventListener('error', event => {
    const img = event.target;
    if (img.tagName !== 'IMG') return;
    if (img.dataset.fallbackSrc && !img.dataset.fellBack) {
        img.dataset.fellBack = '1';   // only once, in case the fallback fails too
        img.src = img.dataset.fallbackSrc;
        return;
    }
    img.dataset.loaded = '1';         // stop the skeleton shimmer either way
}, true);

// Grid covers shimmer until loaded (img.book-cover-img in styles.css). Load
// doesn't bubble either; this listener is in place before any <img> exists,
// since common.js loads in <head>.
document.addEventListener('load', event => {
    if (event.target.tagName === 'IMG') event.target.dataset.loaded = '1';
}, true);

// --- No cover -----------------------------------------------------------------
// The JS twin of templates/_no_cover.html (keep the two in step): a plain
// binding with the title on it, for cards built in script.
function noCoverHtml(title, author, { size = 'md', box = 'w-full h-full' } = {}) {
    const titleHtml = title ? `<span class="no-cover-title">${escapeHtml(title)}</span>` : '';
    const authorHtml = title && author && size !== 'sm'
        ? `<span class="no-cover-author">${escapeHtml(author)}</span>` : '';
    return `<div class="no-cover no-cover-${size} ${box}" aria-hidden="true">${titleHtml}${authorHtml}</div>`;
}

// --- Read more ---------------------------------------------------------------
// Long text (book descriptions, reviews) is clamped to a few lines with a
// fade, and a "Read more" button opens it. The button is only shown when the
// text really overflows, so short reviews don't get a useless toggle.
//
//   <div data-read-more>
//     <div class="read-more-text">...</div>
//     <button type="button" class="read-more-toggle" data-click="toggleReadMore"
//             aria-expanded="false" hidden>Read more</button>
//   </div>
//
// The height is animated by setting max-height to the measured scrollHeight
// (you can't transition to "none"), then dropping the limit once it's open so
// a later resize doesn't cut the text off.
function initReadMore(root = document) {
    root.querySelectorAll('[data-read-more]').forEach(box => {
        const text = box.querySelector('.read-more-text');
        const toggle = box.querySelector('.read-more-toggle');
        if (!text || !toggle || box.dataset.expanded) return;
        const clipped = text.scrollHeight > text.clientHeight + 2;
        text.classList.toggle('is-clipped', clipped);
        toggle.hidden = !clipped;
    });
}

function toggleReadMore(toggle) {
    const box = toggle.closest('[data-read-more]');
    const text = box.querySelector('.read-more-text');
    const opening = !box.dataset.expanded;

    text.style.maxHeight = text.scrollHeight + 'px';
    if (opening) {
        box.dataset.expanded = '1';
        text.classList.remove('is-clipped');
        const unclamp = () => { if (box.dataset.expanded) text.style.maxHeight = 'none'; };
        // No transition with reduced motion, so no transitionend either.
        if (matchMedia('(prefers-reduced-motion: reduce)').matches) unclamp();
        else text.addEventListener('transitionend', unclamp, { once: true });
    } else {
        delete box.dataset.expanded;
        void text.offsetHeight;          // commit the pixel height before shrinking
        text.style.maxHeight = '';       // back to the CSS clamp
        text.classList.add('is-clipped');
    }
    toggle.setAttribute('aria-expanded', String(opening));
    toggle.textContent = opening ? 'Show less' : 'Read more';
}

registerActions({ toggleReadMore: el => toggleReadMore(el) });
document.addEventListener('DOMContentLoaded', () => initReadMore());
// Web fonts can change line breaks after DOMContentLoaded; measure again.
window.addEventListener('load', () => initReadMore());

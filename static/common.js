// Helpers shared by every page. Loaded in <head> by templates/base.html,
// before any page script, so everything here is a plain global.
//
//   getCSRFToken()          the page's CSRF token
//   getCSRFHeaders()        fetch headers with the token and a JSON body type
//   addCSRFToFormData(fd)   append the token to a FormData
//   escapeHtml(text)        escape for innerHTML / template literals
//   coverSrc(url)           img src for a cover, remote ones via the server
//   showFlashMessage(category, message, autoDismiss = true)
//   dismissFlash(element)   close the flash message containing element

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
    if (category === 'success') return 'bg-green-500';
    if (['danger', 'error', 'warning'].includes(category)) return 'bg-red-500';
    return 'bg-primary';
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
        container.className = 'fixed top-4 right-4 z-50 space-y-2 max-w-md';
        document.body.appendChild(container);
    }

    const flashDiv = document.createElement('div');
    flashDiv.className = 'flash-message mb-2 px-4 py-3 rounded-lg shadow-lg text-white '
        + `flex items-start gap-3 animate-slide-in ${flashBackground(category)}`;
    flashDiv.setAttribute('role', 'status');
    flashDiv.innerHTML = `
        <div class="flex-1"></div>
        <button type="button" data-dismiss-flash
                class="flex-shrink-0 text-white hover:text-content-secondary transition-colors focus:outline-none"
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
//   <form data-confirm="Delete this?">        confirm() before submitting
//   <button data-confirm="Sure?">             confirm() before the click acts
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

// Confirmation runs in the capture phase, before any other click/submit
// handler, so a cancelled confirm stops everything that would follow.
document.addEventListener('click', event => {
    const el = event.target.closest('[data-confirm]');
    if (el && el.tagName !== 'FORM' && !confirm(el.dataset.confirm)) {
        event.preventDefault();
        event.stopImmediatePropagation();
    }
}, true);

document.addEventListener('submit', event => {
    const form = event.target;
    if (form.dataset.confirm !== undefined && !confirm(form.dataset.confirm)) {
        event.preventDefault();
        event.stopImmediatePropagation();
    }
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
    if (img.tagName === 'IMG' && img.dataset.fallbackSrc && !img.dataset.fellBack) {
        img.dataset.fellBack = '1';   // only once, in case the fallback fails too
        img.src = img.dataset.fallbackSrc;
    }
}, true);

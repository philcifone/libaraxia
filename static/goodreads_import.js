// Goodreads upload page (templates/goodreads_import.html). The form posts
// the file as is (it works without this script); this only says it's busy
// and stops a second press while a large file uploads. The review and the
// result are static/goodreads_review.js.

'use strict';

// data-submit runs before the browser's own submit, which goes ahead
function goodreadsUploading(form) {
    form.querySelectorAll('button[type="submit"]').forEach(b => {
        b.disabled = true;
        b.classList.add('opacity-50');
    });
    document.getElementById('goodreads-uploading').hidden = false;
}

registerActions({ goodreadsUploading });

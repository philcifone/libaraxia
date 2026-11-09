// The add page for every media type (templates/add_item.html): Add Book,
// Add Movie and Add Album. Shared helpers (escapeHtml, coverSrc, getCSRFHeaders,
// showFlashMessage) are in common.js; the camera is scanner.js.
//
// Three ways to fill the form, one tab each: Search (pick a result), the
// code box (ISBN / barcode, with its Look up button beside it) and Scan.
// Music has all three (barcodes since 8B.12). What differs by type (which
// endpoints, how their answers map onto the form's fields) lives in the
// three adapters, BOOK, MOVIE and RECORD, below; the rest is shared.
//
// A lookup only pre-fills. It never overwrites what you typed: each field
// remembers the value a lookup put in (data-filled), and only an empty field
// or one still holding a lookup's value is replaced by the next lookup. So
// picking a second search result replaces the first, but a title you
// corrected by hand stays.

'use strict';

document.addEventListener('DOMContentLoaded', () => {
    const root = document.getElementById('add-item');
    if (!root) return;

    const $ = id => document.getElementById(id);
    const enc = encodeURIComponent;
    const statusLine = $('lookup-status');
    const codeInput = $('code-input');
    const form = $('item-form');

    // Where a code of the other type goes (a movie barcode on Add Book, or
    // on the wishlist's Add Book), with the code attached
    function otherAddUrl(params = {}, base = root.dataset.otherAddUrl) {
        const url = new URL(base || '/', window.location.origin);
        for (const [key, value] of Object.entries(params)) url.searchParams.set(key, value);
        return url.pathname + url.search;
    }

    // Add Book with a barcode that isn't an ISBN: a movie or an album, and
    // only you know which. Both links carry the code.
    function notABook(code) {
        const link = (url, label) => `<a class="underline" href="${escapeHtml(url)}">${label}</a>`;
        const movie = link(otherAddUrl({ barcode: code }), 'Add it as a movie');
        const music = root.dataset.musicAddUrl
            ? ' or ' + link(otherAddUrl({ barcode: code }, root.dataset.musicAddUrl), 'as an album') : '';
        setStatus(`${escapeHtml(code)} isn't an ISBN, so it's not a book. ${movie}${music}.`, true);
        return null;
    }

    function setStatus(text, html = false) {
        if (!statusLine) return;
        if (html) statusLine.innerHTML = text; else statusLine.textContent = text;
    }

    async function getJSON(url, options) {
        const response = await fetch(url, options);
        let data = {};
        try { data = await response.json(); } catch (e) { /* not JSON: an error page */ }
        if (!response.ok && !data.error) {
            data.error = response.status === 429
                ? 'Too many lookups for now. Try again later, or fill the form in by hand.'
                : 'The lookup failed. Fill the form in by hand.';
        }
        return data;
    }

    // A match you have as "not owned" (read, watched or listened to, never
    // had): bought it now? Its page has "I own it now", which keeps your review
    const NOT_OWNED_NOTE = 'not owned (if you\'ve bought it, open it and choose "I own it now")';

    // --- Filling the form ----------------------------------------------------

    // Put a lookup's value in a field, unless you typed something there.
    function setField(id, value) {
        const el = $(id);
        if (!el || value === undefined || value === null || String(value).trim() === '') return false;
        const current = el.value.trim();
        if (current && current !== el.dataset.filled) return false;     // yours: keep it
        el.value = value;
        el.dataset.filled = String(value).trim();
        return true;
    }

    // A cover the server saved for us (uploads/...), or only a remote
    // thumbnail to preview. A chosen file or a cover from the server-rendered
    // page wins.
    function setCover(savedPath, remoteUrl) {
        const hidden = $('existing_cover_url');
        const preview = $('cover-preview');
        const file = $('image');
        if (!preview || (file && file.files.length)) return false;
        if (hidden && hidden.value && hidden.value !== hidden.dataset.filled) return false;
        let src = null;
        if (savedPath) {
            src = `/static/${encodeURI(savedPath)}`;
            if (hidden) { hidden.value = savedPath; hidden.dataset.filled = savedPath; }
        } else if (remoteUrl) {
            src = coverSrc(remoteUrl);
        }
        if (!src) return false;
        preview.innerHTML = `<img src="${escapeHtml(src)}" alt="Cover" data-fallback-src="/static/no-cover.svg" class="max-w-[12rem] rounded-lg">`;
        return true;
    }

    // Apply a lookup result: {fields: {id: value}, cover, remoteCover}.
    // Returns how many fields changed.
    function apply(result) {
        let n = 0;
        for (const [id, value] of Object.entries(result.fields || {})) {
            if (setField(id, value)) n++;
        }
        if (setCover(result.cover, result.remoteCover)) n++;
        return n;
    }

    function filledMessage(n, sources) {
        const from = sources && sources.length ? ` from ${sources.join(' and ')}` : '';
        if (!n) return `Found${from}, but every field already has something in it: nothing changed.`;
        return `Filled in ${n} field${n === 1 ? '' : 's'}${from}. Check them before adding.`;
    }

    // --- The two media types ---------------------------------------------------

    const BOOK = {
        searchUrl: q => `/books/search_books?q=${enc(q)}`,

        results(data) {
            if (data.error) throw new Error(data.error);
            return (data.items || []).map(item => {
                const v = item.volumeInfo || item;
                const ids = v.industryIdentifiers || [];
                const isbn = (ids.find(i => i.type === 'ISBN_13') || ids.find(i => i.type === 'ISBN_10') || {}).identifier || '';
                // As given (zoom=1, 128 px): without the zoom Google answers its
                // "image not available" banner for any book it hasn't scanned
                const thumb = v.imageLinks && v.imageLinks.thumbnail
                    ? v.imageLinks.thumbnail.replace('http:', 'https:').replace('&edge=curl', '')
                    : null;
                const year = v.publishedDate ? v.publishedDate.split('-')[0] : '';
                const authors = v.authors ? v.authors.join(', ') : '';
                return {
                    title: v.title || 'Unknown title',
                    line: [authors, year].filter(Boolean).join(', '),
                    thumb,
                    data: {
                        title: v.title, subtitle: v.subtitle || '', author: authors,
                        publisher: v.publisher || '', publishedDate: year,
                        pageCount: v.pageCount || '', description: v.description || '',
                        genre: v.categories ? v.categories.join(', ') : '', isbn,
                        thumbnail: v.imageLinks ? v.imageLinks.thumbnail : null,
                    },
                };
            });
        },

        // The server downloads the cover and tidies the fields
        async pick(result) {
            const data = await getJSON('/books/select_search_result', {
                method: 'POST', headers: getCSRFHeaders(),
                body: JSON.stringify({ bookData: result.data }),
            });
            if (!data.success) throw new Error(data.error || "Couldn't fetch that book.");
            return BOOK.form(data.book_details);
        },

        async code(code) {
            // A UPC/EAN that isn't an ISBN: a movie or an album
            if (classifyCode(code) === 'video') return notABook(code);
            const data = await getJSON(`/books/fetch_barcode_details?code=${enc(code)}`);
            if (data.media_type === 'video') return notABook(data.barcode || code);
            if (!data.success || !data.book_details) {
                return { notFound: `No book found for ISBN ${code}. Fill the form in by hand.` };
            }
            return BOOK.form(data.book_details);
        },

        form(d) {
            return {
                fields: {
                    title: d.title, subtitle: d.subtitle, author: d.author, isbn: d.isbn,
                    publisher: d.publisher, genre: d.genre, description: d.description,
                    year: d.year || d.publishedDate, page_count: d.page_count || d.pageCount || '',
                },
                cover: d.local_cover_url || null,
                remoteCover: d.local_cover_url ? null : (d.thumbnail_url || d.thumbnail || null),
                sources: d.source ? [d.source] : [],
            };
        },

        async duplicates() {
            const data = await getJSON('/books/check_duplicates', {
                method: 'POST', headers: getCSRFHeaders(),
                body: JSON.stringify({ title: $('title').value, author: $('author').value, isbn: $('isbn').value }),
            });
            return (data.duplicates || []).map(d => {
                const where = [];
                if (d.in_library) {
                    where.push(d.not_owned ? NOT_OWNED_NOTE
                        : d.removed ? 'removed from the library' : 'in the library');
                }
                if (d.in_wishlist) where.push('on your wishlist');
                return {
                    title: d.title, url: d.in_library ? `/books/book/${enc(d.id)}` : null,
                    note: [d.author, where.join(' and ')].filter(Boolean).join(', '),
                };
            });
        },
        duplicateHeading: 'Already on your household\'s shelf or your wishlist:',
        // add_book refuses a copy already on the shelf until "Add it anyway"
        // is ticked; a wishlist match is only a heads-up
        duplicateNote: 'If it\'s already on the shelf, adding it again will ask you to confirm it\'s a second copy.',
    };

    const MOVIE = {
        searchUrl: q => `/videos/search?q=${enc(q)}`,

        results(data) {
            if (!data.success) throw new Error(data.error || 'The search failed.');
            return (data.results || []).map(r => ({
                title: r.title, line: r.year ? String(r.year) : '', thumb: r.poster, id: r.id,
            }));
        },

        // TMDb's API terms require this notice wherever their data is used
        credit(data) {
            return data.success
                ? 'This product uses the <a class="underline hover:text-accent" href="https://www.themoviedb.org/" rel="noopener">TMDB</a> API but is not endorsed or certified by TMDB.'
                : '';
        },

        async pick(result) {
            return MOVIE.form(await getJSON(`/videos/lookup?tmdb_id=${enc(result.id)}`));
        },

        async code(code) {
            if (classifyCode(code) === 'book') {
                setStatus(`${escapeHtml(code)} is an ISBN: that's a book. <a class="underline" href="${escapeHtml(otherAddUrl())}">Add it as a book</a>.`, true);
                return null;
            }
            setField('barcode', code);
            const data = await getJSON(`/videos/lookup?barcode=${enc(code)}`);
            if (data.success && !data.found) {
                return { notFound: `Nothing found for barcode ${code}${data.tmdb ? ': try searching by title' : ''}. Fill in the rest from the box.` };
            }
            return MOVIE.form(data);
        },

        form(data) {
            if (!data.success) throw new Error(data.error || 'The lookup failed.');
            const d = data.details || {};
            return {
                fields: {
                    title: d.title, author: d.author, publisher: d.publisher, year: d.year,
                    runtime_minutes: d.runtime_minutes, genre: d.genre, description: d.description,
                },
                cover: data.cover || null,
                sources: data.sources || [],
            };
        },

        async duplicates() {
            const data = await getJSON('/videos/check_duplicates', {
                method: 'POST', headers: getCSRFHeaders(),
                body: JSON.stringify({ barcode: $('barcode').value, title: $('title').value }),
            });
            return (data.duplicates || []).map(d => ({
                title: d.title, url: `/videos/${enc(d.id)}`,
                note: [d.format_label, `${d.owner || 'no owner'}'s`, d.not_owned ? NOT_OWNED_NOTE : '',
                       d.removed ? 'removed' : '',
                       `same ${d.match_reason.join(' and ')}`].filter(Boolean).join(', '),
            }));
        },
        duplicateHeading: 'Already on your household\'s shelf:',
        // add_video refuses a duplicate until "Add it anyway" is ticked
        duplicateNote: 'Adding it again will ask you to confirm it\'s a second copy.',
    };

    const RECORD = {
        // The format choice beside the search box (Any / Vinyl / CD / Cassette)
        searchUrl: q => `/records/search?q=${enc(q)}&format=${enc($('search-format')?.value || '')}`,

        // One row per pressing: label, cat. no., year and country tell them apart
        results(data) {
            if (!data.success) throw new Error(data.error || 'The search failed.');
            return (data.results || []).map(r => ({
                title: r.title,
                line: [r.artist, r.year, r.country].filter(Boolean).join(', '),
                line2: [r.format_label, r.label, r.catalog_number].filter(Boolean).join(' \u00b7 '),
                thumb: r.thumb, id: r.id, source: r.source,
            }));
        },

        // Discogs' API terms ask for attribution under their data. Fixed
        // markup, no data in it.
        credit(data) {
            return data.source === 'discogs'
                ? 'Data provided by <a class="underline hover:text-accent" href="https://www.discogs.com/" rel="noopener">Discogs</a>.'
                : '';
        },

        async pick(result) {
            // Discogs ids are numbers, MusicBrainz ids UUIDs: each to its own lookup
            const param = result.source === 'discogs' ? 'discogs' : 'mbid';
            const data = await getJSON(`/records/lookup?${param}=${enc(result.id)}`);
            if (data.success && !data.found) return { notFound: 'Nothing more on that one. Fill the form in by hand.' };
            return RECORD.form(data);
        },

        // Barcode tab and scanner (8B.12): Discogs, then MusicBrainz, server side
        async code(code) {
            if (classifyCode(code) === 'book') {
                setStatus(`${escapeHtml(code)} is an ISBN: that's a book. <a class="underline" href="${escapeHtml(otherAddUrl())}">Add it as a book</a>.`, true);
                return null;
            }
            setField('barcode', code);
            const data = await getJSON(`/records/lookup?barcode=${enc(code)}`);
            if (data.success && !data.found) {
                return { notFound: `Nothing found for barcode ${code}: try searching by artist and title, or fill it in from the sleeve.` };
            }
            return RECORD.form(data);
        },

        form(data) {
            if (!data.success) throw new Error(data.error || 'The lookup failed.');
            const d = data.details || {};
            return {
                fields: {
                    title: d.title, subtitle: d.subtitle, author: d.author, publisher: d.publisher,
                    catalog_number: d.catalog_number, year: d.year, runtime_minutes: d.runtime_minutes,
                    format: d.format, genre: d.genre, description: d.description,
                },
                cover: data.cover || null,
                sources: data.sources || [],
            };
        },

        async duplicates() {
            const data = await getJSON('/records/check_duplicates', {
                method: 'POST', headers: getCSRFHeaders(),
                body: JSON.stringify({ title: $('title').value, author: $('author').value,
                                       catalog_number: $('catalog_number').value,
                                       barcode: $('barcode')?.value || '' }),
            });
            return (data.duplicates || []).map(d => ({
                title: d.title, url: d.url,
                note: [d.author, d.format_label, `${d.owner || 'no owner'}'s`,
                       d.not_owned ? NOT_OWNED_NOTE : '', d.removed ? 'removed' : '',
                       `same ${d.match_reason.join(' and ')}`].filter(Boolean).join(', '),
            }));
        },
        duplicateHeading: 'Already on your household\'s shelf:',
        duplicateNote: 'Adding it again will ask you to confirm it\'s a second copy.',
    };

    const type = { book: BOOK, video: MOVIE, record: RECORD }[root.dataset.type] || BOOK;

    // The format picker starts on a default, not on something you chose, so
    // a picked release may set it (setField keeps what you changed yourself)
    const formatSelect = $('format');
    if (formatSelect && type === RECORD) formatSelect.dataset.filled = formatSelect.value;

    // Books (8B.2): an audiobook is usually borrowed or streamed, so picking
    // Audiobook ticks "I don't own this", and back to Book unticks it. Once
    // you've clicked the box yourself, it's yours and the format leaves it be.
    const notOwnedBox = $('not_owned');
    if (formatSelect && notOwnedBox && type === BOOK) {
        notOwnedBox.addEventListener('change', () => { notOwnedBox.dataset.touched = '1'; });
        formatSelect.addEventListener('change', () => {
            if (!notOwnedBox.dataset.touched) notOwnedBox.checked = formatSelect.value === 'Audiobook';
        });
    }

    // --- Duplicates: a notice above the form, never a blocking dialog --------

    async function showDuplicates() {
        const box = $('duplicate-notice');
        if (!box) return;
        let dups = [];
        try { dups = await type.duplicates(); } catch (e) { console.error('Duplicate check failed', e); }
        if (!dups.length) { box.classList.add('hidden'); box.innerHTML = ''; return; }
        const items = dups.map(d => {
            const title = d.url
                ? `<a class="underline hover:text-accent" href="${escapeHtml(d.url)}">${escapeHtml(d.title)}</a>`
                : escapeHtml(d.title);
            return `<li>${title}${d.note ? ', ' + escapeHtml(d.note) : ''}</li>`;
        }).join('');
        box.innerHTML = `<p class="font-bold text-content-primary">${escapeHtml(type.duplicateHeading)}</p>
                         <ul class="list-disc pl-5 text-content-primary">${items}</ul>
                         <p class="text-content-secondary">${escapeHtml(type.duplicateNote)}</p>`;
        box.classList.remove('hidden');
    }

    // One lookup at a time; a newer one makes an older answer stale
    let lookupSeq = 0;

    async function runLookup(label, getResult) {
        const mine = ++lookupSeq;
        setStatus(label);
        try {
            const result = await getResult();
            if (mine !== lookupSeq || !result) return;
            if (result.notFound) { setStatus(result.notFound); return; }
            setStatus(filledMessage(apply(result), result.sources));
            await showDuplicates();
            form?.scrollIntoView({ behavior: 'smooth', block: 'start' });
        } catch (err) {
            if (mine !== lookupSeq) return;
            console.error('Lookup failed', err);
            setStatus(err.message || 'The lookup failed. Fill the form in by hand.');
        }
    }

    // --- Tabs ------------------------------------------------------------------

    const tabs = root.querySelectorAll('.search-method-btn');
    const sections = root.querySelectorAll('.search-method-content');
    let scanner = null;

    function showTab(method) {
        tabs.forEach(t => t.dataset.active = String(t.dataset.method === method));
        sections.forEach(s => s.classList.toggle('hidden', s.dataset.method !== method));
        if (method !== 'scan') scanner?.stop();
        if (method === 'search') $('search-input')?.focus();
        if (method === 'code') codeInput?.focus();
    }
    tabs.forEach(t => t.addEventListener('click', () => showTab(t.dataset.method)));

    // --- Search ------------------------------------------------------------------

    const resultsBox = $('search-results');
    let results = [];

    function showResults(list) {
        results = list;
        if (!list.length) {
            resultsBox.innerHTML = '<p class="md:col-span-2 text-center py-4 text-content-secondary">Nothing found. Try fewer words, or fill the form in by hand.</p>';
            return;
        }
        resultsBox.innerHTML = list.map((r, i) => `
            <div class="flex gap-4 p-3 bg-primary border border-card rounded-lg">
                <img src="${escapeHtml(r.thumb ? coverSrc(r.thumb) : '/static/no-cover.svg')}" alt=""
                     data-fallback-src="/static/no-cover.svg" class="w-16 h-24 object-cover rounded shrink-0">
                <div class="flex-1 min-w-0 flex flex-col">
                    <p class="font-medium text-content-primary line-clamp-2">${escapeHtml(r.title)}</p>
                    <p class="text-sm text-content-secondary truncate">${escapeHtml(r.line)}</p>
                    ${r.line2 ? `<p class="text-sm text-content-secondary line-clamp-2">${escapeHtml(r.line2)}</p>` : ''}
                    <button type="button" data-pick="${i}"
                            class="mt-auto self-start px-3 py-1.5 text-sm bg-accent hover:bg-accent-hover text-on-accent rounded-lg btn">Use this</button>
                </div>
            </div>`).join('');
    }

    $('search-form')?.addEventListener('submit', async event => {
        event.preventDefault();
        const query = $('search-input').value.trim();
        if (query.length < 2) { setStatus('Type at least two letters.'); return; }
        setStatus('Searching...');
        resultsBox.innerHTML = '';
        try {
            const data = await getJSON(type.searchUrl(query));
            showResults(type.results(data));
            // A source's credit line (Discogs), else clear the status
            setStatus(type.credit ? type.credit(data) : '', true);
        } catch (err) {
            console.error('Search failed', err);
            setStatus(err.message || 'The search failed. Try again.');
        }
    });

    resultsBox?.addEventListener('click', event => {
        const button = event.target.closest('[data-pick]');
        if (!button) return;
        const result = results[Number(button.dataset.pick)];
        if (result) runLookup(`Fetching "${result.title}"...`, () => type.pick(result));
    });

    // --- Code box ------------------------------------------------------------

    function lookUpCode(code) {
        code = (code || '').trim();
        if (!code) { setStatus('Type the code first.'); return; }
        runLookup('Looking it up...', () => type.code(code));
    }

    // Without this the box posts as a plain form (the no-JS fallback)
    $('code-form')?.addEventListener('submit', event => {
        event.preventDefault();
        lookUpCode(codeInput.value);
    });

    // --- Scan ----------------------------------------------------------------

    if ($('interactive')) {
        scanner = createBarcodeScanner({
            container: $('interactive'),
            button: $('toggle-scanner'),
            cameraSelect: $('camera-select'),
            onCode: ({ code }) => {
                if (codeInput) codeInput.value = code;
                lookUpCode(code);
            },
        });
    }

    // --- Cover upload preview ----------------------------------------------------

    $('image')?.addEventListener('change', event => {
        const file = event.target.files[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = e => {
            $('cover-preview').innerHTML = `<img src="${escapeHtml(e.target.result)}" alt="Cover" class="max-w-[12rem] rounded-lg">`;
        };
        reader.readAsDataURL(file);
    });

    // Arrived with a code in the URL (a tape scanned on Add Book, a miss on
    // Do I have this?) and nothing typed yet: look it up
    if (codeInput && codeInput.value.trim() && !$('title').value.trim() && root.dataset.autoLookup) {
        lookUpCode(codeInput.value);
    }
});

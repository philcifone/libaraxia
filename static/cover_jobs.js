// Floating progress panel for background cover fetching.
//
// The panel markup is in templates/_sidebar.html with the user's current job
// (or null) in data-job, rendered by the context processor in app.py. While a
// job runs we poll /covers/status; once it's finished the panel shows the
// result until dismissed. Pages that start a job call coverJobs.track(job).
//
// Two view toggles, remembered per browser (localStorage, best effort):
//   (i)  shows/hides the details card (open by default)
//   [-]  collapses the whole panel down to a [+] button
// The x button stops a running job, or dismisses a finished one.
(function () {
    const panel = document.getElementById('cover-job-panel');
    if (!panel) return;

    const POLL_MS = 4000;
    const STORE_KEY = 'coverJobPanel';
    const part = name => panel.querySelector(`[data-role="${name}"]`);
    let job = null;
    let timer = null;

    // ---- view state (not job state): survives page loads in this browser
    function loadView() {
        try {
            const saved = JSON.parse(localStorage.getItem(STORE_KEY) || '{}');
            return {infoOpen: saved.infoOpen !== false, collapsed: saved.collapsed === true};
        } catch (e) {
            return {infoOpen: true, collapsed: false};
        }
    }
    const view = loadView();
    function saveView() {
        try { localStorage.setItem(STORE_KEY, JSON.stringify(view)); } catch (e) { /* private mode etc. */ }
    }

    function post(url) {
        const form = new FormData();
        form.append('csrf_token', panel.dataset.csrf);
        return fetch(url, {method: 'POST', body: form, headers: {'X-Requested-With': 'XMLHttpRequest'}})
            .then(r => r.json());
    }

    function renderView() {
        part('body').classList.toggle('hidden', view.collapsed);
        part('info').classList.toggle('hidden', view.collapsed || !view.infoOpen);
        part('info-toggle').setAttribute('aria-expanded', String(view.infoOpen));

        const collapse = part('collapse');
        collapse.textContent = view.collapsed ? '[+]' : '[-]';
        collapse.title = view.collapsed ? 'Show progress' : 'Hide progress';
        collapse.setAttribute('aria-expanded', String(!view.collapsed));
    }

    function render() {
        if (!job) {
            panel.classList.add('hidden');
            return;
        }
        panel.classList.remove('hidden');
        const scope = job.scope === 'all' ? 'all books' : 'your books';
        const pct = job.total ? Math.min(100, Math.round(job.checked / job.total * 100)) : 100;
        part('bar').style.height = `${pct}%`;
        part('track').setAttribute('aria-valuenow', String(pct));
        part('pct').textContent = `${pct}%`;

        const action = part('action');
        let label;
        if (job.status === 'running') {
            part('title').textContent = `Fetching covers (${scope})`;
            part('text').textContent = `${job.checked} of ${job.total} checked, ${job.found} found. You can keep browsing.`;
            label = 'Stop fetching covers';
        } else {
            const missed = job.checked - job.found;
            part('title').textContent = job.status === 'cancelled' ? 'Cover fetch stopped' : 'Covers fetched';
            part('text').textContent = `${job.found} of ${job.checked} found.` +
                (missed ? ` ${missed} had none online: search by title from the book's edit page.` : '');
            label = 'Dismiss';
        }
        action.title = label;
        action.setAttribute('aria-label', label);
        renderView();
    }

    function poll() {
        clearTimeout(timer);
        fetch(panel.dataset.statusUrl, {headers: {'X-Requested-With': 'XMLHttpRequest'}})
            .then(r => r.json())
            .then(data => {
                job = data.job;
                render();
                if (job && job.status === 'running') timer = setTimeout(poll, POLL_MS);
            })
            .catch(() => { timer = setTimeout(poll, POLL_MS * 3); });  // offline or restarting: back off
    }

    part('action').addEventListener('click', () => {
        if (!job) return;
        const verb = job.status === 'running' ? 'stop' : 'dismiss';
        if (verb === 'stop' && !confirm('Stop fetching covers? Covers found so far are kept.')) return;
        post(`/covers/${encodeURIComponent(job.id)}/${verb}`).then(data => {
            clearTimeout(timer);
            job = verb === 'stop' ? data.job : null;
            render();
        });
    });

    part('info-toggle').addEventListener('click', () => {
        view.infoOpen = !view.infoOpen;
        saveView();
        renderView();
    });

    part('collapse').addEventListener('click', () => {
        view.collapsed = !view.collapsed;
        saveView();
        renderView();
    });

    window.coverJobs = {
        track(newJob) {
            job = newJob;
            // A job the user just started should be visible, with its details
            view.collapsed = false;
            view.infoOpen = true;
            saveView();
            render();
            if (job && job.status === 'running') timer = setTimeout(poll, 1000);
        },
    };

    try {
        job = JSON.parse(panel.dataset.job || 'null');
    } catch (e) {
        job = null;
    }
    render();
    if (job && job.status === 'running') poll();
})();

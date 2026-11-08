// The floating add button and its menu (templates/_add_fab.html).
// The menu links are out of the tab order while it's closed (tabindex -1),
// so keyboard users don't tab through invisible links.

'use strict';

document.addEventListener('DOMContentLoaded', () => {
    const toggle = document.getElementById('fab-toggle');
    const menu = document.getElementById('fab-menu');
    const icon = document.getElementById('fab-icon');
    const backdrop = document.getElementById('fab-backdrop');
    if (!toggle || !menu) return;

    const links = () => menu.querySelectorAll('a');
    let open = false;

    function setOpen(value) {
        open = value;
        menu.classList.toggle('opacity-0', !open);
        menu.classList.toggle('pointer-events-none', !open);
        menu.classList.toggle('translate-y-4', !open);
        menu.classList.toggle('opacity-100', open);
        menu.classList.toggle('pointer-events-auto', open);
        menu.classList.toggle('translate-y-0', open);
        icon?.classList.toggle('rotate-45', open);       // + turns into x
        backdrop?.classList.toggle('hidden', !open);
        toggle.setAttribute('aria-expanded', String(open));
        links().forEach(a => { a.tabIndex = open ? 0 : -1; });
    }

    toggle.addEventListener('click', () => {
        setOpen(!open);
        if (open) links()[0]?.focus();
    });
    backdrop?.addEventListener('click', () => setOpen(false));
    document.addEventListener('keydown', event => {
        if (event.key === 'Escape' && open) {
            setOpen(false);
            toggle.focus();
        }
    });
});

// The floating "Add Book" button and its menu (templates/_add_book_fab.html).

'use strict';

let fabOpen = false;

function toggleFabMenu() {
    fabOpen = !fabOpen;
    const menu = document.getElementById('fab-menu');
    const icon = document.getElementById('fab-icon');
    const backdrop = document.getElementById('fab-backdrop');

    if (fabOpen) {
        menu.classList.remove('opacity-0', 'pointer-events-none', 'translate-y-4');
        menu.classList.add('opacity-100', 'pointer-events-auto', 'translate-y-0');
        icon.style.transform = 'rotate(45deg)';
        backdrop.classList.remove('hidden');
    } else {
        closeFabMenu();
    }
}

function closeFabMenu() {
    fabOpen = false;
    const menu = document.getElementById('fab-menu');
    const icon = document.getElementById('fab-icon');
    const backdrop = document.getElementById('fab-backdrop');

    menu.classList.add('opacity-0', 'pointer-events-none', 'translate-y-4');
    menu.classList.remove('opacity-100', 'pointer-events-auto', 'translate-y-0');
    icon.style.transform = 'rotate(0deg)';
    backdrop.classList.add('hidden');
}

document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('fab-toggle')?.addEventListener('click', toggleFabMenu);
    document.getElementById('fab-backdrop')?.addEventListener('click', closeFabMenu);
});

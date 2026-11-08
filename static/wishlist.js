// Your wishlist page (templates/wishlist.html): the filter over the cards,
// opened by the magnifying glass in the top bar. Adding is the shared add
// page (add_item.js), so this file is only about the list.

'use strict';

document.addEventListener('DOMContentLoaded', () => {
    const toggle = document.getElementById('search-toggle');
    const panel = document.querySelector('.wishlist-search-container');
    const input = document.getElementById('wishlist-search');
    const count = document.getElementById('wishlist-search-count');
    if (!toggle || !panel || !input) return;

    const hide = () => panel.classList.add('invisible', 'opacity-0', '-translate-y-full');

    toggle.addEventListener('click', event => {
        event.stopPropagation();
        panel.classList.toggle('invisible');
        panel.classList.toggle('opacity-0');
        panel.classList.toggle('-translate-y-full');
        if (!panel.classList.contains('invisible')) setTimeout(() => input.focus(), 100);
    });
    document.addEventListener('click', event => {
        if (!panel.contains(event.target) && !toggle.contains(event.target)) hide();
    });
    document.addEventListener('keydown', event => {
        if (event.key === 'Escape') hide();
    });

    // Filter the cards by title and creator (data-search on each card); a
    // section with nothing left in it hides too
    const cards = Array.from(document.querySelectorAll('.wishlist-item'));
    const sections = Array.from(document.querySelectorAll('.wishlist-section'));

    function filter() {
        const term = input.value.toLowerCase().trim();
        let shown = 0;
        cards.forEach(card => {
            const match = !term || card.dataset.search.includes(term);
            // style, not the hidden attribute: the card's .flex class would win
            card.style.display = match ? '' : 'none';
            if (match) shown++;
        });
        sections.forEach(section => {
            const anyShown = Array.from(section.querySelectorAll('.wishlist-item'))
                .some(card => card.style.display !== 'none');
            section.style.display = anyShown ? '' : 'none';
        });
        if (!term || shown === cards.length) {
            count.classList.add('hidden');
        } else {
            count.textContent = shown ? `Showing ${shown} of ${cards.length}` : 'Nothing on your wishlist matches';
            count.classList.remove('hidden');
        }
    }

    let timer;
    input.addEventListener('input', () => {
        clearTimeout(timer);
        timer = setTimeout(filter, 200);
    });
});

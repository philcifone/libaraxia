// Your wishlist page (templates/wishlist.html): the filter box under the
// tabs, over the cards. Adding is the shared add
// page (add_item.js), so this file is only about the list.

'use strict';

document.addEventListener('DOMContentLoaded', () => {
    const input = document.getElementById('wishlist-search');
    const count = document.getElementById('wishlist-search-count');
    if (!input) return;

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

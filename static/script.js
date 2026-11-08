// Library pages (grid, search, sort, filters, infinite scroll) and a few
// helpers for the book page. Shared helpers (getCSRFToken, escapeHtml, ...)
// are in common.js. Markup calls into this file through data-click /
// data-change / data-submit (registered at the bottom), never inline handlers.

'use strict';

// Sort form submission with loading indicator
function submitSortForm() {
    showLoadingIndicator('Sorting books...');
    document.getElementById('sort-form').submit();
}

// Show loading indicator
function showLoadingIndicator(message = 'Loading...') {
    // Create overlay if it doesn't exist
    let overlay = document.getElementById('loading-overlay');
    if (!overlay) {
        overlay = document.createElement('div');
        overlay.id = 'loading-overlay';
        overlay.className = 'fixed inset-0 bg-black/50 z-50 flex items-center justify-center';
        overlay.innerHTML = `
            <div class="bg-secondary-bg rounded-lg px-6 py-4 shadow-hard flex items-center gap-3 card">
                <svg class="animate-spin h-6 w-6 text-accent" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                <span class="text-content-primary font-medium" id="loading-message">${escapeHtml(message)}</span>
            </div>
        `;
        document.body.appendChild(overlay);
    } else {
        document.getElementById('loading-message').textContent = message;
        overlay.classList.remove('hidden');
    }
}

// Hide loading indicator
function hideLoadingIndicator() {
    const overlay = document.getElementById('loading-overlay');
    if (overlay) {
        overlay.classList.add('hidden');
    }
}
// Filter toggle
function toggleFilters() {
    const panel = document.getElementById('filter-panel');
    const arrow = document.getElementById('filterArrow');

    // Toggle visibility
    panel.classList.toggle('hidden');

    // Rotate arrow
    if (panel.classList.contains('hidden')) {
        arrow.classList.remove('rotate-180');
    } else {
        arrow.classList.add('rotate-180');
    }
}

// Clear filters
// The filter-panel fields. Clearing removes only these, so the search term,
// shared-library member and sort survive.
const FILTER_PARAMS = ['genre', 'format', 'read_status', 'rating', 'tags[]', 'show_removed', 'page', 'csrf_token'];

function clearFilters() {
    const params = new URLSearchParams(window.location.search);
    FILTER_PARAMS.forEach(key => params.delete(key));
    const query = params.toString();
    window.location.href = window.location.pathname + (query ? '?' + query : '');
}

// Update active filters display
function updateActiveFilters() {
    const form = document.getElementById('filter-form');
    if (!form) return;

    const activeFilters = [];
    const pillsContainer = document.getElementById('active-filter-pills');
    const displayContainer = document.getElementById('active-filters-display');
    const countBadge = document.getElementById('filter-count-badge');

    // Check genre
    const genre = document.getElementById('genre');
    if (genre && genre.value) {
        activeFilters.push({ label: 'Genre', value: genre.options[genre.selectedIndex].text });
    }

    // Check format (Movies only)
    const format = document.getElementById('format');
    if (format && format.value) {
        activeFilters.push({ label: 'Format', value: format.options[format.selectedIndex].text });
    }

    // Check read status
    const readStatus = document.getElementById('read_status');
    if (readStatus && readStatus.value) {
        activeFilters.push({ label: 'Status', value: readStatus.options[readStatus.selectedIndex].text });
    }

    // Check rating
    const rating = document.getElementById('rating');
    if (rating && rating.value) {
        activeFilters.push({ label: 'Rating', value: rating.options[rating.selectedIndex].text });
    }

    // Check the removed-books choice (empty = on the shelf only, the default)
    const showRemoved = document.getElementById('show_removed');
    if (showRemoved && showRemoved.value) {
        activeFilters.push({ label: 'Removed', value: showRemoved.options[showRemoved.selectedIndex].text });
    }

    // Check tags
    const checkedTags = document.querySelectorAll('input[name="tags[]"]:checked');
    checkedTags.forEach(tag => {
        activeFilters.push({ label: 'Tag', value: tag.value });
    });

    // Update display
    if (activeFilters.length > 0) {
        pillsContainer.innerHTML = activeFilters.map(filter => `
            <span class="inline-flex items-center px-3 py-1 rounded-pill text-xs font-medium bg-accent/20 text-accent border border-accent/30">
                <span class="opacity-75">${escapeHtml(filter.label)}:</span>
                <span class="ml-1">${escapeHtml(filter.value)}</span>
            </span>
        `).join('');
        displayContainer.classList.remove('hidden');
        countBadge.textContent = activeFilters.length;
        countBadge.classList.remove('hidden');
    } else {
        displayContainer.classList.add('hidden');
        countBadge.classList.add('hidden');
    }
}
// On page load, check if filters should be shown and update active filters
document.addEventListener('DOMContentLoaded', function () {
    const urlParams = new URLSearchParams(window.location.search);
    const filterPanel = document.getElementById('filter-panel');
    const arrow = document.getElementById('filterArrow');

    // Check if there are any filter parameters (excluding sort, page, csrf)
    const filterParams = ['genre', 'format', 'read_status', 'rating', 'tags[]', 'show_removed'];
    const hasFilters = filterParams.some(param => urlParams.has(param));

    // Show filters if any filter parameters are present
    if (hasFilters) {
        if (filterPanel && arrow) {
            filterPanel.classList.remove('hidden');
            arrow.classList.add('rotate-180');
        }
    }

    // Update active filters display on page load
    updateActiveFilters();
});
function initRatingSystem() {
    const ratingContainer = document.getElementById('rating-container');
    const ratingText = document.getElementById('rating-text');
    if (!ratingContainer) return;

    const stars = ratingContainer.querySelectorAll('.rating-star');

    // Function to update stars appearance
    function updateStars(hoveredRating = null, isHover = false) {
        const selectedInput = ratingContainer.querySelector('input[type="radio"]:checked');
        const rating = hoveredRating || (selectedInput ? selectedInput.value : 0);

        stars.forEach(star => {
            const starRating = parseInt(star.dataset.rating);
            if (starRating <= rating) {
                star.classList.add('text-yellow-400');
                star.classList.remove('text-gray-400');
            } else {
                star.classList.remove('text-yellow-400');
                star.classList.add('text-gray-400');
            }
        });

        // Update rating text
        if (isHover && rating > 0) {
            ratingText.textContent = `${rating} star${rating !== 1 ? 's' : ''}?`;
        } else if (!isHover && rating > 0) {
            ratingText.textContent = `${rating} star${rating !== 1 ? 's' : ''}!`;
        } else {
            ratingText.textContent = '';
        }
    }

    // Set initial state
    updateStars();

    // Handle hover events
    stars.forEach(star => {
        star.addEventListener('mouseenter', () => {
            const rating = parseInt(star.dataset.rating);
            updateStars(rating, true);
        });
    });

    ratingContainer.addEventListener('mouseleave', () => {
        updateStars(null, false);
    });

    // Handle click events
    stars.forEach(star => {
        star.addEventListener('click', (e) => {
            const rating = parseInt(star.dataset.rating);
            const input = document.getElementById(`star${rating}`);
            input.checked = true;
            updateStars(rating, false);
        });
    });
}

// Initialize when the DOM is loaded
document.addEventListener('DOMContentLoaded', initRatingSystem);

// ============================================================================
// INFINITE SCROLL PAGINATION
// ============================================================================

class InfiniteScroll {
    constructor() {
        this.currentPage = 1;
        this.isLoading = false;
        this.hasMore = true;
        this.bookGrid = null;
        this.loadingIndicator = null;
        this.endMessage = null;
        this.resultCount = null;

        this.init();
    }

    init() {
        // Find the book grid container by ID - more reliable than class selectors
        this.bookGrid = document.getElementById('book-container');
        if (!this.bookGrid) return;

        // Get initial state from template data - look for parent container with data attributes
        const gridContainer = this.bookGrid.parentElement;
        if (gridContainer && gridContainer.hasAttribute('data-current-page')) {
            this.currentPage = parseInt(gridContainer.dataset.currentPage) || 1;
            this.hasMore = gridContainer.dataset.hasMore === 'true';
        }

        // Create and insert loading indicator
        this.createLoadingIndicator();
        this.createEndMessage();
        this.createResultCount();

        // Set up intersection observer for infinite scroll
        this.setupIntersectionObserver();

        // Update result count if it exists
        this.updateResultCount();
    }

    createLoadingIndicator() {
        this.loadingIndicator = document.createElement('div');
        this.loadingIndicator.id = 'loading-indicator';
        this.loadingIndicator.className = 'hidden text-center py-8';
        this.loadingIndicator.innerHTML = `
            <div class="inline-flex items-center gap-3">
                <svg class="animate-spin h-8 w-8 text-accent" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                <span class="text-lg text-content-secondary">Loading more books...</span>
            </div>
        `;

        // Insert after the grid
        this.bookGrid.parentElement.appendChild(this.loadingIndicator);
    }

    createEndMessage() {
        // Disabled - end message not needed
        this.endMessage = null;
    }

    createResultCount() {
        // Disabled - result count not needed
        this.resultCount = null;
    }

    updateResultCount(totalCount = null, currentCount = null) {
        // Disabled - result count not needed
        return;
    }

    setupIntersectionObserver() {
        // Create a sentinel element at the bottom
        const sentinel = document.createElement('div');
        sentinel.id = 'scroll-sentinel';
        sentinel.className = 'h-px';
        this.bookGrid.parentElement.appendChild(sentinel);

        // Set up intersection observer
        const options = {
            root: null, // viewport
            rootMargin: '200px', // Load 200px before reaching the bottom
            threshold: 0
        };

        this.observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting && this.hasMore && !this.isLoading) {
                    this.loadMoreBooks();
                }
            });
        }, options);

        this.observer.observe(sentinel);
    }

    async loadMoreBooks() {
        if (this.isLoading || !this.hasMore) return;

        this.isLoading = true;
        this.showLoading();

        try {
            // Build URL with current query parameters
            const url = new URL(window.location.href);
            const params = new URLSearchParams(url.search);

            // Add pagination parameters
            params.set('page', this.currentPage + 1);

            // Make AJAX request
            const response = await fetch(`${url.pathname}?${params.toString()}`, {
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });

            if (!response.ok) throw new Error('Network response was not ok');

            const data = await response.json();

            // Append new books to grid
            this.appendBooks(data.books);

            // Update state
            this.currentPage = data.current_page;
            this.hasMore = data.has_more;

            // Update result count
            this.updateResultCount(data.total_count, this.bookGrid.querySelectorAll('.group').length);

            // Show end message if no more results
            if (!this.hasMore) {
                this.showEndMessage();
            }

        } catch (error) {
            console.error('Error loading more books:', error);
            this.showError();
        } finally {
            this.isLoading = false;
            this.hideLoading();
        }
    }

    appendBooks(books) {
        books.forEach(book => {
            const bookCard = this.createBookCard(book);
            this.bookGrid.insertAdjacentHTML('beforeend', bookCard);
        });
    }

    createBookCard(book) {
        // Check current view mode
        const currentView = localStorage.getItem('libraryView') || 'grid';
        const container = document.getElementById('book-container');
        const isListView = container && container.className.includes('flex-col');
        // Deaccessioned books only appear with "Include removed books" on
        const removedBadge = book.removed
            ? '<span class="absolute top-2 left-2 z-10 px-2 py-0.5 text-xs font-medium bg-primary-bg text-content-secondary border border-card rounded-pill">Removed</span>'
            : '';

        if (isListView || currentView === 'list') {
            // List view card
            const coverImage = book.cover_image_url
                ? `<img src="/static/${this.escapeHtml(book.cover_image_url)}"
                        alt="${this.escapeHtml(book.title)}"
                        class="book-cover-img object-cover w-full h-full" />`
                : noCoverHtml(book.title, book.author, { size: 'sm' });

            return `
                <div class="book-item">
                    <a href="/books/book/${book.id}"
                       class="book-link flex gap-4 bg-secondary-bg rounded-lg overflow-hidden hover:bg-secondary-bg/80 p-4 card-link">
                        <div class="book-cover relative flex-shrink-0 w-24 h-32 overflow-hidden rounded">
                            ${removedBadge}
                            ${coverImage}
                        </div>
                        <div class="book-info flex-1 flex flex-col justify-center">
                            <h3 class="book-title text-xl font-semibold mb-2 text-white">
                                ${this.escapeHtml(book.title)}
                            </h3>
                            <p class="book-author text-content-secondary italic">
                                by ${this.escapeHtml(book.author)}
                            </p>
                        </div>
                    </a>
                </div>
            `;
        } else {
            // Grid view card
            const coverImage = book.cover_image_url
                ? `<img src="/static/${this.escapeHtml(book.cover_image_url)}"
                        alt="${this.escapeHtml(book.title)}"
                        class="book-cover-img object-contain w-full h-full group-hover:opacity-90 transition-opacity duration-200" />`
                : noCoverHtml(book.title, book.author);

            return `
                <div class="book-item group">
                    <a href="/books/book/${book.id}"
                       class="book-link block bg-secondary-bg rounded-lg overflow-hidden card-link">
                        <div class="book-cover relative w-full h-64 overflow-hidden bg-primary">
                            ${removedBadge}
                            ${coverImage}
                        </div>
                        <div class="book-info p-3 sm:p-4">
                            <h3 class="book-title text-base leading-snug font-semibold line-clamp-2 min-h-[2.75em] mb-2 text-white">
                                ${this.escapeHtml(book.title)}
                            </h3>
                            <p class="book-author text-content-secondary text-xs sm:text-sm italic truncate">
                                by ${this.escapeHtml(book.author)}
                            </p>
                        </div>
                    </a>
                </div>
            `;
        }
    }

    escapeHtml(text) {
        return escapeHtml(text);
    }

    showLoading() {
        this.loadingIndicator.classList.remove('hidden');
    }

    hideLoading() {
        this.loadingIndicator.classList.add('hidden');
    }

    showEndMessage() {
        // Disabled - end message not needed
        return;
    }

    showError() {
        // Create temporary error message
        const errorMsg = document.createElement('div');
        errorMsg.className = 'text-center py-4 text-red-400';
        errorMsg.textContent = 'Failed to load more books. Please try again.';
        this.bookGrid.parentElement.appendChild(errorMsg);

        setTimeout(() => errorMsg.remove(), 5000);
    }
}

// Initialize infinite scroll when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    // Only initialize on library index and search results pages
    // Check for the book container by ID which persists across view changes
    const bookContainer = document.getElementById('book-container');
    const dataContainer = document.querySelector('.container[data-current-page]');
    if (bookContainer && dataContainer) {
        new InfiniteScroll();
    }
});

// ============================================================================
// LIBRARY VIEW TOGGLE (GRID/LIST)
// ============================================================================

// Switch between grid and list views
function switchView(viewType) {
    const container = document.getElementById('book-container');
    const gridBtn = document.getElementById('grid-view-btn');
    const listBtn = document.getElementById('list-view-btn');

    if (!container) return;

    if (viewType === 'grid') {
        // Grid view - set container to grid layout
        container.className = 'grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-6';

        // Update each book item for grid view
        document.querySelectorAll('.book-item').forEach(item => {
            item.className = 'book-item group';
        });

        document.querySelectorAll('.book-link').forEach(link => {
            link.className = 'book-link block bg-secondary-bg rounded-lg overflow-hidden card-link';
        });

        document.querySelectorAll('.book-cover').forEach(cover => {
            cover.className = 'book-cover relative w-full h-64 overflow-hidden bg-primary';   // relative: the Removed badge
        });

        document.querySelectorAll('.book-cover-img').forEach(img => {
            img.className = 'book-cover-img object-contain w-full h-full group-hover:opacity-90 transition-opacity duration-200';
        });

        document.querySelectorAll('.book-info').forEach(info => {
            info.className = 'book-info p-3 sm:p-4';
        });

        document.querySelectorAll('.book-title').forEach(title => {
            title.className = 'book-title text-base leading-snug font-semibold line-clamp-2 min-h-[2.75em] mb-2 text-white';
        });

        document.querySelectorAll('.book-author').forEach(author => {
            author.className = 'book-author text-content-secondary text-xs sm:text-sm italic truncate';
        });

        // Update button states
        gridBtn?.setAttribute('aria-pressed', 'true');
        listBtn?.setAttribute('aria-pressed', 'false');

    } else {
        // List view - set container to flex layout
        container.className = 'flex flex-col gap-4';

        // Update each book item for list view
        document.querySelectorAll('.book-item').forEach(item => {
            item.className = 'book-item';
        });

        document.querySelectorAll('.book-link').forEach(link => {
            link.className = 'book-link flex gap-4 bg-secondary-bg rounded-lg overflow-hidden hover:bg-secondary-bg/80 p-4 card-link';
        });

        document.querySelectorAll('.book-cover').forEach(cover => {
            cover.className = 'book-cover relative flex-shrink-0 w-24 h-32 overflow-hidden rounded';
        });

        document.querySelectorAll('.book-cover-img').forEach(img => {
            img.className = 'book-cover-img object-cover w-full h-full';
        });

        document.querySelectorAll('.book-info').forEach(info => {
            info.className = 'book-info flex-1 flex flex-col justify-center';
        });

        document.querySelectorAll('.book-title').forEach(title => {
            title.className = 'book-title text-xl font-semibold mb-2 text-white';
        });

        document.querySelectorAll('.book-author').forEach(author => {
            author.className = 'book-author text-content-secondary italic';
        });

        // Update button states
        listBtn?.setAttribute('aria-pressed', 'true');
        gridBtn?.setAttribute('aria-pressed', 'false');
    }

    // Save preference to localStorage
    localStorage.setItem('libraryView', viewType);
}

// Initialize view preference on page load
document.addEventListener('DOMContentLoaded', () => {
    const savedView = localStorage.getItem('libraryView') || 'grid';
    const container = document.getElementById('book-container');

    // Only apply view toggle on pages with book container
    if (container) {
        switchView(savedView);
    }
});

// ============================================================================
// MEMBER FILTER TOGGLE
// ============================================================================

document.addEventListener('DOMContentLoaded', () => {
    const toggleButton = document.getElementById('memberFilterToggle');
    const filterSection = document.getElementById('memberFilterSection');
    const chevron = document.getElementById('memberFilterChevron');

    if (toggleButton && filterSection && chevron) {
        // Check if filter should be open on page load
        const isOpen = localStorage.getItem('memberFilterOpen') === 'true';
        if (isOpen) {
            filterSection.classList.remove('hidden');
            chevron.classList.add('rotate-180');
            toggleButton.setAttribute('aria-expanded', 'true');
        }

        // Toggle on click
        toggleButton.addEventListener('click', function() {
            const isCurrentlyHidden = filterSection.classList.contains('hidden');
            filterSection.classList.toggle('hidden');
            chevron.classList.toggle('rotate-180');
            toggleButton.setAttribute('aria-expanded', String(isCurrentlyHidden));

            // Save state to localStorage
            localStorage.setItem('memberFilterOpen', isCurrentlyHidden ? 'true' : 'false');
        });
    }
});
// ---- Account deactivate/delete dialog (templates/_account_removal.html) ----
// Delegated so it also works for the fragment the admin page loads into a <dialog>.
document.addEventListener('change', function (e) {
    if (!e.target.classList || !e.target.classList.contains('account-removal-choice')) return;
    const form = e.target.closest('form.account-removal');
    const del = e.target.value === 'delete' && e.target.checked;
    form.querySelector('.account-removal-delete').classList.toggle('hidden', !del);
    form.querySelector('.account-removal-submit').textContent = del ? 'Delete permanently' : 'Deactivate';
});
document.addEventListener('click', function (e) {
    if (!e.target.closest || !e.target.closest('.account-removal-cancel')) return;
    const dialog = e.target.closest('dialog');
    if (dialog) dialog.close();
});
document.addEventListener('submit', function (e) {
    const form = e.target;
    if (!form.classList || !form.classList.contains('account-removal')) return;
    const choice = form.querySelector('input[name="action"]:checked');
    if (!choice || choice.value !== 'delete') return;
    const booksTo = form.querySelector('select[name="books_to"]');
    if (booksTo && !booksTo.value) {
        e.preventDefault();
        showFlashMessage('error', 'Choose who gets the books first.');
        booksTo.focus();
        return;
    }
    confirmSubmit(form, e, 'Delete this account permanently? This cannot be undone.', { ok: 'Delete account' });
});

// Open the dialog with server-rendered content from `url` (admin page).
async function openAccountRemoval(url) {
    const dialog = document.getElementById('account-removal-dialog');
    const body = document.getElementById('account-removal-body');
    body.textContent = 'Loading…';
    dialog.showModal();
    try {
        const res = await fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } });
        if (!res.ok) throw new Error(res.status);
        body.innerHTML = await res.text();  // trusted: our own template, values autoescaped by Jinja
    } catch (err) {
        body.textContent = 'Could not load this account. Reload the page and try again.';
    }
}

// Handlers named in data-click / data-change / data-submit attributes
// (_search_sort_filter.html, book_detail.html).
registerActions({
    switchView: el => switchView(el.dataset.view),
    submitSortForm: () => submitSortForm(),
    clearFilters: () => clearFilters(),
    toggleFilters: () => toggleFilters(),
    updateActiveFilters: () => updateActiveFilters(),
    showLoading: el => showLoadingIndicator(el.dataset.loading),
});

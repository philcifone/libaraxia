// CSRF Token Helper Function
function getCSRFToken() {
    // Try to get CSRF token from a hidden input in the page
    const tokenInput = document.querySelector('input[name="csrf_token"]');
    if (tokenInput) {
        return tokenInput.value;
    }
    // Fallback: try to get from meta tag if you add one later
    const tokenMeta = document.querySelector('meta[name="csrf-token"]');
    if (tokenMeta) {
        return tokenMeta.content;
    }
    console.warn('CSRF token not found');
    return null;
}

// Helper function to add CSRF token to FormData
function addCSRFToFormData(formData) {
    const token = getCSRFToken();
    if (token) {
        formData.append('csrf_token', token);
    }
    return formData;
}

// Helper function to get headers with CSRF token
function getCSRFHeaders() {
    const token = getCSRFToken();
    return {
        'X-CSRFToken': token,
        'Content-Type': 'application/json'
    };
}

// // NEW JAVASCRIPT FOR BETTER SEARCH BAR NOT WORKING ROLLED BACK
//
// // Initialize everything on page load
// document.addEventListener("DOMContentLoaded", () => {
//     // Panel controls
//     const hamburger = document.getElementById("hamburger");
//     const sidebar = document.getElementById("sidebar");
//     const filterPanel = document.getElementById("filter-panel");
//     const searchToggle = document.getElementById("search-toggle");
//     const filterToggle = document.getElementById("filter-toggle");
//     const closeFilterBtn = document.getElementById("close-filter-panel");

//     // Sidebar toggle
//     hamburger?.addEventListener("click", (e) => {
//         sidebar.classList.toggle("-translate-x-full");
//         e.stopPropagation();
//     });

//     // Filter panel toggle
//     filterToggle?.addEventListener("click", (e) => {
//         filterPanel.classList.toggle("translate-x-full");
//         e.stopPropagation();
//     });

//     // Close filter panel
//     closeFilterBtn?.addEventListener("click", () => {
//         filterPanel.classList.add("translate-x-full");
//     });

//     // Close panels when clicking outside
//     document.addEventListener("click", (e) => {
//         if (!sidebar?.contains(e.target) && !hamburger?.contains(e.target)) {
//             sidebar?.classList.add("-translate-x-full");
//         }
//         if (!filterPanel?.contains(e.target) && !filterToggle?.contains(e.target)) {
//             filterPanel?.classList.add("translate-x-full");
//         }
//     });

//     // New search functionality
//     searchToggle?.addEventListener("click", (e) => {
//         searchContainer.classList.toggle("invisible");
//         searchContainer.classList.toggle("opacity-0");
//         searchContainer.classList.toggle("-translate-y-full");
//         e.stopPropagation();
            
//         if (!searchContainer.classList.contains("invisible")) {
//             setTimeout(() => {
//                 searchContainer.querySelector("#search_term")?.focus();
//             }, 100);
//         }
//     });

//     // Escape key handler
//     document.addEventListener("keydown", (e) => {
//         if (e.key === "Escape") {
//             sidebar?.classList.add("-translate-x-full");
//             filterPanel?.classList.add("translate-x-full");
//         }
//     });

//     // Set up search and filter handlers
//     const searchInput = document.getElementById('search_term');
//     searchInput?.addEventListener('input', (e) => handleSearch(e.target.value));
    
//     document.querySelectorAll('.sort-select').forEach(select => {
//         select.addEventListener('change', handleSort);
//     });
    
//     document.querySelectorAll('[data-filter]').forEach(filter => {
//         filter.addEventListener('change', handleSort);
//     });
// });

// // Utility functions
// function debounce(func, wait) {
//     let timeout;
//     return function executedFunction(...args) {
//         const later = () => {
//             clearTimeout(timeout);
//             func(...args);
//         };
//         clearTimeout(timeout);
//         timeout = setTimeout(later, wait);
//     };
// }

// // Event handlers
// const handleSearch = debounce((searchTerm) => {
//     const form = document.getElementById('search-form');
//     if (searchTerm.length === 0 || searchTerm.length >= 2) {
//         form.submit();
//     }
// }, 500);

// function handleSort() {
//     const sortBy = document.getElementById('sort_by').value;
//     const sortOrder = document.getElementById('sort_order').value;
//     const activeFilters = getActiveFilters();
    
//     const params = new URLSearchParams(window.location.search);
//     params.set('sort_by', sortBy);
//     params.set('sort_order', sortOrder);
    
//     Object.entries(activeFilters).forEach(([key, value]) => {
//         if (value) params.set(key, value);
//     });
    
//     window.history.pushState({}, '', `${window.location.pathname}?${params.toString()}`);
//     fetchResults(params);
// }

// function getActiveFilters() {
//     const filters = {};
//     document.querySelectorAll('[data-filter]').forEach(filter => {
//         const value = filter.type === 'checkbox' ? filter.checked : filter.value;
//         if (value) {
//             filters[filter.name] = value;
//         }
//     });
//     return filters;
// }

// async function fetchResults(params) {
//     try {
//         const response = await fetch(`/api/books?${params.toString()}`);
//         const data = await response.json();
//         updateBookGrid(data.books);
//         updateFilterIndicators(getActiveFilters());
//     } catch (error) {
//         console.error('Error fetching results:', error);
//         document.getElementById('error-message')?.classList.remove('hidden');
//     }
// }

// function updateFilterIndicators(activeFilters) {
//     const container = document.getElementById('active-filters');
//     if (!container) return;
    
//     container.innerHTML = '';
//     Object.entries(activeFilters).forEach(([key, value]) => {
//         const pill = document.createElement('span');
//         pill.className = 'inline-flex items-center px-2 py-1 rounded-full text-sm bg-accent/10 text-accent';
//         pill.innerHTML = `
//             ${key}: ${value}
//             <button onclick="removeFilter('${key}')" class="ml-1 hover:text-accent-hover">×</button>
//         `;
//         container.appendChild(pill);
//     });
// }

// function removeFilter(filterName) {
//     const element = document.querySelector(`[name="${filterName}"]`);
//     if (element) {
//         if (element.type === 'checkbox') {
//             element.checked = false;
//         } else {
//             element.value = '';
//         }
//         handleSort();
//     }
// }

// function clearFilters() {
//     document.querySelectorAll('[data-filter]').forEach(filter => {
//         if (filter.type === 'checkbox') {
//             filter.checked = false;
//         } else {
//             filter.value = '';
//         }
//     });
//     handleSort();
// }

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
            <div class="bg-secondary-bg rounded-lg px-6 py-4 shadow-xl flex items-center gap-3">
                <svg class="animate-spin h-6 w-6 text-accent" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                <span class="text-content-primary font-medium" id="loading-message">${message}</span>
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
function clearFilters() {
    // Clear URL parameters and redirect to index
    window.location.href = window.location.pathname;
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

    // Check tags
    const checkedTags = document.querySelectorAll('input[name="tags[]"]:checked');
    checkedTags.forEach(tag => {
        activeFilters.push({ label: 'Tag', value: tag.value });
    });

    // Update display
    if (activeFilters.length > 0) {
        pillsContainer.innerHTML = activeFilters.map(filter => `
            <span class="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-accent/20 text-accent border border-accent/30">
                <span class="opacity-75">${filter.label}:</span>
                <span class="ml-1">${filter.value}</span>
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
    const filterParams = ['genre', 'read_status', 'rating', 'tags[]'];
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
document.addEventListener("DOMContentLoaded", () => {
    const hamburger = document.getElementById("hamburger");
    const sidebar = document.getElementById("sidebar");
    const content = document.querySelector(".content");
    const searchToggle = document.getElementById("search-toggle");
    const searchContainer = document.querySelector(".search-form-container");

    // Only set up search functionality if elements exist
    if (searchToggle && searchContainer) {
        // Toggle search dropdown with animation
        searchToggle.addEventListener("click", (event) => {
            // Toggle visibility and transform classes
            searchContainer.classList.toggle("invisible");
            searchContainer.classList.toggle("opacity-0");
            searchContainer.classList.toggle("-translate-y-full");
            event.stopPropagation();

            // Focus search input when opening
            if (!searchContainer.classList.contains("invisible")) {
                setTimeout(() => {
                    searchContainer.querySelector("#search_term").focus();
                }, 100);
            }
        });
        // Close search dropdown when clicking outside
        document.addEventListener("click", (event) => {
            if (!searchContainer.contains(event.target) && !searchToggle.contains(event.target)) {
                searchContainer.classList.add("invisible", "opacity-0", "-translate-y-full");
            }
        });
    }
    // Toggle sidebar
    hamburger.addEventListener("click", (event) => {
        sidebar.classList.toggle("-translate-x-full");

        // Animate hamburger icon
        const spans = hamburger.querySelectorAll("span");
        spans[0].classList.toggle("rotate-45");
        spans[0].classList.toggle("translate-y-2");
        spans[1].classList.toggle("opacity-0");
        spans[2].classList.toggle("-rotate-45");
        spans[2].classList.toggle("-translate-y-2");

        event.stopPropagation();
    });
    // Close sidebar when clicking outside
    document.addEventListener("click", (event) => {
        if (!sidebar.contains(event.target) && !hamburger.contains(event.target)) {
            sidebar.classList.add("-translate-x-full");

            // Reset hamburger icon
            const spans = hamburger.querySelectorAll("span");
            spans[0].classList.remove("rotate-45", "translate-y-2");
            spans[1].classList.remove("opacity-0");
            spans[2].classList.remove("-rotate-45", "-translate-y-2");
        }
    });
    // Handle escape key
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            // Close search if it exists
            if (searchContainer) {
                searchContainer.classList.add("invisible", "opacity-0", "-translate-y-full");
            }

            // Close sidebar if it exists
            if (sidebar) {
                sidebar.classList.add("-translate-x-full");
            }

            // Reset hamburger if it exists
            if (hamburger) {
                const spans = hamburger.querySelectorAll("span");
                if (spans.length >= 3) {
                    spans[0].classList.remove("rotate-45", "translate-y-2");
                    spans[1].classList.remove("opacity-0");
                    spans[2].classList.remove("-rotate-45", "-translate-y-2");
                }
            }
        }
    });
});

// view more for toggle description book details
function toggleDescription() {
    const description = document.getElementById('description');
    const button = description.nextElementSibling;
    const buttonText = button.querySelector('.toggle-text');
    const arrow = button.querySelector('svg');

    if (description.style.maxHeight && description.style.maxHeight !== '12rem') {
        // Collapse
        description.style.maxHeight = '12rem';
        description.style.overflow = 'hidden';
        buttonText.textContent = 'Show More';
        arrow.classList.remove('rotate-180');
    } else {
        // Expand - set to scrollHeight to show all content
        description.style.maxHeight = description.scrollHeight + 'px';
        description.style.overflow = 'visible';
        buttonText.textContent = 'Show Less';
        arrow.classList.add('rotate-180');
    }
}

// toggle friend review expansion
function toggleReview(reviewId, button) {
    const reviewText = document.getElementById(reviewId);
    const buttonText = button.querySelector('.toggle-text');
    const arrow = button.querySelector('svg');

    if (reviewText.classList.contains('line-clamp-4')) {
        // Expand
        reviewText.classList.remove('line-clamp-4');
        buttonText.textContent = 'Show Less';
        arrow.classList.add('rotate-180');
    } else {
        // Collapse
        reviewText.classList.add('line-clamp-4');
        buttonText.textContent = 'Show More';
        arrow.classList.remove('rotate-180');
    }
}

// Toggle friend review card expansion
function toggleFriendReview(button) {
    const card = button.closest('.friend-review-card');
    const expandedContent = card.querySelector('.review-expanded');
    const expandIcon = card.querySelector('.expand-icon');
    const previewText = button.querySelector('.review-preview');

    if (expandedContent.classList.contains('hidden')) {
        // Expand
        expandedContent.classList.remove('hidden');
        expandIcon.style.transform = 'rotate(180deg)';
        button.classList.remove('hover:bg-secondary-hover');
        if (previewText) {
            previewText.classList.add('hidden');
        }
    } else {
        // Collapse
        expandedContent.classList.add('hidden');
        expandIcon.style.transform = 'rotate(0deg)';
        button.classList.add('hover:bg-primary-hover');
        if (previewText) {
            previewText.classList.remove('hidden');
        }
    }
}

// toast for collections
function updateStatus(selectElement) {
    const form = document.getElementById("status-form");
    const toast = document.getElementById("toast");

    // Send the form data via POST
    fetch(form.action, {
        method: "POST",
        body: new FormData(form),
    })
    .then((response) => {
        if (response.ok) {
            // Show a toast notification
            toast.style.display = "block";
            setTimeout(() => {
                toast.style.display = "none";
            }, 2000); // Hide toast after 2 seconds
        } else {
            alert("Failed to update status.");
        }
    })
    .catch((error) => {
        console.error("Error updating status:", error);
        alert("An error occurred.");
    });
}

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

// index.html javascript for filter functions

// On page load, check if filters should be shown
document.addEventListener('DOMContentLoaded', function () {
    // Show filters if any filter parameters are present
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.toString() && urlParams.toString() !== '') {
        const filterPanel = document.getElementById('filter-panel');
        filterPanel.classList.add('active');

        // Update the toggle button arrow
        const filterToggle = document.getElementById('filterToggle');
        filterToggle.innerHTML = 'Filters ▲';
    }
});

function submitSortForm() {
    // Preserve filter state when sorting
    const filterPanel = document.getElementById('filter-panel');
    if (filterPanel.classList.contains('active')) {
        const sortForm = document.getElementById('sort-form');
        const showFiltersInput = document.createElement('input');
        showFiltersInput.type = 'hidden';
        showFiltersInput.name = 'show_filters';
        showFiltersInput.value = '1';
        sortForm.appendChild(showFiltersInput);
    }
    document.getElementById('sort-form').submit();
}

// book details

function toggleCollection(checkbox, bookId, collectionId) {
    const action = checkbox.checked ? 'add' : 'remove';
    console.log(`Toggling collection: ${action} book ${bookId} to collection ${collectionId}`);
    
    // Create form data
    const formData = new FormData();
    formData.append('book_id', bookId);
    
    // Add CSRF token to form data
    addCSRFToFormData(formData);

    // Make the request
    fetch(`/collections/${collectionId}/${action}`, {
        method: 'POST',
        body: formData,
        credentials: 'same-origin'
    })
    .then(response => {
        console.log('Response status:', response.status);
        if (!response.ok) {
            return response.text().then(text => {
                console.error('Error response:', text);
                throw new Error(`HTTP error! status: ${response.status}`);
            });
        }
        return response.json();
    })
    .then(data => {
        console.log('Success:', data);
        if (!data.success) {
            checkbox.checked = !checkbox.checked;
            alert('Failed to update collection: ' + (data.error || 'Unknown error'));
        }
    })
    .catch(error => {
        console.error('Error:', error);
        checkbox.checked = !checkbox.checked;
        alert('Error updating collection. Please try again.');
    });
}

// Collection Tags
function updateCollectionTags() {
    const selectedCollection = document.getElementById('collections');
    const tagsContainer = document.getElementById('collection-tags');
    const bookId = document.querySelector('input[name="book_id"]').value;

    fetch(`/collections/get_book_collections/${bookId}`)
        .then(response => response.json())
        .then(data => {
            tagsContainer.innerHTML = data.collections.map(collection => `
                <span class="collection-tag">
                    ${collection.name}
                    <button onclick="removeFromCollection(${collection.id}, ${bookId})" class="tag-remove">×</button>
                </span>
            `).join('');
        });
}

function removeFromCollection(collectionId, bookId) {
    fetch(`/collections/${collectionId}/remove`, {
        method: 'POST',
        headers: getCSRFHeaders(),
        body: JSON.stringify({ book_id: bookId })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) updateCollectionTags();
    });
}

function createCollection() {
    const input = document.querySelector('.collection-input');
    const name = input.value;
    if (!name) return;

    fetch('/collections/create_custom_collection', {
        method: 'POST',
        headers: getCSRFHeaders(),
        body: JSON.stringify({ name })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            location.reload();
        }
    });
}

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

        if (isListView || currentView === 'list') {
            // List view card
            const coverImage = book.cover_image_url
                ? `<img src="/static/${book.cover_image_url}"
                        alt="${this.escapeHtml(book.title)}"
                        class="book-cover-img object-cover w-full h-full" />`
                : `<div class="flex items-center justify-center h-full bg-primary-bg text-content-secondary">
                        <span class="text-xs italic">No Image</span>
                   </div>`;

            return `
                <div class="book-item">
                    <a href="/books/book/${book.id}"
                       class="book-link flex gap-4 bg-secondary-bg rounded-lg shadow-md overflow-hidden hover:bg-secondary-bg/80 transition-all duration-200 p-4">
                        <div class="book-cover flex-shrink-0 w-24 h-32 overflow-hidden rounded">
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
                ? `<img src="/static/${book.cover_image_url}"
                        alt="${this.escapeHtml(book.title)}"
                        class="book-cover-img object-cover w-full h-full group-hover:opacity-90 transition-opacity duration-200" />`
                : `<div class="flex items-center justify-center h-full bg-primary-bg text-content-secondary">
                        <span class="text-sm italic">No Image Available</span>
                   </div>`;

            return `
                <div class="book-item group">
                    <a href="/books/book/${book.id}"
                       class="book-link block bg-secondary-bg rounded-lg shadow-md overflow-hidden transform hover:scale-105 transition-all duration-200">
                        <div class="book-cover w-full h-64 overflow-hidden">
                            ${coverImage}
                        </div>
                        <div class="book-info p-4">
                            <h3 class="book-title text-lg font-semibold line-clamp-2 mb-2 text-white">
                                ${this.escapeHtml(book.title)}
                            </h3>
                            <p class="book-author text-content-secondary text-sm italic">
                                by ${this.escapeHtml(book.author)}
                            </p>
                        </div>
                    </a>
                </div>
            `;
        }
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
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
            link.className = 'book-link block bg-secondary-bg rounded-lg shadow-md overflow-hidden transform hover:scale-105 transition-all duration-200';
        });

        document.querySelectorAll('.book-cover').forEach(cover => {
            cover.className = 'book-cover w-full h-64 overflow-hidden';
        });

        document.querySelectorAll('.book-cover-img').forEach(img => {
            img.className = 'book-cover-img object-cover w-full h-full group-hover:opacity-90 transition-opacity duration-200';
        });

        document.querySelectorAll('.book-info').forEach(info => {
            info.className = 'book-info p-4';
        });

        document.querySelectorAll('.book-title').forEach(title => {
            title.className = 'book-title text-lg font-semibold line-clamp-2 mb-2 text-white';
        });

        document.querySelectorAll('.book-author').forEach(author => {
            author.className = 'book-author text-content-secondary text-sm italic';
        });

        // Update button states
        gridBtn.classList.add('active', 'bg-accent/30', 'text-accent');
        listBtn.classList.remove('active', 'bg-accent/30', 'text-accent');

    } else {
        // List view - set container to flex layout
        container.className = 'flex flex-col gap-4';

        // Update each book item for list view
        document.querySelectorAll('.book-item').forEach(item => {
            item.className = 'book-item';
        });

        document.querySelectorAll('.book-link').forEach(link => {
            link.className = 'book-link flex gap-4 bg-secondary-bg rounded-lg shadow-md overflow-hidden hover:bg-secondary-bg/80 transition-all duration-200 p-4';
        });

        document.querySelectorAll('.book-cover').forEach(cover => {
            cover.className = 'book-cover flex-shrink-0 w-24 h-32 overflow-hidden rounded';
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
        listBtn.classList.add('active', 'bg-accent/30', 'text-accent');
        gridBtn.classList.remove('active', 'bg-accent/30', 'text-accent');
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
        }

        // Toggle on click
        toggleButton.addEventListener('click', function() {
            const isCurrentlyHidden = filterSection.classList.contains('hidden');
            filterSection.classList.toggle('hidden');
            chevron.classList.toggle('rotate-180');

            // Save state to localStorage
            localStorage.setItem('memberFilterOpen', isCurrentlyHidden ? 'true' : 'false');
        });
    }
});
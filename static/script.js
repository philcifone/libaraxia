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

// Sort form submission
function submitSortForm() {
    // Preserve filter state when sorting
    const filterPanel = document.getElementById('filter-panel');
    if (!filterPanel.classList.contains('hidden')) {
        const sortForm = document.getElementById('sort-form');
        const showFiltersInput = document.createElement('input');
        showFiltersInput.type = 'hidden';
        showFiltersInput.name = 'show_filters';
        showFiltersInput.value = '1';
        sortForm.appendChild(showFiltersInput);
    }
    document.body.style.cursor = 'wait';
    document.getElementById('sort-form').submit();
}
// Filter toggle
function toggleFilters() {
    const panel = document.getElementById('filter-panel');
    const arrow = document.getElementById('filterArrow');

    // Toggle visibility
    panel.classList.toggle('hidden');

    // Rotate arrow - using transform rotate classes
    if (panel.classList.contains('hidden')) {
        arrow.classList.remove('rotate-180');
    } else {
        arrow.classList.add('rotate-180');
    }
}
// Clear filters
function clearFilters() {
    const form = document.getElementById('filter-form');
    const inputs = form.getElementsByTagName('input');
    const selects = form.getElementsByTagName('select');
    // Clear all inputs except show_filters
    for (let input of inputs) {
        if (input.type === 'checkbox' || (input.type === 'hidden' && input.id !== 'show_filters')) {
            input.checked = false;
        }
    }
    // Clear all selects
    for (let select of selects) {
        select.value = '';
    }
    form.submit();
}
// On page load, check if filters should be shown
document.addEventListener('DOMContentLoaded', function () {
    const urlParams = new URLSearchParams(window.location.search);
    const filterPanel = document.getElementById('filter-panel');
    const arrow = document.getElementById('filterArrow');

    // Show filters if any filter parameters are present
    if (urlParams.toString() && urlParams.toString() !== '') {
        filterPanel.classList.remove('hidden');
        arrow.classList.add('rotate-180');
    }
});
document.addEventListener("DOMContentLoaded", () => {
    const hamburger = document.getElementById("hamburger");
    const sidebar = document.getElementById("sidebar");
    const content = document.querySelector(".content");
    const searchToggle = document.getElementById("search-toggle");
    const searchContainer = document.querySelector(".search-form-container");
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
            // Close search
            searchContainer.classList.add("invisible", "opacity-0", "-translate-y-full");

            // Close sidebar
            sidebar.classList.add("-translate-x-full");

            // Reset hamburger
            const spans = hamburger.querySelectorAll("span");
            spans[0].classList.remove("rotate-45", "translate-y-2");
            spans[1].classList.remove("opacity-0");
            spans[2].classList.remove("-rotate-45", "-translate-y-2");
        }
    });
});

// view more for toggle description book details
function toggleDescription() {
    const description = document.getElementById('description');
    const button = description.nextElementSibling;
    const buttonText = button.querySelector('.toggle-text');

    description.classList.toggle('expanded');
    buttonText.textContent = description.classList.contains('expanded') ? 'Show Less' : 'Show More';
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

// rating

function initRatingSystem() {
    const container = document.getElementById('rating-container');
    const input = document.getElementById('rating-input');
    const stars = container.getElementsByClassName('rating-star');

    container.addEventListener('click', (e) => {
        if (e.target.matches('.rating-star')) {
            const rating = e.target.dataset.rating;
            input.value = rating;
            
            Array.from(stars).forEach((star, index) => {
                star.classList.toggle('text-yellow-400', index < rating);
                star.classList.toggle('text-gray-400', index >= rating);
            });
        }
    });
}

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

// add book 
// Handle tab switching
document.addEventListener('DOMContentLoaded', function() {
    const methodButtons = document.querySelectorAll('.search-method-btn');
    const methodSections = document.querySelectorAll('.search-method-content');

    methodButtons.forEach(button => {
        button.addEventListener('click', () => {
            // Remove active class from all buttons and sections
            methodButtons.forEach(btn => btn.classList.remove('active'));
            methodSections.forEach(section => section.classList.remove('active'));

            // Add active class to clicked button and corresponding section
            button.classList.add('active');
            const method = button.dataset.method;
            document.getElementById(`${method}-section`).classList.add('active');

            // Stop scanner if switching away from barcode tab
            if (method !== 'barcode' && Quagga.initialized) {
                Quagga.stop();
            }
        });
    });

    // Handle title/author search
    const searchInput = document.getElementById('book-search');
    const searchBtn = document.getElementById('search-btn');
    const resultsContainer = document.getElementById('search-results');
    let searchTimeout;

    function performSearch() {
        const query = searchInput.value.trim();
        if (query.length < 2) return;

        fetch(`/books/search_books?q=${encodeURIComponent(query)}`)
            .then(response => response.json())
            .then(data => {
                resultsContainer.innerHTML = '';
                data.items.forEach(book => {
                    const bookCard = createBookCard(book);
                    resultsContainer.appendChild(bookCard);
                });
            })
            .catch(error => console.error('Error searching books:', error));
    }

    // Debounce search input
    searchInput.addEventListener('input', () => {
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(performSearch, 500);
    });

    searchBtn.addEventListener('click', (e) => {
        e.preventDefault();
        performSearch();
    });

    // Handle barcode scanning
    const scannerBtn = document.getElementById('toggle-scanner');
    let isScanning = false;

    scannerBtn.addEventListener('click', () => {
        if (!isScanning) {
            startScanner();
            scannerBtn.textContent = 'Stop Scanner';
        } else {
            stopScanner();
            scannerBtn.textContent = 'Start Scanner';
        }
        isScanning = !isScanning;
    });
});

function createBookCard(book) {
    const card = document.createElement('div');
    card.className = 'book-search-result';
    
    const thumbnail = book.volumeInfo.imageLinks?.thumbnail || '/static/images/no-cover.png';
    const title = book.volumeInfo.title;
    const authors = book.volumeInfo.authors?.join(', ') || 'Unknown Author';
    const year = book.volumeInfo.publishedDate?.split('-')[0] || 'Unknown Year';

    card.innerHTML = `
        <img src="${thumbnail}" alt="${title} cover" class="result-thumbnail">
        <div class="result-info">
            <h3>${title}</h3>
            <p>${authors}</p>
            <p>${year}</p>
        </div>
        <button class="select-book-btn">Select</button>
    `;

    card.querySelector('.select-book-btn').addEventListener('click', () => {
        fillBookForm(book);
    });

    return card;
}

function fillBookForm(book) {
    const info = book.volumeInfo;
    document.getElementById('title').value = info.title || '';
    document.getElementById('subtitle').value = info.subtitle || '';
    document.getElementById('author').value = info.authors?.join(', ') || '';
    document.getElementById('isbn').value = info.industryIdentifiers?.[0]?.identifier || '';
    document.getElementById('publisher').value = info.publisher || '';
    document.getElementById('genre').value = info.categories?.[0] || '';
    document.getElementById('year').value = info.publishedDate?.split('-')[0] || '';
    document.getElementById('page_count').value = info.pageCount || '';
    document.getElementById('description').value = info.description || '';

    const coverPreview = document.getElementById('cover-preview');
    if (info.imageLinks?.thumbnail) {
        coverPreview.innerHTML = `<img src="${info.imageLinks.thumbnail}" alt="Book cover" class="thumbnail-preview">`;
    }
}

// Barcode scanning setup
function startScanner() {
    Quagga.init({
        inputStream: {
            name: "Live",
            type: "LiveStream",
            target: document.querySelector("#interactive"),
            constraints: {
                facingMode: "environment"
            },
        },
        decoder: {
            readers: ["ean_reader", "ean_8_reader", "upc_reader", "upc_e_reader"]
        }
    }, function(err) {
        if (err) {
            console.error(err);
            alert("Error starting scanner: " + err);
            return;
        }
        Quagga.start();
    });

    Quagga.onDetected(function(result) {
        const code = result.codeResult.code;
        document.getElementById('isbn_lookup').value = code;
        // Automatically trigger ISBN lookup
        document.getElementById('isbn-fetch').click();
        stopScanner();
    });
}

function stopScanner() {
    Quagga.stop();
    document.getElementById('toggle-scanner').textContent = 'Start Scanner';
}

// book details

// Add this to your book_detail.html, replacing any existing toggleCollection function

function toggleCollection(checkbox, bookId, collectionId) {
    const action = checkbox.checked ? 'add' : 'remove';
    console.log(`Toggling collection: ${action} book ${bookId} to collection ${collectionId}`);
    
    // Create form data
    const formData = new FormData();
    formData.append('book_id', bookId);
    
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
        headers: { 'Content-Type': 'application/json' },
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
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            location.reload();
        }
    });
}
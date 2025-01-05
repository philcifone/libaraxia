// Function to automatically submit the form
function submitSortForm() {
    document.body.style.cursor = 'wait';
    document.getElementById('sort-form').submit();
};

// sidebar function
//document.addEventListener("DOMContentLoaded", () => {
//    const hamburger = document.getElementById("hamburger"); // Select the hamburger menu
//    const sidebar = document.getElementById("sidebar"); // Select the sidebar
//    const content = document.querySelector(".content"); // Select the content area
//
//    // Add click event to hamburger menu
//    hamburger.addEventListener("click", () => {
//        // Toggle the 'active' class on sidebar to slide it in and out
//        sidebar.classList.toggle("active");
//        
//        // Toggle the 'sidebar-active' class on content to shift it when sidebar is visible
//        content.classList.toggle("sidebar-active");
//    });
//});

// sidebar scrolling function
document.addEventListener("DOMContentLoaded", () => {
    const hamburger = document.getElementById("hamburger");
    const sidebar = document.getElementById("sidebar");
    const content = document.querySelector(".content");
    const fixedContainer = document.getElementById("fixed-container"); // The top toolbar

    let lastScrollTop = 0; // Variable to store the last scroll position

    // Toggle sidebar on hamburger click
    hamburger.addEventListener("click", (event) => {
        sidebar.classList.toggle("active");
        content.classList.toggle("sidebar-active");
        event.stopPropagation(); // Prevent the click from propagating to the document
    });

    // Close sidebar when clicking outside of it
    document.addEventListener("click", (event) => {
        if (!sidebar.contains(event.target) && !hamburger.contains(event.target)) {
            sidebar.classList.remove("active");
            content.classList.remove("sidebar-active");
        }
    });

    // Scroll event listener to hide/show the top toolbar
    window.addEventListener("scroll", () => {
        let currentScroll = window.pageYOffset || document.documentElement.scrollTop;

        // If scrolling down, hide the top toolbar
        if (currentScroll > lastScrollTop) {
            fixedContainer.style.transform = "translateY(-100%)"; // Hide the top toolbar
        } else {
            fixedContainer.style.transform = "translateY(0)"; // Show the top toolbar
        }

        lastScrollTop = currentScroll <= 0 ? 0 : currentScroll; // Reset for edge cases
    });
});


// OLD view more description book details
//function toggleDescription() {
//    const description = document.getElementById('description');
//    const button = document.querySelector('.toggle-button');
//
//    if (description.classList.contains('expanded')) {
//        description.classList.remove('expanded');
//        button.textContent = 'View More';
//    } else {
//        description.classList.add('expanded');
//        button.textContent = 'View Less';
//    }
//}

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

// rating slide styles

function updateRatingValue(value) {
    const output = document.getElementById('rating-value');
    output.textContent = value;
}

// Keywording/Tag Javascript
document.addEventListener('DOMContentLoaded', function() {
    const tagInput = document.getElementById('tagInput');
    const tagsList = document.getElementById('tagsList');
    const addTagBtn = document.querySelector('.add-tag-btn');
    
    // Get book ID from a data attribute we'll add to the HTML
    const bookId = document.querySelector('[data-book-id]').dataset.bookId;
    
    // Load existing tags
    fetchTags();
    
    // Add tag on button click
    addTagBtn.addEventListener('click', () => {
        addTags();
    });
    
    // Add tag on Enter key
    tagInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            addTags();
        }
    });
    
    function addTags() {
        const tags = tagInput.value.split(',').map(tag => tag.trim()).filter(tag => tag);
        if (tags.length === 0) return;
        
        fetch('/tags/add', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                book_id: bookId,
                tags: tags
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                tagInput.value = '';
                updateTagsList(data.tags);
            }
        })
        .catch(error => console.error('Error:', error));
    }
    
    function removeTag(tagName) {
        fetch('/tags/remove', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                book_id: bookId,
                tag: tagName
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                updateTagsList(data.tags);
            }
        })
        .catch(error => console.error('Error:', error));
    }
    
    function fetchTags() {
        fetch(`/tags/get/${bookId}`)
        .then(response => response.json())
        .then(data => {
            updateTagsList(data.tags);
        })
        .catch(error => console.error('Error:', error));
    }
    
    function updateTagsList(tags) {
        tagsList.innerHTML = tags.map(tag => `
            <span class="tag">
                ${tag}
                <button class="tag-remove" onclick="event.preventDefault(); window.tagOperations.removeTag('${tag}')">×</button>
            </span>
        `).join('');
    }
    
    // Make removeTag function available globally in a safer way
    window.tagOperations = {
        removeTag: removeTag
    };
});

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

function toggleFilters() {
    const panel = document.getElementById('filter-panel');
    const toggle = document.getElementById('filterToggle');
    panel.classList.toggle('active');

    // Update the arrow direction
    if (panel.classList.contains('active')) {
        toggle.innerHTML = 'Filters ▲';
    } else {
        toggle.innerHTML = 'Filters ▼';
    }
}

function clearFilters() {
    const form = document.getElementById('filter-form');
    const inputs = form.getElementsByTagName('input');
    const selects = form.getElementsByTagName('select');

    // Preserve the show_filters value
    const showFilters = document.getElementById('show_filters');

    for (let input of inputs) {
        if (input.type === 'checkbox' || (input.type === 'hidden' && input.id !== 'show_filters')) {
            input.checked = false;
        }
    }

    for (let select of selects) {
        select.value = '';
    }

    form.submit();
}

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
// light/dark toggle
const themeToggle = document.getElementById('theme-toggle');
const root = document.documentElement;

// Check for saved theme preference
const savedTheme = localStorage.getItem('theme');
if (savedTheme) {
    root.classList.toggle('light-mode', savedTheme === 'light');
}

themeToggle.addEventListener('click', () => {
    const isLightMode = root.classList.toggle('light-mode');
    localStorage.setItem('theme', isLightMode ? 'light' : 'dark');
});

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
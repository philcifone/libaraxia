document.addEventListener('DOMContentLoaded', function() {
    // DOM Elements
    const methodButtons = document.querySelectorAll('.search-method-btn');  // Changed from [data-method]
    const methodSections = document.querySelectorAll('.search-method-content');
    const searchInput = document.getElementById('book-search');
    const searchBtn = document.getElementById('search-btn');
    const resultsContainer = document.getElementById('search-results');
    const scannerBtn = document.getElementById('toggle-scanner');
    let searchTimeout;
    let isScanning = false;

    // Tab Switching
    methodButtons.forEach(button => {
        button.addEventListener('click', () => {
            // Remove active class from all buttons and sections
            methodButtons.forEach(btn => btn.setAttribute('data-active', 'false'));
            methodSections.forEach(section => section.classList.add('hidden'));
            
            // Add active class to clicked button and corresponding section
            button.setAttribute('data-active', 'true');
            const method = button.dataset.method;
            const activeSection = document.querySelector(`.search-method-content[data-method="${method}"]`);
            activeSection.classList.remove('hidden');
            
            // Handle scanner state
            if (method !== 'barcode' && window.Quagga && Quagga.initialized) {
                stopScanner();
            }
        });
    });

// Search Functionality
function performSearch() {
    const query = searchInput.value.trim();
    if (query.length < 2) return;

    // Show loading state
    resultsContainer.innerHTML = `
        <div class="col-span-full text-center py-8 text-content-secondary">
            <svg class="animate-spin h-8 w-8 mx-auto mb-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
            Searching...
        </div>
    `;

    fetch(`/books/search_books?q=${encodeURIComponent(query)}`)
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            return response.json();
        })
        .then(data => {
            displaySearchResults(data.items);
        })
        .catch(error => {
            console.error('Error searching books:', error);
            resultsContainer.innerHTML = `
                <div class="col-span-full text-center py-8 text-content-secondary">
                    An error occurred while searching. Please try again.
                </div>
            `;
        });
}

function displaySearchResults(books) {
    resultsContainer.innerHTML = '';

    if (!books || books.length === 0) {
        resultsContainer.innerHTML = `
            <div class="col-span-full text-center py-8 text-content-secondary">
                No books found matching your search.
            </div>
        `;
        return;
    }

    const template = document.getElementById('search-result-template');
    books.forEach(book => {
        const resultElement = template.content.cloneNode(true);
        const bookResult = resultElement.querySelector('.book-result');

        // Populate data
        const coverImg = bookResult.querySelector('img');
        coverImg.src = book.volumeInfo.imageLinks?.thumbnail || '/static/images/no-cover.png';
        coverImg.onerror = () => coverImg.src = '/static/images/no-cover.png';

        bookResult.querySelector('.book-title').textContent = book.volumeInfo.title;
        bookResult.querySelector('.book-author').textContent = `by ${book.volumeInfo.authors?.join(', ') || 'Unknown Author'}`;
        bookResult.querySelector('.book-year').textContent = book.volumeInfo.publishedDate?.split('-')[0] || '';
        bookResult.querySelector('.book-isbn').textContent = `ISBN: ${book.volumeInfo.industryIdentifiers?.[0]?.identifier || 'N/A'}`;
        bookResult.querySelector('.book-description').textContent = book.volumeInfo.description || 'No description available';

        // Add click handler to select button
        bookResult.querySelector('.select-book-btn').addEventListener('click', () => {
            fillBookForm(book);
        });

        resultsContainer.appendChild(resultElement);
    });
}

    function fillBookForm(book) {
        const info = book.volumeInfo;
        const fields = {
            'title': info.title || '',
            'subtitle': info.subtitle || '',
            'author': info.authors?.join(', ') || '',
            'isbn': info.industryIdentifiers?.[0]?.identifier || '',
            'publisher': info.publisher || '',
            'genre': info.categories?.[0] || '',
            'year': info.publishedDate?.split('-')[0] || '',
            'page_count': info.pageCount || '',
            'description': info.description || ''
        };

        // Populate all fields
        Object.keys(fields).forEach(field => {
            const element = document.getElementById(field);
            if (element) element.value = fields[field];
        });

        // Handle cover preview
        const coverPreview = document.getElementById('cover-preview');
        if (info.imageLinks?.thumbnail) {
            coverPreview.innerHTML = `<img src="${info.imageLinks.thumbnail}" alt="Book cover" class="max-w-xs rounded-lg shadow-lg">`;
        }

        // Scroll form into view
        document.querySelector('.book-info-form').scrollIntoView({ behavior: 'smooth' });
    }

    // Search event listeners
    searchInput.addEventListener('input', () => {
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(performSearch, 500);
    });

    searchBtn.addEventListener('click', (e) => {
        e.preventDefault();
        performSearch();
    });

    // Barcode Scanner Functionality
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
            document.getElementById('isbn-fetch').click();
            stopScanner();
        });
    }

    function stopScanner() {
        if (window.Quagga && Quagga.initialized) {
            Quagga.stop();
            isScanning = false;
            scannerBtn.textContent = 'Start Scanner';
        }
    }

    scannerBtn.addEventListener('click', () => {
        if (!isScanning) {
            startScanner();
            scannerBtn.textContent = 'Stop Scanner';
        } else {
            stopScanner();
        }
        isScanning = !isScanning;
    });

    // Handle image upload preview
    const imageInput = document.getElementById('image');
    imageInput.addEventListener('change', function(e) {
        const file = e.target.files[0];
        if (file) {
            const reader = new FileReader();
            reader.onload = function(e) {
                const coverPreview = document.getElementById('cover-preview');
                coverPreview.innerHTML = `<img src="${e.target.result}" alt="Book cover" class="max-w-xs rounded-lg shadow-lg">`;
            };
            reader.readAsDataURL(file);
        }
    });

    // Clean up on page unload
    window.addEventListener('beforeunload', () => {
        stopScanner();
    });
});
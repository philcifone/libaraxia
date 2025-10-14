document.addEventListener('DOMContentLoaded', function() {
    // DOM Elements
    const methodButtons = document.querySelectorAll('.search-method-btn');
    const methodSections = document.querySelectorAll('.search-method-content');
    const searchInput = document.getElementById('book-search');
    const searchBtn = document.getElementById('search-btn');
    const resultsContainer = document.getElementById('search-results');
    const scannerBtn = document.getElementById('toggle-scanner');
    let searchTimeout;
    let isScanning = false;
    let isProcessingBarcode = false;

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

        console.log('Starting search for:', query);

        // Use wishlist search endpoint
        fetch(`/wishlist/search_books?q=${encodeURIComponent(query)}`)
            .then(response => {
                console.log('Search response status:', response.status);
                if (!response.ok) {
                    return response.json().then(err => {
                        throw new Error(err.error || `HTTP error! status: ${response.status}`);
                    });
                }
                return response.json();
            })
            .then(data => {
                if (data.error) {
                    throw new Error(data.error);
                }
                if (!data.items) {
                    throw new Error('No items array in response');
                }
                displaySearchResults(data.items);
            })
            .catch(error => {
                console.error('Error searching books:', error);
                resultsContainer.innerHTML = `
                    <div class="col-span-full text-center py-8 text-content-secondary">
                        Error: ${error.message || 'An unexpected error occurred'}.<br>
                        Please try again or contact support if the problem persists.
                    </div>
                `;
            });
    }

    function displaySearchResults(books) {
        console.log('Displaying search results:', books);
        resultsContainer.innerHTML = '';

        if (!books || books.length === 0) {
            resultsContainer.innerHTML = `
                <div class="col-span-full text-center py-8 text-content-secondary">
                    No books found matching your search.
                </div>
            `;
            return;
        }

        books.forEach(book => {
            console.log('Processing book:', book);
            const template = document.getElementById('search-result-template');
            if (!template) {
                console.error('Template not found!');
                return;
            }

            const resultElement = template.content.cloneNode(true);
            const bookResult = resultElement.querySelector('.book-result');
            if (!bookResult) {
                console.error('Book result element not found in template!');
                return;
            }

            const volumeInfo = book.volumeInfo || book;
            const coverImg = bookResult.querySelector('img');

            if (volumeInfo.imageLinks && volumeInfo.imageLinks.thumbnail) {
                let thumbnailUrl = volumeInfo.imageLinks.thumbnail;
                thumbnailUrl = thumbnailUrl.replace('http:', 'https:')
                                         .replace('&zoom=1', '')
                                         .replace('&edge=curl', '');
                coverImg.src = thumbnailUrl;
            } else {
                coverImg.src = '/static/no-cover.png';
            }
            coverImg.onerror = () => coverImg.src = '/static/no-cover.png';

            const elements = {
                title: bookResult.querySelector('.book-title'),
                author: bookResult.querySelector('.book-author'),
                year: bookResult.querySelector('.book-year'),
                isbn: bookResult.querySelector('.book-isbn'),
                description: bookResult.querySelector('.book-description')
            };

            if (elements.title) elements.title.textContent = volumeInfo.title || 'Unknown Title';
            if (elements.author) elements.author.textContent =
                `by ${volumeInfo.authors ? volumeInfo.authors.join(', ') : 'Unknown Author'}`;
            if (elements.year) elements.year.textContent =
                volumeInfo.publishedDate ? volumeInfo.publishedDate.split('-')[0] : '';

            const isbn = volumeInfo.industryIdentifiers ?
                volumeInfo.industryIdentifiers.find(id =>
                    id.type === 'ISBN_13' || id.type === 'ISBN_10'
                )?.identifier : '';
            if (elements.isbn) elements.isbn.textContent = `ISBN: ${isbn || 'N/A'}`;

            if (elements.description) elements.description.textContent =
                volumeInfo.description || 'No description available';

            // Add click handler to select button
            const selectButton = bookResult.querySelector('.select-book-btn');
            if (selectButton) {
                selectButton.addEventListener('click', (e) => {
                    e.preventDefault();
                    const bookData = {
                        title: volumeInfo.title,
                        subtitle: volumeInfo.subtitle || '',
                        author: volumeInfo.authors ? volumeInfo.authors.join(', ') : '',
                        publisher: volumeInfo.publisher || '',
                        publishedDate: volumeInfo.publishedDate ? volumeInfo.publishedDate.split('-')[0] : '',
                        pageCount: volumeInfo.pageCount || '',
                        description: volumeInfo.description || '',
                        genre: volumeInfo.categories ? volumeInfo.categories.join(', ') : '',
                        isbn: isbn,
                        thumbnail: volumeInfo.imageLinks?.thumbnail || null
                    };
                    console.log('Selected book data:', bookData);
                    selectBook(bookData, selectButton);
                });
            }

            resultsContainer.appendChild(resultElement);
        });
    }

    async function selectBook(bookData, button) {
        try {
            console.log('Sending book data to backend:', bookData);
            // Use wishlist endpoint
            const response = await fetch('/wishlist/select_search_result', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    bookData: bookData
                })
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            if (data.success) {
                console.log('Received book details from backend:', data.book_details);
                fillBookForm(data.book_details);
                button.innerHTML = `
                    <svg class="w-4 h-4 mr-2" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7"/>
                    </svg>
                    Book info fetched!
                `;
                button.disabled = true;
            } else {
                console.error('Error selecting book:', data.error);
                alert('Error selecting book. Please try again.');
            }
        } catch (error) {
            console.error('Error:', error);
            alert('Error selecting book. Please try again.');
        }
    }

    function fillBookForm(bookDetails) {
        console.log('Filling form with book details:', bookDetails);
        console.log('Book details structure:', JSON.stringify(bookDetails, null, 2));

        // Show the form container
        const formContainer = document.getElementById('book-form-container');
        if (formContainer) {
            formContainer.classList.remove('hidden');
        }

        const fields = {
            'title': bookDetails.title || '',
            'subtitle': bookDetails.subtitle || '',
            'author': bookDetails.author || '',
            'isbn': bookDetails.isbn || '',
            'publisher': bookDetails.publisher || '',
            'genre': bookDetails.genre || '',
            'year': bookDetails.publishedDate || bookDetails.year || '',
            'page_count': bookDetails.pageCount || bookDetails.page_count || '',
            'description': bookDetails.description || ''
        };

        Object.entries(fields).forEach(([fieldId, value]) => {
            const element = document.getElementById(fieldId);
            if (element) {
                console.log(`Setting ${fieldId} to:`, value);
                element.value = value;
            } else {
                console.warn(`Element not found for field: ${fieldId}`);
            }
        });

        const coverPreview = document.getElementById('cover-preview');
        if (!coverPreview) {
            console.error('Cover preview element not found!');
            return;
        }

        // Check multiple possible cover URL keys
        const coverUrl = bookDetails.local_cover_url || bookDetails.cover_image_url;
        const thumbnailUrl = bookDetails.thumbnail_url || bookDetails.thumbnail;

        console.log('Cover URL options:', {
            local_cover_url: bookDetails.local_cover_url,
            cover_image_url: bookDetails.cover_image_url,
            thumbnail_url: bookDetails.thumbnail_url,
            thumbnail: bookDetails.thumbnail,
            chosen: coverUrl
        });

        if (coverUrl) {
            // Construct the correct image path
            let imagePath = coverUrl;

            // If it's a relative path (uploads/...), prepend /static/
            if (coverUrl.startsWith('uploads/')) {
                imagePath = `/static/${coverUrl}`;
            }
            // If it's already /static/uploads/..., use as-is
            else if (coverUrl.startsWith('/static/')) {
                imagePath = coverUrl;
            }
            // If it's an external URL (https://...), use as-is
            else if (coverUrl.startsWith('http')) {
                imagePath = coverUrl;
            }

            console.log('Displaying cover image at:', imagePath);

            coverPreview.innerHTML = `
                <img src="${imagePath}"
                     alt="Book cover"
                     onerror="this.onerror=null; this.src='/static/no-cover.png'; console.error('Failed to load cover:', '${imagePath}');"
                     class="max-w-xs rounded-lg shadow-lg">
            `;

            // Update hidden input for form submission
            let coverUrlInput = document.querySelector('input[name="existing_cover_url"]');
            if (!coverUrlInput) {
                coverUrlInput = document.createElement('input');
                coverUrlInput.type = 'hidden';
                coverUrlInput.name = 'existing_cover_url';
                const form = document.querySelector('form');
                if (form) {
                    form.appendChild(coverUrlInput);
                } else {
                    console.error('Form element not found!');
                }
            }
            // Store the relative path (uploads/...) for database
            coverUrlInput.value = coverUrl.replace('/static/', '');
            console.log('Set hidden input value:', coverUrlInput.value);
        } else if (thumbnailUrl) {
            // Fallback to thumbnail if no local cover
            console.log('No local cover, using thumbnail:', thumbnailUrl);
            coverPreview.innerHTML = `
                <img src="${thumbnailUrl}"
                     alt="Book cover"
                     onerror="this.onerror=null; this.src='/static/no-cover.png';"
                     class="max-w-xs rounded-lg shadow-lg">
            `;
        } else {
            console.warn('No cover image available in book details');
            coverPreview.innerHTML = '<p class="text-content-secondary">No cover image available</p>';
        }

        const form = document.querySelector('form');
        if (form) {
            form.scrollIntoView({ behavior: 'smooth' });
        } else {
            console.error('Form element not found for scrolling!');
        }
    }

    // Search event listeners
    if (searchInput) {
        searchInput.addEventListener('input', () => {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(performSearch, 500);
        });
    }

    if (searchBtn) {
        searchBtn.addEventListener('click', (e) => {
            e.preventDefault();
            performSearch();
        });
    }

    // Barcode Scanner Functionality
    function startScanner() {
        console.log('Initializing barcode scanner...');

        Quagga.init({
            inputStream: {
                name: "Live",
                type: "LiveStream",
                target: document.querySelector("#interactive"),
                constraints: {
                    width: 640,
                    height: 480,
                    facingMode: "environment"
                },
            },
            decoder: {
                readers: [
                    "ean_reader",
                    "ean_8_reader",
                    "upc_reader",
                    "upc_e_reader"
                ]
            },
            locate: true
        }, function(err) {
            if (err) {
                console.error('Scanner initialization error:', err);
                if (err.name === 'NotAllowedError') {
                    alert("Camera access denied. Please allow camera access and try again.");
                } else if (err.name === 'NotFoundError') {
                    alert("No camera found. Please use a device with a camera.");
                } else {
                    alert("Error starting scanner: " + err.message);
                }
                scannerBtn.textContent = 'Start Scanner';
                isScanning = false;
                return;
            }
            console.log('Scanner started successfully');
            Quagga.start();
        });

        Quagga.onDetected(function(result) {
            if (isProcessingBarcode) {
                console.log('Already processing a barcode, ignoring...');
                return;
            }

            const code = result.codeResult.code;
            console.log('Barcode detected:', code);

            if (/^\d{10}(\d{3})?$/.test(code)) {
                isProcessingBarcode = true;
                stopScanner();
                console.log(`Valid ISBN detected: ${code}, fetching details...`);
                fetchBookByISBN(code).finally(() => {
                    isProcessingBarcode = false;
                });
            } else {
                console.log('Invalid ISBN format:', code);
            }
        });
    }

    async function fetchBookByISBN(isbn) {
        try {
            const interactive = document.querySelector('#interactive');
            interactive.innerHTML = `
                <div class="flex items-center justify-center h-full">
                    <div class="text-white text-center">
                        <svg class="animate-spin h-12 w-12 mx-auto mb-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                        </svg>
                        <p>Fetching book details...</p>
                    </div>
                </div>
            `;

            // Use wishlist endpoint
            const response = await fetch(`/wishlist/fetch_isbn_details?isbn=${isbn}`);
            const data = await response.json();

            if (data.success && data.book_details) {
                fillBookForm(data.book_details);
                interactive.innerHTML = `
                    <div class="flex items-center justify-center h-full">
                        <div class="text-white text-center">
                            <svg class="w-16 h-16 mx-auto mb-4 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>
                            </svg>
                            <p>Book details loaded!</p>
                        </div>
                    </div>
                `;
                document.querySelector('form').scrollIntoView({ behavior: 'smooth' });
            } else {
                interactive.innerHTML = `
                    <div class="flex items-center justify-center h-full">
                        <div class="text-white text-center">
                            <p class="text-red-500">Book not found for ISBN: ${isbn}</p>
                            <p class="mt-2">Try scanning again or use ISBN lookup</p>
                        </div>
                    </div>
                `;
            }
        } catch (error) {
            console.error('Error fetching book:', error);
            alert('Error fetching book details. Please try again.');
        }
    }

    function stopScanner() {
        if (window.Quagga) {
            Quagga.offDetected();
            Quagga.offProcessed();

            if (Quagga.initialized) {
                Quagga.stop();
            }

            isScanning = false;
            if (scannerBtn) {
                scannerBtn.textContent = 'Start Scanner';
            }
            console.log('Scanner stopped');
        }
    }

    if (scannerBtn) {
        scannerBtn.addEventListener('click', () => {
            if (!isScanning) {
                startScanner();
                scannerBtn.textContent = 'Stop Scanner';
            } else {
                stopScanner();
            }
            isScanning = !isScanning;
        });
    }

    // Handle image upload preview
    const imageInput = document.getElementById('image');
    if (imageInput) {
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
    }

    // Clean up on page unload
    window.addEventListener('beforeunload', () => {
        stopScanner();
    });

    // Global function to clear and hide form (called from template button)
    window.clearAndHideForm = function() {
        const formContainer = document.getElementById('book-form-container');
        if (formContainer) {
            formContainer.classList.add('hidden');
        }

        // Clear all form fields
        const form = document.querySelector('#book-form-container form');
        if (form) {
            form.reset();
        }

        // Clear cover preview
        const coverPreview = document.getElementById('cover-preview');
        if (coverPreview) {
            coverPreview.innerHTML = '';
        }

        // Clear search results
        if (resultsContainer) {
            resultsContainer.innerHTML = '';
        }

        console.log('Form cleared and hidden');
    };
});

// CSRF Token Helper Functions (copied from script.js)
function getCSRFToken() {
    const tokenInput = document.querySelector('input[name="csrf_token"]');
    if (tokenInput) return tokenInput.value;
    const tokenMeta = document.querySelector('meta[name="csrf-token"]');
    if (tokenMeta) return tokenMeta.content;
    console.warn('CSRF token not found');
    return null;
}

function getCSRFHeaders() {
    const token = getCSRFToken();
    return {
        'X-CSRFToken': token,
        'Content-Type': 'application/json'
    };
}

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

    async function checkForDuplicates(bookData) {
        try {
            const response = await fetch('/wishlist/check_duplicates', {
                method: 'POST',
                headers: getCSRFHeaders(),
                body: JSON.stringify({
                    title: bookData.title,
                    isbn: bookData.isbn
                })
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            return await response.json();
        } catch (error) {
            console.error('Error checking duplicates:', error);
            return { has_duplicates: false, duplicates: [] };
        }
    }

    function showDuplicateWarning(duplicates) {
        const reasons = [];
        const locations = [];

        duplicates.forEach(dup => {
            if (dup.match_reason.includes('title')) reasons.push('title');
            if (dup.match_reason.includes('ISBN')) reasons.push('ISBN');
            if (dup.in_library) locations.push('library');
            if (dup.in_wishlist) locations.push('wishlist');
        });

        const uniqueReasons = [...new Set(reasons)];
        const uniqueLocations = [...new Set(locations)];

        const reasonText = uniqueReasons.join(' and ');
        const locationText = uniqueLocations.join(' and ');

        let message = `A book with matching ${reasonText} already exists`;
        if (locationText) {
            message += ` in your ${locationText}`;
        }
        message += '.\n\n';

        duplicates.forEach(dup => {
            message += `"${dup.title}" by ${dup.author}\n`;
            message += `  - ${dup.in_library ? 'In library' : ''}${dup.in_library && dup.in_wishlist ? ' and ' : ''}${dup.in_wishlist ? 'In wishlist' : ''}\n`;
        });

        message += '\nAre you sure you want to add this book to your wishlist?';

        return confirm(message);
    }

    async function selectBook(bookData, button) {
        try {
            console.log('Sending book data to backend:', bookData);

            // Check for duplicates first
            const duplicateCheck = await checkForDuplicates(bookData);

            if (duplicateCheck.has_duplicates) {
                console.log('Found duplicates:', duplicateCheck.duplicates);
                const userConfirmed = showDuplicateWarning(duplicateCheck.duplicates);

                if (!userConfirmed) {
                    console.log('User cancelled due to duplicates');
                    return;
                }
            }

            // Disable button and show loading state
            button.disabled = true;
            const originalButtonHTML = button.innerHTML;
            button.innerHTML = `
                <svg class="animate-spin w-4 h-4 mr-2" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                Adding...
            `;

            // Use wishlist endpoint
            const response = await fetch('/wishlist/select_search_result', {
                method: 'POST',
                headers: getCSRFHeaders(),
                body: JSON.stringify({
                    bookData: bookData
                })
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            if (data.success) {
                console.log('Book added to wishlist:', data.book);

                // Update button to show success
                button.innerHTML = `
                    <svg class="w-4 h-4 mr-2" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7"/>
                    </svg>
                    Added to wishlist!
                `;

                // Add book card to the wishlist grid
                addBookToWishlistGrid(data.book);

            } else {
                console.error('Error selecting book:', data.error);
                alert(data.error || 'Error adding book to wishlist. Please try again.');
                button.innerHTML = originalButtonHTML;
                button.disabled = false;
            }
        } catch (error) {
            console.error('Error:', error);
            alert('Error adding book to wishlist. Please try again.');
            button.disabled = false;
        }
    }

    function addBookToWishlistGrid(book) {
        console.log('Adding book to wishlist grid:', book);

        // Find the wishlist grid using ID selector (most reliable)
        let wishlistGrid = document.getElementById('wishlist-grid');

        if (!wishlistGrid) {
            console.log('No grid found, creating new wishlist section');
            // If no grid exists, we need to create the entire wishlist section
            const mainContainer = document.querySelector('.max-w-7xl');
            const emptyMessage = document.querySelector('.text-center.py-16');

            if (emptyMessage) {
                console.log('Removing empty message');
                emptyMessage.remove();
            }

            const wishlistSection = document.createElement('div');
            wishlistSection.className = 'mt-12 mb-8';
            wishlistSection.innerHTML = `
                <h2 class="text-3xl font-display text-content-primary mb-6 text-center">Your Wishlist (1 book)</h2>
                <div class="container mx-auto px-4 py-8">
                    <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-6" id="wishlist-grid">
                    </div>
                </div>
            `;
            mainContainer.appendChild(wishlistSection);
            wishlistGrid = document.getElementById('wishlist-grid');
        } else {
            console.log('Grid found, updating count');
            // Update count in the heading
            const heading = document.querySelector('.mt-12.mb-8 h2');
            if (heading) {
                const countMatch = heading.textContent.match(/\((\d+)\s+book/);
                if (countMatch) {
                    const currentCount = parseInt(countMatch[1]) || 0;
                    const newCount = currentCount + 1;
                    heading.textContent = `Your Wishlist (${newCount} book${newCount !== 1 ? 's' : ''})`;
                }
            }
        }

        // Create book card
        const bookCard = document.createElement('div');
        bookCard.className = 'group relative flex flex-col bg-secondary-bg rounded-lg shadow-md overflow-hidden transform hover:scale-105 transition-all duration-200';

        const coverImageUrl = book.cover_image_url ? `/static/${book.cover_image_url}` : '';
        const coverHTML = book.cover_image_url
            ? `<img src="${coverImageUrl}" alt="${book.title}" class="object-cover w-full h-72 group-hover:opacity-90 transition-opacity duration-200" />`
            : `<div class="flex items-center justify-center h-64 bg-primary-bg text-content-secondary">
                   <span class="text-sm italic">No Image Available</span>
               </div>`;

        const csrfToken = getCSRFToken();

        bookCard.innerHTML = `
            <a href="/books/book/${book.id}" class="block flex-1">
                <div class="aspect-w-3 aspect-h-4 relative">
                    ${coverHTML}
                </div>
                <div class="p-4 pb-2">
                    <h3 class="text-lg font-semibold line-clamp-2 mb-2 text-white">
                        ${book.title}
                    </h3>
                    <p class="text-content-secondary text-sm italic mb-2">
                        by ${book.author}
                    </p>
                    ${book.notes ? `<p class="text-xs text-content-secondary italic line-clamp-1 mb-2">"${book.notes}"</p>` : ''}
                </div>
            </a>
            <div class="px-4 pb-4">
                <form action="/wishlist/move_to_library/${book.id}" method="POST">
                    <input type="hidden" name="csrf_token" value="${csrfToken}"/>
                    <button type="submit"
                            class="w-full px-3 py-2 bg-accent hover:bg-accent-hover text-white text-sm rounded-md transition-colors duration-200 shadow-lg flex items-center justify-center">
                        <svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/>
                        </svg>
                        Add to Library
                    </button>
                </form>
            </div>
        `;

        console.log('Inserting book card into grid');
        // Insert at the beginning of the grid
        wishlistGrid.insertBefore(bookCard, wishlistGrid.firstChild);

        console.log('Scrolling to book card');
        // Scroll to the wishlist section
        bookCard.scrollIntoView({ behavior: 'smooth', block: 'center' });
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
                // Check for duplicates before filling form
                const duplicateCheck = await checkForDuplicates({
                    title: data.book_details.title,
                    isbn: data.book_details.isbn
                });

                if (duplicateCheck.has_duplicates) {
                    console.log('Found duplicates:', duplicateCheck.duplicates);
                    const userConfirmed = showDuplicateWarning(duplicateCheck.duplicates);

                    if (!userConfirmed) {
                        console.log('User cancelled due to duplicates');
                        interactive.innerHTML = `
                            <div class="flex items-center justify-center h-full">
                                <div class="text-white text-center">
                                    <p>Cancelled - duplicate book found</p>
                                </div>
                            </div>
                        `;
                        return;
                    }
                }

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

    // ISBN Lookup Form Handler
    const isbnForm = document.querySelector('#isbn-section form');
    const isbnInput = document.getElementById('isbn_lookup');
    const isbnFetchBtn = document.getElementById('isbn-fetch');

    if (isbnForm) {
        isbnForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const isbn = isbnInput.value.trim();

            if (!isbn) {
                alert('Please enter an ISBN');
                return;
            }

            // Show loading state
            isbnFetchBtn.disabled = true;
            const originalButtonHTML = isbnFetchBtn.innerHTML;
            isbnFetchBtn.innerHTML = `
                <svg class="animate-spin w-5 h-5 mr-2" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                Fetching...
            `;

            try {
                const response = await fetch(`/wishlist/fetch_isbn_details?isbn=${encodeURIComponent(isbn)}`);
                const data = await response.json();

                if (data.success && data.book_details) {
                    // Check for duplicates before filling form
                    const duplicateCheck = await checkForDuplicates({
                        title: data.book_details.title,
                        isbn: data.book_details.isbn
                    });

                    if (duplicateCheck.has_duplicates) {
                        console.log('Found duplicates:', duplicateCheck.duplicates);
                        const userConfirmed = showDuplicateWarning(duplicateCheck.duplicates);

                        if (!userConfirmed) {
                            console.log('User cancelled due to duplicates');
                            isbnFetchBtn.innerHTML = originalButtonHTML;
                            isbnFetchBtn.disabled = false;
                            return;
                        }
                    }

                    fillBookForm(data.book_details);
                    alert('Book details loaded! Please review and add to wishlist.');
                } else {
                    alert(data.error || 'Book not found for this ISBN');
                }
            } catch (error) {
                console.error('Error fetching ISBN:', error);
                alert('Error fetching book details. Please try again.');
            } finally {
                isbnFetchBtn.innerHTML = originalButtonHTML;
                isbnFetchBtn.disabled = false;
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

    // ============================================================================
    // WISHLIST GRID SEARCH FUNCTIONALITY
    // ============================================================================

    const wishlistSearchInput = document.getElementById('wishlist-search');
    const wishlistGrid = document.getElementById('wishlist-grid');
    const wishlistSearchCount = document.getElementById('wishlist-search-count');
    const wishlistSearchContainer = document.querySelector('.wishlist-search-container');
    const searchToggle = document.getElementById('search-toggle');

    // Set up navbar search toggle for wishlist page
    if (searchToggle && wishlistSearchContainer) {
        searchToggle.addEventListener('click', (event) => {
            // Toggle visibility
            wishlistSearchContainer.classList.toggle('invisible');
            wishlistSearchContainer.classList.toggle('opacity-0');
            wishlistSearchContainer.classList.toggle('-translate-y-full');
            event.stopPropagation();

            // Focus search input when opening
            if (!wishlistSearchContainer.classList.contains('invisible')) {
                setTimeout(() => {
                    if (wishlistSearchInput) {
                        wishlistSearchInput.focus();
                    }
                }, 100);
            }
        });

        // Close search dropdown when clicking outside
        document.addEventListener('click', (event) => {
            if (wishlistSearchContainer &&
                !wishlistSearchContainer.contains(event.target) &&
                !searchToggle.contains(event.target)) {
                wishlistSearchContainer.classList.add('invisible', 'opacity-0', '-translate-y-full');
            }
        });

        // Handle escape key to close search
        document.addEventListener('keydown', (event) => {
            if (event.key === 'Escape' && wishlistSearchContainer) {
                wishlistSearchContainer.classList.add('invisible', 'opacity-0', '-translate-y-full');
            }
        });
    }

    if (wishlistSearchInput && wishlistGrid) {
        // Get all book cards in the wishlist grid
        const bookCards = Array.from(wishlistGrid.querySelectorAll('.group'));
        const totalBooks = bookCards.length;

        // Function to filter wishlist books
        function filterWishlistBooks() {
            const searchTerm = wishlistSearchInput.value.toLowerCase().trim();

            if (searchTerm === '') {
                // Show all books if search is empty
                bookCards.forEach(card => {
                    card.style.display = '';
                });
                wishlistSearchCount.classList.add('hidden');
                return;
            }

            let visibleCount = 0;

            bookCards.forEach(card => {
                // Get the title and author from the card
                const titleElement = card.querySelector('h3');
                const authorElement = card.querySelector('.text-content-secondary.text-sm.italic');

                const title = titleElement ? titleElement.textContent.toLowerCase() : '';
                const author = authorElement ? authorElement.textContent.toLowerCase().replace('by ', '') : '';

                // Check if search term matches title or author
                if (title.includes(searchTerm) || author.includes(searchTerm)) {
                    card.style.display = '';
                    visibleCount++;
                } else {
                    card.style.display = 'none';
                }
            });

            // Update search count message
            if (visibleCount === 0) {
                wishlistSearchCount.textContent = 'No books found matching your search';
                wishlistSearchCount.classList.remove('hidden');
            } else if (visibleCount < totalBooks) {
                wishlistSearchCount.textContent = `Showing ${visibleCount} of ${totalBooks} books`;
                wishlistSearchCount.classList.remove('hidden');
            } else {
                wishlistSearchCount.classList.add('hidden');
            }
        }

        // Add event listener for search input
        let searchTimeout;
        wishlistSearchInput.addEventListener('input', () => {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(filterWishlistBooks, 300);
        });

        // Also filter on Enter key
        wishlistSearchInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                clearTimeout(searchTimeout);
                filterWishlistBooks();
            }
        });
    }
});

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
    
        fetch(`/books/search_books?q=${encodeURIComponent(query)}`)
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
                coverImg.src = '/static/uploads/no-cover.png';
            }
            coverImg.onerror = () => coverImg.src = '/static/uploads/no-cover.png';
    
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
            const response = await fetch('/books/select_search_result', {
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
                button.textContent = "Selected!";
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
    
        if (bookDetails.local_cover_url) {
            console.log('Setting local cover URL:', bookDetails.local_cover_url);
            coverPreview.innerHTML = `
                <img src="/static/${bookDetails.local_cover_url}" 
                     alt="Book cover" 
                     class="max-w-xs rounded-lg shadow-lg">
            `;
            
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
            coverUrlInput.value = bookDetails.local_cover_url;
            console.log('Set hidden input value:', bookDetails.local_cover_url);
        } else {
            console.log('No local cover URL provided');
            coverPreview.innerHTML = '';
        }
    
        const form = document.querySelector('form');
        if (form) {
            form.scrollIntoView({ behavior: 'smooth' });
        } else {
            console.error('Form element not found for scrolling!');
        }
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
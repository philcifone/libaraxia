document.addEventListener('DOMContentLoaded', function() {
    // Get DOM elements
    const searchInput = document.getElementById('book-search');
    const searchBtn = document.getElementById('search-btn');
    const resultsContainer = document.getElementById('search-results');
    const bookForm = document.querySelector('.book-info-form');

    // Method selection buttons
    const methodBtns = document.querySelectorAll('.search-method-btn');
    const methodSections = document.querySelectorAll('.search-method-content');

    // Handle method switching
    methodBtns.forEach(btn => {
        btn.addEventListener('click', function() {
            const method = this.dataset.method;
            
            // Update active button
            methodBtns.forEach(b => b.classList.remove('active'));
            this.classList.add('active');
            
            // Show correct section
            methodSections.forEach(section => {
                section.classList.remove('active');
                if (section.id === `${method}-section`) {
                    section.classList.add('active');
                }
            });
        });
    });

    // Handle search
    searchBtn.addEventListener('click', performSearch);
    searchInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            performSearch();
        }
    });

    async function performSearch() {
        const query = searchInput.value.trim();
        if (!query) return;

        resultsContainer.innerHTML = '<div class="loading">Searching...</div>';
        
        try {
            const response = await fetch(`/books/search_books?query=${encodeURIComponent(query)}`);
            const data = await response.json();
            
            if (!response.ok) throw new Error(data.error || 'Search failed');
            
            displayResults(data.results);
        } catch (error) {
            resultsContainer.innerHTML = `<div class="error">${error.message}</div>`;
        }
    }

    function displayResults(results) {
        if (!results || !results.length) {
            resultsContainer.innerHTML = '<div class="no-results">No books found</div>';
            return;
        }

        resultsContainer.innerHTML = results.map(book => `
            <div class="search-result">
                <img src="${book.thumbnail || '/static/placeholder-cover.jpg'}" alt="Book cover" class="result-thumbnail">
                <div class="result-info">
                    <h3>${book.title}</h3>
                    ${book.subtitle ? `<h4>${book.subtitle}</h4>` : ''}
                    <p>By: ${book.authors}</p>
                    <p>Published: ${book.publishedDate} by ${book.publisher}</p>
                    <button class="select-book-btn" data-book='${JSON.stringify(book).replace(/'/g, "&#39;")}'>
                        Select This Book
                    </button>
                </div>
            </div>
        `).join('');

        // Add click handlers for select buttons
        document.querySelectorAll('.select-book-btn').forEach(btn => {
            btn.addEventListener('click', function() {
                const book = JSON.parse(this.dataset.book);
                // Send both ISBN and thumbnail URL when selecting a book
                fetch('/books/select_search_result', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        isbn: book.isbn,
                        thumbnail: book.thumbnail,
                        bookData: book
                    })
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success && data.book_details) {
                        populateForm(data.book_details);
                    } else {
                        throw new Error(data.error || 'Failed to get book details');
                    }
                })
                .catch(error => {
                    console.error('Error selecting book:', error);
                    alert('Failed to get book details. Please try again.');
                });
            });
        });
    }

    function populateForm(book) {
        // Populate form fields with book data
        document.getElementById('title').value = book.title || '';
        document.getElementById('subtitle').value = book.subtitle || '';
        document.getElementById('author').value = book.author || '';  // Changed from authors
        document.getElementById('isbn').value = book.isbn || '';
        document.getElementById('publisher').value = book.publisher || '';
        document.getElementById('genre').value = book.genre || '';    // Changed from categories
        document.getElementById('year').value = book.year || '';      // Changed from publishedDate
        document.getElementById('page_count').value = book.pageCount || '';
        document.getElementById('description').value = book.description || '';

        // Handle cover image
        const coverPreview = document.getElementById('cover-preview');
        if (book.local_cover_url) {
            const staticUrl = book.local_cover_url.startsWith('/static/') ? 
                book.local_cover_url : `/static/${book.local_cover_url}`;
            coverPreview.innerHTML = `<img src="${staticUrl}" alt="Book cover" class="thumbnail-preview">`;
            // Set the hidden input for the cover URL
            document.querySelector('input[name="existing_cover_url"]').value = book.local_cover_url;
        } else if (book.thumbnail) {
            coverPreview.innerHTML = `<img src="${book.thumbnail}" alt="Book cover" class="thumbnail-preview">`;
        } else {
            coverPreview.innerHTML = '';
        }

        // Scroll to form
        bookForm.scrollIntoView({ behavior: 'smooth' });
    }
});
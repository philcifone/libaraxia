// Edit Book - Fetch Cover Functionality

// CSRF Token Helper Functions
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
    const fetchCoverBtn = document.getElementById('fetchCoverBtn');
    const fetchCoverText = document.getElementById('fetchCoverText');
    const fetchCoverSpinner = document.getElementById('fetchCoverSpinner');
    const newCoverPreview = document.getElementById('newCoverPreview');
    const newCoverImage = document.getElementById('newCoverImage');
    const fetchedCoverUrlInput = document.getElementById('fetched_cover_url');
    const coverOptionsContainer = document.getElementById('coverOptionsContainer');
    const coverOptionsGrid = document.getElementById('coverOptionsGrid');

    let availableCovers = [];

    if (fetchCoverBtn) {
        fetchCoverBtn.addEventListener('click', async function() {
            // Get current form values
            const isbn = document.getElementById('isbn').value.trim();
            const title = document.getElementById('title').value.trim();
            const author = document.getElementById('author').value.trim();

            // Validate that we have at least ISBN or title
            if (!isbn && !title) {
                alert('Please provide at least an ISBN or title to fetch a cover');
                return;
            }

            // Show loading state
            fetchCoverBtn.disabled = true;
            fetchCoverText.classList.add('hidden');
            fetchCoverSpinner.classList.remove('hidden');

            try {
                const response = await fetch('/books/fetch_cover', {
                    method: 'POST',
                    headers: getCSRFHeaders(),
                    body: JSON.stringify({
                        isbn: isbn,
                        title: title,
                        author: author
                    })
                });

                const data = await response.json();

                if (data.success && data.covers && data.covers.length > 0) {
                    availableCovers = data.covers;

                    // Display cover options inline
                    displayCoverOptions(data.covers);
                    coverOptionsContainer.classList.remove('hidden');

                    showMessage(`Found ${data.total_downloaded} covers from ${data.total_found} sources!`, 'success');
                } else {
                    showMessage(data.error || 'Failed to fetch cover', 'error');
                }
            } catch (error) {
                console.error('Error fetching cover:', error);
                showMessage('An error occurred while fetching the cover', 'error');
            } finally {
                // Reset button state
                fetchCoverBtn.disabled = false;
                fetchCoverText.classList.remove('hidden');
                fetchCoverSpinner.classList.add('hidden');
            }
        });
    }

    // Display cover options inline
    function displayCoverOptions(covers) {
        coverOptionsGrid.innerHTML = '';

        covers.forEach((cover, index) => {
            const coverOption = document.createElement('div');
            coverOption.className = 'cover-option cursor-pointer border-2 border-gray-600 hover:border-accent rounded-lg p-2 transition-all duration-200 bg-primary-bg';
            coverOption.innerHTML = `
                <img src="/static/${cover.url}"
                     alt="Cover from ${cover.source}"
                     class="w-full h-72 rounded-lg shadow-md mb-2"
                     loading="lazy">
                <p class="text-xs text-content-secondary text-center mb-2">${cover.source}</p>
                <button type="button" class="w-full bg-accent hover:bg-accent-hover text-white text-xs py-1 px-2 rounded transition-colors duration-200">
                    Select
                </button>
            `;

            coverOption.querySelector('button').addEventListener('click', function() {
                selectCover(cover);
            });

            coverOptionsGrid.appendChild(coverOption);
        });
    }

    // Handle cover selection
    function selectCover(cover) {
        // Update the preview
        newCoverImage.src = `/static/${cover.url}`;
        fetchedCoverUrlInput.value = cover.url;
        newCoverPreview.classList.remove('hidden');

        // Hide the cover options
        coverOptionsContainer.classList.add('hidden');

        // Show success message
        showMessage(`Selected cover from ${cover.source}`, 'success');
    }

    // Helper function to show messages
    function showMessage(message, type) {
        // Create a temporary message element
        const messageDiv = document.createElement('div');
        messageDiv.className = `fixed top-4 right-4 px-6 py-3 rounded-lg shadow-lg z-50 ${
            type === 'success'
                ? 'bg-green-600 text-white'
                : 'bg-red-600 text-white'
        }`;
        messageDiv.textContent = message;

        document.body.appendChild(messageDiv);

        // Remove after 3 seconds
        setTimeout(() => {
            messageDiv.remove();
        }, 3000);
    }
});

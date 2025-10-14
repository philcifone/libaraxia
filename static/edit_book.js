// Edit Book - Fetch Cover Functionality

document.addEventListener('DOMContentLoaded', function() {
    const fetchCoverBtn = document.getElementById('fetchCoverBtn');
    const fetchCoverText = document.getElementById('fetchCoverText');
    const fetchCoverSpinner = document.getElementById('fetchCoverSpinner');
    const newCoverPreview = document.getElementById('newCoverPreview');
    const newCoverImage = document.getElementById('newCoverImage');
    const fetchedCoverUrlInput = document.getElementById('fetched_cover_url');

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
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        isbn: isbn,
                        title: title,
                        author: author
                    })
                });

                const data = await response.json();

                if (data.success) {
                    // Show the new cover preview
                    newCoverImage.src = `/static/${data.cover_url}`;
                    fetchedCoverUrlInput.value = data.cover_url;
                    newCoverPreview.classList.remove('hidden');

                    // Show success message with source info
                    const sourcesInfo = data.tried_sources > 1
                        ? ` (searched ${data.tried_sources} sources)`
                        : '';
                    showMessage(`Cover found from ${data.source}${sourcesInfo}!`, 'success');
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

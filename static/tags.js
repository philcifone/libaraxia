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
            <span class="inline-flex items-center px-3 py-0.5 rounded-full text-sm font-medium bg-gray-100 text-gray-800 mr-2 mb-2">
                ${tag}
                <button class="tag-remove ml-1.5 text-gray-400 hover:text-gray-900 focus:outline-none" data-tag="${tag}">
                    <svg class="w-4 h-4" stroke="currentColor" fill="none" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                    </svg>
                </button>
            </span>
        `).join('');
    
        // Add event listeners to remove tag buttons
        const removeTagButtons = document.querySelectorAll('.tag-remove');
        removeTagButtons.forEach(button => {
            button.addEventListener('click', (e) => {
                e.preventDefault();
                const tagName = button.dataset.tag;
                removeTag(tagName);
            });
        });
    }
});
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
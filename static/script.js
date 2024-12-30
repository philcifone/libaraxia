// Function to automatically submit the form
function submitSortForm() {
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

    // Add click event to hamburger menu
    hamburger.addEventListener("click", () => {
        sidebar.classList.toggle("active");
        content.classList.toggle("sidebar-active");
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


// view more description book details
function toggleDescription() {
    const description = document.getElementById('description');
    const button = document.querySelector('.toggle-button');

    if (description.classList.contains('expanded')) {
        description.classList.remove('expanded');
        button.textContent = 'View More';
    } else {
        description.classList.add('expanded');
        button.textContent = 'View Less';
    }
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



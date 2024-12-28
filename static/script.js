// Function to automatically submit the form
function submitSortForm() {
    document.getElementById('sort-form').submit();
};

// sidebar function
document.addEventListener("DOMContentLoaded", () => {
    const hamburger = document.getElementById("hamburger");
    const sidebar = document.getElementById("sidebar");
    const content = document.getElementById("content");

    hamburger.addEventListener("click", () => {
        sidebar.classList.toggle("active");
        content.classList.toggle("sidebar-active");
    });
});

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



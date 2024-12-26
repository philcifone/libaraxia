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
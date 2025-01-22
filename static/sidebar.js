document.addEventListener("DOMContentLoaded", () => {
    const hamburger = document.getElementById("hamburger");
    const sidebar = document.getElementById("sidebar");
    const content = document.querySelector(".content");
    const fixedContainer = document.getElementById("fixed-container");
    const searchToggle = document.getElementById("search-toggle");
    const searchContainer = document.querySelector(".search-form-container");

    // Toggle search dropdown
    searchToggle.addEventListener("click", (event) => {
        searchContainer.classList.toggle("active");
        event.stopPropagation();
    });

    // Close search dropdown when clicking outside
    document.addEventListener("click", (event) => {
        if (!searchContainer.contains(event.target) && !searchToggle.contains(event.target)) {
            searchContainer.classList.remove("active");
        }
    });

    let lastScrollTop = 0; // Variable to store the last scroll position

    // Toggle sidebar on hamburger click - UPDATED FOR TAILWIND
    hamburger.addEventListener("click", (event) => {
        sidebar.classList.toggle("-translate-x-full"); // Changed from "active"
        content.classList.toggle("sidebar-active");
        hamburger.classList.toggle("active"); // Keep this for hamburger animation
        event.stopPropagation();
    });

    // Close sidebar when clicking outside - UPDATED FOR TAILWIND
    document.addEventListener("click", (event) => {
        if (!sidebar.contains(event.target) && !hamburger.contains(event.target)) {
            sidebar.classList.add("-translate-x-full"); // Changed from remove("active")
            content.classList.remove("sidebar-active");
            hamburger.classList.remove("active");
        }
    });

    // Scroll event listener to hide/show the top toolbar
    window.addEventListener("scroll", () => {
        let currentScroll = window.pageYOffset || document.documentElement.scrollTop;
        const searchContainer = document.querySelector(".search-form-container");
        const filterPanel = document.getElementById("filter-panel");
        
        // Check if search or filters are active
        const isSearchActive = searchContainer.classList.contains("active");
        const isFilterActive = filterPanel.classList.contains("active");
    
        // Only hide header if neither search nor filters are active
        if (!isSearchActive && !isFilterActive) {
            if (currentScroll > lastScrollTop) {
                fixedContainer.style.transform = "translateY(-100%)"; // Hide the top toolbar
            } else {
                fixedContainer.style.transform = "translateY(0)"; // Show the top toolbar
            }
        } else {
            // Keep header visible when search/filters are active
            fixedContainer.style.transform = "translateY(0)";
        }
    
        lastScrollTop = currentScroll <= 0 ? 0 : currentScroll; // Reset for edge cases
    });
});
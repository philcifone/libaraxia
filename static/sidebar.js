// Header bar and sidebar (templates/_sidebar.html): the hamburger menu, the
// search dropdown (only on pages that include _search_sort_filter.html), and
// Escape / click-outside to close them. Loaded by _sidebar.html, so every page
// with a sidebar gets it.

'use strict';

document.addEventListener("DOMContentLoaded", () => {
    const hamburger = document.getElementById("hamburger");
    const sidebar = document.getElementById("sidebar");
    const searchToggle = document.getElementById("search-toggle");
    const searchContainer = document.querySelector(".search-form-container");

    // Only set up search functionality if elements exist
    if (searchToggle && searchContainer) {
        // Toggle search dropdown with animation
        searchToggle.addEventListener("click", (event) => {
            // Toggle visibility and transform classes
            searchContainer.classList.toggle("invisible");
            searchContainer.classList.toggle("opacity-0");
            searchContainer.classList.toggle("-translate-y-full");
            event.stopPropagation();

            // Focus search input when opening
            if (!searchContainer.classList.contains("invisible")) {
                setTimeout(() => {
                    searchContainer.querySelector("#search_term").focus();
                }, 100);
            }
        });
        // Close search dropdown when clicking outside
        document.addEventListener("click", (event) => {
            if (!searchContainer.contains(event.target) && !searchToggle.contains(event.target)) {
                searchContainer.classList.add("invisible", "opacity-0", "-translate-y-full");
            }
        });
    }
    // Toggle sidebar
    hamburger.addEventListener("click", (event) => {
        sidebar.classList.toggle("-translate-x-full");

        // Animate hamburger icon
        const spans = hamburger.querySelectorAll("span");
        spans[0].classList.toggle("rotate-45");
        spans[0].classList.toggle("translate-y-2");
        spans[1].classList.toggle("opacity-0");
        spans[2].classList.toggle("-rotate-45");
        spans[2].classList.toggle("-translate-y-2");

        event.stopPropagation();
    });
    // Close sidebar when clicking outside
    document.addEventListener("click", (event) => {
        if (!sidebar.contains(event.target) && !hamburger.contains(event.target)) {
            sidebar.classList.add("-translate-x-full");

            // Reset hamburger icon
            const spans = hamburger.querySelectorAll("span");
            spans[0].classList.remove("rotate-45", "translate-y-2");
            spans[1].classList.remove("opacity-0");
            spans[2].classList.remove("-rotate-45", "-translate-y-2");
        }
    });
    // Handle escape key
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            // Close search if it exists
            if (searchContainer) {
                searchContainer.classList.add("invisible", "opacity-0", "-translate-y-full");
            }

            // Close sidebar if it exists
            if (sidebar) {
                sidebar.classList.add("-translate-x-full");
            }

            // Reset hamburger if it exists
            if (hamburger) {
                const spans = hamburger.querySelectorAll("span");
                if (spans.length >= 3) {
                    spans[0].classList.remove("rotate-45", "translate-y-2");
                    spans[1].classList.remove("opacity-0");
                    spans[2].classList.remove("-rotate-45", "-translate-y-2");
                }
            }
        }
    });
});

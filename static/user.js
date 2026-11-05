// Profile page (templates/user.html): long reviews, stats tabs, inline
// settings, avatar upload, bio, friend search and the appearance picker.
// Markup reaches these through data-click / data-change (registered at the
// bottom); values the server knows come from data- attributes.

'use strict';

// ---- Long reviews: "Show more" -------------------------------------------

// Function to check if review texts are truncated and show "show more" buttons
function initializeReviewToggles() {
    const reviewTexts = document.querySelectorAll('.review-text');

    reviewTexts.forEach(text => {
        // Check if content is taller than max-height (120px)
        if (text.scrollHeight > 120) {
            // Show the "show more" button
            const button = text.nextElementSibling;
            if (button && button.classList.contains('show-more-btn')) {
                button.classList.remove('hidden');
            }
        }
    });
}

// Function to toggle review text expansion
function toggleReviewText(button) {
    const reviewText = button.previousElementSibling;
    const isExpanded = reviewText.getAttribute('data-expanded') === 'true';

    if (isExpanded) {
        // Collapse
        reviewText.style.maxHeight = '120px';
        reviewText.style.overflow = 'hidden';
        reviewText.setAttribute('data-expanded', 'false');
        button.textContent = 'Show more';
    } else {
        // Expand
        reviewText.style.maxHeight = 'none';
        reviewText.style.overflow = 'visible';
        reviewText.setAttribute('data-expanded', 'true');
        button.textContent = 'Show less';
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', initializeReviewToggles);

// ---- Stats tabs ----------------------------------------------------------

// Tab switching functionality
function switchTab(tabName) {
    // Hide all tab contents
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.add('hidden');
    });

    // Deactivate all tab buttons
    document.querySelectorAll('.tab-button').forEach(button => {
        button.classList.remove('active');
        button.classList.remove('text-content-primary');
        button.classList.add('text-content-secondary');
    });

    // Show selected tab content
    document.getElementById('content-' + tabName).classList.remove('hidden');

    // Activate selected tab button
    const activeButton = document.getElementById('tab-' + tabName);
    activeButton.classList.add('active', 'text-content-primary');
    activeButton.classList.remove('text-content-secondary');
}

// ---- Inline settings (email, username, password, avatar, bio) and friend search

// Inline editing functionality
function editField(fieldName) {
    const display = document.getElementById(`${fieldName}-display`);
    const input = document.getElementById(`${fieldName}-input`);
    const editBtn = document.getElementById(`${fieldName}-edit-btn`);
    const saveBtn = document.getElementById(`${fieldName}-save-btn`);
    const cancelBtn = document.getElementById(`${fieldName}-cancel-btn`);

    // Hide display and edit button, show input and action buttons
    display.classList.add('hidden');
    editBtn.classList.add('hidden');
    input.classList.remove('hidden');
    saveBtn.classList.remove('hidden');
    cancelBtn.classList.remove('hidden');
    if (fieldName === 'email') {
        document.getElementById('email-password-input').classList.remove('hidden');
    }

    // Focus the input
    input.focus();
    input.select();
}

function cancelEdit(fieldName) {
    const display = document.getElementById(`${fieldName}-display`);
    const input = document.getElementById(`${fieldName}-input`);
    const editBtn = document.getElementById(`${fieldName}-edit-btn`);
    const saveBtn = document.getElementById(`${fieldName}-save-btn`);
    const cancelBtn = document.getElementById(`${fieldName}-cancel-btn`);

    // Reset input to original value
    input.value = display.textContent;

    // Show display and edit button, hide input and action buttons
    display.classList.remove('hidden');
    editBtn.classList.remove('hidden');
    input.classList.add('hidden');
    saveBtn.classList.add('hidden');
    cancelBtn.classList.add('hidden');
    if (fieldName === 'email') {
        const pw = document.getElementById('email-password-input');
        pw.value = '';
        pw.classList.add('hidden');
    }
}

async function saveField(fieldName) {
    const input = document.getElementById(`${fieldName}-input`);
    const newValue = input.value.trim();

    if (!newValue) {
        alert(`${fieldName.charAt(0).toUpperCase() + fieldName.slice(1)} cannot be empty!`);
        return;
    }

    // Basic email validation
    if (fieldName === 'email') {
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if (!emailRegex.test(newValue)) {
            alert('Please enter a valid email address!');
            return;
        }
    }
    const body = { [fieldName]: newValue };
    if (fieldName === 'email') {
        body.current_password = document.getElementById('email-password-input').value;
        if (!body.current_password) {
            alert('Enter your current password to change your email.');
            return;
        }
    }

    try {
        const response = await fetch(`/user/update_${fieldName}`, {
            method: 'POST',
            headers: getCSRFHeaders(),
            body: JSON.stringify(body)
        });

        const data = await response.json();

        if (response.ok && data.success) {
            // Update the display text
            const display = document.getElementById(`${fieldName}-display`);
            display.textContent = newValue;

            // Exit edit mode
            cancelEdit(fieldName);

            // Show success message
            showFlashMessage('success', data.message || `${fieldName.charAt(0).toUpperCase() + fieldName.slice(1)} updated successfully!`);

            // If username was changed, redirect to new profile URL
            if (fieldName === 'username') {
                setTimeout(() => {
                    window.location.href = `/user/${encodeURIComponent(newValue)}`;
                }, 1000);
            }
        } else {
            alert(data.message || `Failed to update ${fieldName}`);
        }
    } catch (error) {
        console.error('Error:', error);
        alert(`An error occurred while updating ${fieldName}`);
    }
}

// showFlashMessage is in static/common.js
// No need to redefine it here

// Password editing functions
function editPassword() {
    const display = document.getElementById('password-display');
    const inputs = document.getElementById('password-inputs');
    const editBtn = document.getElementById('password-edit-btn');
    const saveBtn = document.getElementById('password-save-btn');
    const cancelBtn = document.getElementById('password-cancel-btn');

    // Hide display and edit button, show inputs and action buttons
    display.classList.add('hidden');
    editBtn.classList.add('hidden');
    inputs.classList.remove('hidden');
    saveBtn.classList.remove('hidden');
    cancelBtn.classList.remove('hidden');

    // Focus the first input
    document.getElementById('current-password-input').focus();
}

function cancelPasswordEdit() {
    const display = document.getElementById('password-display');
    const inputs = document.getElementById('password-inputs');
    const editBtn = document.getElementById('password-edit-btn');
    const saveBtn = document.getElementById('password-save-btn');
    const cancelBtn = document.getElementById('password-cancel-btn');

    // Clear all password inputs
    document.getElementById('current-password-input').value = '';
    document.getElementById('new-password-input').value = '';
    document.getElementById('confirm-password-input').value = '';

    // Show display and edit button, hide inputs and action buttons
    display.classList.remove('hidden');
    editBtn.classList.remove('hidden');
    inputs.classList.add('hidden');
    saveBtn.classList.add('hidden');
    cancelBtn.classList.add('hidden');
}

async function savePassword() {
    const currentPassword = document.getElementById('current-password-input').value;
    const newPassword = document.getElementById('new-password-input').value;
    const confirmPassword = document.getElementById('confirm-password-input').value;

    // Validation
    if (!currentPassword) {
        alert('Please enter your current password');
        return;
    }

    if (!newPassword) {
        alert('Please enter a new password');
        return;
    }

    if (newPassword.length < 6) {
        alert('New password must be at least 6 characters long');
        return;
    }

    if (newPassword !== confirmPassword) {
        alert('New passwords do not match');
        return;
    }

    try {
        const response = await fetch('/user/update_password', {
            method: 'POST',
            headers: getCSRFHeaders(),
            body: JSON.stringify({
                current_password: currentPassword,
                new_password: newPassword,
                confirm_password: confirmPassword
            })
        });

        const data = await response.json();

        if (response.ok && data.success) {
            // Exit edit mode
            cancelPasswordEdit();

            // Show success message
            showFlashMessage('success', data.message || 'Password updated successfully!');
        } else {
            alert(data.message || 'Failed to update password');
        }
    } catch (error) {
        console.error('Error:', error);
        alert('An error occurred while updating password');
    }
}

// Avatar upload function
async function uploadAvatar(event) {
    const file = event.target.files[0];
    console.log('uploadAvatar called', file);

    if (!file) {
        console.log('No file selected');
        return;
    }

    console.log('File info:', {
        name: file.name,
        size: file.size,
        type: file.type
    });

    // Validate file type
    const allowedTypes = ['image/png', 'image/jpeg', 'image/jpg', 'image/gif', 'image/webp'];
    if (!allowedTypes.includes(file.type)) {
        alert('Please upload a valid image file (PNG, JPG, GIF, or WebP)');
        return;
    }

    // Show loading text
    const statusText = document.getElementById('avatar-upload-status');
    if (statusText) {
        statusText.classList.remove('hidden');
    }

    // Create FormData and append file
    const formData = new FormData();
    formData.append('avatar', file);
    addCSRFToFormData(formData); // Add CSRF token
    console.log('FormData created with file and CSRF token');

    try {
        console.log('Sending upload request to /user/upload_avatar');

        const response = await fetch('/user/upload_avatar', {
            method: 'POST',
            body: formData
        });

        console.log('Response status:', response.status);
        const data = await response.json();
        console.log('Response data:', data);

        if (response.ok && data.success) {
            console.log('Upload successful, avatar URL:', data.avatar_url);

            // Hide status text
            if (statusText) {
                statusText.classList.add('hidden');
            }

            // Update avatar display
            const avatarImage = document.getElementById('avatar-image');
            const avatarPlaceholder = document.getElementById('avatar-placeholder');

            if (avatarImage) {
                // Update existing image with cache bust
                console.log('Updating existing avatar image');
                avatarImage.src = data.avatar_url + '?t=' + new Date().getTime();
            } else if (avatarPlaceholder) {
                // Replace placeholder with image
                console.log('Replacing placeholder with new image');
                const newImg = document.createElement('img');
                newImg.id = 'avatar-image';
                newImg.src = data.avatar_url;
                newImg.alt = event.target.dataset.username;
                newImg.className = 'w-full h-full rounded-full object-cover';
                newImg.style.width = '64px';
                newImg.style.height = '64px';
                avatarPlaceholder.replaceWith(newImg);
            }

            // Update all other avatar instances on page without reload
            const sidebarAvatar = document.querySelector('.sidebar-avatar');
            if (sidebarAvatar) {
                sidebarAvatar.src = data.avatar_url + '?t=' + new Date().getTime();
            }

            // Show success message
            showFlashMessage('success', data.message || 'Profile picture updated successfully!');
        } else {
            console.error('Upload failed:', data.message);
            alert(data.message || 'Failed to upload profile picture');

            // Hide status text on error
            if (statusText) {
                statusText.classList.add('hidden');
            }
        }
    } catch (error) {
        console.error('Upload error:', error);
        alert('An error occurred while uploading profile picture: ' + error.message);

        // Hide status text on error
        if (statusText) {
            statusText.classList.add('hidden');
        }
    }

    // Reset file input
    event.target.value = '';
}

// Bio editing functions
function editBio() {
    const displayContainer = document.getElementById('bio-display-container');
    const editContainer = document.getElementById('bio-edit-container');
    const editBtn = document.getElementById('bio-edit-btn');
    const input = document.getElementById('bio-input');

    displayContainer.classList.add('hidden');
    editContainer.classList.remove('hidden');
    editBtn.classList.add('hidden');

    // Update character count
    updateCharCount();

    // Focus the textarea
    input.focus();
}

function cancelBioEdit() {
    const displayContainer = document.getElementById('bio-display-container');
    const editContainer = document.getElementById('bio-edit-container');
    const editBtn = document.getElementById('bio-edit-btn');
    const input = document.getElementById('bio-input');
    const display = document.getElementById('bio-display');

    // Reset textarea to original value
    input.value = input.defaultValue;   // the saved bio (updated by saveBio)

    displayContainer.classList.remove('hidden');
    editContainer.classList.add('hidden');
    editBtn.classList.remove('hidden');
}

async function saveBio() {
    const input = document.getElementById('bio-input');
    const newBio = input.value.trim();

    if (newBio.length > 500) {
        alert('Bio must be 500 characters or less!');
        return;
    }

    try {
        const response = await fetch('/user/update_bio', {
            method: 'POST',
            headers: getCSRFHeaders(),
            body: JSON.stringify({ bio: newBio })
        });

        const data = await response.json();

        if (response.ok && data.success) {
            // Update the display text
            const display = document.getElementById('bio-display');
            display.textContent = newBio || 'Add a bio to tell others about yourself...';
            input.defaultValue = newBio;   // what Cancel goes back to from now on

            // Exit edit mode
            cancelBioEdit();

            // Show success message
            showFlashMessage('success', data.message || 'Bio updated successfully!');
        } else {
            alert(data.message || 'Failed to update bio');
        }
    } catch (error) {
        console.error('Error:', error);
        alert('An error occurred while updating bio');
    }
}

function updateCharCount() {
    const input = document.getElementById('bio-input');
    const charCount = document.getElementById('bio-char-count');
    const count = input.value.length;
    charCount.textContent = `${count} / 500`;
}

// Add event listener for character count
const bioInput = document.getElementById('bio-input');
if (bioInput) {
    bioInput.addEventListener('input', updateCharCount);
    // Initialize count on page load
    updateCharCount();
}

// Friend search inline toggle functionality
const toggleBtn = document.getElementById('toggle-friend-search');
const closeBtn = document.getElementById('close-friend-search');
const searchContainer = document.getElementById('friend-search-container');
const searchInput = document.getElementById('friend-search-input');
const searchResults = document.getElementById('search-results');
let searchTimeout;

// Toggle search container
if (toggleBtn && searchContainer) {
    toggleBtn.addEventListener('click', function() {
        searchContainer.classList.toggle('hidden');
        if (!searchContainer.classList.contains('hidden')) {
            // Focus the search input when opening
            setTimeout(() => {
                if (searchInput) searchInput.focus();
            }, 100);
        }
    });
}

// Close search container
if (closeBtn && searchContainer) {
    closeBtn.addEventListener('click', function() {
        searchContainer.classList.add('hidden');
        if (searchInput) {
            searchInput.value = '';
            searchResults.innerHTML = '<p class="text-content-secondary text-center py-4 text-sm">Start typing to search for users...</p>';
        }
    });
}

// Search functionality
if (searchInput && searchResults) {
    searchInput.addEventListener('input', function(e) {
        clearTimeout(searchTimeout);
        const query = e.target.value.trim();

        if (query.length < 2) {
            searchResults.innerHTML = '<p class="text-content-secondary text-center py-4 text-sm">Start typing to search for users...</p>';
            return;
        }

        searchResults.innerHTML = '<p class="text-content-secondary text-center py-4 text-sm">Searching...</p>';

        searchTimeout = setTimeout(() => {
            fetch(`/friends/search_users?q=${encodeURIComponent(query)}`)
                .then(response => response.json())
                .then(users => {
                    if (users.length === 0) {
                        searchResults.innerHTML = '<p class="text-content-secondary text-center py-4 text-sm">No users found</p>';
                    } else {
                        const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'})[c]);
                        searchResults.innerHTML = users.map(user => {
                            const username = esc(user.username);
                            const userPath = esc(encodeURIComponent(user.username));
                            const avatarHtml = user.avatar_url
                                ? `<img src="/static/${esc(user.avatar_url)}" alt="${username}" class="w-10 h-10 rounded-full object-cover">`
                                : `<div class="w-10 h-10 rounded-full bg-accent flex items-center justify-center text-base font-bold text-on-accent">${esc(user.username[0].toUpperCase())}</div>`;

                            let actionHtml = '';
                            if (user.friendship_status === 'friends') {
                                actionHtml = '<span class="text-sm text-green-500">✓ Friends</span>';
                            } else if (user.friendship_status === 'request_sent') {
                                actionHtml = '<span class="text-sm text-content-secondary">Request Sent</span>';
                            } else if (user.friendship_status === 'request_received') {
                                actionHtml = '<span class="text-sm text-blue-500">Request Received</span>';
                            } else {
                                actionHtml = `<form method="POST" action="/friends/send_request/${userPath}" class="inline">
                                    <input type="hidden" name="csrf_token" value="${escapeHtml(getCSRFToken())}">
                                    <button type="submit" class="px-3 py-1 bg-accent hover:bg-accent-hover text-on-accent border border-card text-sm transition-colors">
                                        Add Friend
                                    </button>
                                </form>`;
                            }

                            return `
                                <div class="p-2 mt-2 hover:bg-primary transition-colors rounded-lg">
                                    <div class="flex items-center justify-between gap-3">
                                        <a href="/user/${userPath}" class="flex items-center gap-3 flex-1">
                                            ${avatarHtml}
                                            <div>
                                                <p class="text-content-primary font-medium">${username}</p>
                                            </div>
                                        </a>
                                        <div class="flex-shrink-0">
                                            ${actionHtml}
                                        </div>
                                    </div>
                                </div>
                            `;
                        }).join('');
                    }
                })
                .catch(error => {
                    console.error('Search error:', error);
                    searchResults.innerHTML = '<p class="text-red-500 text-center py-4 text-sm">Error searching users</p>';
                });
        }, 300);
    });
}

// ---- Appearance picker ---------------------------------------------------

// Appearance picker: apply instantly, then save; revert if the save fails.
document.querySelectorAll('#appearance-settings .theme-opt').forEach(btn => {
    btn.addEventListener('click', async () => {
        const kind = btn.dataset.kind;          // 'style' or 'mode'
        const root = document.documentElement;
        const previous = root.dataset[kind];
        const group = btn.parentElement.querySelectorAll('.theme-opt');
        const press = value => group.forEach(b => b.setAttribute('aria-pressed', String(b.dataset.value === value)));

        if (btn.dataset.value === previous) return;
        root.dataset[kind] = btn.dataset.value;
        press(btn.dataset.value);

        try {
            const response = await fetch('/user/update_theme', {
                method: 'POST',
                headers: getCSRFHeaders(),
                body: JSON.stringify({ [kind]: btn.dataset.value })
            });
            const data = await response.json();
            if (!response.ok || !data.success) throw new Error(data.message);
        } catch (err) {
            root.dataset[kind] = previous;
            press(previous);
            showFlashMessage('error', 'Could not save appearance settings.');
        }
    });
});

registerActions({
    toggleReviewText: button => toggleReviewText(button),
    switchTab: button => switchTab(button.dataset.tab),
    editField: button => editField(button.dataset.field),
    saveField: button => saveField(button.dataset.field),
    cancelEdit: button => cancelEdit(button.dataset.field),
    editPassword: () => editPassword(),
    savePassword: () => savePassword(),
    cancelPasswordEdit: () => cancelPasswordEdit(),
    uploadAvatar: (input, event) => uploadAvatar(event),
    editBio: () => editBio(),
    saveBio: () => saveBio(),
    cancelBioEdit: () => cancelBioEdit(),
});

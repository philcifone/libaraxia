// Admin settings (templates/admin_settings.html): the create/edit user form,
// avatars, and opening the deactivate/delete dialog.

'use strict';

// Store current editing user ID globally
let currentEditUserId = null;

// Switch to edit user form
function showEditForm(userId, username, email, isActive, isAdmin, avatarUrl) {
    console.log('Showing edit form for', username);
    currentEditUserId = userId;

    // Update the panel title
    document.getElementById('form-title').textContent = 'Edit User: ' + username;

    // Show cancel button
    document.getElementById('cancel-edit-btn').classList.remove('hidden');

    // Hide create form
    document.getElementById('create-user-form').classList.add('hidden');

    // Show edit form
    const editForm = document.getElementById('edit-user-form');
    editForm.classList.remove('hidden');

    // Populate user info
    const avatarImg = document.getElementById('edit-avatar-img');
    const avatarPlaceholder = document.getElementById('edit-avatar-placeholder');
    const removeAvatarBtn = document.getElementById('remove-avatar-btn');

    if (avatarUrl && avatarUrl !== '') {
        // Show image, hide placeholder
        avatarImg.src = '/static/' + avatarUrl;
        avatarImg.classList.remove('hidden');
        avatarPlaceholder.classList.add('hidden');
        removeAvatarBtn.classList.remove('hidden');
    } else {
        // Show placeholder, hide image
        avatarImg.classList.add('hidden');
        avatarPlaceholder.classList.remove('hidden');
        avatarPlaceholder.textContent = username[0].toUpperCase();
        removeAvatarBtn.classList.add('hidden');
    }

    document.getElementById('edit-username').textContent = username;
    document.getElementById('edit-email-display').textContent = email;

    // Set all hidden user IDs
    document.getElementById('edit-user-id-email').value = userId;
    document.getElementById('edit-user-id-password').value = userId;
    document.getElementById('edit-user-id-admin').value = userId;
    document.getElementById('edit-user-id-active').value = userId;
    document.getElementById('remove-user-btn').dataset.userId = userId;

    // Update toggle button styles
    const adminBtn = document.getElementById('admin-toggle-btn');
    const activeBtn = document.getElementById('active-toggle-btn');

    if (isAdmin) {
        adminBtn.textContent = 'Revoke Admin';
        adminBtn.className = 'w-full px-4 py-2 bg-red-900/50 hover:bg-red-900/70 text-red-400 rounded-lg transition-colors';
    } else {
        adminBtn.textContent = 'Make Admin';
        adminBtn.className = 'w-full px-4 py-2 bg-accent hover:bg-accent-hover text-on-accent rounded-lg btn';
    }

    if (isActive) {
        activeBtn.textContent = 'Deactivate';
        activeBtn.className = 'w-full px-4 py-2 bg-red-900/50 hover:bg-red-900/70 text-red-400 rounded-lg transition-colors';
    } else {
        activeBtn.textContent = 'Activate';
        activeBtn.className = 'w-full px-4 py-2 bg-accent hover:bg-accent-hover text-on-accent rounded-lg btn';
    }

    // Scroll to the form panel smoothly
    document.getElementById('user-form-panel').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// Reset back to create user form
function resetToCreateForm() {
    console.log('Resetting to create form');

    // Update the panel title
    document.getElementById('form-title').textContent = 'Create New User';

    // Hide cancel button
    document.getElementById('cancel-edit-btn').classList.add('hidden');

    // Show create form
    document.getElementById('create-user-form').classList.remove('hidden');

    // Hide edit form
    document.getElementById('edit-user-form').classList.add('hidden');

    // Clear create form inputs
    document.getElementById('create-user-form').reset();
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    console.log('Initializing admin user management');

    // Add click handlers to all edit buttons
    const editButtons = document.querySelectorAll('.edit-user-btn');
    console.log('Found', editButtons.length, 'edit buttons');

    editButtons.forEach(function(btn) {
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            console.log('Edit button clicked for user:', this.dataset.username);

            const userId = parseInt(this.dataset.userId);
            const username = this.dataset.username;
            const email = this.dataset.email;
            const isActive = parseInt(this.dataset.isActive) === 1;
            const isAdmin = parseInt(this.dataset.isAdmin) === 1;
            const avatarUrl = this.dataset.avatarUrl;

            showEditForm(userId, username, email, isActive, isAdmin, avatarUrl);
        });
    });

    console.log('Admin user management initialized successfully');
});

// Upload avatar for user being edited
async function uploadUserAvatar(event) {
    const file = event.target.files[0];
    if (!file || !currentEditUserId) return;

    console.log('Uploading avatar for user', currentEditUserId, file);

    // Validate file type
    const allowedTypes = ['image/png', 'image/jpeg', 'image/jpg', 'image/gif', 'image/webp'];
    if (!allowedTypes.includes(file.type)) {
        showFlashMessage('error', 'Please upload a valid image file (PNG, JPG, GIF, or WebP)');
        return;
    }

    // Show loading text
    const statusText = document.getElementById('admin-avatar-status');
    if (statusText) {
        statusText.classList.remove('hidden');
    }

    // Create FormData and append file and user_id
    const formData = new FormData();
    formData.append('avatar', file);
    formData.append('user_id', currentEditUserId);

    try {
        // Get CSRF token from meta tag or form
        const csrfToken = document.querySelector('input[name="csrf_token"]').value;
        formData.append('csrf_token', csrfToken);

        const response = await fetch('/admin/upload_user_avatar', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();
        console.log('Upload response:', data);

        if (response.ok && data.success) {
            // Hide status text
            if (statusText) {
                statusText.classList.add('hidden');
            }

            // Update avatar display
            const avatarImg = document.getElementById('edit-avatar-img');
            const avatarPlaceholder = document.getElementById('edit-avatar-placeholder');
            const removeAvatarBtn = document.getElementById('remove-avatar-btn');

            avatarImg.src = data.avatar_url + '?t=' + new Date().getTime();
            avatarImg.classList.remove('hidden');
            avatarPlaceholder.classList.add('hidden');
            removeAvatarBtn.classList.remove('hidden');

            // Update avatar in user table if visible
            const userRow = document.querySelector(`tr[data-user-id="${currentEditUserId}"]`);
            if (userRow) {
                const tableAvatar = userRow.querySelector('.user-table-avatar');
                if (tableAvatar) {
                    tableAvatar.src = data.avatar_url + '?t=' + new Date().getTime();
                }
            }

            showFlashMessage('success', data.message || 'Avatar uploaded successfully!');
        } else {
            showFlashMessage('error', data.message || 'Failed to upload avatar');

            // Hide status text on error
            if (statusText) {
                statusText.classList.add('hidden');
            }
        }
    } catch (error) {
        console.error('Upload error:', error);
        showFlashMessage('error', 'An error occurred while uploading avatar');

        // Hide status text on error
        if (statusText) {
            statusText.classList.add('hidden');
        }
    }

    // Reset file input
    event.target.value = '';
}

// Remove avatar for user being edited
async function removeUserAvatar() {
    if (!currentEditUserId) return;

    if (!await confirmDialog('Remove this user\'s avatar?')) return;

    try {
        // Get CSRF token
        const csrfToken = document.querySelector('input[name="csrf_token"]').value;

        const response = await fetch('/admin/remove_user_avatar', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            body: JSON.stringify({ user_id: currentEditUserId })
        });

        const data = await response.json();
        console.log('Remove response:', data);

        if (response.ok && data.success) {
            // Update avatar display
            const avatarImg = document.getElementById('edit-avatar-img');
            const avatarPlaceholder = document.getElementById('edit-avatar-placeholder');
            const removeAvatarBtn = document.getElementById('remove-avatar-btn');
            const username = document.getElementById('edit-username').textContent;

            avatarImg.classList.add('hidden');
            avatarPlaceholder.classList.remove('hidden');
            avatarPlaceholder.textContent = username[0].toUpperCase();
            removeAvatarBtn.classList.add('hidden');

            // Update avatar in user table if visible
            const userRow = document.querySelector(`tr[data-user-id="${currentEditUserId}"]`);
            if (userRow) {
                const tableAvatarContainer = userRow.querySelector('.user-avatar-container');
                if (tableAvatarContainer) {
                    // Replace image with placeholder
                    tableAvatarContainer.innerHTML = `
                        <div class="h-8 w-8 rounded-full bg-accent flex items-center justify-center text-on-accent text-sm font-bold">
                            ${escapeHtml(username[0].toUpperCase())}
                        </div>
                    `;
                }
            }

            showFlashMessage('success', data.message || 'Avatar removed successfully!');
        } else {
            showFlashMessage('error', data.message || 'Failed to remove avatar');
        }
    } catch (error) {
        console.error('Remove error:', error);
        showFlashMessage('error', 'An error occurred while removing avatar');
    }
}

registerActions({
    resetToCreateForm: () => resetToCreateForm(),
    uploadUserAvatar: (input, event) => uploadUserAvatar(event),
    removeUserAvatar: () => removeUserAvatar(),
    // The button's data-user-id is set by showEditForm. openAccountRemoval is in script.js.
    openUserRemoval: button => openAccountRemoval('/admin/users/' + encodeURIComponent(button.dataset.userId) + '/removal'),
});

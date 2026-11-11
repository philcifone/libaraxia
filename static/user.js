// Profile page (templates/user.html): long reviews, stats tabs, inline
// settings, avatar upload, bio and the appearance picker. (Friend search
// moved to the Friends page, static/friends.js.)
// Markup reaches these through data-click / data-change (registered at the
// bottom); values the server knows come from data- attributes.

'use strict';

// Long reviews use the shared "Read more" helper in common.js.

// ---- Stats tabs ----------------------------------------------------------

// Tab switching functionality
// Profile statistics (12.1, _profile_stats.html): the section's data-view
// (overview / insights) and data-kind (book / video / record) pick the one
// panel shown; the buttons say which is on.
function showStats(section) {
    const { view, kind } = section.dataset;
    section.querySelectorAll('[data-stats-panel]').forEach(panel => {
        panel.hidden = !(panel.dataset.view === view && panel.dataset.kind === kind);
    });
    section.querySelectorAll('[data-stats-view]').forEach(button => {
        const on = button.dataset.statsView === view;
        button.classList.toggle('active', on);
        button.setAttribute('aria-selected', on ? 'true' : 'false');
    });
    section.querySelectorAll('[data-stats-kind]').forEach(button => {
        const on = button.dataset.statsKind === kind;
        button.classList.toggle('tab-active', on);
        button.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
}

// ---- Inline settings (email, username, password, avatar, bio)

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
        showFlashMessage('error', `${fieldName.charAt(0).toUpperCase() + fieldName.slice(1)} cannot be empty!`);
        return;
    }

    // Basic email validation
    if (fieldName === 'email') {
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if (!emailRegex.test(newValue)) {
            showFlashMessage('error', 'Please enter a valid email address!');
            return;
        }
    }
    const body = { [fieldName]: newValue };
    if (fieldName === 'email') {
        body.current_password = document.getElementById('email-password-input').value;
        if (!body.current_password) {
            showFlashMessage('error', 'Enter your current password to change your email.');
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
            showFlashMessage('error', data.message || `Failed to update ${fieldName}`);
        }
    } catch (error) {
        console.error('Error:', error);
        showFlashMessage('error', `An error occurred while updating ${fieldName}`);
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
        showFlashMessage('error', 'Please enter your current password');
        return;
    }

    if (!newPassword) {
        showFlashMessage('error', 'Please enter a new password');
        return;
    }

    if (newPassword.length < 6) {
        showFlashMessage('error', 'New password must be at least 6 characters long');
        return;
    }

    if (newPassword !== confirmPassword) {
        showFlashMessage('error', 'New passwords do not match');
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
            showFlashMessage('error', data.message || 'Failed to update password');
        }
    } catch (error) {
        console.error('Error:', error);
        showFlashMessage('error', 'An error occurred while updating password');
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
        showFlashMessage('error', 'Please upload a valid image file (PNG, JPG, GIF, or WebP)');
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
            showFlashMessage('error', data.message || 'Failed to upload profile picture');

            // Hide status text on error
            if (statusText) {
                statusText.classList.add('hidden');
            }
        }
    } catch (error) {
        console.error('Upload error:', error);
        showFlashMessage('error', 'An error occurred while uploading profile picture: ' + error.message);

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
        showFlashMessage('error', 'Bio must be 500 characters or less!');
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
            showFlashMessage('error', data.message || 'Failed to update bio');
        }
    } catch (error) {
        console.error('Error:', error);
        showFlashMessage('error', 'An error occurred while updating bio');
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

// The Appearance picker (style and mode) is handled in sidebar.js, shared
// with the sidebar's Mode shortcut.

// Profile -> Recent bulk edits: undo in place, the row then says "Undone"
// (the grids' banner Undo is static/bulk.js)
async function bulkHistoryUndo(button) {
    button.disabled = true;
    let data = null;
    try {
        const res = await fetch(`/bulk/${encodeURIComponent(button.dataset.editId)}/undo`, {
            method: 'POST', headers: getCSRFHeaders(), body: JSON.stringify({ banner: false }) });
        data = await res.json();
    } catch { /* network or a non-JSON error page */ }
    if (data?.success) {
        const done = document.createElement('span');
        done.className = 'text-sm text-content-secondary';
        done.textContent = 'Undone';
        button.replaceWith(done);
        // Something left alone (changed since) is a yellow "done, but", not a green "done"
        showFlashMessage(data.skipped || !data.restored ? 'warning' : 'success', data.summary);
    } else {
        button.disabled = false;
        showFlashMessage('error', data?.error || 'Could not undo that.');
    }
}

registerActions({
    bulkHistoryUndo,
    statsView: button => {
        const section = button.closest('[data-stats]');
        section.dataset.view = button.dataset.statsView;
        showStats(section);
    },
    statsKind: button => {
        const section = button.closest('[data-stats]');
        section.dataset.kind = button.dataset.statsKind;
        showStats(section);
    },
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

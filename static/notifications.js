// Notifications and Friend Requests Handler

async function loadNotifications() {
    try {
        const response = await fetch('/friends/notifications');
        if (!response.ok) {
            throw new Error('Failed to fetch notifications');
        }

        const notifications = await response.json();
        displayNotifications(notifications);
    } catch (error) {
        console.error('Error loading notifications:', error);
        document.getElementById('notifications-container').innerHTML =
            '<div class="px-4 py-2 text-xs text-red-400">Failed to load notifications</div>';
    }
}

function displayNotifications(notifications) {
    console.log('Displaying notifications:', notifications);
    const container = document.getElementById('notifications-container');

    if (!notifications || notifications.length === 0) {
        container.innerHTML = '<div class="px-4 py-2 text-xs text-content-secondary">No new notifications</div>';
        return;
    }

    container.innerHTML = '';

    notifications.forEach(notif => {
        console.log('Creating notification item:', notif);
        const item = createNotificationItem(notif);
        container.appendChild(item);
    });
}

function createNotificationItem(notif) {
    const div = document.createElement('div');
    div.className = `px-4 py-2 text-xs ${notif.is_read === false ? 'bg-accent/10' : ''} hover:bg-primary/20 transition-colors`;

    // Create avatar/icon
    let avatar = '';
    if (notif.avatar_url || notif.from_avatar_url) {
        const avatarUrl = notif.avatar_url || notif.from_avatar_url;
        avatar = `<img src="/static/${avatarUrl}" class="w-8 h-8 rounded-full object-cover" alt="">`;
    } else if (notif.username || notif.from_username) {
        const username = notif.username || notif.from_username;
        avatar = `<div class="w-8 h-8 rounded-full bg-accent flex items-center justify-center text-white text-sm font-semibold">${username[0].toUpperCase()}</div>`;
    }

    if (notif.type === 'friend_request') {
        div.innerHTML = `
            <div class="flex items-start gap-2">
                ${avatar}
                <div class="flex-1 min-w-0">
                    <p class="text-content-primary text-xs mb-1">${notif.message}</p>
                    <div class="flex gap-1 mt-1">
                        <button onclick="acceptFriendRequest(${notif.id}, ${notif.sender_id})"
                                class="px-2 py-1 bg-green-600 hover:bg-green-700 text-white rounded text-xs transition-colors">
                            Accept
                        </button>
                        <button onclick="declineFriendRequest(${notif.id})"
                                class="px-2 py-1 bg-gray-600 hover:bg-gray-700 text-white rounded text-xs transition-colors">
                            Decline
                        </button>
                    </div>
                </div>
            </div>
        `;
    } else {
        div.innerHTML = `
            <div class="flex items-start gap-2">
                ${avatar}
                <div class="flex-1 min-w-0">
                    <p class="text-content-primary text-xs">${notif.message}</p>
                    <p class="text-content-secondary text-xs mt-0.5">${formatTimestamp(notif.created_at)}</p>
                </div>
                <button onclick="event.stopPropagation(); dismissNotification(${notif.id});"
                        class="text-content-secondary hover:text-red-400 transition-colors p-1 flex-shrink-0"
                        title="Dismiss">
                    <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                    </svg>
                </button>
            </div>
        `;
    }

    return div;
}

async function acceptFriendRequest(requestId, senderId) {
    try {
        const csrfToken = getCSRFToken();
        const response = await fetch(`/friends/accept/${requestId}`, {
            method: 'POST',
            headers: {
                'X-CSRFToken': csrfToken,
                'Content-Type': 'application/x-www-form-urlencoded'
            },
            body: `csrf_token=${encodeURIComponent(csrfToken)}`
        });

        if (response.ok) {
            // Reload notifications to update the UI
            loadNotifications();
            showToast('Friend request accepted!', 'success');
        } else {
            showToast('Failed to accept friend request', 'error');
        }
    } catch (error) {
        console.error('Error accepting friend request:', error);
        showToast('Error accepting friend request', 'error');
    }
}

async function declineFriendRequest(requestId) {
    try {
        const csrfToken = getCSRFToken();
        const response = await fetch(`/friends/decline/${requestId}`, {
            method: 'POST',
            headers: {
                'X-CSRFToken': csrfToken,
                'Content-Type': 'application/x-www-form-urlencoded'
            },
            body: `csrf_token=${encodeURIComponent(csrfToken)}`
        });

        if (response.ok) {
            // Reload notifications to update the UI
            loadNotifications();
            showToast('Friend request declined', 'info');
        } else {
            showToast('Failed to decline friend request', 'error');
        }
    } catch (error) {
        console.error('Error declining friend request:', error);
        showToast('Error declining friend request', 'error');
    }
}

async function markNotificationRead(notificationId) {
    try {
        const csrfToken = getCSRFToken();
        await fetch(`/friends/mark_notification_read/${notificationId}`, {
            method: 'POST',
            headers: {
                'X-CSRFToken': csrfToken
            }
        });
        // Reload notifications to update the UI
        loadNotifications();
    } catch (error) {
        console.error('Error marking notification as read:', error);
    }
}

async function dismissNotification(notificationId) {
    console.log('Dismissing notification:', notificationId);

    try {
        const csrfToken = getCSRFToken();
        console.log('CSRF Token:', csrfToken);

        const response = await fetch(`/friends/dismiss_notification/${notificationId}`, {
            method: 'POST',
            headers: {
                'X-CSRFToken': csrfToken,
                'Content-Type': 'application/json'
            }
        });

        console.log('Response status:', response.status);
        const data = await response.json();
        console.log('Response data:', data);

        if (response.ok && data.success) {
            console.log('Notification dismissed successfully');
            showToast('Notification dismissed', 'info');
            // Reload notifications to update the UI
            loadNotifications();
        } else {
            console.error('Failed to dismiss:', data);
            showToast('Failed to dismiss notification', 'error');
        }
    } catch (error) {
        console.error('Error dismissing notification:', error);
        showToast('Error dismissing notification: ' + error.message, 'error');
    }
}

function formatTimestamp(timestamp) {
    const date = new Date(timestamp);
    const now = new Date();
    const diff = now - date;
    const seconds = Math.floor(diff / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);
    const days = Math.floor(hours / 24);

    if (seconds < 60) return 'Just now';
    if (minutes < 60) return `${minutes}m ago`;
    if (hours < 24) return `${hours}h ago`;
    if (days < 7) return `${days}d ago`;

    return date.toLocaleDateString();
}

function showToast(message, type = 'info') {
    // Simple toast implementation - you can enhance this
    const colors = {
        success: 'bg-green-600',
        error: 'bg-red-600',
        info: 'bg-blue-600'
    };

    const toast = document.createElement('div');
    toast.className = `fixed top-20 right-4 ${colors[type]} text-white px-4 py-2 rounded shadow-lg z-50 transition-opacity`;
    toast.textContent = message;
    document.body.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

function getCSRFToken() {
    // Try to get from meta tag first
    const metaTag = document.querySelector('meta[name="csrf-token"]');
    if (metaTag) {
        return metaTag.content;
    }

    // Fallback to cookie
    const cookies = document.cookie.split(';');
    for (let cookie of cookies) {
        const [name, value] = cookie.trim().split('=');
        if (name === 'csrf_token') {
            return decodeURIComponent(value);
        }
    }

    return '';
}

// Load notifications when the page loads
document.addEventListener('DOMContentLoaded', () => {
    loadNotifications();

    // Refresh notifications every 30 seconds
    setInterval(loadNotifications, 30000);
});

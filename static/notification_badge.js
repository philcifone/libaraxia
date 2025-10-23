// Simple notification badge - shows red dot when there are notifications

async function updateNotificationBadge() {
    try {
        const response = await fetch('/friends/notification_count');
        if (!response.ok) return;

        const data = await response.json();
        const badge = document.getElementById('notification-badge');

        if (badge) {
            if (data.count > 0) {
                badge.classList.remove('hidden');
            } else {
                badge.classList.add('hidden');
            }
        }
    } catch (error) {
        console.error('Error fetching notification count:', error);
    }
}

// Update badge on page load
document.addEventListener('DOMContentLoaded', updateNotificationBadge);

// Refresh badge every 30 seconds
setInterval(updateNotificationBadge, 30000);

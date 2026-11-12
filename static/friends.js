// The Friends page (templates/friends.html, ROADMAP 11.3): find users by
// username and send a request. Moved from the profile page (user.js).
// Results are built as HTML, so every value goes through escapeHtml
// (common.js) and URL path parts through encodeURIComponent.

const searchInput = document.getElementById('friend-search-input');
const searchResults = document.getElementById('search-results');
let searchTimeout;

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
                                        searchResults.innerHTML = users.map(user => {
                            const username = escapeHtml(user.username);
                            const userPath = escapeHtml(encodeURIComponent(user.username));
                            const avatarHtml = user.avatar_url
                                ? `<img src="/static/${escapeHtml(user.avatar_url)}" alt="${username}" class="w-10 h-10 rounded-full object-cover">`
                                : `<div class="w-10 h-10 rounded-full bg-accent flex items-center justify-center text-base font-bold text-on-accent">${escapeHtml(user.username[0].toUpperCase())}</div>`;

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
                                    <button type="submit" class="px-3 py-1 bg-accent hover:bg-accent-hover text-on-accent text-sm btn rounded-lg">
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

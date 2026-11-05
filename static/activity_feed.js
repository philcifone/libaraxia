// Activity feed (templates/activity_feed.html): liking and unliking.

'use strict';

async function toggleLike(button) {
    const activityType = button.dataset.activityType;
    const bookId = JSON.parse(button.dataset.bookId);            // number or null
    const activityUserId = JSON.parse(button.dataset.activityUserId);
    const isLiked = button.dataset.liked === 'true';
    const endpoint = isLiked ? '/feed/unlike_activity' : '/feed/like_activity';

    try {
        const response = await fetch(endpoint, {
            method: 'POST',
            headers: getCSRFHeaders(),
            body: JSON.stringify({
                activity_type: activityType,
                book_id: bookId,
                activity_user_id: activityUserId
            })
        });

        const data = await response.json();

        if (data.success) {
            // Toggle the liked state
            button.dataset.liked = isLiked ? 'false' : 'true';

            // Update the heart icon
            const svg = button.querySelector('svg');
            if (isLiked) {
                svg.classList.remove('fill-red-500', 'text-red-500');
                svg.classList.add('fill-none');
                button.title = 'Like';
            } else {
                svg.classList.remove('fill-none');
                svg.classList.add('fill-red-500', 'text-red-500');
                button.title = 'Unlike';
            }

            // Update the like count
            const likeCountSpan = button.querySelector('.like-count');
            likeCountSpan.textContent = data.like_count > 0 ? data.like_count : '';
        } else {
            console.error('Error toggling like:', data.error);
            if (data.error === 'Cannot like your own activity') {
                alert('You cannot like your own activity!');
            }
        }
    } catch (error) {
        console.error('Error:', error);
        alert('An error occurred while processing your request.');
    }
}

registerActions({ toggleLike });

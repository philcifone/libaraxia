from flask import render_template, Blueprint
from flask_login import login_required, current_user
from utils.database import get_db_connection

feed_blueprint = Blueprint('feed', __name__, template_folder='templates')


@feed_blueprint.route("/activity")
@login_required
def activity_feed():
    """Display a social feed of recent book additions and reviews"""
    conn = get_db_connection()
    try:
        # Fetch recent book additions (last 20)
        recent_books = conn.execute("""
            SELECT
                b.id,
                b.title,
                b.author,
                b.cover_image_url,
                b.created_at,
                b.genre,
                b.added_by,
                u.username,
                'book_added' as activity_type
            FROM books b
            LEFT JOIN users u ON b.added_by = u.id
            ORDER BY b.created_at DESC
            LIMIT 20
        """).fetchall()

        # Fetch recent reviews/ratings (last 20)
        recent_reviews = conn.execute("""
            SELECT
                r.user_id,
                r.book_id,
                r.date_read,
                r.rating,
                r.comment,
                b.title,
                b.author,
                b.cover_image_url,
                u.username,
                'review_added' as activity_type
            FROM read_data r
            JOIN books b ON r.book_id = b.id
            JOIN users u ON r.user_id = u.id
            WHERE r.rating IS NOT NULL OR r.comment IS NOT NULL
            ORDER BY r.date_read DESC
            LIMIT 20
        """).fetchall()

        # Combine and sort all activities by date
        activities = []

        for book in recent_books:
            activities.append({
                'type': 'book_added',
                'date': book['created_at'],
                'book_id': book['id'],
                'title': book['title'],
                'author': book['author'],
                'cover_image_url': book['cover_image_url'],
                'genre': book['genre'],
                'username': book['username'],
                'user_id': book['added_by']
            })

        for review in recent_reviews:
            activities.append({
                'type': 'review_added',
                'date': review['date_read'],
                'book_id': review['book_id'],
                'title': review['title'],
                'author': review['author'],
                'cover_image_url': review['cover_image_url'],
                'username': review['username'],
                'user_id': review['user_id'],
                'rating': review['rating'],
                'comment': review['comment']
            })

        # Sort by date, most recent first
        activities.sort(key=lambda x: x['date'] if x['date'] else '', reverse=True)

        # Limit to 30 most recent activities
        activities = activities[:30]

        return render_template("activity_feed.html", activities=activities)

    finally:
        conn.close()

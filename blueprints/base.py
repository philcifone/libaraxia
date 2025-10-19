from flask import render_template, redirect, url_for, request, Blueprint, jsonify
from flask_login import login_required, current_user
from utils.database import get_db_connection
from datetime import datetime
from utils.book_utils import get_filter_options

base_blueprint = Blueprint('base', __name__, template_folder='templates')

def get_filter_options():
    """Get all filter options from the database"""
    conn = get_db_connection()
    try:
        # Get unique genres (case-insensitive)
        genres = conn.execute('''
            SELECT genre
            FROM books
            WHERE genre IS NOT NULL
            GROUP BY LOWER(genre)
            ORDER BY LOWER(genre)
        ''').fetchall()
        
        # Get unique read statuses
        read_statuses = conn.execute('''
            SELECT DISTINCT status 
            FROM collections 
            WHERE status IS NOT NULL 
            ORDER BY status
        ''').fetchall()
        
        # Get all tags
        tags = conn.execute('''
            SELECT DISTINCT tag_name 
            FROM book_tags 
            WHERE tag_name IS NOT NULL 
            ORDER BY tag_name
        ''').fetchall()

        # Create date range options
        date_ranges = [
            {"value": "all", "label": "All Time"},
            {"value": "this_year", "label": "This Year"},
            {"value": "last_year", "label": "Last Year"},
            {"value": "older", "label": "Older"}
        ]

        return {
            "genres": [genre[0] for genre in genres],
            "read_statuses": [status[0] for status in read_statuses],
            "tags": [tag[0] for tag in tags],
            "date_ranges": date_ranges,
            "ratings": list(range(1, 6))  # 1 to 5 stars
        }
    finally:
        conn.close()

@base_blueprint.route("/")
def home():
    if current_user.is_authenticated:
        return redirect(url_for('base.index'))
    return redirect(url_for('auth.login'))

@base_blueprint.route("/index")
@login_required
def index():
    # Get pagination parameters
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 30, type=int)

    # Get sort parameters with validation
    sort_by = request.args.get("sort_by", "title")
    sort_order = request.args.get("sort_order", "asc")

    valid_columns = {"title", "author", "publish_year", "created_at"}
    valid_orders = {"asc", "desc"}

    if sort_by not in valid_columns:
        sort_by = "title"
    if sort_order not in valid_orders:
        sort_order = "asc"

    # Limit per_page to reasonable values
    per_page = max(12, min(per_page, 100))

    conn = get_db_connection()
    try:
        # Simplified query - just get books not in wishlist
        query = '''
            SELECT b.* FROM books b
            WHERE NOT EXISTS (SELECT 1 FROM wishlist w WHERE w.book_id = b.id)
        '''
        params = []

        # Apply filters if they exist (simplified - no complex joins unless needed)
        if request.args.get('genre'):
            query += " AND LOWER(b.genre) = LOWER(?)"
            params.append(request.args.get('genre'))

        if request.args.get('read_status'):
            query += " AND EXISTS (SELECT 1 FROM collections c WHERE c.book_id = b.id AND c.user_id = ? AND c.status = ?)"
            params.extend([current_user.id, request.args.get('read_status')])

        if request.args.get('rating'):
            query += " AND EXISTS (SELECT 1 FROM read_data r WHERE r.book_id = b.id AND r.user_id = ? AND r.rating = ?)"
            params.extend([current_user.id, int(request.args.get('rating'))])

        tags = request.args.getlist('tags[]')
        if tags:
            # Validate tags exist for this user
            valid_tags_query = 'SELECT DISTINCT tag_name FROM book_tags WHERE user_id = ?'
            valid_tags = [row['tag_name'] for row in conn.execute(valid_tags_query, (current_user.id,)).fetchall()]

            # Filter to only valid tags
            valid_tags_in_request = [tag for tag in tags if tag in valid_tags]
            if valid_tags_in_request:
                placeholders = ','.join(['?' for _ in valid_tags_in_request])
                query += f" AND EXISTS (SELECT 1 FROM book_tags t WHERE t.book_id = b.id AND t.user_id = ? AND t.tag_name IN ({placeholders}))"
                params.append(current_user.id)
                params.extend(valid_tags_in_request)

        # Get total count before pagination
        count_query = query.replace("SELECT b.*", "SELECT COUNT(b.id)")
        total_count = conn.execute(count_query, params).fetchone()[0]

        # Add sorting and pagination
        query += f" ORDER BY b.{sort_by} {sort_order} LIMIT ? OFFSET ?"
        offset = (page - 1) * per_page
        params.extend([per_page, offset])

        # Get paginated books
        books = conn.execute(query, params).fetchall()
        has_more = (offset + len(books)) < total_count

        # Handle AJAX requests for infinite scroll
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            books_data = [{
                'id': book['id'],
                'title': book['title'],
                'author': book['author'],
                'cover_image_url': book['cover_image_url']
            } for book in books]

            return jsonify({
                'books': books_data,
                'total_count': total_count,
                'has_more': has_more,
                'current_page': page
            })

        # Get filter options for the template
        filter_options = get_filter_options()

        return render_template("index.html",
                             books=books,
                             filter_options=filter_options,
                             sort_by=sort_by,
                             sort_order=sort_order,
                             total_count=total_count,
                             has_more=has_more,
                             current_page=page)
    finally:
        conn.close()



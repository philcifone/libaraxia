from flask import render_template, redirect, url_for, request, Blueprint
from flask_login import login_required, current_user
from utils.database import get_db_connection
from datetime import datetime
from utils.book_utils import get_filter_options

base_blueprint = Blueprint('base', __name__, template_folder='templates')

def get_filter_options():
    """Get all filter options from the database"""
    conn = get_db_connection()
    try:
        # Get unique genres
        genres = conn.execute('''
            SELECT DISTINCT genre 
            FROM books 
            WHERE genre IS NOT NULL 
            ORDER BY genre
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
    # Get sort parameters with validation
    sort_by = request.args.get("sort_by", "title")
    sort_order = request.args.get("sort_order", "asc")

    valid_columns = {"title", "author", "publish_year", "created_at"}
    valid_orders = {"asc", "desc"}

    if sort_by not in valid_columns:
        sort_by = "title"
    if sort_order not in valid_orders:
        sort_order = "asc"

    # Build the base query
    query = '''
        SELECT DISTINCT b.* FROM books b
        LEFT JOIN collections c ON b.id = c.book_id AND c.user_id = ?
        LEFT JOIN read_data r ON b.id = r.book_id AND r.user_id = ?
        LEFT JOIN book_tags t ON b.id = t.book_id AND t.user_id = ?
    '''
    params = [current_user.id, current_user.id, current_user.id]
    conditions = []

    # Apply filters if they exist
    if request.args.get('genre'):
        conditions.append("b.genre = ?")
        params.append(request.args.get('genre'))
    
    if request.args.get('read_status'):
        conditions.append("c.status = ?")
        params.append(request.args.get('read_status'))
    
    if request.args.get('rating'):
        conditions.append("r.rating = ?")
        params.append(request.args.get('rating'))
    
    tags = request.args.getlist('tags[]')
    if tags:
        # Only use tags from the database
        valid_tags_query = '''
            SELECT DISTINCT tag_name FROM book_tags WHERE user_id = ?
        '''
        conn = get_db_connection()
        valid_tags = [row['tag_name'] for row in conn.execute(valid_tags_query, (current_user.id,)).fetchall()]
        conn.close()

        # Filter to only include valid tags
        valid_tags_in_request = [tag for tag in tags if tag in valid_tags]
        if valid_tags_in_request:
            placeholders = ','.join(['?' for _ in valid_tags_in_request])
            conditions.append(f"t.tag_name IN ({placeholders})")
            params.extend(valid_tags_in_request)
    
    if request.args.get('date_range'):
        date_range = request.args.get('date_range')
        current_year = datetime.now().year
        if date_range == 'this_year':
            conditions.append("strftime('%Y', b.publish_year) = ?")
            params.append(str(current_year))
        elif date_range == 'last_year':
            conditions.append("strftime('%Y', b.publish_year) = ?")
            params.append(str(current_year - 1))
        elif date_range == 'older':
            conditions.append("strftime('%Y', b.publish_year) < ?")
            params.append(str(current_year - 1))

    # Add WHERE clause if conditions exist
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    
    # Add sorting
    query += f" ORDER BY {sort_by} {sort_order}"

    # Execute query
    conn = get_db_connection()
    try:
        books = conn.execute(query, params).fetchall()
        
        # Get filter options for the template
        filter_options = get_filter_options()
        
        return render_template("index.html",
                             books=books,
                             filter_options=filter_options,
                             sort_by=sort_by,
                             sort_order=sort_order)
    finally:
        conn.close()



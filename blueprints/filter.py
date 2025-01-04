from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from utils.database import get_db_connection
from datetime import datetime, timedelta

filter_blueprint = Blueprint('filter', __name__)

@filter_blueprint.route('/apply', methods=['GET'])
@login_required
def apply_filters():
    # Get filter parameters
    genre = request.args.get('genre')
    read_status = request.args.get('read_status')
    date_range = request.args.get('date_range')
    tags = request.args.getlist('tags[]')
    rating = request.args.get('rating')
    
    # Build the query dynamically
    query = '''
        SELECT DISTINCT b.* FROM books b
        LEFT JOIN collections c ON b.id = c.book_id AND c.user_id = ?
        LEFT JOIN read_data r ON b.id = r.book_id AND r.user_id = ?
        LEFT JOIN book_tags t ON b.id = t.book_id AND t.user_id = ?
    '''
    params = [current_user.id, current_user.id, current_user.id]
    
    # List to store WHERE conditions
    conditions = []
    
    if genre:
        conditions.append("b.genre = ?")
        params.append(genre)
    
    if read_status:
        conditions.append("c.status = ?")
        params.append(read_status)
    
    if rating:
        conditions.append("r.rating = ?")
        params.append(rating)
    
    if tags:
        placeholders = ','.join(['?' for _ in tags])
        conditions.append(f"t.tag_name IN ({placeholders})")
        params.extend(tags)
    
    if date_range:
        current_year = datetime.now().year
        if date_range == 'this_year':
            conditions.append("strftime('%Y', r.date_read) = ?")
            params.append(str(current_year))
        elif date_range == 'last_year':
            conditions.append("strftime('%Y', r.date_read) = ?")
            params.append(str(current_year - 1))
    
    # Add WHERE clause if conditions exist
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    
    # Add sorting
    sort_by = request.args.get('sort_by', 'title')
    sort_order = request.args.get('sort_order', 'asc')
    query += f" ORDER BY b.{sort_by} {sort_order}"
    
    # Execute query
    conn = get_db_connection()
    try:
        books = conn.execute(query, params).fetchall()
        
        # Calculate statistics
        stats = calculate_stats(conn, current_user.id, date_range)
        
        return jsonify({
            'books': [dict(book) for book in books],
            'stats': stats
        })
    finally:
        conn.close()

def calculate_stats(conn, user_id, date_range=None):
    """Calculate reading statistics based on filters"""
    base_query = '''
        SELECT 
            COUNT(DISTINCT r.book_id) as books_read,
            SUM(b.page_count) as pages_read,
            AVG(r.rating) as avg_rating
        FROM read_data r
        JOIN books b ON r.book_id = b.id
        WHERE r.user_id = ?
    '''
    params = [user_id]
    
    if date_range:
        current_year = datetime.now().year
        if date_range == 'this_year':
            base_query += " AND strftime('%Y', r.date_read) = ?"
            params.append(str(current_year))
        elif date_range == 'last_year':
            base_query += " AND strftime('%Y', r.date_read) = ?"
            params.append(str(current_year - 1))
    
    stats = conn.execute(base_query, params).fetchone()
    return dict(stats)


@filter_blueprint.route('/filter/options')
def get_filter_options():
    try:
        # Get unique values from your database
        genres = db.session.query(distinct(Book.genre)).filter(Book.genre != None).all()
        genres = [g[0] for g in genres]  # Unpack from tuples

        read_statuses = db.session.query(distinct(Book.read_status)).filter(Book.read_status != None).all()
        read_statuses = [rs[0] for rs in read_statuses]

        # Get unique tags (assuming you have a tags relationship)
        tags = db.session.query(distinct(Tag.name)).all()
        tags = [t[0] for t in tags]

        # Define date ranges
        date_ranges = [
            {"value": "all", "label": "All Time"},
            {"value": "2024", "label": "2024"},
            {"value": "2023", "label": "2023"},
            {"value": "older", "label": "Older"}
        ]

        # Define ratings
        ratings = list(range(1, 6))  # 1 to 5 stars

        return jsonify({
            "genres": ["All"] + genres,
            "read_statuses": ["All"] + read_statuses,
            "tags": tags,
            "date_ranges": date_ranges,
            "ratings": ratings
        })
    except Exception as e:
        print(f"Error getting filter options: {str(e)}")
        return jsonify({"error": "Failed to get filter options"}), 500

@filter_blueprint.route('/api/books/filter', methods=['POST'])
def filter_books():
    try:
        filters = request.get_json()
        
        # Start with base query
        query = Book.query
        
        # Apply filters if they're not 'All' or empty
        if filters.get('genre') and filters['genre'] != 'All':
            query = query.filter(Book.genre == filters['genre'])
            
        if filters.get('read_status') and filters['read_status'] != 'All':
            query = query.filter(Book.read_status == filters['read_status'])
            
        if filters.get('rating'):
            query = query.filter(Book.rating == int(filters['rating']))
            
        if filters.get('date_range'):
            if filters['date_range'] == '2024':
                query = query.filter(extract('year', Book.publish_year) == 2024)
            elif filters['date_range'] == '2023':
                query = query.filter(extract('year', Book.publish_year) == 2023)
            elif filters['date_range'] == 'older':
                query = query.filter(extract('year', Book.publish_year) < 2023)
        
        # Apply tag filters if any
        if filters.get('tags'):
            for tag in filters['tags']:
                query = query.filter(Book.tags.any(Tag.name == tag))
        
        # Execute query
        books = query.all()
        
        # Calculate stats
        stats = {
            "books_read": len([b for b in books if b.read_status == 'Read']),
            "pages_read": sum(b.pages for b in books if b.read_status == 'Read' and b.pages),
            "average_rating": sum(b.rating for b in books if b.rating) / len([b for b in books if b.rating]) if any(b.rating for b in books) else 0
        }
        
        return jsonify({
            "books": [book.to_dict() for book in books],
            "stats": stats
        })
    except Exception as e:
        print(f"Error filtering books: {str(e)}")
        return jsonify({"error": "Failed to filter books"}), 500
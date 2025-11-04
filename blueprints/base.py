from flask import render_template, redirect, url_for, request, Blueprint, jsonify
from flask_login import login_required, current_user
from utils.database import get_db_connection
from datetime import datetime
from utils.book_utils import get_filter_options
from models import get_library_members, is_friends_with, can_view_content

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
        # "My Library" now shows ONLY books added by current user
        query = '''
            SELECT b.* FROM books b
            WHERE b.added_by = ?
            AND NOT EXISTS (SELECT 1 FROM wishlist w WHERE w.book_id = b.id AND w.user_id = ?)
        '''
        params = [current_user.id, current_user.id]

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


@base_blueprint.route("/shared-library")
@login_required
def shared_library():
    """View combined library from all users in your shared library group"""
    # Get pagination parameters
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 30, type=int)
    sort_by = request.args.get("sort_by", "title")
    sort_order = request.args.get("sort_order", "asc")
    member_filter = request.args.get("member", type=int)

    valid_columns = {"title", "author", "publish_year", "created_at"}
    valid_orders = {"asc", "desc"}

    if sort_by not in valid_columns:
        sort_by = "title"
    if sort_order not in valid_orders:
        sort_order = "asc"

    per_page = max(12, min(per_page, 100))

    conn = get_db_connection()
    try:
        # Get all users in shared library (from library_members table)
        shared_user_ids = get_library_members(current_user.id)

        # If member filter is applied, validate it's in the shared library
        if member_filter:
            if member_filter not in shared_user_ids:
                # Invalid member filter, ignore it
                member_filter = None
            else:
                # Filter to show books from selected member AND current user
                shared_user_ids = [member_filter, current_user.id]
                # Remove duplicate if user selected themselves
                shared_user_ids = list(set(shared_user_ids))

        # Build query to show books from all shared library members (or filtered member)
        placeholders = ','.join(['?' for _ in shared_user_ids])
        query = f'''
            SELECT b.* FROM books b
            WHERE b.added_by IN ({placeholders})
            AND NOT EXISTS (SELECT 1 FROM wishlist w WHERE w.book_id = b.id AND w.user_id IN ({placeholders}))
        '''
        params = shared_user_ids + shared_user_ids

        # Apply filters
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
            valid_tags_query = 'SELECT DISTINCT tag_name FROM book_tags WHERE user_id = ?'
            valid_tags = [row['tag_name'] for row in conn.execute(valid_tags_query, (current_user.id,)).fetchall()]
            valid_tags_in_request = [tag for tag in tags if tag in valid_tags]
            if valid_tags_in_request:
                placeholders_tags = ','.join(['?' for _ in valid_tags_in_request])
                query += f" AND EXISTS (SELECT 1 FROM book_tags t WHERE t.book_id = b.id AND t.user_id = ? AND t.tag_name IN ({placeholders_tags}))"
                params.append(current_user.id)
                params.extend(valid_tags_in_request)

        # Get total count
        count_query = query.replace("SELECT b.*", "SELECT COUNT(b.id)")
        total_count = conn.execute(count_query, params).fetchone()[0]

        # Add sorting and pagination
        query += f" ORDER BY b.{sort_by} {sort_order} LIMIT ? OFFSET ?"
        offset = (page - 1) * per_page
        params.extend([per_page, offset])

        books = conn.execute(query, params).fetchall()
        has_more = (offset + len(books)) < total_count

        # Handle AJAX requests
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

        # Get shared library members for display (always get all members, not filtered)
        all_library_members = get_library_members(current_user.id)
        shared_members = []
        if len(all_library_members) > 0:
            placeholders_members = ','.join(['?' for _ in all_library_members])
            shared_members = conn.execute(
                f'SELECT id, username, avatar_url FROM users WHERE id IN ({placeholders_members})',
                all_library_members
            ).fetchall()

        filter_options = get_filter_options()

        return render_template("shared_library.html",
                             books=books,
                             filter_options=filter_options,
                             sort_by=sort_by,
                             sort_order=sort_order,
                             total_count=total_count,
                             has_more=has_more,
                             current_page=page,
                             shared_members=shared_members,
                             member_filter=member_filter)
    finally:
        conn.close()


@base_blueprint.route("/friends-libraries")
@login_required
def friends_libraries():
    """View all friends and their library stats"""
    conn = get_db_connection()
    try:
        # Get all friends with their book counts
        friends = conn.execute('''
            SELECT
                u.id,
                u.username,
                u.avatar_url,
                u.bio,
                COUNT(DISTINCT b.id) as book_count
            FROM users u
            JOIN friendships f ON (
                (f.user_id_1 = ? AND f.user_id_2 = u.id) OR
                (f.user_id_2 = ? AND f.user_id_1 = u.id)
            )
            LEFT JOIN books b ON b.added_by = u.id
            GROUP BY u.id
            ORDER BY u.username
        ''', (current_user.id, current_user.id)).fetchall()

        return render_template('friends_libraries.html', friends=friends)
    finally:
        conn.close()


@base_blueprint.route("/library/<username>")
@login_required
def friend_library(username):
    """View a friend's library"""
    conn = get_db_connection()
    try:
        # Get the friend's user info
        friend = conn.execute(
            'SELECT id, username, avatar_url, bio, reading_goal FROM users WHERE username = ?',
            (username,)
        ).fetchone()

        if not friend:
            from flask import flash, abort
            abort(404)

        # Check if they are friends or if the user is viewing their own library
        if friend['id'] != current_user.id and not is_friends_with(current_user.id, friend['id']):
            from flask import flash, abort
            flash('You must be friends to view this library', 'warning')
            abort(403)

        # Get shelf filter
        shelf = request.args.get('shelf')

        # Build query to get friend's books
        if shelf == 'wishlist':
            # Show wishlist books
            query = '''
                SELECT DISTINCT b.*
                FROM books b
                JOIN wishlist w ON b.id = w.book_id
                WHERE w.user_id = ?
            '''
            params = [friend['id']]
        else:
            # Show library books (excluding wishlist)
            query = '''
                SELECT DISTINCT b.*
                FROM books b
                WHERE b.added_by = ?
                AND NOT EXISTS (
                    SELECT 1 FROM wishlist w
                    WHERE w.book_id = b.id
                    AND w.user_id = ?
                )
            '''
            params = [friend['id'], friend['id']]

            # Apply shelf filter if specified
            if shelf:
                query += '''
                    AND EXISTS (
                        SELECT 1 FROM collections c
                        WHERE c.book_id = b.id
                        AND c.user_id = ?
                        AND c.status = ?
                    )
                '''
                params.extend([friend['id'], shelf])

        # Note: Privacy filtering will be added in next phase
        # For now, friends can see all books

        query += ' ORDER BY b.title'

        books = conn.execute(query, params).fetchall()
        book_count = len(books)

        return render_template('friend_library.html',
                             friend=friend,
                             books=books,
                             book_count=book_count,
                             shelf=shelf)
    finally:
        conn.close()



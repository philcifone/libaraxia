import json
import sqlite3

from flask import abort, current_app, Blueprint, request, redirect, url_for, flash, render_template, g, jsonify, session
from utils.database import get_db
from flask_login import login_required, current_user
from models import can_view_book
from utils import bulk, goodreads, media, shelves, sorting
from utils.rate_limiting import limiter

collections_blueprint = Blueprint('collections', __name__, template_folder='templates')


# The item page's forms come back to the card they were sent from (16.0),
# not to the top of the page. A fixed list: the fragment is never a value
# echoed from the form.
ITEM_ANCHORS = {'your-info'}


def _back(fallback=None):
    url = request.referrer or fallback or url_for('base.index')
    anchor = request.form.get('anchor')
    if anchor in ITEM_ANCHORS:
        url = url.split('#')[0] + '#' + anchor
    return redirect(url)

# The Collections page's tabs (?type=), in order: Books, Movies, Music
TABS = (media.BOOK, media.VIDEO, media.RECORD)


def collection_order(added_column, media_type):
    """A collection page's order: newest in it first ('collected', the sort
    menu's "Date added here"), or any of the grid sorts (utils/sorting.py).
    Returns (sort_by, sort_order, ' ORDER BY ...', params)."""
    if request.args.get('sort_by', 'collected') == 'collected':
        order = 'asc' if request.args.get('sort_order') == 'asc' else 'desc'
        # added_column is one of ours, never request input
        return 'collected', order, f' ORDER BY {added_column} {order.upper()}, b.id', []
    sort_by, sort_order = sorting.choice(request.args, media_type)
    return (sort_by, sort_order, *sorting.order_by(sort_by, sort_order, current_user.id))


def _tab(value):
    return value if value in TABS else media.BOOK


@collections_blueprint.route('/collections', methods=['GET'])
@login_required
def view_collections():
    # Your shelves for one section (ROADMAP 8C): its status shelves (Read /
    # Want to Read..., Watched / Want to Watch, Listened / Want to Listen)
    # and the custom shelves you made for it (utils/shelves.py).
    conn = get_db()
    media_type = _tab(request.args.get('type'))
    custom = shelves.custom_shelves(conn, current_user.id, media_type)
    for shelf in custom:
        shelf['delete_url'] = url_for('collections.delete_collection', collection_id=shelf['id'])
    # Tab counts: statuses plus custom shelf entries, per section
    counts = shelves.section_counts(conn, current_user.id)
    for t, n in conn.execute('''
        SELECT uc.media_type, COUNT(cb.book_id) FROM user_collections uc
        JOIN collection_books cb ON cb.collection_id = uc.collection_id
        WHERE uc.user_id = ? GROUP BY uc.media_type''', (current_user.id,)).fetchall():
        counts[t] = counts.get(t, 0) + n
    # Goodreads shelves card (14c): Books only, your own imports
    gr_shelves = goodreads.custom_shelves(conn, current_user.id) if media_type == media.BOOK else []
    taken = {s['label'] for s in custom}
    for shelf in gr_shelves:
        shelf['has_collection'] = shelf['name'] in taken
        shelf['open_url'] = url_for('base.index', gr_shelf=shelf['name'], show='all')
    return render_template('collections.html',
                           gr_shelves=gr_shelves,
                           media_type=media_type,
                           m=media.media_labels(media_type),
                           tabs=[(t, shelves.SECTION_NAMES[t], counts.get(t, 0)) for t in TABS],
                           status_shelves=shelves.status_shelves(conn, current_user.id, media_type),
                           custom_shelves=custom)

def _per_user():
    return f'user:{current_user.id}' if current_user.is_authenticated else request.remote_addr


@collections_blueprint.route('/goodreads_shelf', methods=['POST'])
@login_required
@limiter.limit('60 per hour', key_func=_per_user)
def goodreads_shelf():
    """The Goodreads shelves card (ROADMAP 14c): put a custom Goodreads
    shelf's books in a collection. mode=new makes one (named `name`, the
    shelf's name by default), mode=add uses `collection_id`; books already
    in it are skipped. Written through the bulk journal ('shelf_add'), so
    the banner on the collection's page can undo it, and so can Profile's
    Recent bulk edits."""
    conn = get_db()
    back = url_for('collections.view_collections', type=media.BOOK)
    shelf = (request.form.get('shelf') or '').strip().lower()
    ids = goodreads.shelf_book_ids(conn, current_user.id, shelf) if shelf else []
    if not ids:
        flash('No books from your Goodreads imports are on that shelf.', 'error')
        return redirect(back)

    if request.form.get('mode') == 'new':
        params = {'media_type': media.BOOK, 'new_shelf': (request.form.get('name') or shelf).strip()}
    else:
        params = {'media_type': media.BOOK, 'shelf_id': request.form.get('collection_id', type=int)}
    try:
        plan = bulk.plan(conn, current_user, 'shelf_add', params, ids)
        if not plan.changes:
            flash(f'All {len(ids)} are already in {plan.params["shelf_name"]}.', 'info')
            return redirect(url_for('collections.view_custom_collection', collection_id=plan.params['shelf_id']))
        result = bulk.apply(conn, current_user, 'shelf_add', params, ids, plan.fingerprint)
    except bulk.BulkError as e:
        flash(str(e), 'error')
        return redirect(back)
    except Exception:
        conn.rollback()
        current_app.logger.exception('Goodreads shelf to collection failed')
        flash('Something went wrong. Nothing was changed.', 'error')
        return redirect(back)

    edit = conn.execute('SELECT params FROM bulk_edits WHERE id = ?', (result.edit_id,)).fetchone() \
        if result.edit_id else None
    if edit is None:
        flash(result.summary, 'info')
        return redirect(back)
    session['bulk_result'] = {'edit_id': result.edit_id, 'summary': result.summary}
    shelf_id = json.loads(edit['params'])['shelf_id']
    return redirect(url_for('collections.view_custom_collection', collection_id=shelf_id))


@collections_blueprint.route('/collections/create', methods=['POST'])
@login_required
def create_custom_collection():
    name = (request.form.get('name') or '').strip()
    media_type = _tab(request.form.get('media_type'))
    back = url_for('collections.view_collections', type=media_type)
    if not name:
        flash('Collection name is required.', 'error')
        return redirect(back)

    conn = get_db()
    try:
        collection_id = conn.execute('''
            INSERT INTO user_collections (user_id, name, media_type)
            VALUES (?, ?, ?)
        ''', (current_user.id, name, media_type)).lastrowid
        # From an item page (16.0): the item goes straight into it
        book_id = request.form.get('book_id')
        if book_id and can_view_book(conn, current_user, book_id):
            conn.execute('INSERT INTO collection_books (collection_id, book_id) VALUES (?, ?)',
                         (collection_id, book_id))
            flash(f'Created "{name}" and added this to it.', 'success')
        else:
            flash('Collection created successfully!', 'success')
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback()
        flash(f'You already have a collection called "{name}" here.', 'error')
    except Exception:
        conn.rollback()
        current_app.logger.exception('Error creating collection')
        flash('Error creating collection.', 'error')

    # From an item page's "Create Collection" box: back to that page
    if request.form.get('next') == 'item' and request.referrer:
        return _back()
    return redirect(back)

@collections_blueprint.route('/collections/<int:collection_id>/add', methods=['POST'])
@login_required
def add_to_custom_collection(collection_id):
    
    book_id = request.form.get('book_id')
    if not book_id:
        return jsonify({'success': False, 'error': 'Missing book ID'}), 400
    
    conn = get_db()
    try:
        # Verify the collection belongs to the user
        cursor = conn.execute('''
            SELECT 1 FROM user_collections 
            WHERE collection_id = ? AND user_id = ?
        ''', (collection_id, current_user.id))
        if not cursor.fetchone():
            return jsonify({'success': False, 'error': 'Collection not found'}), 404
        if not can_view_book(conn, current_user, book_id):
            return jsonify({'success': False, 'error': 'Book not found'}), 404

        # Add book to collection
        conn.execute('''
            INSERT OR REPLACE INTO collection_books (collection_id, book_id)
            VALUES (?, ?)
        ''', (collection_id, book_id))
        conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        current_app.logger.exception('Error adding book to collection')
        return jsonify({'success': False, 'error': 'Could not update collection'}), 500

@collections_blueprint.route('/collections/<int:collection_id>/remove', methods=['POST'])
@login_required
def remove_from_custom_collection(collection_id):
    
    book_id = request.form.get('book_id')
    if not book_id:
        return jsonify({'success': False, 'error': 'Missing book ID'}), 400
    
    conn = get_db()
    try:
        # Verify the collection belongs to the user
        cursor = conn.execute('''
            SELECT 1 FROM user_collections 
            WHERE collection_id = ? AND user_id = ?
        ''', (collection_id, current_user.id))
        if not cursor.fetchone():
            return jsonify({'success': False, 'error': 'Collection not found'}), 404
        
        # Remove book from collection
        conn.execute('''
            DELETE FROM collection_books 
            WHERE collection_id = ? AND book_id = ?
        ''', (collection_id, book_id))
        conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        current_app.logger.exception('Error removing book from collection')
        return jsonify({'success': False, 'error': 'Could not update collection'}), 500

@collections_blueprint.route('/collections/<int:collection_id>/view', methods=['GET'])
@login_required
def view_custom_collection(collection_id):
    conn = get_db()
    # Get collection details
    cursor = conn.execute('''
        SELECT uc.*, COUNT(cb.book_id) as book_count
        FROM user_collections uc
        LEFT JOIN collection_books cb ON uc.collection_id = cb.collection_id
        WHERE uc.collection_id = ? AND uc.user_id = ?
        GROUP BY uc.collection_id
    ''', (collection_id, current_user.id))
    collection = cursor.fetchone()
    
    if not collection:
        flash('Collection not found.', 'error')
        return redirect(url_for('collections.view_collections'))
    
    # Get books in collection: most recently added first, or the sort menu's choice
    sort_by, sort_order, order_sql, order_params = collection_order('cb.added_at', collection['media_type'])
    books = conn.execute('''
        SELECT b.*
        FROM books b
        JOIN collection_books cb ON b.id = cb.book_id
        WHERE cb.collection_id = ?
    ''' + order_sql, (collection_id, *order_params)).fetchall()

    return render_template('collection_status.html',
                         media_type=collection['media_type'],
                         m=media.media_labels(collection['media_type']),
                         sort_by=sort_by, sort_order=sort_order, collected_sort=True,
                         status_labels=media.STATUS_LABELS,
                         collection=collection,
                         books=books,
                         is_custom=True,
                         status=None,  # custom shelves have no reading status
                         is_own_profile=True,  # the query above only finds your own shelves
                         target_username=current_user.username)

@collections_blueprint.route('/collections/status/add', methods=['POST'])
@login_required
def add_to_status_collection():
    book_id = request.form.get('id')
    status = request.form.get('status')
    
    if not book_id or not status:
        flash('Missing book ID or status.', 'danger')
        return redirect(request.referrer)
    
    conn = get_db()
    try:
        # Only books in the user's circle (models.can_view_book)
        if not can_view_book(conn, current_user, book_id):
            flash('Book not found.', 'danger')
            return redirect(request.referrer or url_for('base.index'))

        # Books and videos have their own statuses (utils/media.py)
        media_type = media.media_type_of(conn.execute(
            'SELECT media_type FROM books WHERE id = ?', (book_id,)).fetchone())
        if status == 'untracked':
            conn.execute('DELETE FROM collections WHERE user_id = ? AND book_id = ?',
                         (current_user.id, book_id))
            conn.commit()
            flash('Status cleared.', 'success')
            return _back()
        if not media.is_valid_status(media_type, status):
            flash('That status is not available here.', 'danger')
            return redirect(request.referrer or url_for('base.index'))

        cursor = conn.execute('''
            SELECT 1 FROM collections
            WHERE user_id = ? AND book_id = ?
        ''', (current_user.id, book_id))
        exists = cursor.fetchone()
        
        if exists:
            conn.execute('''
                UPDATE collections
                SET status = ?, updated_at = CURRENT_TIMESTAMP,
                    quiet = 0  -- a status you set by hand is yours to announce again (031)
                WHERE user_id = ? AND book_id = ?
            ''', (status, current_user.id, book_id))
        else:
            conn.execute('''
                INSERT INTO collections (user_id, book_id, status, created_at, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ''', (current_user.id, book_id, status))
        
        conn.commit()
        flash('Collection updated successfully!', 'success')
        
        if status == media.DONE_STATUS[media_type]:   # 'read' / 'watched'
            # finished=1: the review page offers today as the finished date (12.3)
            return redirect(url_for('read.rate_review', book_id=book_id, finished=1))
            
    except Exception as e:
        current_app.logger.exception('Error updating collection')
        flash('Failed to update the reading status.', 'danger')

    return _back()

@collections_blueprint.route('/collections/status/<status>', methods=['GET'])
@login_required
def view_by_status(status):
    # Get optional username parameter (defaults to current user)
    username = request.args.get('username', current_user.username)

    conn = get_db()
    # Get the target user
    target_user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()

    if not target_user:
        flash('User not found!', 'danger')
        return redirect(url_for('base.index'))

    target_user_id = target_user['id']
    is_own_profile = (target_user_id == current_user.id)

    # Check friendship status if viewing someone else's profile
    if not is_own_profile:
        from models import get_friendship_status
        friendship_status = get_friendship_status(current_user.id, target_user_id)

        # Only allow viewing if they are friends
        if friendship_status not in ('self', 'friends'):
            flash('You must be friends to view this collection!', 'warning')
            return redirect(url_for('user.profile', username=username))

    # Status names are per type (media.STATUSES), so the status says which
    # section's shelf this is
    media_type = next((t for t in TABS if media.is_valid_status(t, status)), None)
    if media_type is None:
        abort(404)
    # Most recently set first, or the sort menu's choice ("Date read" and
    # "Your rating" are the viewer's, as on every grid)
    sort_by, sort_order, order_sql, order_params = collection_order('c.updated_at', media_type)
    books = conn.execute('''
        SELECT b.*
        FROM collections c
        JOIN books b ON c.book_id = b.id
        WHERE c.user_id = ? AND c.status = ? AND b.media_type = ?
    ''' + order_sql, (target_user_id, status, media_type, *order_params)).fetchall()

    return render_template('collection_status.html',
                         media_type=media_type,
                         m=media.media_labels(media_type),
                         sort_by=sort_by, sort_order=sort_order, collected_sort=True,
                         status_labels=media.STATUS_LABELS,
                         status=status,
                         books=books,
                         is_custom=False,
                         collection=None,
                         target_username=username,
                         is_own_profile=is_own_profile)

@collections_blueprint.route('/manage_book_collections', methods=['POST'])
@login_required
def manage_book_collections():
    book_id = request.form.get('book_id')
    collection_id = request.form.get('collection_id')
    
    if not book_id or not collection_id:
        flash('Missing required information', 'error')
        return redirect(request.referrer)

    conn = get_db()
    try:
        # Verify the collection belongs to the user
        owns_collection = conn.execute('''
            SELECT 1 FROM user_collections
            WHERE collection_id = ? AND user_id = ?
        ''', (collection_id, current_user.id)).fetchone()
        if not owns_collection:
            flash('Collection not found', 'error')
            return redirect(request.referrer or url_for('collections.view_collections'))
        if not can_view_book(conn, current_user, book_id):
            flash('Book not found', 'error')
            return redirect(request.referrer or url_for('collections.view_collections'))

        # Check if book is already in collection
        existing = conn.execute('''
            SELECT 1 FROM collection_books 
            WHERE collection_id = ? AND book_id = ?
        ''', (collection_id, book_id)).fetchone()

        if existing:
            # Remove from collection if already exists
            conn.execute('''
                DELETE FROM collection_books 
                WHERE collection_id = ? AND book_id = ?
            ''', (collection_id, book_id))
            flash('Book removed from collection', 'success')
        else:
            # Add to collection
            conn.execute('''
                INSERT INTO collection_books (collection_id, book_id)
                VALUES (?, ?)
            ''', (collection_id, book_id))
            flash('Book added to collection', 'success')
        
        conn.commit()
    except Exception as e:
        current_app.logger.exception('Error managing collection')
        flash('Error managing collection.', 'error')

    return _back()

@collections_blueprint.route('/delete_collection/<int:collection_id>', methods=['POST'])
@login_required
def delete_collection(collection_id):
    conn = get_db()
    media_type = media.BOOK
    try:
        # Verify ownership and delete
        deleted = conn.execute('''
            DELETE FROM user_collections
            WHERE collection_id = ? AND user_id = ?
            RETURNING media_type
        ''', (collection_id, current_user.id)).fetchone()
        if deleted:
            media_type = deleted['media_type']
            # Also delete associated books
            conn.execute('DELETE FROM collection_books WHERE collection_id = ?', (collection_id,))
            conn.commit()
            flash('Collection deleted successfully', 'success')
        else:
            flash('Collection not found', 'error')
            
    except Exception as e:
        current_app.logger.exception('Error deleting collection')
        flash('Error deleting collection.', 'error')

    return redirect(url_for('collections.view_collections', type=media_type))

@collections_blueprint.route('/get_book_collections/<int:book_id>')
@login_required
def get_book_collections(book_id):
    conn = get_db()
    collections = conn.execute('''
        SELECT uc.collection_id as id, uc.name 
        FROM user_collections uc
        JOIN collection_books cb ON uc.collection_id = cb.collection_id
        WHERE uc.user_id = ? AND cb.book_id = ?
    ''', (current_user.id, book_id)).fetchall()
    return jsonify({'collections': [dict(c) for c in collections]})
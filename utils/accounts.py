"""Deactivating and deleting accounts (used by admin and by self-delete).

Rules (ROADMAP 2.3 / 2.7):
- Deactivate keeps everything; the person just can't log in. Reversible.
- Delete removes the person's own data (reviews, reading history, shelves,
  wishlist, friendships, notifications, likes, household membership) via
  ON DELETE CASCADE. Their *books* are records other people's reviews hang
  on, so they're never deleted: they go to another user or become unowned.
  Their wishlist-only entries are deleted unless someone else has data on them.
"""
from models import get_library_members, other_users_with_book_data


class AccountError(Exception):
    """A deletion that isn't allowed; the message is safe to show."""


def removal_context(conn, user_id, viewer_is_admin):
    """What the confirm dialog needs to explain and offer."""
    user = conn.execute('SELECT id, username, is_admin, is_active FROM users WHERE id = ?',
                        (user_id,)).fetchone()
    if not user:
        return None
    owned = conn.execute('''
        SELECT COUNT(*) FROM books b WHERE b.added_by = ?
          AND NOT EXISTS (SELECT 1 FROM wishlist w WHERE w.book_id = b.id AND w.user_id = b.added_by)
    ''', (user_id,)).fetchone()[0]
    household_ids = [i for i in get_library_members(user_id) if i != user_id]
    household = conn.execute(
        f"SELECT id, username FROM users WHERE id IN ({','.join('?' * len(household_ids))}) ORDER BY username",
        household_ids).fetchall() if household_ids else []
    others = conn.execute(
        'SELECT id, username FROM users WHERE id != ? ORDER BY username', (user_id,)
    ).fetchall() if viewer_is_admin else []
    others = [u for u in others if u['id'] not in household_ids]
    counts = conn.execute('''
        SELECT (SELECT COUNT(*) FROM read_data WHERE user_id = :u
                  AND (rating IS NOT NULL OR comment IS NOT NULL)) AS reviews,
               (SELECT COUNT(*) FROM collections WHERE user_id = :u) AS statuses,
               (SELECT COUNT(*) FROM reading_sessions WHERE user_id = :u) AS sessions,
               (SELECT COUNT(*) FROM user_collections WHERE user_id = :u) AS shelves,
               (SELECT COUNT(*) FROM wishlist WHERE user_id = :u) AS wishlist,
               (SELECT COUNT(*) FROM friendships WHERE user_id_1 = :u OR user_id_2 = :u) AS friends
    ''', {'u': user_id}).fetchone()
    last_admin = bool(user['is_admin']) and conn.execute(
        'SELECT COUNT(*) FROM users WHERE is_admin = 1').fetchone()[0] <= 1
    return {
        'user': user,
        'owned_books': owned,
        'household': household,
        'other_users': others,
        'counts': dict(counts),
        'last_admin': last_admin,
    }


def deactivate_account(conn, user_id):
    conn.execute('UPDATE users SET is_active = 0 WHERE id = ?', (user_id,))
    conn.commit()


def delete_account(conn, user_id, books_to):
    """Delete a user. books_to: another user's id (str/int) or 'none'.

    Returns (username, owned_count, new_owner_username or None, cover paths to
    delete after the caller has finished). Raises AccountError when refused.
    The caller deletes avatar/cover files only after this returns.
    """
    user = conn.execute('SELECT username, is_admin, avatar_url FROM users WHERE id = ?',
                        (user_id,)).fetchone()
    if not user:
        raise AccountError('User not found.')
    if user['is_admin'] and conn.execute('SELECT COUNT(*) FROM users WHERE is_admin = 1').fetchone()[0] <= 1:
        raise AccountError("The last admin can't be deleted. Make someone else an admin first.")

    wishlist_books = conn.execute('''
        SELECT b.id, b.cover_image_url FROM books b
        WHERE b.added_by = ?
          AND EXISTS (SELECT 1 FROM wishlist w WHERE w.book_id = b.id AND w.user_id = b.added_by)
    ''', (user_id,)).fetchall()
    owned_count = conn.execute('SELECT COUNT(*) FROM books WHERE added_by = ?',
                               (user_id,)).fetchone()[0] - len(wishlist_books)

    new_owner = None
    if owned_count:
        books_to = str(books_to or '')
        if books_to == 'none':
            new_owner = None
        elif books_to.isdigit() and int(books_to) != user_id:
            new_owner = conn.execute('SELECT id, username FROM users WHERE id = ?',
                                     (int(books_to),)).fetchone()
            if not new_owner:
                raise AccountError('The user chosen to receive the books no longer exists.')
        else:
            raise AccountError(f"{user['username']} owns {owned_count} book(s). Choose who gets them "
                               "(another user, or no owner) before deleting.")

    covers = []
    for b in wishlist_books:
        if other_users_with_book_data(conn, b['id'], user_id):
            conn.execute('UPDATE books SET added_by = NULL WHERE id = ?', (b['id'],))
        else:
            conn.execute('DELETE FROM books WHERE id = ?', (b['id'],))
            if b['cover_image_url']:
                covers.append(b['cover_image_url'])

    conn.execute('UPDATE books SET added_by = ? WHERE added_by = ?',
                 (new_owner['id'] if new_owner else None, user_id))
    # Everything else of theirs goes via ON DELETE CASCADE.
    conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
    conn.commit()

    if user['avatar_url']:
        covers.append(user['avatar_url'])
    return user['username'], owned_count, (new_owner['username'] if new_owner else None), covers

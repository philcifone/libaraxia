"""CSV exports of one user's data: the library CSV and the "export my data" ZIP.

Everything here is scoped to one user: books they own, plus books they have
their own data on (status, rating/review, sessions, tags, shelves).
"""
import csv
import io
import zipfile
from datetime import datetime


def _csv(header, rows):
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(header)
    w.writerows(rows)
    return out.getvalue()


LIBRARY_HEADER = [
    'Book ID', 'Title', 'Subtitle', 'Author', 'Publisher', 'Year', 'ISBN', 'Pages', 'Genre',
    'Owner', 'You Own It', 'Removed From Library', 'Removed Note',
    'Reading Status', 'Date Added to Collection', 'Date Started', 'Date Completed', 'Reread Count',
    'Rating', 'Review', 'Tags', 'Custom Collections',
]


def library_rows(conn, user_id):
    """One row per book the user owns or has their own data on (wishlist excluded)."""
    rows = conn.execute('''
        SELECT b.id, b.title, b.subtitle, b.author, b.publisher, b.publish_year, b.isbn,
               b.page_count, b.genre, owner.username AS owner, b.added_by = :u AS own,
               b.removed_at, b.removed_note,
               c.status, c.created_at AS status_added,
               (SELECT MIN(date_started) FROM reading_sessions WHERE book_id = b.id AND user_id = :u) AS started,
               (SELECT MAX(date_completed) FROM reading_sessions WHERE book_id = b.id AND user_id = :u) AS completed,
               (SELECT COUNT(*) FROM reading_sessions
                 WHERE book_id = b.id AND user_id = :u AND date_completed IS NOT NULL) AS reads,
               r.rating, r.comment,
               (SELECT GROUP_CONCAT(tag_name, ', ') FROM book_tags WHERE book_id = b.id AND user_id = :u) AS tags,
               (SELECT GROUP_CONCAT(uc.name, ', ') FROM collection_books cb
                  JOIN user_collections uc ON uc.collection_id = cb.collection_id
                 WHERE cb.book_id = b.id AND uc.user_id = :u) AS shelves
        FROM books b
        LEFT JOIN users owner ON owner.id = b.added_by
        LEFT JOIN collections c ON c.book_id = b.id AND c.user_id = :u
        LEFT JOIN read_data r ON r.book_id = b.id AND r.user_id = :u
        WHERE NOT EXISTS (SELECT 1 FROM wishlist w WHERE w.book_id = b.id AND w.user_id = :u)
          AND (b.added_by = :u
               OR c.book_id IS NOT NULL OR r.book_id IS NOT NULL
               OR EXISTS (SELECT 1 FROM reading_sessions s WHERE s.book_id = b.id AND s.user_id = :u)
               OR EXISTS (SELECT 1 FROM book_tags t WHERE t.book_id = b.id AND t.user_id = :u))
        ORDER BY LOWER(b.title)
    ''', {'u': user_id}).fetchall()
    return [[
        r['id'], r['title'], r['subtitle'], r['author'], r['publisher'], r['publish_year'], r['isbn'],
        r['page_count'], r['genre'], r['owner'] or '', 'yes' if r['own'] else 'no',
        r['removed_at'] or '', r['removed_note'] or '',
        r['status'] or 'Untracked', r['status_added'], r['started'], r['completed'], r['reads'] or 0,
        r['rating'], r['comment'], r['tags'], r['shelves'],
    ] for r in rows]


def library_csv(conn, user_id):
    return _csv(LIBRARY_HEADER, library_rows(conn, user_id))


def data_zip(conn, user_id):
    """Everything of one user's, as a ZIP of CSVs. Returns bytes."""
    user = conn.execute('SELECT username, email, bio, reading_goal FROM users WHERE id = ?',
                        (user_id,)).fetchone()
    files = {
        'library.csv': library_csv(conn, user_id),
        'reading_sessions.csv': _csv(
            ['Book ID', 'Title', 'Author', 'Date Started', 'Date Completed'],
            conn.execute('''
                SELECT b.id, b.title, b.author, s.date_started, s.date_completed
                FROM reading_sessions s JOIN books b ON b.id = s.book_id
                WHERE s.user_id = ? ORDER BY s.date_completed, s.date_started
            ''', (user_id,)).fetchall()),
        'reviews.csv': _csv(
            ['Book ID', 'Title', 'Author', 'Rating', 'Review'],
            conn.execute('''
                SELECT b.id, b.title, b.author, r.rating, r.comment
                FROM read_data r JOIN books b ON b.id = r.book_id
                WHERE r.user_id = ? AND (r.rating IS NOT NULL OR r.comment IS NOT NULL)
                ORDER BY LOWER(b.title)
            ''', (user_id,)).fetchall()),
        'shelves.csv': _csv(
            ['Shelf', 'Book ID', 'Title', 'Author', 'Added'],
            conn.execute('''
                SELECT uc.name, b.id, b.title, b.author, cb.added_at
                FROM user_collections uc
                JOIN collection_books cb ON cb.collection_id = uc.collection_id
                JOIN books b ON b.id = cb.book_id
                WHERE uc.user_id = ? ORDER BY uc.name, LOWER(b.title)
            ''', (user_id,)).fetchall()),
        'wishlist.csv': _csv(
            ['Book ID', 'Title', 'Author', 'ISBN', 'Added', 'Notes', 'Purchase Link'],
            conn.execute('''
                SELECT b.id, b.title, b.author, b.isbn, w.added_at, w.notes, w.purchase_link
                FROM wishlist w JOIN books b ON b.id = w.book_id
                WHERE w.user_id = ? ORDER BY w.added_at
            ''', (user_id,)).fetchall()),
        'profile.csv': _csv(
            ['Username', 'Email', 'Bio', 'Reading Goal', 'Exported At'],
            [[user['username'], user['email'], user['bio'], user['reading_goal'],
              datetime.now().isoformat(timespec='seconds')]] if user else []),
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, text in files.items():
            z.writestr(name, text)
    return buf.getvalue()

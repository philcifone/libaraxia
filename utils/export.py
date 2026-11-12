"""CSV exports of one user's data: the library CSV and the "export my data" ZIP.

Everything here is scoped to one user: books they own, their household's
shelf (Phil, 2026-11-12), and books they have their own data on (status,
rating/review, sessions, tags, shelves). The library CSV's first column,
Section, says which: "Yours", "Shared (<owner>)" or "Your data on others'
items". Only the user's own status, rating and so on are in it, never a
household member's.
"""
import csv
import io
import zipfile
from datetime import datetime

from utils.media import NO_STATUS_LABEL, kind_of


def _csv(header, rows):
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(header)
    w.writerows(rows)
    return out.getvalue()


LIBRARY_HEADER = [
    'Section', 'Book ID', 'Title', 'Subtitle', 'Author', 'Publisher', 'Year', 'ISBN', 'Pages', 'Genre',
    'Owner', 'You Own It', 'Removed From Library', 'Removed Note',
    'Reading Status', 'Date Added to Collection', 'Date Started', 'Date Completed', 'Reread Count',
    'Rating', 'Review', 'Tags', 'Custom Collections',
    # Movies and music (Phase 8) share the file; appended so older readers of it
    # keep working. For a movie, Author is the director and Publisher the studio;
    # for an album, Author is the artist and Publisher the label.
    'Type', 'Format', 'Barcode', 'Catalogue Number', 'Runtime (min)',
    # Movies & TV (15.1): movie / tv for a video, blank otherwise; season is TV's
    'Kind', 'Season',
]


# Appended to the other files of the ZIP, for the same reason: which section a
# row belongs to (book, video, record) and its format (VHS, DVD, LP, CD, ...).
TYPE_COLUMNS = ['Type', 'Format']


SECTION_YOURS, SECTION_OTHERS = 'Yours', "Your data on others' items"


def library_rows(conn, user_id):
    """One row per item: the user's own, then their household's shelf, then
    others' items they have data on; by title within each. Wishlist entries
    (the user's, or a household member's) are left out."""
    from models import get_library_members
    household = [m for m in get_library_members(user_id, conn) if m != user_id]
    params = {'u': user_id, **{f'h{i}': m for i, m in enumerate(household)}}
    in_household = ', '.join(f':h{i}' for i in range(len(household))) or 'NULL'
    rows = conn.execute('''
        SELECT b.id, b.added_by, b.title, b.subtitle, b.author, b.publisher, b.publish_year, b.isbn,
               b.page_count, b.genre, owner.username AS owner, b.added_by = :u AND b.owned = 1 AS own,
               b.removed_at, b.removed_note,
               b.media_type, b.format, b.barcode, b.catalog_number, b.runtime_minutes,
               b.video_kind, b.season,
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
               OR EXISTS (SELECT 1 FROM book_tags t WHERE t.book_id = b.id AND t.user_id = :u)
               -- the household's shelf: owned, not removed, not a wishlist entry
               OR (b.added_by IN (%s) AND b.owned = 1 AND b.removed_at IS NULL
                   AND NOT EXISTS (SELECT 1 FROM wishlist w2
                                   WHERE w2.book_id = b.id AND w2.user_id = b.added_by)))
    ''' % in_household, params).fetchall()

    def section(r):
        if r['added_by'] == user_id:
            return 0, SECTION_YOURS
        if r['added_by'] in household:
            return 1, f"Shared ({r['owner']})"
        return 2, SECTION_OTHERS
    rows = sorted(rows, key=lambda r: (section(r), (r['title'] or '').lower()))
    return [[
        section(r)[1], r['id'], r['title'], r['subtitle'], r['author'], r['publisher'], r['publish_year'], r['isbn'],
        r['page_count'], r['genre'], r['owner'] or '', 'yes' if r['own'] else 'no',
        r['removed_at'] or '', r['removed_note'] or '',
        r['status'] or NO_STATUS_LABEL.get(r['media_type'], 'Unread'), r['status_added'], r['started'], r['completed'], r['reads'] or 0,
        r['rating'], r['comment'], r['tags'], r['shelves'],
        r['media_type'], r['format'] or '', r['barcode'] or '', r['catalog_number'] or '',
        r['runtime_minutes'] or '', kind_of(r) or '', r['season'] or '',
    ] for r in rows]


def library_csv(conn, user_id):
    return _csv(LIBRARY_HEADER, library_rows(conn, user_id))


def data_zip(conn, user_id):
    """Everything of one user's, as a ZIP of CSVs. Returns bytes."""
    user = conn.execute('SELECT username, email, bio FROM users WHERE id = ?',
                        (user_id,)).fetchone()
    files = {
        'library.csv': library_csv(conn, user_id),
        'reading_sessions.csv': _csv(
            ['Book ID', 'Title', 'Author', 'Date Started', 'Date Completed'] + TYPE_COLUMNS,
            conn.execute('''
                SELECT b.id, b.title, b.author, s.date_started, s.date_completed,
                       b.media_type, COALESCE(b.format, '')
                FROM reading_sessions s JOIN books b ON b.id = s.book_id
                WHERE s.user_id = ? ORDER BY s.date_completed, s.date_started
            ''', (user_id,)).fetchall()),
        'reviews.csv': _csv(
            ['Book ID', 'Title', 'Author', 'Rating', 'Review'] + TYPE_COLUMNS,
            conn.execute('''
                SELECT b.id, b.title, b.author, r.rating, r.comment,
                       b.media_type, COALESCE(b.format, '')
                FROM read_data r JOIN books b ON b.id = r.book_id
                WHERE r.user_id = ? AND (r.rating IS NOT NULL OR r.comment IS NOT NULL)
                ORDER BY LOWER(b.title)
            ''', (user_id,)).fetchall()),
        'collections.csv': _csv(
            ['Collection', 'Book ID', 'Title', 'Author', 'Added'] + TYPE_COLUMNS,
            conn.execute('''
                SELECT uc.name, b.id, b.title, b.author, cb.added_at,
                       b.media_type, COALESCE(b.format, '')
                FROM user_collections uc
                JOIN collection_books cb ON cb.collection_id = uc.collection_id
                JOIN books b ON b.id = cb.book_id
                WHERE uc.user_id = ? ORDER BY uc.name, LOWER(b.title)
            ''', (user_id,)).fetchall()),
        'wishlist.csv': _csv(
            ['Book ID', 'Title', 'Author', 'ISBN', 'Added', 'Notes', 'Purchase Link'] + TYPE_COLUMNS,
            conn.execute('''
                SELECT b.id, b.title, b.author, b.isbn, w.added_at, w.notes, w.purchase_link,
                       b.media_type, COALESCE(b.format, '')
                FROM wishlist w JOIN books b ON b.id = w.book_id
                WHERE w.user_id = ? ORDER BY w.added_at
            ''', (user_id,)).fetchall()),
        'profile.csv': _csv(
            ['Username', 'Email', 'Bio', 'Exported At'],
            [[user['username'], user['email'], user['bio'],
              datetime.now().isoformat(timespec='seconds')]] if user else []),
        # One row per year with a goal (ROADMAP 12.3)
        'reading_goals.csv': _csv(
            ['Year', 'Goal'],
            conn.execute('SELECT year, goal FROM reading_goals WHERE user_id = ? ORDER BY year',
                         (user_id,)).fetchall()),
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, text in files.items():
            z.writestr(name, text)
    return buf.getvalue()

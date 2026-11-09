"""Search matching for the grid search boxes and "Do I have this?" (ROADMAP 7.2b).

A search used to be one `LIKE '%term%'` on a few columns, so "Les Miserables"
missed "Les Misérables", "catch 22" missed "Catch-22" and "harari lessons"
missed "21 Lessons for the 21st Century" by Yuval Noah Harari. Now:

- both sides are folded (`fold`): lowercase, accents dropped, and everything
  that isn't a letter or digit removed, spaces included. So punctuation and
  spacing never matter: "catch 22", "Catch-22" and "catch22" are the same.
- each word of the search must match somewhere (any of the columns, or one of
  the viewer's tags on the item), in any order: "harari lessons" works.

`fold` is registered on every connection as an SQL function
(utils/database.get_db_connection), so the folding happens in SQLite. It's a
Python call per row and column: fine for a household's catalogue (thousands
of rows); SQLite FTS5 is the step up if it ever needs ranking or speed.
"""
import unicodedata


def fold(value):
    """'Les Misérables!' -> 'lesmiserables'. None stays None; numbers become
    their digits (so a year or an ISBN folds too)."""
    if value is None:
        return None
    text = unicodedata.normalize('NFKD', str(value))
    return ''.join(ch for ch in text if ch.isalnum() and not unicodedata.combining(ch)).lower()


def register(conn):
    """Make fold() available to SQL on this connection."""
    conn.create_function('fold', 1, fold, deterministic=True)


def match(term, columns, viewer_id=None, alias='b'):
    """(SQL condition, params) for a search term on `alias`: every word must
    be found, folded, in one of `columns`, or (with `viewer_id`) in one of
    that viewer's tags on the item. A term with nothing searchable in it
    (only punctuation) matches everything, like an empty search.

    `columns` are column names from our own code, never request input."""
    words = [w for w in (fold(part) for part in (term or '').split()) if w]
    if not words:
        return '1', []
    clauses, params = [], []
    for word in words:
        like = f'%{word}%'
        parts = [f'fold({alias}.{col}) LIKE ?' for col in columns]
        params += [like] * len(columns)
        if viewer_id is not None:
            parts.append(f'EXISTS (SELECT 1 FROM book_tags t WHERE t.book_id = {alias}.id'
                         ' AND t.user_id = ? AND fold(t.tag_name) LIKE ?)')
            params += [viewer_id, like]
        clauses.append('(' + ' OR '.join(parts) + ')')
    return ' AND '.join(clauses), params

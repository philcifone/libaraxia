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
import re
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


# --- Online lookups: "title by creator" (16.0, Phil 2026-11-13) -------------
# The Add pages' Search tab (books and music) reads "the silver cord by king
# gizzard" as a title and a creator, and asks the source for exactly that
# (Discogs' release_title + artist, MusicBrainz's fields, Google's intitle +
# inauthor). A title with "by" in it ("Stand by Me", "Death by Black Hole")
# would split wrongly, so a split that finds nothing on its first page falls
# back to the words as typed (by_or_plain).

# The last " by " splits it, so "Stand by Me by Ben E. King" works
_BY = re.compile(r'^(.*\S)\s+by\s+(\S.*)$', re.IGNORECASE)


def split_by(text):
    """'the silver cord by king gizzard' -> ('the silver cord', 'king gizzard');
    None when there's no " by " with words on both sides."""
    m = _BY.match((text or '').strip())
    return (m.group(1).strip(), m.group(2).strip()) if m else None


# Joining words a credit may spell either way ("&" or "and"): not required
JOINERS = {'and', '&', '+'}


def _word_set(text):
    """The folded words of a title or a credit ('Catch-22' -> catch, 22)."""
    return {fold(w) for w in re.split(r'[\s\-/.,:;]+', text or '') if fold(w)}


def fits(split, title, creator):
    """Whether a result is the split's: every word of its title among the
    words of `title`, every word of its creator among those of `creator`,
    folded (case, accents and punctuation don't matter) and whole words
    ("stand" isn't "Standards"). Sources match loosely (Discogs finds
    *something* for title "Stand" by "Me"), so a split's rows are checked."""
    in_title, in_creator = _word_set(title), _word_set(creator)
    return (_word_set(split[0]) <= in_title
            and {w for w in _word_set(split[1]) if w not in JOINERS} <= in_creator)


def by_or_plain(text, run, page=1, by=None, keep=None):
    """Run one page of an online search, as title + creator when `text` reads
    "X by Y", else as typed. `run(split, page)` gets the (title, creator)
    pair or None and returns (rows, more); `keep(row, split)` says whether a
    row really is the split's (fits() on its fields), and only those are
    shown. Answers (rows, more, by): `by` says which way this search went,
    and the page sends it back with the next page so "Show more" stays on
    the same search. by=None decides: the split, unless nothing on its
    first page fits."""
    split = split_by(text)
    if split and by is not False:
        rows, more = run(split, page)
        if keep:
            rows = [r for r in rows if keep(r, split)]
        if rows or page > 1 or by:
            return rows, more, True
    rows, more = run(None, page)
    return rows, more, False


MAX_PAGE = 20               # "Show more" stops here (240 albums, 200 books)


def page_arg(args):
    """?page= as 1..MAX_PAGE (anything else is 1)."""
    value = (args.get('page') or '').strip()
    return min(int(value), MAX_PAGE) if value.isdigit() and int(value) >= 1 else 1


def next_page(page, more, **keep):
    """A search answer's `next`: the query parameters that ask for the page
    after `page` on the same search (`keep`: how this one was read, e.g.
    by=1), or None when there's no more. The page appends them to its search
    URL as they are, so "Show more" never needs to know why they're there."""
    if not more or page >= MAX_PAGE:
        return None
    return {'page': page + 1, **{k: int(v) if isinstance(v, bool) else v
                                  for k, v in keep.items() if v is not None}}


def by_arg(args):
    """?by=1 / ?by=0 from the page's last answer; absent = decide (None)."""
    return {'1': True, '0': False}.get(args.get('by'))

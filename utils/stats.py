"""Profile statistics, one shape for every type (ROADMAP 12.1).

type_stats(conn, user_id, kind) gives books, movies and music the same
numbers, each in its own words (the template words them with
media.media_labels). Replaces calculate_user_stats (books only),
calculate_library_stats and calculate_media_stats in blueprints/user.py.

Two sets of items are counted, and the difference matters:
  shelf   what the user owns now (their own rows in the type's view, owned,
          not removed): "owned", sizes on the shelf, formats, decades,
          longest, creators and genres on the shelf;
  done    what they finished (the type's done status: read / watched /
          listened), whoever's copy it was: "read", pages read, hours
          watched, top genres and creators.

Size is pages for books (never an audiobook's: its page count is the print
edition's, 8B.2) and minutes for movies and music (runtime_minutes).
Every type and status here is one of our constants, so they're inlined.
"""
from datetime import datetime

from utils import media
from utils.media import BOOK, only


def _size_sql(kind, alias='b'):
    """SQL for one item's size: pages (books) or minutes (movies, music)."""
    if kind == BOOK:
        return (f"CASE WHEN {alias}.format = '{media.AUDIOBOOK}' THEN NULL "
                f"ELSE NULLIF(CAST({alias}.page_count AS INTEGER), 0) END")
    return f'NULLIF({alias}.runtime_minutes, 0)'


def _hours(minutes):
    """Minutes as hours to one decimal, whole hours without one (0, not 0.0)."""
    hours = round(minutes / 60, 1)
    return int(hours) if hours == int(hours) else hours


def type_stats(conn, user_id, kind, today=None):
    """The profile's numbers for one type, or None when the user has none of
    it at all (nothing owned, finished, wanted or reviewed), so its tab can
    stay hidden. Books are never None: the reading goal hangs on them."""
    today = today or datetime.now()
    view = media.VIEWS[kind]
    size = _size_sql(kind)
    p = {'u': user_id, 'kind': kind, 'done': media.DONE_STATUS[kind],
         'want': media.WANT_STATUS[kind], 'year': str(today.year)}
    shelf_cte = f'''
        shelf AS (SELECT * FROM {view} b
                  WHERE b.added_by = :u AND b.owned = 1 AND b.removed_at IS NULL),
        done AS (SELECT b.* FROM collections c JOIN books b ON b.id = c.book_id
                 WHERE c.user_id = :u AND c.status = :done AND b.media_type = :kind)'''
    s = dict(conn.execute(f'''
        WITH {shelf_cte}
        SELECT
            (SELECT COUNT(*) FROM shelf) AS owned,
            (SELECT COUNT(*) FROM done) AS done,
            (SELECT COUNT(*) FROM collections c
             WHERE c.user_id = :u AND c.status = :want AND {only(kind, 'c.book_id')}) AS want,
            (SELECT COUNT(*) FROM {view} b
             WHERE b.added_by = :u AND b.owned = 0 AND b.removed_at IS NULL) AS not_owned,
            (SELECT COUNT(*) FROM shelf b WHERE EXISTS (
                SELECT 1 FROM collections c
                WHERE c.book_id = b.id AND c.user_id = :u AND c.status = :done)) AS done_owned,
            (SELECT COUNT(DISTINCT rs.book_id) FROM reading_sessions rs
             WHERE rs.user_id = :u AND {only(kind, 'rs.book_id')}
               AND strftime('%Y', rs.date_completed) = :year) AS done_this_year,
            (SELECT SUM({size}) FROM done b) AS size_done,
            (SELECT SUM({size}) FROM shelf b) AS size_owned,
            (SELECT ROUND(AVG(r.rating), 1) FROM read_data r
             WHERE r.user_id = :u AND r.rating IS NOT NULL AND {only(kind, 'r.book_id')}) AS avg_rating,
            (SELECT COUNT(*) FROM read_data r
             WHERE r.user_id = :u AND (r.rating IS NOT NULL OR r.comment IS NOT NULL)
               AND {only(kind, 'r.book_id')}) AS reviews,
            (SELECT COUNT(DISTINCT LOWER(b.author)) FROM shelf b
             WHERE b.author IS NOT NULL AND b.author != '') AS creators,
            (SELECT b.genre FROM shelf b WHERE b.genre IS NOT NULL AND b.genre != ''
             GROUP BY LOWER(b.genre) ORDER BY COUNT(*) DESC, b.genre LIMIT 1) AS top_shelf_genre
    ''', p).fetchone())
    if kind != BOOK and not (s['owned'] or s['done'] or s['want'] or s['reviews'] or s['not_owned']):
        return None

    s['size_done'] = s['size_done'] or 0
    s['size_owned'] = s['size_owned'] or 0
    # Movies and music count hours, not minutes
    if kind != BOOK:
        s['size_done'] = _hours(s['size_done'])
        s['size_owned'] = _hours(s['size_owned'])
    s['done_pct'] = round(100 * s['done_owned'] / s['owned']) if s['owned'] else 0

    longest = conn.execute(f'''
        SELECT b.title, {size} AS size FROM {view} b
        WHERE b.added_by = ? AND b.owned = 1 AND b.removed_at IS NULL AND {size} IS NOT NULL
        ORDER BY size DESC, b.title LIMIT 1
    ''', (user_id,)).fetchone()
    s['longest'] = dict(longest) if longest else None
    if s['longest'] and kind != BOOK:
        s['longest']['size'] = media.format_runtime(s['longest']['size'])

    def rows(sql, params=p):
        return [dict(r) for r in conn.execute(sql, params).fetchall()]

    s['by_format'] = rows(f'''
        SELECT COALESCE(NULLIF(b.format, ''), :plain) AS format, COUNT(*) AS count
        FROM {view} b WHERE b.added_by = :u AND b.owned = 1 AND b.removed_at IS NULL
        GROUP BY 1 ORDER BY count DESC, format
    ''', {**p, 'plain': 'Print' if kind == BOOK else 'Unknown'})
    s['top_genres'] = rows(f'''
        WITH {shelf_cte}
        SELECT b.genre, COUNT(*) AS count FROM done b
        WHERE b.genre IS NOT NULL AND b.genre != ''
        GROUP BY LOWER(b.genre) ORDER BY count DESC, b.genre LIMIT 5
    ''')
    s['top_creators'] = rows(f'''
        WITH {shelf_cte}
        SELECT b.author AS name, COUNT(*) AS count, ROUND(AVG(r.rating), 1) AS avg_rating
        FROM done b
        LEFT JOIN read_data r ON r.book_id = b.id AND r.user_id = :u
        WHERE b.author IS NOT NULL AND b.author != ''
        GROUP BY LOWER(b.author) ORDER BY count DESC, avg_rating DESC, b.author LIMIT 5
    ''')
    s['statuses'] = rows(f'''
        SELECT c.status, COUNT(*) AS count FROM collections c
        WHERE c.user_id = :u AND {only(kind, 'c.book_id')}
        GROUP BY c.status ORDER BY count DESC
    ''')
    s['by_decade'] = rows(f'''
        WITH {shelf_cte}
        SELECT (CAST(b.publish_year AS INTEGER) / 10) * 10 AS decade, COUNT(*) AS count
        FROM shelf b WHERE CAST(b.publish_year AS INTEGER) > 0
        GROUP BY decade ORDER BY decade
    ''')
    spread = {r['rating']: r['count'] for r in rows(f'''
        SELECT r.rating, COUNT(*) AS count FROM read_data r
        WHERE r.user_id = :u AND r.rating BETWEEN 1 AND 5 AND {only(kind, 'r.book_id')}
        GROUP BY r.rating
    ''')}
    s['ratings'] = [{'stars': n, 'count': spread.get(n, 0)} for n in range(5, 0, -1)]

    # Movies & TV (15.1): owned and watched per kind, NULL being a movie. A
    # split of the counts only; hours stay one number.
    if kind == media.VIDEO:
        split = {k: {'owned': 0, 'done': 0} for k in media.VIDEO_KINDS}
        for r in rows(f'''
            WITH {shelf_cte}
            SELECT 'owned' AS what, CASE WHEN b.video_kind = 'tv' THEN 'tv' ELSE 'movie' END AS k,
                   COUNT(*) AS count FROM shelf b GROUP BY k
            UNION ALL
            SELECT 'done', CASE WHEN b.video_kind = 'tv' THEN 'tv' ELSE 'movie' END AS k,
                   COUNT(*) FROM done b GROUP BY k
        '''):
            split[r['k']][r['what']] = r['count']
        s['by_kind'] = split
        s['has_tv'] = bool(split[media.TV]['owned'] or split[media.TV]['done'])
    s['rated'] = sum(spread.values())
    s['by_month'] = by_month(conn, user_id, kind, today)
    return s


def by_month(conn, user_id, kind=BOOK, today=None):
    """Items finished per month, for the profile chart: twelve months ending
    this month. If nothing was finished in that window (say the log went
    quiet), the window ends at the last finished one instead, so the chart
    still shows something; the template prints the range either way.

    An item finished twice in one month counts once. Returns None when the
    user has never finished one of this type.
    """
    rows = conn.execute(f"""
        SELECT strftime('%Y-%m', date_completed) AS month, COUNT(DISTINCT book_id) AS items
        FROM reading_sessions
        WHERE user_id = ? AND date_completed IS NOT NULL AND {only(kind)}
          AND strftime('%Y-%m', date_completed) IS NOT NULL
        GROUP BY month
    """, (user_id,)).fetchall()
    counts = {row['month']: row['items'] for row in rows}
    if not counts:
        return None

    today = today or datetime.now()

    def window(y, m):
        """The twelve (year, month) pairs ending at y-m, oldest first."""
        months = []
        for _ in range(12):
            months.append((y, m))
            y, m = (y, m - 1) if m > 1 else (y - 1, 12)
        return months[::-1]

    months = window(today.year, today.month)
    if not any(f'{y:04d}-{m:02d}' in counts for y, m in months):
        last = max(counts)                       # 'YYYY-MM' sorts as a date
        months = window(int(last[:4]), int(last[5:]))

    bars = [{'year': y,
             'label': datetime(y, m, 1).strftime('%b'),
             'name': datetime(y, m, 1).strftime('%B %Y'),
             'items': counts.get(f'{y:04d}-{m:02d}', 0)} for y, m in months]
    peak = max(bar['items'] for bar in bars)
    for bar in bars:
        bar['pct'] = round(100 * bar['items'] / peak) if peak else 0
    return {'bars': bars, 'peak': peak, 'total': sum(bar['items'] for bar in bars),
            'start': bars[0]['name'], 'end': bars[-1]['name']}


def reading_goals(conn, user_id, today=None):
    """This year's reading goal, for the line under the bio (ROADMAP 12.3):
        {'year': 2026, 'goal': 30 or None, 'done': 12, 'pct': 40}
    `done` is the books with a session finished this year, each once. Past
    years are the stats card's "Year by year" (year_by_year)."""
    today = today or datetime.now()
    goal = conn.execute('SELECT goal FROM reading_goals WHERE user_id = ? AND year = ?',
                        (user_id, today.year)).fetchone()
    goal = goal['goal'] if goal else None
    done = conn.execute(f"""
        SELECT COUNT(DISTINCT book_id) FROM reading_sessions
        WHERE user_id = ? AND {only(BOOK)} AND strftime('%Y', date_completed) = ?
    """, (user_id, str(today.year))).fetchone()[0]
    return {'year': today.year, 'goal': goal, 'done': done,
            'pct': min(100, round(100 * done / goal)) if goal else 0}


# ---------------------------------------------------------------- all media

def year_by_year(conn, user_id, today=None):
    """Items finished per year and type, with the reading goal (books), for
    the All tab's "Year by year" (ROADMAP 12.2/12.3). Newest first, from
    this year back to the first year with a finished item or a goal. A run
    of two or more empty years (nothing finished, no goal) is one row whose
    'since' is the run's first year. Each row:
        {'year', 'counts': {type: n}, 'total', 'goal' or None, 'since' or None,
         'segments': [(type, pct)], 'goal_pct'}
    with percentages of the busiest year (or the biggest goal), so every
    bar in the block shares one scale. Returns [] when there's nothing."""
    today = today or datetime.now()
    counts = {}
    for r in conn.execute("""
        SELECT CAST(strftime('%Y', s.date_completed) AS INTEGER) AS year, b.media_type AS kind,
               COUNT(DISTINCT s.book_id) AS n
        FROM reading_sessions s JOIN books b ON b.id = s.book_id
        WHERE s.user_id = ? AND strftime('%Y', s.date_completed) IS NOT NULL
        GROUP BY year, kind
    """, (user_id,)).fetchall():
        counts.setdefault(r['year'], {})[r['kind']] = r['n']
    goals = {r['year']: r['goal'] for r in conn.execute(
        'SELECT year, goal FROM reading_goals WHERE user_id = ?', (user_id,)).fetchall()}
    years = [y for y in (*counts, *goals) if y <= today.year]
    if not years:
        return []
    rows = []
    for y in range(today.year, min(years) - 1, -1):
        c = counts.get(y, {})
        row = {'year': y, 'counts': c, 'total': sum(c.values()), 'goal': goals.get(y), 'since': None}
        prev = rows[-1] if rows else None
        empty = not (row['total'] or row['goal'])
        if (prev and empty and not (prev['total'] or prev['goal'])
                and prev['year'] != today.year):
            prev['since'] = y
        else:
            rows.append(row)
    # One scale for every bar: the busiest year, or the biggest goal
    scale = max([r['total'] for r in rows] + [r['goal'] or 0 for r in rows]) or 1
    for r in rows:
        r['segments'] = [(kind, 100 * r['counts'][kind] / scale)
                         for kind in media.MEDIA_TYPES if r['counts'].get(kind)]
        r['goal_pct'] = 100 * r['goal'] / scale if r['goal'] else None
    return rows


def all_stats(conn, user_id, per_type, today=None):
    """The All tab (ROADMAP 12.2): numbers across books, movies and music.
    `per_type` is {kind: type_stats(...)} for the types the user has; the
    totals add those up, the rest is queried across types."""
    today = today or datetime.now()
    total = lambda key: sum(s[key] for s in per_type.values())
    s = {
        'owned': total('owned'), 'done': total('done'), 'done_this_year': total('done_this_year'),
        'reviews': total('reviews'),
        'owned_by_type': [(k, v['owned']) for k, v in per_type.items()],
        'done_by_type': [(k, v['done']) for k, v in per_type.items()],
        'this_year_by_type': [(k, v['done_this_year']) for k, v in per_type.items()],
        # Pages read for books, hours for movies and music: not one unit
        'time': [(k, v['size_done']) for k, v in per_type.items() if v['size_done']],
    }
    p = {'u': user_id}
    s['avg_rating'] = conn.execute(
        'SELECT ROUND(AVG(rating), 1) FROM read_data WHERE user_id = :u AND rating IS NOT NULL', p).fetchone()[0]

    def rows(sql):
        return [dict(r) for r in conn.execute(sql, p).fetchall()]

    done_sql = '''SELECT b.* FROM collections c JOIN books b ON b.id = c.book_id
                  WHERE c.user_id = :u AND c.status IN ({})'''.format(
        ','.join(f"'{v}'" for v in media.DONE_STATUS.values()))
    s['top_creators'] = rows(f'''
        SELECT MIN(b.author) AS name, COUNT(*) AS count,
               GROUP_CONCAT(DISTINCT b.media_type) AS kinds
        FROM ({done_sql}) b WHERE b.author IS NOT NULL AND b.author != ''
        GROUP BY LOWER(b.author) ORDER BY count DESC, name LIMIT 5''')
    for r in s['top_creators']:
        r['kinds'] = (r['kinds'] or '').split(',')
    s['top_genres'] = rows(f'''
        SELECT MIN(b.genre) AS genre, COUNT(*) AS count
        FROM ({done_sql}) b WHERE b.genre IS NOT NULL AND b.genre != ''
        GROUP BY LOWER(b.genre) ORDER BY count DESC, genre LIMIT 5''')
    spread = {r['rating']: r['count'] for r in rows(
        'SELECT rating, COUNT(*) AS count FROM read_data WHERE user_id = :u AND rating BETWEEN 1 AND 5 GROUP BY rating')}
    s['ratings'] = [{'stars': n, 'count': spread.get(n, 0)} for n in range(5, 0, -1)]
    s['rated'] = sum(spread.values())
    # Firsts: how far back the log goes, the oldest thing on the shelf, how
    # much came in this year
    first = conn.execute('SELECT MIN(date_completed) FROM reading_sessions WHERE user_id = :u', p).fetchone()[0]
    s['logging_since'] = first[:4] if first else None
    oldest = conn.execute('''
        SELECT title, media_type, CAST(publish_year AS INTEGER) AS year FROM books
        WHERE added_by = :u AND owned = 1 AND removed_at IS NULL AND CAST(publish_year AS INTEGER) > 0
          AND NOT EXISTS (SELECT 1 FROM wishlist w WHERE w.book_id = books.id AND w.user_id = :u)
        ORDER BY year, title LIMIT 1''', p).fetchone()
    s['oldest'] = dict(oldest) if oldest else None
    s['added_this_year'] = conn.execute('''
        SELECT COUNT(*) FROM books
        WHERE added_by = :u AND owned = 1 AND strftime('%Y', created_at) = :y
          AND NOT EXISTS (SELECT 1 FROM wishlist w WHERE w.book_id = books.id AND w.user_id = :u)''',
        {**p, 'y': str(today.year)}).fetchone()[0]
    s['years'] = year_by_year(conn, user_id, today)
    return s

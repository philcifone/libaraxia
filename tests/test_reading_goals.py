"""Reading goals per year (ROADMAP 12.3)."""
import sqlite3
from datetime import datetime

from conftest import add_book, login, scalar
from test_migrations import fresh_db, run_manage

THIS_YEAR = datetime.now().year


def finish(db, user_id, book_id, date):
    db.execute('INSERT INTO reading_sessions (user_id, book_id, date_completed) VALUES (?, ?, ?)',
               (user_id, book_id, date))
    db.commit()


def test_029_keeps_the_old_goal_as_this_years(tmp_path):
    path = tmp_path / 'at-028.db'
    conn = fresh_db(path)
    conn.executescript("""
        DROP TABLE reading_goals;
        DELETE FROM schema_migrations WHERE name = '029_reading_goals.sql';
        INSERT INTO users (id, username, email, password, reading_goal) VALUES
            (1, 'phil', 'p@example.test', 'x', 30), (2, 'nogoal', 'n@example.test', 'x', 0);
    """)
    conn.close()
    run_manage('--db', str(path), 'migrate', '-y')
    conn = sqlite3.connect(path)
    rows = conn.execute('SELECT user_id, year, goal FROM reading_goals').fetchall()
    conn.close()
    assert rows == [(1, THIS_YEAR, 30)]


def test_counts_per_year_and_year_by_year(app, db, people):
    from utils.stats import reading_goals, year_by_year
    alice = people['alice']
    one, two = add_book(db, alice, 'One'), add_book(db, alice, 'Two')
    finish(db, alice, one, '2024-03-01')
    finish(db, alice, one, '2024-09-01')         # twice in a year: once
    finish(db, alice, one, '2026-01-05')         # a re-read next year counts again
    finish(db, alice, two, '2026-02-01')
    db.executemany('INSERT INTO reading_goals (user_id, year, goal) VALUES (?, ?, ?)',
                   [(alice, 2024, 5), (alice, 2026, 4)])
    db.commit()
    today = datetime(2026, 6, 1)
    g = reading_goals(db, alice, today=today)
    assert (g['year'], g['goal'], g['done'], g['pct']) == (2026, 4, 2, 50)

    years = year_by_year(db, alice, today=today)
    assert [(y['year'], y['total'], y['goal'], y['since']) for y in years] == [
        (2026, 2, 4, None), (2025, 0, None, None), (2024, 1, 5, None)]
    # One scale for every bar: the biggest goal here (5)
    assert years[0]['segments'] == [('book', 40.0)] and years[0]['goal_pct'] == 80.0
    # A run of empty years is one row; movies count in their own segment
    finish(db, alice, two, '2019-05-05')
    film = db.execute("INSERT INTO books (title, author, added_by, media_type) VALUES ('Heat', 'M', ?, 'video')",
                      (alice,)).lastrowid
    finish(db, alice, film, '2026-03-03')
    years = year_by_year(db, alice, today=today)
    assert [(y['year'], y['since']) for y in years] == [(2026, None), (2025, None), (2024, None), (2023, 2020), (2019, None)]
    assert years[0]['counts'] == {'book': 2, 'video': 1}
    # Nothing at all: no rows
    assert year_by_year(db, people['carol'], today=today) == []


def test_set_change_and_clear_this_years_goal(client, db, people):
    alice = people['alice']
    db.execute('INSERT INTO reading_goals (user_id, year, goal) VALUES (?, ?, 12)', (alice, THIS_YEAR - 1))
    db.commit()
    login(client, 'alice')
    page = client.get('/user/alice').get_data(as_text=True)
    assert f'Set a reading goal for {THIS_YEAR}' in page
    assert 'Year by year' in page                 # past years live in the stats card now

    client.post('/user/update_reading_goal', data={'reading_goal': '30'})
    client.post('/user/update_reading_goal', data={'reading_goal': '25'})
    assert scalar(db, 'SELECT goal FROM reading_goals WHERE user_id = ? AND year = ?', alice, THIS_YEAR) == 25
    page = client.get('/user/alice').get_data(as_text=True)
    assert f'{THIS_YEAR} goal:</span>\n            0 of 25 books' in page
    assert f'{THIS_YEAR - 1}</span>' in page and 'goal 12' in page       # last year's is kept

    client.post('/user/update_reading_goal', data={'reading_goal': '0'})
    assert scalar(db, 'SELECT COUNT(*) FROM reading_goals WHERE user_id = ? AND year = ?', alice, THIS_YEAR) == 0
    assert scalar(db, 'SELECT goal FROM reading_goals WHERE user_id = ?', alice) == 12
    # Nonsense is refused, nothing changes
    client.post('/user/update_reading_goal', data={'reading_goal': 'lots'})
    client.post('/user/update_reading_goal', data={'reading_goal': '-3'})
    assert scalar(db, 'SELECT COUNT(*) FROM reading_goals WHERE user_id = ?', alice) == 1


def test_friends_see_the_goal_but_cant_set_it(client, db, people):
    alice = people['alice']
    login(client, 'carol')                         # alice's friend, no goal of her own
    page = client.get('/user/alice').get_data(as_text=True)
    assert 'reading-goal' not in page              # alice has none: nothing shown
    db.execute('INSERT INTO reading_goals (user_id, year, goal) VALUES (?, ?, 10)', (alice, THIS_YEAR))
    db.commit()
    page = client.get('/user/alice').get_data(as_text=True)
    assert f'{THIS_YEAR} goal:' in page and 'Change goal' not in page and 'update_reading_goal' not in page


def test_marking_read_offers_today_as_the_finished_date(client, db, people):
    from datetime import date
    alice = people['alice']
    book = add_book(db, alice, 'Dune')
    login(client, 'alice')
    r = client.post('/collections/collections/status/add', data={'id': book, 'status': 'read'})
    assert 'finished=1' in r.headers['Location']
    today = date.today().isoformat()
    page = client.get(f'/read/rate_review/{book}?finished=1').get_data(as_text=True)
    assert 'data-prefill-mode="add"' in page and f'data-prefill-completed="{today}"' in page

    # A session started earlier is the one to finish
    db.execute("INSERT INTO reading_sessions (user_id, book_id, date_started) VALUES (?, ?, '2026-01-02')",
               (alice, book))
    db.commit()
    page = client.get(f'/read/rate_review/{book}?finished=1').get_data(as_text=True)
    assert 'data-prefill-mode="edit"' in page and 'data-prefill-started="2026-01-02"' in page

    # Already finished today: nothing offered; and never without ?finished
    db.execute('UPDATE reading_sessions SET date_completed = ? WHERE user_id = ?', (today, alice))
    db.commit()
    assert 'data-prefill-mode' not in client.get(f'/read/rate_review/{book}?finished=1').get_data(as_text=True)
    assert 'data-prefill-mode' not in client.get(f'/read/rate_review/{book}').get_data(as_text=True)

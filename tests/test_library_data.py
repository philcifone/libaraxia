"""Phase 3: what counts as "your library" (the library_books view), stats,
filter options and the removed-books filter."""
import json

from conftest import add_book, add_review, login, scalar


def wishlist(db, user_id, book_id):
    db.execute('INSERT INTO wishlist (user_id, book_id) VALUES (?, ?)', (user_id, book_id))
    db.commit()


def wishlist_stub(db, user_id, title='Wanted'):
    """A wishlist entry the way the app stores one: a books row owned by the
    person wishing, plus their wishlist row."""
    book = add_book(db, user_id, title=title)
    wishlist(db, user_id, book)
    return book


# --- the view ----------------------------------------------------------------

def test_library_books_excludes_own_wishlist_entries_only(db, people):
    alice, carol = people['alice'], people['carol']
    owned = add_book(db, alice, title='On the shelf')
    stub = wishlist_stub(db, alice)
    unowned = add_book(db, None, title='Nobody')
    # carol wishlisting alice's book doesn't take it off alice's shelf
    wishlist(db, carol, owned)

    ids = {r[0] for r in db.execute('SELECT id FROM library_books')}
    assert owned in ids
    assert stub not in ids
    assert unowned not in ids


def test_someone_elses_wishlist_doesnt_hide_book_from_search(client, db, people):
    """Search used to drop any book on *anyone's* wishlist."""
    book = add_book(db, people['alice'], title='Dune')
    wishlist(db, people['carol'], book)
    login(client, 'alice')
    r = client.get('/books/search?search_term=Dune')
    assert b'Dune' in r.data


def test_wishlist_entries_not_in_library_grid_or_friend_counts(client, db, people):
    add_book(db, people['carol'], title='Carols Real Book')
    wishlist_stub(db, people['carol'], title='Carols Wish')
    login(client, 'alice')
    r = client.get('/base/library/carol')
    assert b'Carols Real Book' in r.data and b'Carols Wish' not in r.data


# --- stats -------------------------------------------------------------------

def test_stats_count_only_your_shelf(app, db, people):
    from utils.stats import type_stats
    alice, bob = people['alice'], people['bob']
    read = add_book(db, alice, title='Short', author='X')
    db.execute("UPDATE books SET page_count = 100, genre = 'Fiction' WHERE id = ?", (read,))
    add_review(db, alice, read)                       # on the Read shelf
    add_book(db, alice, title='Unread', author='Y')
    gone = add_book(db, alice, title='Given away', author='Z')
    db.execute("UPDATE books SET removed_at = CURRENT_TIMESTAMP, page_count = 9000 WHERE id = ?", (gone,))
    wishlist_stub(db, alice, title='Wished')
    for i in range(5):                                 # other people's books
        add_book(db, bob, title=f'Bob {i}')
    db.commit()

    s = type_stats(db, alice, 'book')
    assert s['owned'] == 2                             # not removed, not wishlist, not bob's
    assert s['done'] == 1 and s['done_owned'] == 1
    assert s['done_pct'] == 50
    assert s['creators'] == 2
    assert s['longest']['title'] == 'Short'            # the removed 9000-pager doesn't count
    assert s['top_shelf_genre'] == 'Fiction'


def test_books_read_matches_read_shelf_not_reviews(app, db, people):
    from utils.stats import type_stats
    alice = people['alice']
    rated_only = add_book(db, alice, title='Rated, not read')
    db.execute('INSERT INTO read_data (user_id, book_id, rating) VALUES (?, ?, 3)', (alice, rated_only))
    read = add_book(db, alice, title='Read, no review')
    db.execute("INSERT INTO collections (user_id, book_id, status) VALUES (?, ?, 'read')", (alice, read))
    db.commit()
    assert type_stats(db, alice, 'book')['done'] == 1


# --- filters -----------------------------------------------------------------

def test_filter_genres_come_from_your_library(client, db, people):
    mine = add_book(db, people['alice'])
    theirs = add_book(db, people['carol'])
    db.execute("UPDATE books SET genre = 'Mine Genre' WHERE id = ?", (mine,))
    db.execute("UPDATE books SET genre = 'Carol Genre' WHERE id = ?", (theirs,))
    db.commit()
    login(client, 'alice')
    r = client.get('/base/index')
    assert b'Mine Genre' in r.data and b'Carol Genre' not in r.data


def test_removed_filter_hide_include_only(client, db, people):
    add_book(db, people['alice'], title='Still Here')
    gone = add_book(db, people['alice'], title='Long Gone')
    db.execute('UPDATE books SET removed_at = CURRENT_TIMESTAMP WHERE id = ?', (gone,))
    db.commit()
    login(client, 'alice')
    ajax = {'X-Requested-With': 'XMLHttpRequest'}

    def titles(arg):
        return {b['title'] for b in client.get('/base/index' + arg, headers=ajax).get_json()['books']}

    assert titles('') == {'Still Here'}
    assert titles('?show_removed=include') == {'Still Here', 'Long Gone'}
    assert titles('?show_removed=1') == {'Still Here', 'Long Gone'}     # old links
    assert titles('?show_removed=only') == {'Long Gone'}


def test_minimum_rating_filter_means_and_up(client, db, people):
    four = add_book(db, people['alice'], title='Four')
    five = add_book(db, people['alice'], title='Five')
    add_review(db, people['alice'], four, rating=4)
    add_review(db, people['alice'], five, rating=5)
    login(client, 'alice')
    r = client.get('/base/index?rating=4', headers={'X-Requested-With': 'XMLHttpRequest'})
    assert {b['title'] for b in r.get_json()['books']} == {'Four', 'Five'}


# --- duplicate check (3.3) ---------------------------------------------------

def test_duplicate_check_matches_other_editions(client, db, people):
    """Les Misérables wishlisted twice: once with an ISBN, once without."""
    stub = wishlist_stub(db, people['alice'], title='Les Miserables')
    db.execute("UPDATE books SET author = 'Victor Hugo', isbn = '1616003553' WHERE id = ?", (stub,))
    db.commit()
    login(client, 'alice')
    for url in ('/wishlist/check_duplicates', '/books/check_duplicates'):
        r = client.post(url, json={'title': 'Les Misérables', 'author': 'Victor Hugo', 'isbn': ''})
        dups = r.get_json()['duplicates']
        assert [d['id'] for d in dups] == [stub]
        assert dups[0]['in_wishlist'] and not dups[0]['in_library']


def test_duplicate_check_title_with_different_author_is_not_a_match(client, db, people):
    add_book(db, people['alice'], title='Collected Poems', author='Philip Larkin')
    login(client, 'alice')
    r = client.post('/books/check_duplicates', json={'title': 'Collected Poems', 'author': 'Sylvia Plath'})
    assert r.get_json()['has_duplicates'] is False


def test_duplicate_check_ignores_books_outside_household(client, db, people):
    """carol is a friend, not household: her shelf isn't searched (and her
    titles aren't revealed)."""
    add_book(db, people['carol'], title='Secret Title')
    household = add_book(db, people['bob'], title='Shared Title')
    login(client, 'alice')
    assert client.post('/wishlist/check_duplicates', json={'title': 'Secret Title'}).get_json()['has_duplicates'] is False
    dups = client.post('/wishlist/check_duplicates', json={'title': 'shared title'}).get_json()['duplicates']
    assert [d['id'] for d in dups] == [household] and dups[0]['in_library']


def test_duplicate_check_isbn_ignores_hyphens(client, db, people):
    book = add_book(db, people['alice'], title='Whatever')
    db.execute("UPDATE books SET isbn = '9780593098264' WHERE id = ?", (book,))
    db.commit()
    login(client, 'alice')
    dups = client.post('/books/check_duplicates', json={'title': 'Heretics', 'isbn': '978-0-593-09826-4'}).get_json()['duplicates']
    assert dups[0]['match_reason'] == ['ISBN']


# --- placeholder covers (3.2) ------------------------------------------------

def _cover_like(seed=1, size=(300, 450)):
    """A busy, cover-shaped test image (random noise blocks)."""
    import random
    from PIL import Image
    rnd = random.Random(seed)
    small = Image.new('RGB', (12, 18))
    small.putdata([tuple(rnd.randrange(256) for _ in range(3)) for _ in range(12 * 18)])
    return small.resize(size, Image.NEAREST)


def test_placeholder_reason_blank_strip_tiny_and_real():
    from PIL import Image
    from utils.book_utils import placeholder_reason
    assert placeholder_reason(Image.new('RGB', (500, 700), 'white')) == 'blank'
    assert 'strip' in placeholder_reason(_cover_like(size=(500, 80)))
    assert 'tiny' in placeholder_reason(Image.new('RGB', (1, 1)))
    assert placeholder_reason(_cover_like()) is None


def _page(ink='black', accent=None, accent_share=0.0):
    """A white 300x450 'page' with some lines of text-like ink, and optionally
    a coloured block covering accent_share of the area."""
    from PIL import Image, ImageDraw
    img = Image.new('RGB', (300, 450), 'white')
    d = ImageDraw.Draw(img)
    for y in range(60, 200, 24):                     # title-page lines of "text"
        d.rectangle([60, y, 240, y + 6], fill=ink)
    if accent:
        side = int((300 * 450 * accent_share) ** 0.5)
        d.rectangle([20, 380, 20 + side, 380 + side], fill=accent)
    return img


def test_placeholder_reason_title_page_scan():
    """Google Books sometimes offers a scanned title page as the cover:
    mostly white, grey ink, no colour."""
    from utils.book_utils import placeholder_reason
    assert 'page scan' in placeholder_reason(_page())
    assert 'page scan' in placeholder_reason(_page(ink='#555555'))


def test_white_covers_with_colour_are_kept():
    """A white jacket with a little colour (Blink: 0.9% blue) is a real cover,
    and so is a colourless one that isn't mostly white (a grey photo cover)."""
    from PIL import Image
    from utils.book_utils import placeholder_reason
    assert placeholder_reason(_page(accent='#2255cc', accent_share=0.012)) is None
    grey_photo = _cover_like(seed=3).convert('L').convert('RGB')
    assert placeholder_reason(grey_photo) is None


def test_dhash_survives_resize_and_reencode():
    """Why a perceptual hash and not SHA-256: the saved copy is resized and
    re-encoded, and must still match."""
    from io import BytesIO
    from PIL import Image
    from utils.book_utils import cover_dhash
    original = _cover_like(seed=7)
    buf = BytesIO()
    original.resize((500, 750)).save(buf, 'JPEG', quality=60)
    copy = Image.open(BytesIO(buf.getvalue()))
    assert bin(cover_dhash(original) ^ cover_dhash(copy)).count('1') <= 6
    other = _cover_like(seed=8)
    assert bin(cover_dhash(original) ^ cover_dhash(other)).count('1') > 6


def test_fetch_image_rejects_placeholders(app, monkeypatch):
    """A cover service answering with a blank image is treated as a miss."""
    from io import BytesIO
    from PIL import Image
    import utils.book_utils as bu

    class FakeRaw:
        def __init__(self, img):
            buf = BytesIO()
            img.save(buf, 'PNG')
            self.data = buf.getvalue()

        def read(self, n, decode_content=True):
            return self.data[:n]

    class FakeResponse:
        status_code = 200

        def __init__(self, img):
            self.raw = FakeRaw(img)

    images = {'blank': Image.new('RGB', (400, 600), (200, 200, 200)), 'real': _cover_like()}
    monkeypatch.setattr(bu, '_get_public', lambda url: FakeResponse(images[url]))
    with app.app_context():
        assert bu._fetch_image('blank') is None
        assert bu._fetch_image('real') is not None


def test_clear_placeholder_covers(client, app, db, people):
    import os
    import uuid
    from PIL import Image
    uploads = os.path.join(app.root_path, 'static', 'uploads')
    os.makedirs(uploads, exist_ok=True)
    blank = f'uploads/test_blank_{uuid.uuid4().hex}.jpg'
    real = f'uploads/test_real_{uuid.uuid4().hex}.jpg'
    Image.new('RGB', (500, 700), 'white').save(os.path.join(app.root_path, 'static', blank))
    _cover_like().save(os.path.join(app.root_path, 'static', real))
    try:
        a = add_book(db, people['alice'], title='Blank A', cover=blank)
        b = add_book(db, people['alice'], title='Blank B', cover=blank)    # same file, two books
        keep = add_book(db, people['alice'], title='Real', cover=real)
        login(client, 'alice')
        page = client.get('/admin/placeholder_covers')
        assert b'Blank A' in page.data and b'Real' not in page.data.split(b'2. Fetch')[0]

        client.post('/admin/clear_placeholder_covers')
        covers = dict(db.execute('SELECT id, cover_image_url FROM books').fetchall())
        assert covers[a] is None and covers[b] is None and covers[keep] == real
        assert not os.path.exists(os.path.join(app.root_path, 'static', blank))
        assert os.path.exists(os.path.join(app.root_path, 'static', real))
    finally:
        for path in (blank, real):
            full = os.path.join(app.root_path, 'static', path)
            if os.path.exists(full):
                os.remove(full)


def test_clear_placeholder_covers_is_admin_only(client, db, people):
    login(client, 'bob')
    r = client.post('/admin/clear_placeholder_covers')
    assert r.status_code in (302, 403)
    assert b'Cleared' not in client.get('/base/index').data


# --- Goodreads HTML in reviews (3.4) -------------------------------------------

def test_migration_019_turns_br_into_newlines(db, people):
    import os
    from conftest import ROOT
    alice = people['alice']
    reviews = {
        'Goodreads style<br/><br/>second paragraph<br/>line': 'Goodreads style\n\nsecond paragraph\nline',
        'Hand edited \r\n<br>\r\nnext': 'Hand edited \n\nnext',
        'Trailing break<br/>': 'Trailing break',
        'No HTML here\n\n\n\nkept as is': 'No HTML here\n\n\n\nkept as is',
    }
    for i, text in enumerate(reviews):
        book = add_book(db, alice, title=f'B{i}')
        db.execute('INSERT INTO read_data (user_id, book_id, rating, comment) VALUES (?, ?, 4, ?)', (alice, book, text))
    db.commit()
    with open(os.path.join(ROOT, 'migrations', '019_clean_goodreads_reviews.sql'), encoding='utf-8') as f:
        db.executescript(f.read())
    got = [r[0] for r in db.execute('SELECT comment FROM read_data ORDER BY book_id')]
    assert got == list(reviews.values())


def test_goodreads_review_text():
    from utils.goodreads import review_text as goodreads_review_text
    assert goodreads_review_text('One<br/><br/>Two &amp; <b>three</b><BR />four') == 'One\n\nTwo & three\nfour'
    assert goodreads_review_text('') == ''
    assert goodreads_review_text(None) == ''


# --- error handling (3.5) ----------------------------------------------------

def test_exception_text_is_not_sent_to_the_browser(client, db, people, monkeypatch):
    import blueprints.books as books_bp

    def boom(**kwargs):
        raise RuntimeError('SECRET /home/phil/library.db detail')
    monkeypatch.setattr(books_bp, 'cover_search_steps', boom)
    login(client, 'alice')
    r = client.post('/books/fetch_cover', json={'isbn': '9780000000000', 'title': 'X'})
    assert b'SECRET' not in r.data
    last = json.loads(r.get_data(as_text=True).strip().splitlines()[-1])
    assert last['type'] == 'done' and last['count'] == 0 and last['error']


def test_find_a_better_cover_streams_progress_and_covers(client, db, people, monkeypatch):
    """One line per source asked, one per download, each cover as it lands,
    and a final 'done'. A source that fails is skipped; a duplicate URL is
    downloaded once; a failed download just isn't sent."""
    import blueprints.books as books_bp

    def broken():
        raise TimeoutError('slow')
    monkeypatch.setattr(books_bp, 'cover_search_steps', lambda **kw: [
        ('Open Library', lambda: [('https://a.test/1.jpg', 'Open Library'), ('https://a.test/2.jpg', 'Open Library')]),
        ('Goodreads', broken),
        ('Google Books', lambda: [('https://a.test/1.jpg', 'Google Books'), ('https://b.test/3.jpg', 'Google Books')]),
    ])
    # Each URL is downloaded as its own candidate list (a Google link would
    # become two sizes, google_cover_candidates; these aren't Google's)
    monkeypatch.setattr(books_bp, 'save_best_cover',
                        lambda urls: None if urls[0].endswith('2.jpg') else 'uploads/' + urls[0].rsplit('/', 1)[1])
    login(client, 'alice')
    r = client.post('/books/fetch_cover', json={'title': 'Dune', 'author': 'Herbert'})
    assert r.mimetype == 'application/x-ndjson'
    events = [json.loads(l) for l in r.get_data(as_text=True).splitlines()]
    assert [(e['phase'], e['label']) for e in events if e['type'] == 'step'] == [
        ('search', 'Open Library'), ('search', 'Goodreads'), ('search', 'Google Books'),
        ('download', 'Open Library'), ('download', 'Open Library'), ('download', 'Google Books')]
    assert [e['url'] for e in events if e['type'] == 'cover'] == ['uploads/1.jpg', 'uploads/3.jpg']
    assert events[-1] == {'type': 'done', 'count': 2}


# --- Add Book: "Add it anyway" for a second copy (8.6) ------------------------

def _post_book(client, title, **extra):
    return client.post('/books/add', data={'submit_book': '1', 'title': title,
                                           'author': 'Ann Author', **extra})


def test_add_book_refuses_a_copy_on_the_household_shelf(client, db, people):
    """bob (household) owns it: refused, re-rendered filled in with the
    notice and the tick box, nothing saved."""
    add_book(db, people['bob'], title='Dune', author='Ann Author')
    login(client, 'alice')
    r = _post_book(client, 'Dune', isbn='9780441013593')
    assert r.status_code == 400
    page = r.get_data(as_text=True)
    assert 'name="confirm_duplicate"' in page and 'Add it anyway' in page
    assert 'value="9780441013593"' in page        # the form keeps what you typed
    assert scalar(db, "SELECT COUNT(*) FROM books WHERE title = 'Dune'") == 1


def test_add_book_second_copy_when_ticked(client, db, people):
    add_book(db, people['alice'], title='Dune', author='Ann Author')
    login(client, 'alice')
    r = _post_book(client, 'Dune', confirm_duplicate='1')
    assert r.status_code == 302
    assert scalar(db, "SELECT COUNT(*) FROM books WHERE title = 'Dune'") == 2


def test_add_book_wishlist_match_is_not_refused(client, db, people):
    """Buying a book you wished for is the normal case, not a duplicate."""
    wishlist_stub(db, people['alice'], title='Wanted Book')
    login(client, 'alice')
    assert _post_book(client, 'Wanted Book').status_code == 302


def test_add_book_refused_keeps_only_safe_cover_paths(client, db, people):
    add_book(db, people['alice'], title='Dune', author='Ann Author')
    login(client, 'alice')
    page = _post_book(client, 'Dune', existing_cover_url='../../etc/passwd').get_data(as_text=True)
    assert 'etc/passwd' not in page


def test_find_a_better_cover_on_add_book_and_for_owners(client, db, people, monkeypatch):
    """The button is on Add Book (books only) as well as Edit Book, and the
    route isn't admin-only any more: an owner who isn't an admin can use it."""
    import blueprints.books as books_bp
    monkeypatch.setattr(books_bp, 'cover_search_steps', lambda **kw: [])
    login(client, 'bob')                                        # not an admin
    add = client.get('/books/add').get_data(as_text=True)
    assert 'id="fetch-cover-btn"' in add and 'cover_finder.js' in add
    movie = client.get('/videos/add').get_data(as_text=True)
    assert 'id="fetch-cover-btn"' not in movie and 'cover_finder.js' not in movie
    r = client.post('/books/fetch_cover', json={'title': 'Dune'})
    assert r.status_code == 200
    assert json.loads(r.get_data(as_text=True).splitlines()[-1])['type'] == 'done'


# --- Cover quality (ROADMAP 8F) ---------------------------------------------

def test_google_cover_candidates_ask_for_the_large_size_first():
    """Any Google cover link for a volume becomes the same pair: 800x1200
    (fife), then the 128 px zoom=1 every volume has. Never the zoom-less
    URL: that's Google's "image not available" banner for unscanned books."""
    from utils.book_utils import google_cover_candidates, _google_cover_urls
    link = 'http://books.google.com/books/content?id=XfFvDwAAQBAJ&printsec=frontcover&img=1&zoom=1&edge=curl&source=gbs_api'
    expected = ['https://books.google.com/books/content?id=XfFvDwAAQBAJ&printsec=frontcover&img=1&fife=w800-h1200',
                'https://books.google.com/books/content?id=XfFvDwAAQBAJ&printsec=frontcover&img=1&zoom=1']
    assert google_cover_candidates(link) == expected
    assert _google_cover_urls({'imageLinks': {'smallThumbnail': link.replace('zoom=1', 'zoom=5'),
                                              'thumbnail': link}}) == expected
    assert _google_cover_urls({}) == []
    # Anything else is left alone
    ol = 'https://covers.openlibrary.org/b/isbn/9780735211292-L.jpg?default=false'
    assert google_cover_candidates(ol) == [ol]
    assert google_cover_candidates('') == []


def test_search_results_without_a_google_image_show_open_library(app, monkeypatch):
    """Some volumes have no Google image at all (Infinite Jest): the result
    shows Open Library's cover for its ISBN instead, and one with neither
    has no thumbnail (the page shows its no-cover box)."""
    from utils import book_utils
    link = 'http://books.google.com/books/content?id=XfFvDwAAQBAJ&printsec=frontcover&img=1&zoom=1'
    monkeypatch.setattr(book_utils, '_google_volumes', lambda q, n: [
        {'volumeInfo': {'title': 'Infinite Jest',
                        'industryIdentifiers': [{'type': 'ISBN_10', 'identifier': '0316920045'}]}},
        {'volumeInfo': {'title': 'Has one', 'imageLinks': {'thumbnail': link},
                        'industryIdentifiers': [{'type': 'ISBN_10', 'identifier': '0316920045'}]}},
        {'volumeInfo': {'title': 'Neither'}},
    ])
    with app.app_context():
        results = book_utils.search_google_books('infinite jest')
    thumbs = [r['volumeInfo']['imageLinks'].get('thumbnail') for r in results]
    assert thumbs == ['https://covers.openlibrary.org/b/isbn/0316920045-M.jpg?default=false',
                      'https://books.google.com/books/content?id=XfFvDwAAQBAJ&printsec=frontcover&img=1&zoom=1',
                      None]


def test_picking_a_search_result_tries_large_google_then_open_library(client, db, people, monkeypatch):
    """Add Book's search result only carries Google's 128 px thumbnail.
    Picking it tries the large size, the thumbnail, then Open Library by
    ISBN, and saves the best (save_best_cover keeps the largest)."""
    import blueprints.books as books_bp
    tried = []
    monkeypatch.setattr(books_bp, 'save_best_cover', lambda urls: tried.extend(urls) or 'uploads/best.jpg')
    login(client, 'alice')
    r = client.post('/books/select_search_result', json={'bookData': {
        'title': 'Atomic Habits', 'isbn': '9780735211292',
        'thumbnail': 'https://books.google.com/books/content?id=XfFvDwAAQBAJ&printsec=frontcover&img=1&zoom=1'}})
    assert r.get_json()['book_details']['local_cover_url'] == 'uploads/best.jpg'
    assert tried[0].endswith('&fife=w800-h1200') and tried[1].endswith('&zoom=1')
    assert any('covers.openlibrary.org/b/isbn/9780735211292' in u for u in tried[2:])

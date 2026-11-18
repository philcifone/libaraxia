"""The item page's catalog card (utils/catalog_card.py, _catalog_card.html;
paper-cards trial): the facts typed as a library main-entry card."""
from conftest import add_book, login

from utils import catalog_card


def row(**fields):
    """A books row as a dict, every column the card reads defaulting to None."""
    base = dict(id=7, media_type='book', title='A Book', author=None, publisher=None,
                publish_year=None, page_count=None, isbn=None, genre=None, format=None,
                runtime_minutes=None, catalog_number=None, barcode=None, video_kind=None)
    base.update(fields)
    return base


def test_a_book_card_reads_like_a_library_main_entry():
    book = row(id=123, title='The Fellowship of the Ring', author='J. R. R. Tolkien',
               publisher='Houghton Mifflin', publish_year=1954, page_count=423,
               isbn='0395489318', genre='Fiction')
    card = catalog_card.entry(book)
    assert card['call_number'] == ['FIC', 'TOL', 'f', '1954']     # "The" is skipped for the work mark
    assert card['heading'] == 'Tolkien, J. R. R.'
    assert card['title'] == 'The Fellowship of the Ring / J. R. R. Tolkien. -- Houghton Mifflin, 1954.'
    assert card['physical'] == '423 p.'
    assert card['number'] == 'ISBN 0395489318'
    assert card['tracings'] == '1. Fiction.  I. Title.'
    assert card['accession'] == '000123'


def test_the_class_comes_from_the_genre_and_is_left_out_when_unknown():
    assert catalog_card.class_for(row(genre='Biography & Autobiography')) == '920'
    assert catalog_card.class_for(row(genre='BIOGRAPHY & AUTOBIOGRAPHY')) == '920'
    assert catalog_card.class_for(row(genre='Juvenile Fiction')) == 'J FIC'      # the longest prefix wins
    assert catalog_card.class_for(row(genre='Fiction / Fantasy / Epic')) == 'FIC'
    assert catalog_card.class_for(row(genre='Dragons')) == ''                   # no guess
    assert catalog_card.class_for(row(genre=None)) == ''
    # No class, author, year: what's known is all that's printed
    assert catalog_card.call_number(row(title='Untitled')) == ['UNT', 'u']


def test_only_a_books_people_are_inverted_and_split():
    assert catalog_card.heading(row(author='Neil Gaiman, Terry Pratchett')) == 'Gaiman, Neil'
    assert catalog_card.heading(row(author='Plato')) == 'Plato'
    # An album's artist is one act, never inverted or split
    album = row(media_type='record', title='Bridge over Troubled Water',
                author='Simon & Garfunkel', format='LP')
    assert catalog_card.heading(album) == 'Simon & Garfunkel'
    assert catalog_card.call_number(row(media_type='record', title='Abbey Road',
                                        author='The Beatles', format='LP'))[:3] == ['LP', 'BEA', 'a']


def test_a_movie_is_a_title_entry_filed_by_format():
    film = row(media_type='video', title='Dr. Strangelove', author='Stanley Kubrick',
               format='VHS', publish_year=1964, runtime_minutes=95, genre='Comedy')
    card = catalog_card.entry(film)
    assert card['heading'] == ''                      # the title paragraph starts the card
    assert card['call_number'] == ['CART', 'DRS', '1964']
    assert card['title'] == 'Dr. Strangelove / directed by Stanley Kubrick. -- 1964.'
    assert card['physical'] == '1 videocartridge (95 min.)'
    assert card['tracings'] == '1. Comedy.  I. Stanley Kubrick.'
    show = row(media_type='video', video_kind='tv', title='Twin Peaks', author='David Lynch', format='DVD')
    assert 'created by David Lynch' in catalog_card.title_paragraph(show)
    assert catalog_card.physical_description(show) == '1 videodisc'
    assert catalog_card.standard_number(row(media_type='video', barcode='0012345678905')) == 'UPC 0012345678905'


def test_every_format_has_a_physical_description():
    rec = dict(media_type='record', runtime_minutes=45)
    assert catalog_card.physical_description(row(**rec, format='LP')) == \
        '1 sound disc (45 min.) : analog, 33 1/3 rpm ; 12 in.'
    assert catalog_card.physical_description(row(**rec, format='7in')).endswith('45 rpm ; 7 in.')
    assert catalog_card.physical_description(row(**rec, format='CD')).endswith('digital ; 4 3/4 in.')
    assert catalog_card.physical_description(row(**rec, format='Cassette')) == '1 sound cassette (45 min.) : analog.'
    assert catalog_card.physical_description(row(format='Audiobook', page_count=300)) == '1 audiobook'
    assert catalog_card.physical_description(row()) == ''           # a book without a page count
    for fmt in ('LP', 'EP', '7in', '10in', '12in', 'CD', 'Cassette'):
        assert catalog_card.physical_description(row(media_type='record', format=fmt)).startswith('1 sound')
    assert catalog_card.standard_number(row(media_type='record', publisher='Sub Pop',
                                            catalog_number='SP1293')) == 'Sub Pop SP1293'


def test_the_item_page_carries_the_card(client, db, people):
    book = add_book(db, people['alice'], title='Dune', author='Frank Herbert')
    login(client, 'alice')
    page = client.get(f'/books/book/{book}').get_data(as_text=True)
    assert 'data-catalog-card' in page
    assert 'Herbert, Frank' in page
    assert f'{book:06d}' in page


def test_stamp_date_prints_a_library_date_stamp():
    assert catalog_card.stamp_date('2026-11-13 04:15:19') == 'NOV 13 2026'
    assert catalog_card.stamp_date('2024-01-01') == 'JAN 01 2024'
    for nothing in (None, '', 'soon', '2024-13-01'):
        assert catalog_card.stamp_date(nothing) == ''


def test_the_reading_info_is_a_book_card_with_stamped_reads(client, db, people):
    from conftest import add_review
    book = add_book(db, people['alice'], title='Dune', author='Frank Herbert')
    add_review(db, people['alice'], book)              # read on 2024-01-01, reviewed
    login(client, 'alice')
    page = client.get(f'/books/book/{book}').get_data(as_text=True)
    assert 'class="library-card book-card' in page
    # The ledger: the read came back on 2024-01-01 (no start date, so one line)
    ledger = page.split('<ol class="ledger">')[1].split('</ol>')[0]
    assert '<span class="ledger-date">JAN 01 2024' in ledger
    assert ledger.count('checked in') == 1 and 'checked out' not in ledger
    assert 'data-click="editSession"' in ledger and 'data-click="showAddSessionForm"' in ledger
    # The review's pencil, and no Author / Title lines (the page heading has them)
    assert 'class="review-pencil"' in page
    assert 'card-head' not in page
    # The status boxes are still the status form's own submit buttons
    status_form = page.split('data-item-status>')[1].split('</form>')[0]
    assert status_form.count('type="submit" name="status"') >= 4
    assert 'aria-pressed="true">' in status_form        # the ticked one: Read


def test_the_shelf_cabinet_puts_filters_in_the_bottom_row(client, db, people):
    """In the Shelf style's catalog cabinet over a grid, the filter button and
    panel end the view bar and bulk select reads Batch; elsewhere they stay
    beside the search box."""
    add_book(db, people['alice'], title='Dune')
    login(client, 'alice')
    page = client.get('/base/index').get_data(as_text=True)
    assert page.index('id="filter-toggle"') < page.index('class="view-bar')
    assert 'data-idle="Select"' in page

    db.execute("UPDATE users SET theme_style = 'shelf' WHERE id = ?", (people['alice'],))
    db.commit()
    page = client.get('/base/index').get_data(as_text=True)
    assert page.count('id="filter-toggle"') == 1 and page.count('id="filter-panel"') == 1
    assert page.index('class="view-bar') < page.index('id="filter-toggle"')
    assert 'data-idle="Batch"' in page

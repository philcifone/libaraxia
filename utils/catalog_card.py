"""The item page's catalog card (Shelf style; paper-cards trial, Phil
2026-11-18): an item's facts typed out as a library's main-entry card,
the way a cataloguer laid one out under AACR2.

    FIC      Tolkien, J. R. R.
    TOL         The fellowship of the ring / J. R. R. Tolkien. --
    f        Houghton Mifflin, 1954.
    1954        423 p. ; ISBN 0395489318
                   1. Fiction.  I. Title.
                                                    Acc. no. 000123

- Call number (the left margin, one part per line): a class from the
  genre, a Cutter-style mark (the first three letters of the author's
  surname, or of the title when there's no author), the work mark (the
  title's first letter after an article) and the year. The class is the
  only guess: the genres are Google Books' categories, mapped to the
  Dewey hundreds they correspond to (CLASSES); an unknown genre gets no
  class rather than a wrong one. Movies and music file by format instead
  (DVD, CART, LP, CD ...), as a library's media shelves do.
- Physical description in cataloguers' terms ("1 videocartridge (120
  min.)", "1 sound disc : analog, 33 1/3 rpm ; 12 in."). AACR2 really does
  call a cartridge a videocartridge, which suits the UI's name for VHS.
- Tracings: the genre as subject, then the added entries.
- Accession number: the row's id. A library numbers what it acquires in
  order, which is what the id is; it's in the item's URL already, and
  access is can_view_book's job, so printing it reveals nothing new.

Everything here is pure (a row in, strings out); the template lays it out.
"""
import re

from utils import media

# Google Books categories -> Dewey class (the hundreds, or the usual number
# a library shelves the subject under). Matched on the category's first
# words, ignoring case; 'Juvenile Fiction' before 'Fiction' and so on, so
# the longest prefix wins (see class_for).
CLASSES = {
    'fiction': 'FIC',
    'juvenile fiction': 'J FIC',
    'young adult fiction': 'YA FIC',
    'science fiction': 'FIC',
    'fantasy': 'FIC',
    'mystery': 'FIC',
    'romance': 'FIC',
    'thriller': 'FIC',
    'horror': 'FIC',
    'comics & graphic novels': '741.5',
    'juvenile nonfiction': 'J',
    'computers': '004',
    'reference': '030',
    'philosophy': '100',
    'body, mind & spirit': '133',
    'psychology': '150',
    'self-help': '158.1',
    'self help': '158.1',
    'religion': '200',
    'social science': '300',
    'family & relationships': '306.8',
    'political science': '320',
    'business & economics': '330',
    'law': '340',
    'true crime': '364.1',
    'education': '370',
    'transportation': '388',
    'language arts & disciplines': '400',
    'foreign language study': '400',
    'science': '500',
    'nature': '508',
    'mathematics': '510',
    'technology & engineering': '600',
    'medical': '610',
    'health & fitness': '613',
    'gardening': '635',
    'pets': '636',
    'cooking': '641.5',
    'house & home': '643',
    'art': '700',
    'architecture': '720',
    'crafts & hobbies': '745.5',
    'design': '745.4',
    'photography': '770',
    'music': '780',
    'performing arts': '790',
    'games & activities': '793',
    'games': '793',
    'sports & recreation': '796',
    'literary criticism': '809',
    'literary collections': '808.8',
    'poetry': '811',
    'drama': '812',
    'humor': '817',
    'history': '900',
    'travel': '910',
    'biography & autobiography': '920',
    'memoir': '920',
}

# What a movie or album files under, by format: the shelf mark a library's
# media shelves use. A cartridge (VHS) is CART, after the UI's name for it.
FORMAT_CLASSES = {
    'VHS': 'CART', 'DVD': 'DVD',
    'LP': 'LP', 'EP': 'EP', '7in': '7"', '10in': '10"', '12in': '12"',
    'CD': 'CD', 'Cassette': 'CASS',
}

# Physical description by format: (extent, other details). The playing
# time goes after the extent when there is one.
_RECORD_DETAILS = {
    'LP': 'analog, 33 1/3 rpm ; 12 in.',
    '12in': 'analog ; 12 in.',
    '10in': 'analog ; 10 in.',
    '7in': 'analog, 45 rpm ; 7 in.',
    'EP': 'analog',
    'CD': 'digital ; 4 3/4 in.',
    'Cassette': 'analog',
}

# Articles a title is filed without ("The Hobbit" files under H)
_ARTICLES = ('the ', 'a ', 'an ')


def _filing_title(title):
    """The title without a leading article, for the work mark and the
    title-entry Cutter."""
    t = (title or '').strip()
    low = t.lower()
    for article in _ARTICLES:
        if low.startswith(article) and len(t) > len(article):
            return t[len(article):].lstrip()
    return t


def _letters(text):
    """Only the letters of text (an apostrophe or a dot can't be in a mark)."""
    return re.sub(r'[^A-Za-z]', '', text or '')


def first_creator(book):
    """The first of a book's or movie's creators ("A, B", "A & B", "A; B";
    a comma before a single word is an inverted name, not a list). An
    album's artist stays whole: "Simon & Garfunkel" is one act."""
    author = (book['author'] or '').strip()
    if media.media_type_of(book) == media.RECORD:
        return author
    return re.split(r'\s*(?:;|&|,(?=\s*\S+\s+\S))\s*', author)[0].strip()


def inverted(name):
    """"J. R. R. Tolkien" -> "Tolkien, J. R. R.": a person's name as a
    catalog heading. One word stays as it is; so does a name already
    inverted. (Books only: an artist is as often a band, never inverted.)"""
    name = (name or '').strip()
    if not name or ',' in name or ' ' not in name:
        return name
    forenames, surname = name.rsplit(' ', 1)
    return f'{surname}, {forenames}'


def class_for(book):
    """The call number's class line: by format for a movie or album, by
    genre for a book (the longest matching category); '' when unknown."""
    kind = media.media_type_of(book)
    if kind != media.BOOK:
        return FORMAT_CLASSES.get(book['format'] or media.DEFAULT_FORMAT[kind], '')
    genre = (book['genre'] or '').strip().lower()
    best = ''
    for prefix, cls in CLASSES.items():
        if (genre == prefix or genre.startswith(prefix + ' ') or genre.startswith(prefix + ' /')) \
                and len(prefix) > len(best):
            best = prefix
    return CLASSES.get(best, '')


def call_number(book):
    """The call number's lines: class, Cutter mark, work mark, year (each
    only when known). The Cutter is the creator's surname (a book's) or
    name (an album's), or the title for a movie, which a library enters
    under its title."""
    kind = media.media_type_of(book)
    creator = first_creator(book)
    if kind == media.BOOK and creator:
        source = inverted(creator).split(',')[0]
    elif kind == media.RECORD and creator:
        source = _filing_title(creator)        # "The Beatles" files under B
    else:
        source = _filing_title(book['title'])
    lines = [class_for(book), _letters(source)[:3].upper()]
    # The work mark: the title's first letter, lower case (not for a movie,
    # whose Cutter is already the title)
    if kind != media.VIDEO:
        lines.append(_letters(_filing_title(book['title']))[:1].lower())
    if book['publish_year']:
        lines.append(str(book['publish_year']))
    return [line for line in lines if line]


def heading(book):
    """The main entry heading, typed on the card's top line: the author
    (inverted) for a book, the artist for an album. '' for a title entry (a
    movie, or anything without a creator): that card has no heading, its
    title paragraph starts on the top line instead, in hanging indent."""
    kind = media.media_type_of(book)
    creator = first_creator(book)
    if kind == media.VIDEO or not creator:
        return ''
    return inverted(creator) if kind == media.BOOK else creator


def title_paragraph(book):
    """Title / statement of responsibility. -- Publisher, year."""
    kind = media.media_type_of(book)
    title = (book['title'] or '').strip()
    by = (book['author'] or '').strip()
    if by and kind == media.VIDEO:
        # "directed by", or "created by" for a TV show (media.KIND_WORDS)
        by = f"{media.KIND_WORDS.get(media.kind_of(book), {}).get('by', 'directed by')} {by}"
    text = f'{title} / {by}.' if by else f'{title}.'
    imprint = ', '.join(str(x) for x in (book['publisher'], book['publish_year']) if x)
    if imprint:
        text += f' -- {imprint}.'
    return text


def physical_description(book):
    """The collation line, as a cataloguer writes it for the format."""
    kind = media.media_type_of(book)
    fmt = book['format']
    minutes = book['runtime_minutes']
    time = f' ({minutes} min.)' if minutes else ''
    if kind == media.VIDEO:
        carrier = 'videodisc' if fmt == 'DVD' else 'videocartridge'
        return f'1 {carrier}{time}'
    if kind == media.RECORD:
        fmt = fmt or media.DEFAULT_FORMAT[media.RECORD]
        extent = '1 sound cassette' if fmt == 'Cassette' else '1 sound disc'
        details = _RECORD_DETAILS.get(fmt)
        # The line ends in a full stop, once ("; 12 in." already has it)
        return f"{extent}{time} : {details.rstrip('.')}." if details else f'{extent}{time}'
    if fmt == media.AUDIOBOOK:
        return '1 audiobook'
    if fmt == media.EBOOK:
        return '1 online resource'      # AACR2's wording for an ebook
    return f"{book['page_count']} p." if book['page_count'] else ''


def standard_number(book):
    """The number line: ISBN for a book, the publisher's number for an
    album or a movie, the barcode (UPC) for a movie without one."""
    kind = media.media_type_of(book)
    if kind == media.BOOK:
        return f"ISBN {book['isbn']}" if book['isbn'] else ''
    if book['catalog_number']:
        return f"{book['publisher'] + ' ' if book['publisher'] else ''}{book['catalog_number']}"
    if kind == media.VIDEO and book['barcode']:
        return f"UPC {book['barcode']}"
    return ''


def tracings(book):
    """Subject and added entries: "1. Fiction.  I. Title." The genre is the
    item's own (tags are each user's, so never on the card). A book entered
    under its author gets a title entry; a movie, entered under its title,
    gets one for its director."""
    kind = media.media_type_of(book)
    parts = []
    genre = (book['genre'] or '').strip()
    if genre:
        parts.append(f'1. {genre.capitalize() if genre.isupper() else genre}.')
    creator = first_creator(book)
    if kind == media.VIDEO and creator:
        parts.append(f'I. {creator}.')
    elif kind != media.VIDEO and creator:
        parts.append('I. Title.')
    return '  '.join(parts)


def accession_number(book):
    """The id, zero-padded as a stamped accession number."""
    return f"{book['id']:06d}"


def entry(book):
    """Everything the card prints, for the template."""
    return {
        'call_number': call_number(book),
        'heading': heading(book),
        'title': title_paragraph(book),
        'physical': physical_description(book),
        'number': standard_number(book),
        'tracings': tracings(book),
        'accession': accession_number(book),
    }


_MONTHS = ('JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC')


def stamp_date(value):
    """A date as a library's date stamp prints it: "2026-11-13 04:15:19" ->
    "NOV 13 2026". '' for no date or one that isn't a date. (The |stamp_date
    filter: the Friends card's stamps and the book card's.)"""
    text = str(value or '')[:10]
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', text) or not 1 <= int(text[5:7]) <= 12:
        return ''
    return f'{_MONTHS[int(text[5:7]) - 1]} {text[8:10]} {text[:4]}'

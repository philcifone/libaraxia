"""Condition grades per media type (ROADMAP 16.0a, docs/PHOTOS-VALUE-SPEC.md
section 4, migration 037).

The standard terms for each type, best first. The database keeps the same
list in its `condition_grades` table (a test checks they agree); this module
is what the app reads, as utils/media.py is for types and statuses.

    records   the Goldmine scale, with Discogs' exact labels, so a grade asks
              Discogs for its price with no mapping (utils/valuation.py).
              Two fields: the record (vinyl, tape or disc) and its sleeve;
              the sleeve also takes Generic, No Cover and Not Graded.
    books     the booksellers' scale (ABAA / ILAB). One field.
    videos    used-media terms, as eBay and Amazon use them. One field.

Stored on the item as the code (`books.condition`, `books.sleeve_condition`),
shown as the label. Empty means not graded, stored as NULL.
"""
from utils.media import BOOK, VIDEO, RECORD

# (code, label), best first. The order is the rank.
GRADES = {
    RECORD: (
        ('M', 'Mint (M)'),
        ('NM', 'Near Mint (NM or M-)'),
        ('VG+', 'Very Good Plus (VG+)'),
        ('VG', 'Very Good (VG)'),
        ('G+', 'Good Plus (G+)'),
        ('G', 'Good (G)'),
        ('F', 'Fair (F)'),
        ('P', 'Poor (P)'),
    ),
    BOOK: (
        ('as_new', 'As New'),
        ('fine', 'Fine'),
        ('near_fine', 'Near Fine'),
        ('very_good', 'Very Good'),
        ('good', 'Good'),
        ('fair', 'Fair'),
        ('poor', 'Poor'),
    ),
    VIDEO: (
        ('new', 'New (sealed)'),
        ('like_new', 'Like New'),
        ('very_good', 'Very Good'),
        ('good', 'Good'),
        ('acceptable', 'Acceptable'),
    ),
}

# A record's sleeve takes the record grades plus these (Discogs' extras).
SLEEVE_EXTRAS = (
    ('Generic', 'Generic'),
    ('No Cover', 'No Cover'),
    ('Not Graded', 'Not Graded'),
)


def grades_for(media_type):
    """The (code, label) pairs for an item's own condition, best first."""
    return GRADES.get(media_type, ())


def sleeve_grades():
    """The (code, label) pairs for a record's sleeve."""
    return GRADES[RECORD] + SLEEVE_EXTRAS


def label(media_type, code, sleeve=False):
    """The label for a stored code, or '' when it's empty or unknown."""
    if not code:
        return ''
    pairs = sleeve_grades() if sleeve else grades_for(media_type)
    return dict(pairs).get(code, '')


def short(media_type, code):
    """What a tight line shows: a record's code as is ('NM', 'VG+'), which
    collectors read at a glance, or a book's or a video's label ('Near Fine')."""
    if not code:
        return ''
    return code if media_type == RECORD else label(media_type, code)


def clean(media_type, value, sleeve=False):
    """What to store for a form's choice: the code, or None for "Not graded".

    Raises ValueError for a code that isn't one of the item's type (a book
    can't be 'NM'; only a record has a sleeve)."""
    value = (value or '').strip()
    if not value:
        return None
    if sleeve and media_type != RECORD:
        raise ValueError('Only records have a sleeve grade.')
    pairs = sleeve_grades() if sleeve else grades_for(media_type)
    if value not in dict(pairs):
        raise ValueError('That condition is not one of the grades for this item.')
    return value

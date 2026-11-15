"""This copy's condition, price paid and value: the add and edit forms'
"This copy" fields (templates/_copy_fields.html; ROADMAP 16.0a,
docs/PHOTOS-VALUE-SPEC.md sections 4 to 6).

Shared by every add and edit route, so books, movies and music read and
save them the same way. Condition is public to anyone who sees the item;
price paid and value are the owner's (and admins') only.

Where a value came from (books.value_source):
  'manual'   typed in, or changed by hand after a fetch
  'discogs'  Discogs' price suggestion for the record's grade
  'ebay'     the median asking price of eBay listings
A fetch on the edit page (Fetch value) fills the field and its hidden
source fields; the value is stored only when the form is saved, so it can
be looked at first. Typing over it makes it manual.
"""
import re

from utils import condition, money
from utils.media import RECORD

FETCHED_SOURCES = ('discogs', 'ebay')
FIELDS = ('condition', 'sleeve_condition', 'price_paid_cents', 'value_cents', 'value_source',
          'value_note', 'value_checked_at', 'discogs_release_id')


def parse_discogs_release(text):
    """A Discogs release as typed: '1234567', 'r1234567' or a release URL
    (https://www.discogs.com/release/1234567-Artist-Title). Returns the id,
    None for blank; ValueError otherwise. A master release isn't a release
    (it has no prices), so its URL is refused with that reason."""
    text = (text or '').strip()
    if not text:
        return None
    if re.search(r'/master/', text):
        raise ValueError('That is a Discogs master; open the release you own and use its link.')
    found = re.fullmatch(r'\[?r?(\d{1,10})\]?', text) or re.search(r'/release/(\d{1,10})', text)
    if not found:
        raise ValueError('The Discogs release should be its number or its link.')
    return int(found.group(1))


def from_form(form, media_type, row=None):
    """(values, errors) for the "This copy" fields of a posted form.

    `row` is the item as stored (edit) or None (add); it decides whether an
    unchanged value keeps its source. `values` has every key in FIELDS plus
    the raw text ('price_paid', 'value', 'discogs_release'), so a refused
    form shows what was typed. value_checked_at is 'now' when the value is
    new or fetched (save() turns it into CURRENT_TIMESTAMP)."""
    errors = []
    values = {
        'price_paid': (form.get('price_paid') or '').strip(),
        'value': (form.get('value') or '').strip(),
        'discogs_release': (form.get('discogs_release') or '').strip(),
    }

    def grade(name, sleeve=False):
        try:
            return condition.clean(media_type, form.get(name), sleeve=sleeve)
        except ValueError as e:
            errors.append(str(e))
            return None

    values['condition'] = grade('condition')
    values['sleeve_condition'] = grade('sleeve_condition', sleeve=True) if media_type == RECORD else None

    def amount(name, label):
        try:
            return money.parse(values[name])
        except ValueError as e:
            errors.append(f'{label}: {e}')
            return None

    values['price_paid_cents'] = amount('price_paid', 'Price paid')
    cents = amount('value', 'Value')
    values['value_cents'] = cents

    fetched_source = form.get('value_source') if form.get('value_source') in FETCHED_SOURCES else None
    try:
        fetched_cents = int(form.get('value_fetched_cents') or '')
    except ValueError:
        fetched_cents = None

    if cents is None:
        values.update(value_source=None, value_note=None, value_checked_at=None)
    elif fetched_source and cents == fetched_cents:
        # A fetch on this form, saved as it came
        values.update(value_source=fetched_source,
                      value_note=(form.get('value_note') or '').strip()[:300] or None,
                      value_checked_at='now')
    elif row is not None and cents == row['value_cents']:
        # Unchanged: keep where it came from and when
        values.update(value_source=row['value_source'], value_note=row['value_note'],
                      value_checked_at=row['value_checked_at'])
    else:
        values.update(value_source='manual', value_note=None, value_checked_at='now')

    values['discogs_release_id'] = None
    if media_type == RECORD:
        try:
            values['discogs_release_id'] = parse_discogs_release(values['discogs_release'])
        except ValueError as e:
            errors.append(str(e))
    return values, errors


def save(conn, book_id, values):
    """Write the "This copy" fields onto an item (after its insert, or as
    part of an edit). The caller commits."""
    checked = values.get('value_checked_at')
    conn.execute(f'''
        UPDATE books SET condition = ?, sleeve_condition = ?, price_paid_cents = ?, value_cents = ?,
               value_source = ?, value_note = ?,
               value_checked_at = {"CURRENT_TIMESTAMP" if checked == "now" else "?"},
               discogs_release_id = ?
        WHERE id = ?
    ''', [values['condition'], values['sleeve_condition'], values['price_paid_cents'],
          values['value_cents'], values['value_source'], values['value_note'],
          *([] if checked == 'now' else [checked]), values['discogs_release_id'], book_id])


def form_defaults(row):
    """The fields' text for an edit page's first view, from the stored row."""
    return {
        'price_paid': money.plain(row['price_paid_cents']),
        'value': money.plain(row['value_cents']),
        'discogs_release': str(row['discogs_release_id'] or ''),
    }


def edit_context(row):
    """The edit page's extras for "This copy": where the stored value came
    from, and the Fetch value button's URL when a source could answer (a
    record with Discogs set up; a book or movie with a code and eBay)."""
    from flask import url_for
    from utils import valuation
    return {'value_line': source_line(row),
            'value_fetch': url_for('values.fetch', book_id=row['id']) if valuation.source_for(row) else None}


def source_line(row):
    """Where a stored value came from and when, for under the Value field
    and the item page: 'Discogs suggestion for NM, 2026-11-14',
    'Entered by you, 2026-11-14'. '' without a value."""
    if row['value_cents'] is None:
        return ''
    when = (row['value_checked_at'] or '')[:10]
    if row['value_source'] in FETCHED_SOURCES:
        text = row['value_note'] or row['value_source'].capitalize()
    else:
        text = 'Entered by you'
    return f'{text}, {when}' if when else text

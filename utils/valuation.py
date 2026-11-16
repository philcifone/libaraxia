"""Fetching an item's value (ROADMAP 16.0a, docs/PHOTOS-VALUE-SPEC.md section 6).

Two sources, both optional (without their keys the Fetch buttons don't show):

  records          Discogs' price suggestion for the record's grade
                   (GET /marketplace/price_suggestions/{release}). Uses the
                   DISCOGS_TOKEN that album search already has; Discogs only
                   answers for an account whose seller settings are filled in.
  books, movies    the median asking price of fixed-price eBay listings for
                   the ISBN or barcode (Browse API item_summary/search), with
                   an application token from EBAY_CLIENT_ID and
                   EBAY_CLIENT_SECRET. Asking prices, not sales: eBay's sold
                   prices (Marketplace Insights) are for approved partners
                   only. Labelled as a rough estimate wherever it shows.

`fetch(row)` returns a Result and never raises: an answer the person can
read either way. A value is only offered when it's worth storing (a Discogs
suggestion; an eBay median of at least MIN_LISTINGS listings), and only in
VALUE_CURRENCY: another currency is refused with a message, never converted.

Secrets: the eBay client secret goes only in the token request's
Authorization header, the token only in the search's; neither is ever in a
URL or a log line. Discogs' token is a header too (discogs_lookup).
Requests go to fixed hosts with redirects refused, so the SSRF guard of
book_utils._get_public isn't needed beyond that.
"""
import base64
import json
import os
import re
import statistics
import threading
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlencode

from flask import current_app

from utils import condition, discogs_lookup, money
from utils.book_utils import HTTP_TIMEOUT, _session, isbn_variants
from utils.media import BOOK, RECORD, VIDEO

EBAY_API = 'https://api.ebay.com'
EBAY_SCOPE = 'https://api.ebay.com/oauth/api_scope'
DISCOGS_API = discogs_lookup.API
MIN_LISTINGS = 3            # fewer eBay listings than this: reported, not stored
MAX_LISTINGS = 50
DEFAULT_RECORD_GRADE = 'VG+'  # the most common grade, for an ungraded record
MAX_BODY = 2 * 1024 * 1024


@dataclass
class Result:
    """What a fetch found. `cents` is None when there's nothing to store;
    `message` says why, or what was found, in words fit to show."""
    source: str                      # 'discogs' or 'ebay' (or '' if none applies)
    cents: Optional[int] = None
    note: str = ''                   # stored with the value: 'eBay: median asking price of 23 listings'
    message: str = ''
    release_id: Optional[int] = None  # Discogs: the release it matched, to keep on the item
    busy: bool = False               # rate limited or down: worth trying again later

    def as_dict(self):
        return {'source': self.source, 'cents': self.cents, 'value': money.plain(self.cents),
                'shown': money.show(self.cents), 'note': self.note, 'message': self.message,
                'release_id': self.release_id, 'busy': self.busy}


# ------------------------------------------------------------ setup

def ebay_enabled():
    return bool(os.environ.get('EBAY_CLIENT_ID', '').strip() and os.environ.get('EBAY_CLIENT_SECRET', '').strip())


def discogs_enabled():
    return discogs_lookup.enabled()


def marketplace():
    return (os.environ.get('EBAY_MARKETPLACE') or 'EBAY_US').strip().upper()


def source_for(row):
    """'discogs', 'ebay' or None: who could value this item, given the keys
    set and what the item has (a record; a book's ISBN; a movie's barcode)."""
    kind = row['media_type']
    if kind == RECORD:
        return 'discogs' if discogs_enabled() else None
    if kind in (BOOK, VIDEO) and ebay_enabled() and _gtin(row):
        return 'ebay'
    return None


# ------------------------------------------------------------ HTTP

def _request(method, url, headers, data=None):
    """(status, parsed JSON or None). Raises OSError-ish exceptions from
    requests on no answer; callers turn those into a busy Result. Tests
    replace this function with recorded answers."""
    response = _session.request(method, url, headers=headers, data=data,
                                timeout=HTTP_TIMEOUT, allow_redirects=False, stream=True)
    try:
        body = response.raw.read(MAX_BODY + 1, decode_content=True)
        try:
            parsed = json.loads(body) if body and len(body) <= MAX_BODY else None
        except ValueError:
            parsed = None
        return response.status_code, parsed
    finally:
        response.close()


# ------------------------------------------------------------ Discogs

def _discogs_get(path):
    discogs_lookup._throttle()      # shares album search's one-a-second pace
    headers = {'User-Agent': discogs_lookup.user_agent(), 'Accept': 'application/json',
               'Authorization': f'Discogs token={discogs_lookup.token()}'}
    return _request('GET', f'{DISCOGS_API}{path}', headers)


def _norm_catno(text):
    return re.sub(r'[\s\-.]', '', (text or '').lower())


def match_release(row):
    """A Discogs release id for a record without one: by barcode, then by
    catalogue number with artist and title. Only a single clear match is
    kept; otherwise None. Raises discogs_lookup.Busy."""
    if row['barcode']:
        found = discogs_lookup.barcode_search(row['barcode'])
        if len(found) == 1:
            return found[0]['id']
        if row['catalog_number']:
            same = [r for r in found if _norm_catno(r['catalog_number']) == _norm_catno(row['catalog_number'])]
            if len(same) == 1:
                return same[0]['id']
    if row['catalog_number']:
        query = ' '.join(x for x in (row['author'], row['title'], row['catalog_number']) if x)
        found = discogs_lookup.search(query, limit=12)
        same = [r for r in found if _norm_catno(r['catalog_number']) == _norm_catno(row['catalog_number'])]
        if len(same) == 1:
            return same[0]['id']
    return None


def discogs_value(row):
    """Discogs' suggested price for this record at its grade."""
    if not discogs_enabled():
        return Result('discogs', message='Discogs is not set up (DISCOGS_TOKEN).')
    try:
        release_id = row['discogs_release_id'] or match_release(row)
    except discogs_lookup.Busy:
        return Result('discogs', message='Discogs is busy; try again in a minute.', busy=True)
    if not release_id:
        return Result('discogs', message='Not matched on Discogs: add the release (its number or '
                                         'link) on the edit page.')

    code = row['condition'] or DEFAULT_RECORD_GRADE
    label = condition.label(RECORD, code)
    try:
        status, data = _discogs_get(f'/marketplace/price_suggestions/{int(release_id)}')
    except Exception as e:
        current_app.logger.warning('Discogs price suggestions failed: %s', e.__class__.__name__)
        return Result('discogs', message='Discogs did not answer; try again later.', busy=True,
                      release_id=release_id)
    if status == 429 or status >= 500:
        return Result('discogs', message='Discogs is busy; try again in a minute.', busy=True,
                      release_id=release_id)
    if status != 200:
        said = (data or {}).get('message') if isinstance(data, dict) else None
        if status in (401, 403) or (said and 'seller' in said.lower()):
            message = ('Discogs gives prices only to accounts with seller settings filled in '
                       '(discogs.com, Settings, Seller Settings).')
        elif status == 404:
            message = f'Discogs has no release {release_id}.'
        else:
            message = f'Discogs answered {status}' + (f': {said}' if said else '.')
        return Result('discogs', message=message, release_id=release_id)

    suggestion = (data or {}).get(label) if isinstance(data, dict) else None
    if not suggestion or suggestion.get('value') is None:
        return _discogs_stats(release_id, label)
    currency = (suggestion.get('currency') or '').upper()
    if currency != money.currency():
        return Result('discogs', release_id=release_id,
                      message=f'Discogs answered in {currency}; set your Discogs seller currency '
                              f'to {money.currency()} (this site doesn\'t convert).')
    cents = round(float(suggestion['value']) * 100)
    graded = f'for {code}' if row['condition'] else f'for {code} (not graded, so the usual grade)'
    note = f'Discogs suggestion {graded}'
    return Result('discogs', cents=cents, note=note, release_id=release_id,
                  message=f'{money.show(cents)}: {note}.')


def _discogs_stats(release_id, label):
    """No suggestion for the grade: the lowest price for sale, reported only."""
    try:
        status, data = _discogs_get(f'/marketplace/stats/{int(release_id)}')
    except Exception:
        status, data = 0, None
    lowest = (data or {}).get('lowest_price') if status == 200 and isinstance(data, dict) else None
    if lowest and lowest.get('value') is not None:
        count = data.get('num_for_sale') or 0
        shown = money.show(round(float(lowest['value']) * 100), (lowest.get('currency') or '').upper())
        return Result('discogs', release_id=release_id,
                      message=f'No Discogs suggestion for {label}. Lowest of {count} for sale: {shown} '
                              '(not stored).')
    return Result('discogs', release_id=release_id, message=f'No Discogs price for {label}.')


# ------------------------------------------------------------ eBay

_token_lock = threading.Lock()
_token = {'value': None, 'expires': 0.0}


def _ebay_token():
    """An application access token (client credentials), cached in memory
    until a minute before it expires (about two hours). None if refused."""
    with _token_lock:
        if _token['value'] and time.time() < _token['expires']:
            return _token['value']
        pair = f"{os.environ['EBAY_CLIENT_ID'].strip()}:{os.environ['EBAY_CLIENT_SECRET'].strip()}"
        headers = {'Content-Type': 'application/x-www-form-urlencoded',
                   'Authorization': 'Basic ' + base64.b64encode(pair.encode()).decode()}
        status, data = _request('POST', f'{EBAY_API}/identity/v1/oauth2/token', headers,
                                data=urlencode({'grant_type': 'client_credentials', 'scope': EBAY_SCOPE}))
        if status != 200 or not isinstance(data, dict) or not data.get('access_token'):
            # The answer's error code only; never the request (it holds the secret)
            current_app.logger.warning('eBay token refused: %s %s', status,
                                       (data or {}).get('error') if isinstance(data, dict) else '')
            return None
        _token['value'] = data['access_token']
        _token['expires'] = time.time() + int(data.get('expires_in') or 7200) - 60
        return _token['value']


def _gtin(row):
    """The code eBay searches by: a book's ISBN-13 (from a 10 or 13), a
    movie's barcode (a UPC as its 12 digits)."""
    if row['media_type'] == BOOK:
        variants = [v for v in isbn_variants(row['isbn'] or '') if len(v) == 13]
        return variants[0] if variants else None
    code = re.sub(r'\D', '', row['barcode'] or '')
    if len(code) == 13 and code.startswith('0'):
        return code[1:]
    return code or None


# eBay condition ids near each grade (Browse API conditionIds): 1000 New,
# 1500 New other, 2750 Like New, 3000 Used, 4000 Very Good, 5000 Good,
# 6000 Acceptable. No grade: any condition.
EBAY_CONDITIONS = {
    BOOK: {'as_new': '1000|1500|2750', 'fine': '2750|4000', 'near_fine': '2750|4000',
           'very_good': '3000|4000', 'good': '3000|4000|5000', 'fair': '5000|6000', 'poor': '6000'},
    VIDEO: {'new': '1000', 'like_new': '1500|2750|3000', 'very_good': '3000|4000',
            'good': '3000|4000|5000', 'acceptable': '5000|6000'},
}


def ebay_value(row):
    """The median asking price of fixed-price eBay listings for the item's
    ISBN or barcode, near its grade; item price only, not shipping."""
    if not ebay_enabled():
        return Result('ebay', message='eBay is not set up (EBAY_CLIENT_ID and EBAY_CLIENT_SECRET).')
    gtin = _gtin(row)
    if not gtin:
        return Result('ebay', message='Needs an ISBN or barcode to look it up on eBay.')
    try:
        token = _ebay_token()
        if not token:
            return Result('ebay', message='eBay refused the keys; check EBAY_CLIENT_ID and EBAY_CLIENT_SECRET.')
        filters = ['buyingOptions:{FIXED_PRICE}']
        ids = EBAY_CONDITIONS.get(row['media_type'], {}).get(row['condition'] or '')
        if ids:
            filters.append(f'conditionIds:{{{ids}}}')
        params = urlencode({'gtin': gtin, 'filter': ','.join(filters), 'limit': MAX_LISTINGS})
        status, data = _request('GET', f'{EBAY_API}/buy/browse/v1/item_summary/search?{params}',
                                {'Authorization': f'Bearer {token}',
                                 'X-EBAY-C-MARKETPLACE-ID': marketplace(),
                                 'Accept': 'application/json'})
    except Exception as e:
        current_app.logger.warning('eBay search failed: %s', e.__class__.__name__)
        return Result('ebay', message='eBay did not answer; try again later.', busy=True)
    if status == 401:
        _token['value'] = None          # expired early: the next fetch gets a new one
        return Result('ebay', message='eBay refused the token; try again.', busy=True)
    if status == 429 or status >= 500:
        return Result('ebay', message='eBay is busy; try again later.', busy=True)
    if status != 200 or not isinstance(data, dict):
        return Result('ebay', message=f'eBay answered {status}.')

    wanted = money.currency()
    prices, other = [], set()
    for item in data.get('itemSummaries') or []:
        price = item.get('price') or {}
        try:
            cents = round(float(price.get('value')) * 100)
        except (TypeError, ValueError):
            continue
        currency = (price.get('currency') or '').upper()
        if currency == wanted:
            prices.append(cents)
        else:
            other.add(currency)
    if not prices and other:
        return Result('ebay', message=f'eBay answered in {", ".join(sorted(other))}; set EBAY_MARKETPLACE '
                                      f'to one that sells in {wanted}.')
    graded = ' near its condition' if ids else ''
    if len(prices) < MIN_LISTINGS:
        found = len(prices)
        return Result('ebay', message=f'Only {found} fixed-price listing{"s" if found != 1 else ""} on eBay'
                                      f'{graded}; not enough for a value.')
    cents = int(statistics.median(prices))
    note = f'eBay: median asking price of {len(prices)} listings{graded}'
    return Result('ebay', cents=cents, note=note,
                  message=f'{money.show(cents)}: {note} (asking prices, a rough estimate).')


# ------------------------------------------------------------ both

def fetch(row):
    """The value of one item from the source that fits it. Never raises."""
    try:
        if row['media_type'] == RECORD:
            return discogs_value(row)
        if row['media_type'] in (BOOK, VIDEO):
            return ebay_value(row)
    except Exception:
        current_app.logger.exception('Value fetch failed for book %s', row['id'])
        return Result('', message="Couldn't fetch a value.")
    return Result('', message='Nothing values this kind of item.')


def test_sources():
    """For Settings, Maintenance, Test value sources: [(name, ok, message)]."""
    out = []
    if discogs_enabled():
        # A well-known release (Rick Astley, Never Gonna Give You Up, 7")
        result = discogs_value({'media_type': RECORD, 'discogs_release_id': 249504, 'condition': 'VG+',
                                'barcode': None, 'catalog_number': None, 'author': '', 'title': '', 'id': 0})
        out.append(('Discogs', result.cents is not None, result.message))
    else:
        out.append(('Discogs', False, 'Not set up: DISCOGS_TOKEN is empty.'))
    if ebay_enabled():
        result = ebay_value({'media_type': BOOK, 'isbn': '9780316066525', 'condition': None,
                             'barcode': None, 'id': 0})
        ok = result.cents is not None or result.message.startswith('Only')
        out.append(('eBay', ok, result.message))
    else:
        out.append(('eBay', False, 'Not set up: EBAY_CLIENT_ID and EBAY_CLIENT_SECRET are empty.'))
    return out

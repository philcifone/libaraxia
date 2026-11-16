"""Fetching values (utils/valuation.py, ROADMAP 16.0a section 6), on recorded
Discogs and eBay answers: the network is blocked in tests, so
valuation._request is replaced with one that answers from a table."""
import pytest

from utils import valuation


@pytest.fixture
def answers(monkeypatch, app):
    """Recorded answers by URL fragment: {fragment: (status, json)}. Every
    request made is kept in .calls, with its headers."""
    class Table(dict):
        calls = []
    table = Table()

    def fake(method, url, headers, data=None):
        table.calls.append((method, url, headers, data))
        for fragment, answer in table.items():
            if fragment in url:
                return answer
        return 404, None
    monkeypatch.setattr(valuation, '_request', fake)
    monkeypatch.setattr(valuation.discogs_lookup, '_throttle', lambda: None)
    monkeypatch.setenv('DISCOGS_TOKEN', 'disc-token')
    monkeypatch.setenv('EBAY_CLIENT_ID', 'client-id')
    monkeypatch.setenv('EBAY_CLIENT_SECRET', 'client-secret')
    monkeypatch.setenv('VALUE_CURRENCY', 'USD')
    valuation._token.update(value=None, expires=0)
    with app.app_context():
        yield table


SUGGESTIONS = {
    'Mint (M)': {'currency': 'USD', 'value': 40.0},
    'Near Mint (NM or M-)': {'currency': 'USD', 'value': 31.5},
    'Very Good Plus (VG+)': {'currency': 'USD', 'value': 22.25},
}


def record(**extra):
    return {'id': 1, 'media_type': 'record', 'discogs_release_id': 1531111, 'condition': None,
            'barcode': None, 'catalog_number': None, 'author': 'Joni Mitchell', 'title': 'Blue', **extra}


def book(**extra):
    return {'id': 2, 'media_type': 'book', 'isbn': '0316920045', 'barcode': None, 'condition': None, **extra}


def listings(*prices, currency='USD', shipping=99.0):
    return {'itemSummaries': [{'price': {'value': str(p), 'currency': currency},
                               'shippingOptions': [{'shippingCost': {'value': str(shipping)}}]}
                              for p in prices]}


# --- Discogs ----------------------------------------------------------------

def test_discogs_grade_picks_the_price(answers):
    answers['/marketplace/price_suggestions/1531111'] = (200, SUGGESTIONS)
    result = valuation.fetch(record(condition='NM'))
    assert result.cents == 3150 and result.note == 'Discogs suggestion for NM'
    # The token is a header, never in the URL
    method, url, headers, _ = answers.calls[-1]
    assert 'disc-token' not in url and headers['Authorization'] == 'Discogs token=disc-token'


def test_discogs_ungraded_uses_vg_plus_and_says_so(answers):
    answers['/marketplace/price_suggestions/1531111'] = (200, SUGGESTIONS)
    result = valuation.fetch(record())
    assert result.cents == 2225 and 'not graded' in result.note


def test_discogs_other_currency_is_refused(answers):
    answers['/marketplace/price_suggestions/1531111'] = (
        200, {'Very Good Plus (VG+)': {'currency': 'EUR', 'value': 20.0}})
    result = valuation.fetch(record())
    assert result.cents is None and 'EUR' in result.message and 'USD' in result.message


def test_discogs_without_seller_settings_says_what_to_do(answers):
    answers['/marketplace/price_suggestions/'] = (
        403, {'message': 'You must fill out your seller settings first.'})
    result = valuation.fetch(record())
    assert result.cents is None and 'Seller Settings' in result.message


def test_discogs_no_suggestion_reports_lowest_but_stores_nothing(answers):
    answers['/marketplace/price_suggestions/'] = (200, {})
    answers['/marketplace/stats/'] = (200, {'lowest_price': {'currency': 'USD', 'value': 9.99},
                                            'num_for_sale': 4})
    result = valuation.fetch(record(condition='G'))
    assert result.cents is None and '$9.99' in result.message and '4 for sale' in result.message


def test_discogs_busy(answers):
    answers['/marketplace/price_suggestions/'] = (429, None)
    result = valuation.fetch(record())
    assert result.busy and result.cents is None


def test_discogs_matches_a_release_by_single_barcode(answers, monkeypatch):
    monkeypatch.setattr(valuation.discogs_lookup, 'barcode_search',
                        lambda ean: [{'id': 777, 'catalog_number': 'MS 2038'}])
    answers['/marketplace/price_suggestions/777'] = (200, SUGGESTIONS)
    result = valuation.fetch(record(discogs_release_id=None, barcode='0075992203827'))
    assert result.release_id == 777 and result.cents == 2225


def test_discogs_ambiguous_barcode_is_not_matched(answers, monkeypatch):
    monkeypatch.setattr(valuation.discogs_lookup, 'barcode_search',
                        lambda ean: [{'id': 1, 'catalog_number': 'A'}, {'id': 2, 'catalog_number': 'B'}])
    monkeypatch.setattr(valuation.discogs_lookup, 'search', lambda *a, **k: [])
    result = valuation.fetch(record(discogs_release_id=None, barcode='0075992203827'))
    assert result.cents is None and 'Not matched on Discogs' in result.message


# --- eBay -------------------------------------------------------------------

def test_ebay_median_of_item_prices_not_shipping(answers):
    answers['/oauth2/token'] = (200, {'access_token': 'tok', 'expires_in': 7200})
    answers['/item_summary/search'] = (200, listings(10, 12, 30, 14, 11))
    result = valuation.fetch(book())
    assert result.cents == 1200
    assert result.note == 'eBay: median asking price of 5 listings'
    token_call, search_call = answers.calls[-2], answers.calls[-1]
    # ISBN-10 searched as its ISBN-13; the secret only in the token request's header
    assert 'gtin=9780316920049' in search_call[1]
    assert search_call[2]['Authorization'] == 'Bearer tok'
    assert all('client-secret' not in str(part) for call in answers.calls for part in (call[1], call[3]))
    assert token_call[2]['Authorization'].startswith('Basic ')


def test_ebay_token_is_cached(answers):
    answers['/oauth2/token'] = (200, {'access_token': 'tok', 'expires_in': 7200})
    answers['/item_summary/search'] = (200, listings(10, 12, 14))
    valuation.fetch(book())
    valuation.fetch(book())
    assert sum('/oauth2/token' in c[1] for c in answers.calls) == 1


def test_ebay_needs_three_listings(answers):
    answers['/oauth2/token'] = (200, {'access_token': 'tok', 'expires_in': 7200})
    answers['/item_summary/search'] = (200, listings(10, 12))
    result = valuation.fetch(book())
    assert result.cents is None and 'Only 2' in result.message


def test_ebay_condition_filter_follows_the_grade(answers):
    answers['/oauth2/token'] = (200, {'access_token': 'tok', 'expires_in': 7200})
    answers['/item_summary/search'] = (200, listings(10, 12, 14))
    result = valuation.fetch(book(condition='good'))
    assert 'conditionIds' in answers.calls[-1][1] and 'near its condition' in result.note


def test_ebay_other_currency_is_refused(answers):
    answers['/oauth2/token'] = (200, {'access_token': 'tok', 'expires_in': 7200})
    answers['/item_summary/search'] = (200, listings(10, 12, 14, currency='GBP'))
    result = valuation.fetch(book())
    assert result.cents is None and 'GBP' in result.message


def test_ebay_without_a_code_does_nothing(answers):
    result = valuation.fetch(book(isbn=None))
    assert result.cents is None and 'ISBN or barcode' in result.message
    assert answers.calls == []


def test_ebay_refused_keys(answers):
    answers['/oauth2/token'] = (401, {'error': 'invalid_client'})
    result = valuation.fetch(book())
    assert result.cents is None and 'refused the keys' in result.message


def test_source_for(answers, monkeypatch):
    assert valuation.source_for(record()) == 'discogs'
    assert valuation.source_for(book()) == 'ebay'
    assert valuation.source_for(book(isbn='')) is None
    monkeypatch.delenv('EBAY_CLIENT_ID')
    assert valuation.source_for(book()) is None


# --- routes -------------------------------------------------------------------

from conftest import add_book, add_user, login   # noqa: E402


def test_fetch_route_uses_the_form_grade_and_owner_only(client, db, people, answers):
    answers['/marketplace/price_suggestions/42'] = (200, SUGGESTIONS)
    rec = db.execute("INSERT INTO books (title, author, added_by, media_type, format, discogs_release_id) "
                     "VALUES ('Blue', 'Joni', ?, 'record', 'LP', 42)", (people['bob'],)).lastrowid
    db.commit()
    login(client, 'bob')
    r = client.post(f'/values/fetch/{rec}', data={'condition': 'M'})
    result = r.get_json()['result']
    assert result['cents'] == 4000 and result['value'] == '40.00' and result['source'] == 'discogs'
    # Nothing stored until the form is saved
    assert db.execute('SELECT value_cents FROM books WHERE id = ?', (rec,)).fetchone()[0] is None
    assert client.post(f'/values/fetch/{rec}', data={'condition': 'fine'}).status_code == 400
    client.get('/auth/logout')
    login(client, 'carol')      # can't see bob's record at all
    assert client.post(f'/values/fetch/{rec}').status_code == 404


def test_edit_page_shows_fetch_only_when_a_source_can_answer(client, db, people, monkeypatch):
    with_isbn = db.execute("INSERT INTO books (title, author, added_by, isbn) VALUES ('IJ', 'DFW', ?, '0316920045')",
                           (people['bob'],)).lastrowid
    without = add_book(db, people['bob'])
    db.commit()
    login(client, 'bob')
    monkeypatch.delenv('EBAY_CLIENT_ID', raising=False)
    assert 'data-click="fetchValue"' not in client.get(f'/books/edit/{with_isbn}').get_data(as_text=True)
    monkeypatch.setenv('EBAY_CLIENT_ID', 'x')
    monkeypatch.setenv('EBAY_CLIENT_SECRET', 'y')
    assert 'data-click="fetchValue"' in client.get(f'/books/edit/{with_isbn}').get_data(as_text=True)
    assert 'data-click="fetchValue"' not in client.get(f'/books/edit/{without}').get_data(as_text=True)


def test_test_sources_is_admin_only(client, db, people, monkeypatch):
    monkeypatch.delenv('DISCOGS_TOKEN', raising=False)
    monkeypatch.delenv('EBAY_CLIENT_ID', raising=False)
    login(client, 'bob')
    assert client.post('/values/test').status_code in (302, 403)
    assert 'Not set up' not in client.get('/user/settings').get_data(as_text=True)
    client.get('/auth/logout')
    login(client, 'alice')
    r = client.post('/values/test', follow_redirects=True)
    assert 'Discogs: not working. Not set up' in r.get_data(as_text=True)

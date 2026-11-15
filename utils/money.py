"""Money for price paid and value (ROADMAP 16.0a, docs/PHOTOS-VALUE-SPEC.md
section 5).

Stored as whole cents in an INTEGER, so no float ever rounds a price. One
currency for the site, VALUE_CURRENCY in .env (default USD): forms and pages
show it, and a fetched price in another currency is refused, not converted
(utils/valuation.py).
"""
import os
import re

SYMBOLS = {'USD': '$', 'CAD': 'CA$', 'AUD': 'A$', 'GBP': '£', 'EUR': '€', 'JPY': '¥'}
MAX_CENTS = 100_000_000 * 100       # a hundred million: anything above is a typo


def currency():
    """The site's currency code, upper case ('USD')."""
    return (os.environ.get('VALUE_CURRENCY') or 'USD').strip().upper() or 'USD'


def parse(text):
    """'12.50', '$12.50', '1,250', '12' -> cents (1250, 125000, 1200); blank
    -> None. Raises ValueError with a message for anything else."""
    text = (text or '').strip()
    if not text:
        return None
    cleaned = re.sub(r'[\s,]', '', text)
    # A leading symbol or code, as people type them: $12, CA$12, USD 12
    cleaned = re.sub(r'^(?:[A-Za-z]{0,2}[$£€¥]|[A-Za-z]{3})', '', cleaned)
    match = re.fullmatch(r'(\d+)(?:\.(\d{1,2}))?', cleaned)
    if not match:
        raise ValueError(f'"{text}" isn\'t an amount (write it like 12.50).')
    cents = int(match.group(1)) * 100 + int((match.group(2) or '0').ljust(2, '0'))
    if cents > MAX_CENTS:
        raise ValueError(f'"{text}" is more than this site stores.')
    return cents


def plain(cents):
    """Cents as a form's value: 1250 -> '12.50'; None -> ''."""
    if cents is None:
        return ''
    return f'{cents // 100}.{cents % 100:02d}'


def show(cents, code=None):
    """Cents for reading: 1250 -> '$12.50' (or '12.50 SEK' without a
    symbol), with thousands separated; None -> ''."""
    if cents is None:
        return ''
    code = code or currency()
    amount = f'{cents // 100:,}.{cents % 100:02d}'
    symbol = SYMBOLS.get(code)
    return f'{symbol}{amount}' if symbol else f'{amount} {code}'

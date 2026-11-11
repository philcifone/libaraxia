"""ROADMAP 14a step 4: the pure helpers of static/bulk.js, run under node.

The browser parts (select mode, the sheet) are tested by hand; this covers
the logic that is easy to get subtly wrong: ranges, the column count arrow
keys move by, group tick state, the genre snapping that stops near-duplicate
spellings, and carrying the user's choices over a stale plan.
"""
import json
import pathlib
import shutil
import subprocess

import pytest

from utils import search

BULK = pathlib.Path(__file__).resolve().parent.parent / 'static' / 'bulk.js'
NODE = shutil.which('node')

pytestmark = pytest.mark.skipif(NODE is None, reason='node is not installed')


def call(fn, *args):
    script = (f'const b = require({json.dumps(str(BULK))});\n'
              f'console.log(JSON.stringify(b.{fn}(...{json.dumps(list(args))})))')
    out = subprocess.run([NODE, '-e', script], capture_output=True, text=True, timeout=30, check=True)
    return json.loads(out.stdout) if out.stdout.strip() else None


def test_fold_agrees_with_the_servers():
    """The picker snaps by the same folding utils/search.py uses for filters."""
    for text in ['Les Misérables!', 'Catch-22', 'Sci-Fi / Fantasy', '  Cook  books ', 'Café', '', '123 abc']:
        assert call('fold', text) == (search.fold(text) or ''), text


def test_range_between_either_way_round():
    assert call('rangeBetween', 2, 5) == [2, 3, 4, 5]
    assert call('rangeBetween', 5, 2) == [2, 3, 4, 5]
    assert call('rangeBetween', 3, 3) == [3]


def test_column_count_from_the_cards_tops():
    assert call('columnCount', [0, 0, 0, 0, 300, 300]) == 4
    assert call('columnCount', [10, 11, 300]) == 2          # sub-pixel jitter
    assert call('columnCount', [0, 300, 600]) == 1          # list view
    assert call('columnCount', [0, 0]) == 2                 # one short row
    assert call('columnCount', []) == 1


@pytest.mark.parametrize('index, key, cols, count, expected', [
    (5, 'ArrowRight', 4, 10, 6), (5, 'ArrowLeft', 4, 10, 4),
    (5, 'ArrowDown', 4, 10, 9), (5, 'ArrowUp', 4, 10, 1),
    (0, 'ArrowLeft', 4, 10, None), (9, 'ArrowRight', 4, 10, None),   # edges: stay
    (8, 'ArrowDown', 4, 10, None), (2, 'ArrowUp', 4, 10, None),
    (5, 'Home', 4, 10, 0), (5, 'End', 4, 10, 9),
    (5, 'x', 4, 10, None),
])
def test_next_index(index, key, cols, count, expected):
    assert call('nextIndex', index, key, cols, count) == expected


def test_group_tick_state():
    def state(ids, excluded):
        script = (f'const b = require({json.dumps(str(BULK))});'
                  f'console.log(JSON.stringify(b.groupTickState({json.dumps(ids)}, new Set({json.dumps(excluded)}))))')
        return json.loads(subprocess.run([NODE, '-e', script], capture_output=True, text=True, check=True).stdout)
    assert state([1, 2, 3], []) == 'all'
    assert state([1, 2, 3], [1]) == 'some'
    assert state([1, 2, 3], [1, 2, 3, 9]) == 'none'


def test_wording():
    assert call('summaryLine', 44, 1, 2) == '44 will change · 1 already set · 2 skipped'
    assert call('summaryLine', 3, 0, 0) == '3 will change'
    assert call('applyLabel', 1) == 'Apply to 1 item'
    assert call('applyLabel', 42) == 'Apply to 42 items'
    assert call('selectedLabel', 12) == '12 selected'


def test_apply_count_follows_every_tick():
    plan = {'groups': [{'items': [{'id': 1}, {'id': 2}]}, {'items': [{'id': 3}]}]}
    script = (f'const b = require({json.dumps(str(BULK))});'
              f'const plan = {json.dumps(plan)};'
              'console.log(JSON.stringify([b.applyCount(plan, new Set()), b.applyCount(plan, new Set([2, 3])),'
              ' b.applyCount(plan, new Set([1, 2, 3]))]))')
    out = subprocess.run([NODE, '-e', script], capture_output=True, text=True, check=True)
    assert json.loads(out.stdout) == [3, 1, 0]


GENRES = [{'value': 'Cookbooks', 'count': 12}, {'value': 'Fiction', 'count': 88}, {'value': 'Sci-Fi', 'count': 4}]


def test_typing_an_existing_genre_snaps_to_its_spelling():
    got = call('matchGenre', 'cookbooks', GENRES)
    assert got == {'value': 'Cookbooks', 'hint': 'Using existing spelling “Cookbooks”', 'valid': True}
    assert call('matchGenre', 'COOK-BOOKS', GENRES)['value'] == 'Cookbooks'
    assert call('matchGenre', 'sci fi', GENRES)['value'] == 'Sci-Fi'
    assert call('matchGenre', '  Fiction ', GENRES) == {'value': 'Fiction', 'hint': 'Existing genre', 'valid': True}


def test_a_new_or_cleared_or_empty_genre():
    assert call('matchGenre', 'Poetry', GENRES) == {'value': 'Poetry', 'hint': 'New genre', 'valid': True}
    assert call('matchGenre', 'Poetry  and   verse', GENRES)['value'] == 'Poetry and verse'    # whitespace collapsed
    assert call('matchGenre', '', GENRES)['valid'] is False
    assert call('matchGenre', '   ', GENRES)['valid'] is False
    assert call('matchGenre', 'x' * 81, GENRES)['valid'] is False
    cleared = call('matchGenre', '(no genre)', GENRES, True)
    assert cleared['valid'] is True and cleared['value'] is None


def test_filter_genres_by_folded_text():
    assert [g['value'] for g in call('filterGenres', GENRES, 'cook')] == ['Cookbooks']
    assert [g['value'] for g in call('filterGenres', GENRES, 'sci')] == ['Sci-Fi']
    assert len(call('filterGenres', GENRES, '')) == 3
    assert call('filterGenres', GENRES, 'zzz') == []


def test_choices_carry_over_a_stale_plan():
    old = {'groups': [{'before': 'Cooking', 'items': [{'id': 1}, {'id': 2}]},
                      {'before': 'Cookery', 'items': [{'id': 3}, {'id': 4}]}]}
    new = {'groups': [{'before': 'Cooking', 'items': [{'id': 1}, {'id': 2}, {'id': 9}]},   # 9 is new
                      {'before': 'Cookery', 'items': [{'id': 4}]}]}                      # 3 moved on
    script = (f'const b = require({json.dumps(str(BULK))});'
              f'const out = b.carryExclusions({json.dumps(old)}, new Set([1, 2, 4]), {json.dumps(new)});'
              'console.log(JSON.stringify([...out].sort()))')
    out = subprocess.run([NODE, '-e', script], capture_output=True, text=True, check=True)
    # The whole Cooking group was unticked, so its new item stays out too;
    # item 4 was unticked by itself and still is
    assert json.loads(out.stdout) == [1, 2, 4, 9]


def test_id_from_a_card_link():
    assert call('idFromHref', '/books/book/12') == 12
    assert call('idFromHref', '/videos/7?x=1') == 7
    assert call('idFromHref', '/records/300') == 300
    assert call('idFromHref', '/nothing') is None
    assert call('idFromHref', None) is None

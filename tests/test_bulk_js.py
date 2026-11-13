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
    old = {'groups': [{'key': 'Cooking', 'items': [{'id': 1}, {'id': 2}]},
                      {'key': 'Cookery', 'items': [{'id': 3}, {'id': 4}]}]}
    new = {'groups': [{'key': 'Cooking', 'items': [{'id': 1}, {'id': 2}, {'id': 9}]},   # 9 is new
                      {'key': 'Cookery', 'items': [{'id': 4}]}]}                      # 3 moved on
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


def test_the_button_names_the_verb_and_the_count():
    assert call('applyLabel', 44, 'status') == 'Apply to 44 items'
    assert call('applyLabel', 1, 'genre') == 'Apply to 1 item'
    assert call('applyLabel', 44, 'remove') == 'Remove 44 from library'
    assert call('applyLabel', 30, 'shelf_add', 'Jazz') == 'Add 30 to Jazz'
    assert call('applyLabel', 3, 'shelf_remove', 'Jazz') == 'Remove 3 from Jazz'
    assert call('applyLabel', 2, 'restore') == 'Put 2 items back'


def test_what_each_panel_sends():
    assert call('buildParams', 'status', {'value': 'read'}) == {
        'action': 'status', 'params': {'status': 'read'}, 'valid': True}
    assert call('buildParams', 'status', {'value': ''})['valid'] is False
    assert call('buildParams', 'format', {'value': 'DVD'})['params'] == {'format': 'DVD'}
    assert call('buildParams', 'owned', {'value': '0'})['params'] == {'owned': '0'}
    assert call('buildParams', 'owned', {})['valid'] is False
    assert call('buildParams', 'kind', {'value': 'tv'}) == {'action': 'kind', 'params': {'kind': 'tv'}, 'valid': True}
    assert call('buildParams', 'kind', {'value': 'anime'})['valid'] is False
    assert call('buildParams', 'remove', {'text': '  sold  '})['params'] == {'note': 'sold'}
    assert call('buildParams', 'remove', {'text': '  '}) == {'action': 'remove', 'params': {'note': None},
                                                              'valid': True}     # the note is optional
    assert call('buildParams', 'restore', {}) == {'action': 'restore', 'params': {}, 'valid': True}
    assert call('buildParams', 'genre', {'text': 'cookbooks', 'genres': GENRES}) == {
        'action': 'genre', 'params': {'genre': 'Cookbooks'}, 'valid': True}
    assert call('buildParams', 'nothing', {})['valid'] is False


def test_shelf_panel_adds_removes_and_creates():
    add = call('buildParams', 'shelf', {'mode': 'add', 'shelf': '7', 'mediaType': 'book'})
    assert add == {'action': 'shelf_add', 'params': {'media_type': 'book', 'shelf_id': 7}, 'valid': True}
    remove = call('buildParams', 'shelf', {'mode': 'remove', 'shelf': '7', 'mediaType': 'video'})
    assert remove['action'] == 'shelf_remove' and remove['params'] == {'media_type': 'video', 'shelf_id': 7}
    new = call('buildParams', 'shelf', {'mode': 'add', 'shelf': '__new__', 'newName': ' Road trip ', 'mediaType': 'book'})
    assert new == {'action': 'shelf_add', 'params': {'media_type': 'book', 'new_shelf': 'Road trip'}, 'valid': True}
    assert call('buildParams', 'shelf', {'mode': 'add', 'shelf': '__new__', 'newName': ' ', 'mediaType': 'book'})['valid'] is False
    assert call('buildParams', 'shelf', {'mode': 'add', 'shelf': '', 'mediaType': 'book'})['valid'] is False
    # You can't create a shelf by removing from it
    assert call('buildParams', 'shelf', {'mode': 'remove', 'shelf': '__new__', 'newName': 'x', 'mediaType': 'book'})['valid'] is False


def test_tag_panel_and_its_hint():
    got = call('buildParams', 'tag', {'mode': 'add', 'text': '  Gifted '})
    assert got == {'action': 'tag_add', 'params': {'tag': 'gifted'}, 'valid': True}
    assert call('buildParams', 'tag', {'mode': 'remove', 'text': 'x'})['action'] == 'tag_remove'
    assert call('buildParams', 'tag', {'mode': 'add', 'text': ' '})['valid'] is False
    assert call('buildParams', 'tag', {'mode': 'add', 'text': 'x' * 51})['valid'] is False
    assert call('tagHint', 'Gifted') == 'Saved as \u201cgifted\u201d'
    assert call('tagHint', 'gifted') == ''
    assert call('tagHint', '') == ''
    assert call('tagHint', 'x' * 51) == 'Keep it to 50 characters or fewer.'


def test_now_text_shows_the_value_the_action_changes():
    item = {'yours': True, 'genre': None, 'status': 'Read', 'format': 'Audiobook', 'owned': False,
            'removed': True, 'shelves': ['Jazz', 'Keep'], 'tags': []}
    assert call('nowText', 'genre', item) == '(no genre)'
    assert call('nowText', 'status', item) == 'Read'
    assert call('nowText', 'format', item) == 'Audiobook'
    assert call('nowText', 'owned', item) == 'Unshelved'
    assert call('nowText', 'restore', item) == 'Removed'
    assert call('nowText', 'shelf', item) == 'In Jazz, Keep'
    assert call('nowText', 'tag', item) == 'No tags'
    # Item edits on someone else's item say so up front; marks don't
    theirs = {**item, 'yours': False}
    assert call('nowText', 'genre', theirs) == 'Not yours, will be skipped'
    assert call('nowText', 'status', theirs) == 'Read'


def test_view_label_and_the_cap():
    # A grid is a shelf; a searched grid has results (16.0: every grid searches itself)
    assert call('viewLabel', 57, False) == 'All 57 on this shelf'
    assert call('viewLabel', 500, False) == 'All 500 on this shelf'
    assert call('viewLabel', 612, False) == 'Too many for one edit (612). Narrow the view.'
    assert call('viewLabel', 57, True) == 'All 57 results'
    assert call('viewLabel', 612, True) == 'Too many for one edit (612). Narrow the search.'
    assert call('viewButtonLabel', False) == 'Select all on this shelf'
    assert call('viewButtonLabel', True) == 'Select all results'

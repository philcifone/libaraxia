"""ROADMAP 14b step 5: the pure helpers of static/goodreads_review.js, run
under node (it borrows fold and rangeBetween from bulk.js). The page itself
is checked by hand (spec section 5)."""
import json
import pathlib
import shutil
import subprocess

import pytest

SCRIPT = pathlib.Path(__file__).resolve().parent.parent / 'static' / 'goodreads_review.js'
NODE = shutil.which('node')

pytestmark = pytest.mark.skipif(NODE is None, reason='node is not installed')


def call(fn, *args):
    script = (f'const g = require({json.dumps(str(SCRIPT))});\n'
              f'console.log(JSON.stringify(g.{fn}(...{json.dumps(list(args))})))')
    out = subprocess.run([NODE, '-e', script], capture_output=True, text=True, timeout=30, check=True)
    return json.loads(out.stdout) if out.stdout.strip() else None


def test_allowed_choices_are_those_every_selected_row_has():
    read_new = ['not_owned', 'library', 'skip']
    fill = ['fill', 'skip']
    assert call('grAllowedChoices', [read_new]) == read_new
    assert call('grAllowedChoices', [read_new, fill]) == ['skip']
    assert call('grAllowedChoices', [read_new, []]) == []
    assert call('grAllowedChoices', []) == []
    assert call('grAllowedChoices', [['ask', 'finished', 'skip']]) == ['finished', 'skip']


def test_import_label_names_undecided_rows():
    assert call('grImportLabel', 214, 12) == 'Import 214, leave 12 undecided'
    assert call('grImportLabel', 3, 0) == 'Import 3'


def test_row_filter_by_box_shelf_and_folded_words():
    row = {'box': 'read_new', 'shelves': ['read', 'kindle'], 'search': 'Les Misérables Victor Hugo'}
    assert call('grRowMatches', row, {'box': '', 'shelf': '', 'q': ''})
    assert call('grRowMatches', row, {'box': 'read_new', 'shelf': 'kindle', 'q': 'miserables hugo'})
    assert not call('grRowMatches', row, {'box': 'fill', 'shelf': '', 'q': ''})
    assert not call('grRowMatches', row, {'box': '', 'shelf': 'to-read', 'q': ''})
    assert not call('grRowMatches', row, {'box': '', 'shelf': '', 'q': 'dumas'})

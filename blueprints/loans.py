"""Lending (ROADMAP 16.0d, docs/LENDING-SPEC.md): Lend, Mark returned and
Delete, from the item page's Loans section. The rules live in
utils/loans.py; these routes only read the form, commit and come back to
the item page's #loans with a flash.

Someone who can't see the item gets a 404, as on the item page. A refused
action (not theirs, not on the shelf, already lent, a bad date) is a flash
with LoanError's message.
"""
from flask import Blueprint, abort, current_app, flash, redirect, request, url_for
from flask_login import current_user, login_required

from models import can_view_book
from utils import loans, media
from utils.database import get_db
from utils.loans import LoanError
from utils.rate_limiting import limiter

loans_blueprint = Blueprint('loans', __name__)


def _back(book):
    """The item's page, at its Loans section."""
    endpoint = media.item_endpoint(media.media_type_of(book))
    return redirect(url_for(endpoint, id=book['id'], _anchor='loans'))


def _book(conn, book_id):
    book = conn.execute('SELECT * FROM books WHERE id = ?', (book_id,)).fetchone()
    if not book or not can_view_book(conn, current_user, book_id):
        abort(404)
    return book


def _run(conn, book, action, done):
    """Run a write; commit and flash `done`, or roll back and flash why not."""
    try:
        action()
        conn.commit()
        flash(done, 'success')
    except LoanError as e:
        conn.rollback()
        flash(str(e), 'error')
    except Exception:
        conn.rollback()
        current_app.logger.exception('Loan action failed on book %s', book['id'])
        flash('Something went wrong; nothing was changed.', 'error')
    return _back(book)


@loans_blueprint.route('/<int:book_id>/lend', methods=['POST'])
@login_required
@limiter.limit('60 per hour')
def lend(book_id):
    conn = get_db()
    book = _book(conn, book_id)
    form = request.form
    # The borrower select sends a user id, or 'other' with the name field
    borrower = form.get('borrower', '')
    borrower_id = None if borrower in ('', 'other') else borrower
    return _run(conn, book, lambda: loans.lend(
        conn, current_user, book,
        borrower_id=borrower_id,
        borrower_name=form.get('borrower_name', '') if borrower_id is None else '',
        lent_at=form.get('lent_at'), due_at=form.get('due_at'), note=form.get('note', '')),
        'Lent.')


def _loan_book(conn, loan_id):
    """The item of a loan, with the item page's 404 rule; a loan id that
    doesn't exist is a 404 too."""
    row = conn.execute('SELECT book_id FROM loans WHERE id = ?', (loan_id,)).fetchone()
    if not row:
        abort(404)
    return _book(conn, row['book_id'])


@loans_blueprint.route('/<int:loan_id>/return', methods=['POST'])
@login_required
@limiter.limit('60 per hour')
def mark_returned(loan_id):
    conn = get_db()
    book = _loan_book(conn, loan_id)
    return _run(conn, book, lambda: loans.mark_returned(
        conn, current_user, loan_id, request.form.get('returned_at')), 'Marked returned.')


@loans_blueprint.route('/<int:loan_id>/delete', methods=['POST'])
@login_required
@limiter.limit('60 per hour')
def delete(loan_id):
    conn = get_db()
    book = _loan_book(conn, loan_id)
    return _run(conn, book, lambda: loans.delete(conn, current_user, loan_id), 'Loan deleted.')

from flask import Flask, render_template, redirect, url_for, request, flash, Blueprint, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
import sqlite3
import os
import time
import requests
from PIL import Image, ImageOps
from functools import wraps
from typing import Optional, Dict, Any
from utils.database import get_db_connection
from models import admin_required
from utils.book_utils import (
    fetch_book_details_from_isbn,
    process_image,
    download_and_save_cover,
    ALLOWED_EXTENSIONS,
    MAX_IMAGE_SIZE
)

books_blueprint = Blueprint('books', __name__, template_folder='templates')

# Constants
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
MAX_IMAGE_SIZE = (500, 1000)


@books_blueprint.route("/add", methods=["GET", "POST"])
@login_required
@admin_required
def add_book():
    book_details = None
    
    if request.method == "POST":
        if "isbn_lookup" in request.form:
            isbn = request.form["isbn"]
            book_details = fetch_book_details_from_isbn(isbn)
            if book_details:
                flash(f"Book details fetched from {book_details['source']}", "success")
            else:
                book_details = {"error": "Book not found in any available sources. Please enter details manually."}
                flash("Book not found. Please enter details manually.", "error")

        if "submit_book" in request.form:
            # Process uploaded image or use downloaded cover
            cover_image_url = process_image(
                request.files.get("image"),
                request.form.get("existing_cover_url")
            )
            
            with get_db_connection() as conn:
                conn.execute("""
                    INSERT INTO books (title, author, publisher, publish_year, isbn, 
                                     page_count, cover_image_url, description, subtitle, genre)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    request.form["title"],
                    request.form["author"],
                    request.form["publisher"],
                    request.form["year"],
                    request.form["isbn"],
                    request.form["page_count"],
                    cover_image_url,
                    request.form.get("description"),
                    request.form["subtitle"],
                    request.form["genre"]
                ))
            
            return redirect(url_for("base.index"))

    return render_template("add_book.html", book_details=book_details)

@books_blueprint.route("/edit/<int:id>", methods=["GET", "POST"])
@login_required
@admin_required
def edit_book(id):
    with get_db_connection() as conn:
        book_details = None
        
        if request.method == "POST":
            if "isbn_lookup" in request.form:
                isbn = request.form["isbn"]
                book_details = fetch_book_details_from_isbn(isbn)
                if not book_details:
                    flash("Book not found. Please enter details manually.", "error")
            else:
                cover_image_url = process_image(
                    request.files.get("image"),
                    conn.execute("SELECT cover_image_url FROM books WHERE id = ?", (id,)).fetchone()[0]
                )
                
                conn.execute("""
                    UPDATE books
                    SET title = ?, author = ?, publisher = ?, publish_year = ?, 
                        page_count = ?, cover_image_url = ?, description = ?, subtitle = ?, genre = ?
                    WHERE id = ?
                """, (
                    request.form["title"],
                    request.form["author"],
                    request.form.get("publisher"),
                    request.form.get("year"),
                    request.form.get("page_count", 0),
                    cover_image_url,
                    request.form.get("description", ""),
                    request.form["subtitle"],
                    request.form["genre"],
                    id
                ))
                
                return redirect(url_for("base.index"))
        
        book = conn.execute("SELECT * FROM books WHERE id = ?", (id,)).fetchone()
        
    return render_template("edit_book.html", book=book, book_details=book_details)

@books_blueprint.route("/book/<int:id>")
@login_required
def show_book(id):
    with get_db_connection() as conn:
        book = conn.execute("SELECT * FROM books WHERE id = ?", (id,)).fetchone()
        
        read_data = conn.execute("""
            SELECT date_read, rating, comment 
            FROM read_data 
            WHERE user_id = ? AND book_id = ?
        """, (current_user.id, id)).fetchone()
        
        collection_status = conn.execute("""
            SELECT status 
            FROM collections 
            WHERE user_id = ? AND book_id = ?
        """, (current_user.id, id)).fetchone()
        
    collection_status = collection_status['status'] if collection_status else 'untracked'
    
    return render_template(
        "book_detail.html", 
        book=book, 
        read_data=read_data, 
        collection_status=collection_status
    )

@books_blueprint.route("/delete/<int:id>")
@login_required
@admin_required
def delete_book(id):
    with get_db_connection() as conn:
        conn.execute("DELETE FROM books WHERE id = ?", (id,))
    return redirect(url_for('base.index'))

@books_blueprint.route("/search", methods=["GET"])
@login_required
def search():
    search_term = request.args.get("search_term", "").lower()
    sort_by = request.args.get("sort_by", "title")
    sort_order = request.args.get("sort_order", "asc")
    
    # Allowed sorting columns
    allowed_sort_columns = {"title", "author", "publish_year", "date_added", "genre"}
    if sort_by not in allowed_sort_columns:
        sort_by = "title"
    
    # Sorting direction
    sort_direction = "ASC" if sort_order == "asc" else "DESC"
    
    # Build the query
    query = f"""
        SELECT books.*, 
               GROUP_CONCAT(DISTINCT book_tags.tag_name) AS tags
        FROM books
        LEFT JOIN book_tags ON books.id = book_tags.book_id
        WHERE 
            lower(books.title) LIKE ? OR 
            lower(books.author) LIKE ? OR 
            books.publish_year LIKE ? OR
            lower(books.genre) LIKE ? OR
            lower(books.description) LIKE ? OR
            lower(books.subtitle) LIKE ? OR
            lower(books.publisher) LIKE ? OR
            lower(book_tags.tag_name) LIKE ?
        GROUP BY books.id
        ORDER BY {sort_by} {sort_direction}
    """
    params = [f"%{search_term}%"] * 8  # Reuse the search term for all fields

    # Execute the query
    with get_db_connection() as conn:
        books = conn.execute(query, params).fetchall()
    
    return render_template(
        "search.html",
        books=books,
        search_term=search_term,
        sort_by=sort_by,
        sort_order=sort_order
    )


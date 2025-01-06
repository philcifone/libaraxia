from flask import Flask, render_template, redirect, url_for, request, flash, Blueprint, current_app, jsonify
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
from utils.book_utils import (
    get_filter_options,
    fetch_book_details_from_isbn,
    process_image,
    fetch_google_books
)
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
    search_results = None
    
    if request.method == "POST":
        if "isbn_lookup" in request.form:
            # ISBN search
            isbn = request.form["isbn"]
            book_details = fetch_book_details_from_isbn(isbn)
            if book_details:
                flash(f"Book details fetched from {book_details['source']}", "success")
            else:
                book_details = {"error": "Book not found. Please enter details manually."}
                flash("Book not found. Please enter details manually.", "error")
                
        elif "title_search" in request.form:
            # Title/Author search
            query = request.form["search_query"]
            try:
                # Use Google Books API for searching
                api_url = f"https://www.googleapis.com/books/v1/volumes?q={query}"
                response = requests.get(api_url).json()
                
                if "items" in response:
                    search_results = []
                    for item in response["items"][:10]:  # Limit to first 10 results
                        volume_info = item["volumeInfo"]
                        result = {
                            "title": volume_info.get("title", ""),
                            "subtitle": volume_info.get("subtitle", ""),
                            "authors": ", ".join(volume_info.get("authors", [])),
                            "publisher": volume_info.get("publisher", ""),
                            "publishedDate": volume_info.get("publishedDate", "").split("-")[0],
                            "isbn": next((id["identifier"] for id in volume_info.get("industryIdentifiers", []) 
                                       if id["type"] in ["ISBN_13", "ISBN_10"]), ""),
                            "thumbnail": volume_info.get("imageLinks", {}).get("thumbnail", ""),
                            "description": volume_info.get("description", ""),
                            "pageCount": volume_info.get("pageCount", 0),
                            "categories": ", ".join(volume_info.get("categories", []))
                        }
                        search_results.append(result)
                else:
                    flash("No results found", "error")
            except Exception as e:
                flash(f"Error during search: {str(e)}", "error")
                
        elif "barcode_scan" in request.form:
            # Handle barcode scan result
            isbn = request.form["barcode_result"]
            if isbn:
                book_details = fetch_book_details_from_isbn(isbn)
                if book_details:
                    flash(f"Book details fetched from {book_details['source']}", "success")
                else:
                    book_details = {"error": "Book not found. Please enter details manually."}
                    flash("Book not found. Please enter details manually.", "error")
                    
        elif "submit_book" in request.form:
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
                
            flash("Book added successfully!", "success")
            return redirect(url_for("base.index"))

    return render_template(
        "add_book.html",
        book_details=book_details,
        search_results=search_results
    )

@books_blueprint.route("/select_search_result", methods=["POST"])
@login_required
@admin_required
def select_search_result():
    """Handle selection of a book from search results"""
    try:
        data = request.get_json()
        isbn = data.get("isbn")
        thumbnail_url = data.get("thumbnail")
        original_data = data.get("bookData", {})  # Get the full book data
        
        if not isbn:
            return jsonify({"success": False, "error": "No ISBN provided"})
        
        # Download and save cover image if available
        local_cover_url = None
        if thumbnail_url:
            local_cover_url = download_and_save_cover(thumbnail_url)
        
        # Create book details dictionary using the original data
        book_details = {
            "title": original_data.get("title", ""),
            "subtitle": original_data.get("subtitle", ""),
            "author": original_data.get("authors", ""),
            "publisher": original_data.get("publisher", ""),
            "year": original_data.get("publishedDate", ""),
            "isbn": isbn,
            "pageCount": original_data.get("pageCount", 0),
            "description": original_data.get("description", ""),
            "genre": original_data.get("categories", ""),
            "thumbnail_url": thumbnail_url
        }
        
        if local_cover_url:
            book_details["local_cover_url"] = local_cover_url
            
        return jsonify({"success": True, "book_details": book_details})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})
        
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
    conn = get_db_connection()
    try:
        # Get book details
        book = conn.execute("SELECT * FROM books WHERE id = ?", (id,)).fetchone()
        
        # Get reading status
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
        
        # Get custom collections with book membership status
        custom_collections = conn.execute("""
            SELECT 
                uc.collection_id,
                uc.name,
                COUNT(cb2.book_id) as book_count,
                CASE WHEN cb.book_id IS NOT NULL THEN 1 ELSE 0 END as has_book
            FROM user_collections uc
            LEFT JOIN collection_books cb ON uc.collection_id = cb.collection_id 
                AND cb.book_id = ?
            LEFT JOIN collection_books cb2 ON uc.collection_id = cb2.collection_id
            WHERE uc.user_id = ?
            GROUP BY uc.collection_id, uc.name
        """, (id, current_user.id)).fetchall()
        
        collection_status = collection_status['status'] if collection_status else 'untracked'
        
        return render_template(
            "book_detail.html",
            book=book,
            read_data=read_data,
            collection_status=collection_status,
            custom_collections=custom_collections
        )
    finally:
        conn.close()

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
    # Get search term
    search_term = request.args.get("search_term", "").lower()
    
    # Get sort parameters with validation
    sort_by = request.args.get("sort_by", "title")
    sort_order = request.args.get("sort_order", "asc")

    valid_columns = {"title", "author", "publish_year", "created_at"}
    valid_orders = {"asc", "desc"}

    if sort_by not in valid_columns:
        sort_by = "title"
    if sort_order not in valid_orders:
        sort_order = "asc"

    # Build the base query
    query = '''
        SELECT DISTINCT b.* FROM books b
        LEFT JOIN collections c ON b.id = c.book_id AND c.user_id = ?
        LEFT JOIN read_data r ON b.id = r.book_id AND r.user_id = ?
        LEFT JOIN book_tags t ON b.id = t.book_id AND t.user_id = ?
        WHERE (b.title LIKE ? OR b.author LIKE ? OR b.publish_year LIKE ?)
    '''
    params = [current_user.id, current_user.id, current_user.id]
    search_like = f"%{search_term}%"
    params.extend([search_like, search_like, search_like])
    
    # Apply filters if they exist
    if request.args.get('genre'):
        query += " AND b.genre = ?"
        params.append(request.args.get('genre'))
    
    if request.args.get('read_status'):
        query += " AND c.status = ?"
        params.append(request.args.get('read_status'))
    
    if request.args.get('rating'):
        query += " AND r.rating = ?"
        params.append(request.args.get('rating'))
    
    tags = request.args.getlist('tags[]')
    if tags:
        # Only use tags from the database
        valid_tags_query = '''
            SELECT DISTINCT tag_name FROM book_tags WHERE user_id = ?
        '''
        conn = get_db_connection()
        valid_tags = [row['tag_name'] for row in conn.execute(valid_tags_query, (current_user.id,)).fetchall()]
        conn.close()

        # Filter to only include valid tags
        valid_tags_in_request = [tag for tag in tags if tag in valid_tags]
        if valid_tags_in_request:
            placeholders = ','.join(['?' for _ in valid_tags_in_request])
            query += f" AND t.tag_name IN ({placeholders})"
            params.extend(valid_tags_in_request)
    
    # Add sorting
    query += f" ORDER BY {sort_by} {sort_order}"

    # Execute query
    conn = get_db_connection()
    try:
        books = conn.execute(query, params).fetchall()
        
        # Get filter options for the template
        filter_options = get_filter_options()
        
        return render_template("search.html",
                             books=books,
                             filter_options=filter_options,
                             sort_by=sort_by,
                             sort_order=sort_order,
                             search_term=search_term)
    finally:
        conn.close()

@books_blueprint.route("/search_books")
@login_required
@admin_required
def search_books():
    query = request.args.get("query", "")
    if not query:
        return jsonify({"results": []})
        
    try:
        # Use Google Books API for searching
        api_url = f"https://www.googleapis.com/books/v1/volumes?q={query}"
        response = requests.get(api_url).json()
        
        results = []
        if "items" in response:
            for item in response["items"][:10]:  # Limit to first 10 results
                volume_info = item["volumeInfo"]
                
                # Handle image URLs - get the largest available image
                image_links = volume_info.get("imageLinks", {})
                thumbnail_url = (
                    image_links.get("extraLarge") or
                    image_links.get("large") or
                    image_links.get("medium") or
                    image_links.get("small") or
                    image_links.get("thumbnail")
                )
                
                # Convert HTTP to HTTPS if necessary
                if thumbnail_url and thumbnail_url.startswith('http:'):
                    thumbnail_url = thumbnail_url.replace('http:', 'https:')

                # Remove zoom parameters from Google Books URLs to get full resolution
                if thumbnail_url:
                    thumbnail_url = thumbnail_url.replace('&zoom=1', '').replace('&edge=curl', '')
                
                result = {
                    "title": volume_info.get("title", ""),
                    "subtitle": volume_info.get("subtitle", ""),
                    "authors": ", ".join(volume_info.get("authors", [])),
                    "publisher": volume_info.get("publisher", ""),
                    "publishedDate": volume_info.get("publishedDate", "").split("-")[0],
                    "isbn": next((id["identifier"] for id in volume_info.get("industryIdentifiers", []) 
                               if id["type"] in ["ISBN_13", "ISBN_10"]), ""),
                    "thumbnail": thumbnail_url,
                    "description": volume_info.get("description", ""),
                    "pageCount": volume_info.get("pageCount", 0),
                    "categories": ", ".join(volume_info.get("categories", []))
                }
                results.append(result)
                
        return jsonify({"results": results})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500
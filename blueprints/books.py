from flask import Flask, render_template, redirect, url_for, request, flash, Blueprint, current_app
from flask_login import login_required
from werkzeug.utils import secure_filename
import sqlite3
import os
import time
import requests
from PIL import Image, ImageOps
from utils.database import get_db_connection  # If you're using this to handle DB connections
from models import admin_required  # Custom decorator for admin access control

# BOOK FUNCTIONS
## ADD BOOK
# Image upload variables
#UPLOAD_FOLDER = os.path.join('static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
#current_app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# helper function for image upload
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# initialize blueprint
books_blueprint = Blueprint('books', __name__, template_folder='templates')


@books_blueprint.route("/add", methods=["GET", "POST"])
@login_required
@admin_required
def add_book():
    book_details = None

    if request.method == "POST":
        if "isbn_lookup" in request.form:
            isbn = request.form["isbn"]
            # Fetch details using Google Books API
            api_url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}"
            response = requests.get(api_url).json()

            if "items" in response:
                book_data = response["items"][0]["volumeInfo"]
                book_details = {
                    "title": book_data.get("title", ""),
                    "author": ", ".join(book_data.get("authors", [])),  # Join multiple authors
                    "publisher": book_data.get("publisher", ""),
                    "year": book_data.get("publishedDate", "").split("-")[0],  # Extract year
                    "isbn": isbn,
                    "page_count": book_data.get("pageCount", 0),
                    "description": book_data.get("description", ""),  # Fetch description
                    "read": 0,
                }
            else:
                book_details = {"error": "Book not found. Please enter details manually."}

        if "submit_book" in request.form:
            title = request.form["title"]
            author = request.form["author"]
            publisher = request.form["publisher"]
            year = request.form["year"]
            isbn = request.form["isbn"]
            page_count = request.form["page_count"]
            description = request.form.get("description")  # Add description here
            read = 1 if "read" in request.form else 0

            # Handle the image upload
            cover_image_url = None
            if "image" in request.files:
                image = request.files["image"]
                if image.filename != '':
                    if image and allowed_file(image.filename):
                        filename = secure_filename(image.filename)        
                        
                        # Add timestamp to the filename for uniqueness
                        timestamp = int(time.time())  # Current timestamp in seconds
                        unique_filename = f"{filename.split('.')[0]}_{timestamp}.{filename.split('.')[-1]}"
                        save_path = os.path.join(current_app.config['UPLOAD_FOLDER'], unique_filename)
                        
                        # Open and resize the image
                        img = Image.open(image)
                        max_size = (500, 1000)  # Maximum dimensions (width, height)
                        img.thumbnail(max_size)  # Resize while maintaining aspect ratio
                        img = ImageOps.exif_transpose(img)

                        # Save the resized image
                        img.save(save_path)
                        cover_image_url = os.path.join('uploads', unique_filename)
                    else:
                        print("Invalid file type.")

            # Save book details to the database
            conn = sqlite3.connect("library.db")
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO books (title, author, publisher, publish_year, isbn, page_count, read, cover_image_url, description)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (title, author, publisher, year, isbn, page_count, read, cover_image_url, description))
            conn.commit()
            conn.close()
            return redirect("base.index")

    return render_template("add_book.html", book_details=book_details)

## EDIT BOOK
@books_blueprint.route("/edit/<int:id>", methods=["GET", "POST"])
@login_required
@admin_required
def edit_book(id):
    conn = get_db_connection()
    book_details = None  # Initialize book_details for ISBN lookup

    if request.method == "POST":
        if "isbn_lookup" in request.form:
            # Handle ISBN lookup
            isbn = request.form["isbn"]
            import requests
            api_url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}"
            response = requests.get(api_url).json()
            if "items" in response:
                book_data = response["items"][0]["volumeInfo"]
                book_details = {
                    "title": book_data.get("title", ""),
                    "author": ", ".join(book_data.get("authors", [])),
                    "publisher": book_data.get("publisher",""),
                    "year": book_data.get("publishedDate", "").split("-")[0],
                    "isbn": isbn,
                    "page_count": book_data.get("pageCount", 0),
                    "description": book_data.get("description", ""),
                }
            else:
                flash("Book not found. Please enter details manually.", "error")
        
        else:
            # Handle editing the book
            title = request.form["title"]
            author = request.form["author"]
            publisher = request.form.get("publisher")
            year = request.form.get("year")
            page_count = request.form.get("page_count", 0)
            description = request.form.get("description", "")
            read = 1 if "read" in request.form else 0

            # Handle the image upload
            cover_image_url = None  # Default to None if no image is uploaded
            if "image" in request.files:
                image = request.files["image"]
                if image and allowed_file(image.filename):
                    filename = secure_filename(image.filename)
            
                    # Add timestamp to the filename for uniqueness
                    timestamp = int(time.time())  # Current timestamp in seconds
                    unique_filename = f"{filename.split('.')[0]}_{timestamp}.{filename.split('.')[-1]}"
                    save_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                    
                    # Open and resize the image
                    img = Image.open(image)
                    max_size = (500, 1000)  # Maximum dimensions (width, height)
                    img.thumbnail(max_size)  # Resize while maintaining aspect ratio
                    img = ImageOps.exif_transpose(img)


                    # Save the resized image
                    img.save(save_path)
                    cover_image_url = os.path.join('uploads', unique_filename)
                else:
                    # If no valid image is uploaded, keep the existing image path from the database
                    cover_image_url = conn.execute("SELECT cover_image_url FROM books WHERE id = ?", (id,)).fetchone()[0] 
            
            # Update the book record, including the new image path (if uploaded)
            conn.execute("""
                UPDATE books
                SET title = ?, author = ?, publisher = ?, publish_year = ?, page_count = ?, read = ?, cover_image_url = ?, description = ?
                WHERE id = ?
            """, (title, author, publisher, year, page_count, read, cover_image_url, description, id))
            conn.commit()
            conn.close()

            return redirect("base.index")

    # Retrieve the existing book details for the form
    book = conn.execute("SELECT * FROM books WHERE id = ?", (id,)).fetchone()
    conn.close()
    return render_template("edit_book.html", book=book, book_details=book_details)

## VIEW BOOK
@books_blueprint.route("/book/<int:id>")
@login_required
def show_book(id):
    conn = get_db_connection()
    book = conn.execute("SELECT * FROM books WHERE id = ?", (id,)).fetchone()
    conn.close()
    return render_template("book_detail.html", book=book)

## DELETE BOOK
@books_blueprint.route("/delete/<int:id>")
@login_required
@admin_required
def delete_book(id):
    conn = get_db_connection()
    conn.execute("DELETE FROM books WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return redirect("base.index")

# SEARCH BOOKS
@books_blueprint.route("/search", methods=["GET"])
@login_required
def search():
    search_term = request.args.get("search_term", "").lower()  # Get the search term from the form

    conn = get_db_connection()

    # Query the database for books based on the search term
    books = conn.execute("""
        SELECT * FROM books
        WHERE lower(title) LIKE ? OR lower(author) LIKE ? OR publish_year LIKE ?
    """, (f"%{search_term}%", f"%{search_term}%", f"%{search_term}%")).fetchall()

    conn.close()

    return render_template("search.html", books=books)
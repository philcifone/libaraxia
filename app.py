from flask import Flask, render_template, request, redirect, url_for
from werkzeug.utils import secure_filename
import sqlite3, os, time, requests

app = Flask(__name__)

# Image upload variables
UPLOAD_FOLDER = os.path.join('static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# helper function for image upload
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


DATABASE = 'library.db'

# Helper function to connect to the database
def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row  # Allows dict-like access to rows
    return conn

@app.route("/")
def index():
    conn = get_db_connection()
    books = conn.execute("SELECT * FROM books").fetchall()
    conn.close()
    return render_template("index.html", books=books)

@app.route("/add", methods=["GET", "POST"])
def add_book():
    book_details = None

    if request.method == "POST":
        if "isbn_lookup" in request.form:
            isbn = request.form["isbn"]
            # Fetch details using API
            import requests
            api_url = f"https://openlibrary.org/api/books?bibkeys=ISBN:{isbn}&format=json&jscmd=data"
            response = requests.get(api_url).json()
            if f"ISBN:{isbn}" in response:
                book_data = response[f"ISBN:{isbn}"]
                book_details = {
                    "title": book_data.get("title", ""),
                    "author": book_data["authors"][0]["name"] if "authors" in book_data else "",
                    "publisher": book_data["publishers"][0]["name"] if "publishers" in book_data else "",
                    "year": book_data.get("publish_date", "").split()[-1],
                    "isbn": isbn,
                    "page_count": book_data.get("pagination", 0),
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
                        cover_image_url = os.path.join('uploads', unique_filename)

                        # Save the image with the unique filename
                        image.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_filename))
                    else:
                        print("Invalid file type.")

            # Save book details to the database
            conn = sqlite3.connect("library.db")
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO books (title, author, publisher, publish_year, isbn, page_count, read, cover_image_url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (title, author, publisher, year, isbn, page_count, read, cover_image_url))
            conn.commit()
            conn.close()
            return redirect("/")

    return render_template("add_book.html", book_details=book_details)

@app.route("/edit/<int:id>", methods=["GET", "POST"])
def edit_book(id):
    conn = get_db_connection()

    if request.method == "POST":
        # Get form data
        title = request.form["title"]
        author = request.form["author"]
        publisher = request.form.get("publisher")
        year = request.form.get("year")
        page_count = request.form.get("page_count", 0)
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
        
                cover_image_url = os.path.join('uploads', unique_filename)  # Store relative path
                image.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_filename))  # Save the image to the uploads folder
            else:
                # If no valid image is uploaded, keep the existing image path from the database
                cover_image_url = conn.execute("SELECT cover_image_url FROM books WHERE id = ?", (id,)).fetchone()[0] 
        
        # Update the book record, including the new image path (if uploaded)
        conn.execute("""
            UPDATE books
            SET title = ?, author = ?, publisher = ?, publish_year = ?, page_count = ?, read = ?, cover_image_url = ?
            WHERE id = ?
        """, (title, author, publisher, year, page_count, read, cover_image_url, id))
        conn.commit()
        conn.close()

        return redirect("/")

    # Retrieve the existing book details for the form
    book = conn.execute("SELECT * FROM books WHERE id = ?", (id,)).fetchone()
    conn.close()
    return render_template("edit_book.html", book=book)

@app.route("/search", methods=["GET"])
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

@app.route("/book/<int:id>")
def show_book(id):
    conn = get_db_connection()
    book = conn.execute("SELECT * FROM books WHERE id = ?", (id,)).fetchone()
    conn.close()
    return render_template("book_detail.html", book=book)

@app.route("/delete/<int:id>")
def delete_book(id):
    conn = get_db_connection()
    conn.execute("DELETE FROM books WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return redirect("/")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

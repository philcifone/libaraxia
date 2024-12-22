from flask import Flask, render_template, request, redirect, url_for, flash
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
import sqlite3, os, time, requests, logging, bcrypt

# user models
from models import User

#load environment variables from .env
from dotenv import load_dotenv
load_dotenv()

from config import DevelopmentConfig, ProductionConfig

DATABASE = 'library.db'

app = Flask(__name__)
# Set configuration based on an environment variable
env = os.getenv('FLASK_ENV', 'development')

if env == 'production':
    app.config.from_object(ProductionConfig)
else:
    app.config.from_object(DevelopmentConfig)

# Initialize SQLite database
from flask_sqlalchemy import SQLAlchemy
app.config['SQLALCHEMY_DATABASE_URI'] = app.config['DATABASE_URI']
db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)

# Configure logging
logging.basicConfig(level=logging.DEBUG)

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row  # Dict-like access to rows
    return conn

@login_manager.user_loader
def load_user(user_id):
    logging.debug(f"Loading user with ID: {user_id}") 
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    conn.close()
    if user:
        user_dict = dict(user)
        return User(
            id=user_dict['id'],
            username=user_dict['username'],
            email=user_dict['email'],
            is_active=user_dict.get('is_active', 0) == 1
        )
    return None

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']  # Capture password from the form

        # Ensure password is hashed using bcrypt
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                'INSERT INTO users (username, email, password) VALUES (?, ?, ?)',
                (username, email, hashed_password.decode('utf-8'))  # Decode hashed password for storage
            )
            conn.commit()
            flash('Registration successful!', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Email or username already registered!', 'danger')
        finally:
            conn.close()
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        conn.close()

        if user:
            user_dict = dict(user)
            if bcrypt.checkpw(password.encode('utf-8'), user_dict['password'].encode('utf-8')):
                # Password matches
                user_obj = User(
                    id=user_dict['id'],
                    username=user_dict['username'],
                    email=user_dict['email'],
                    is_active=user_dict.get('is_active', 0) == 1
                )
                login_user(user_obj)
                flash(f"Welcome, {user_obj.username}!", 'success')
                return redirect(url_for('index'))
        flash('Invalid email or password!', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    logout_user()
    flash('Logged out successfully!', 'success')
    return redirect(url_for('login'))

app.secret_key = os.urandom(24)  # Generates a secure random secret key


# Image upload variables
UPLOAD_FOLDER = os.path.join('static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# helper function for image upload
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Helper function to connect to the database
def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row  # Allows dict-like access to rows
    return conn

@app.route("/")
def home():
    return redirect(url_for('login'))

@app.route("/index")
@login_required
def index():
    sort_by = request.args.get("sort_by", "title")  # Default sort by title
    sort_order = request.args.get("sort_order", "asc")  # Default ascending order

    valid_columns = {"title", "author", "publish_year", "created_at"}  # Add columns you want to sort by
    valid_orders = {"asc", "desc"}

    if sort_by not in valid_columns:
        sort_by = "title"
    if sort_order not in valid_orders:
        sort_order = "asc"

    conn = get_db_connection()
    query = f"SELECT * FROM books ORDER BY {sort_by} {sort_order}"
    books = conn.execute(query).fetchall()
    conn.close()

    return render_template("index.html", books=books, sort_by=sort_by, sort_order=sort_order)

    return redirect(url_for('login'))

@app.route("/add", methods=["GET", "POST"])
@login_required
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
                        cover_image_url = os.path.join('uploads', unique_filename)

                        # Save the image with the unique filename
                        image.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_filename))
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
            return redirect("/")

    return render_template("add_book.html", book_details=book_details)

@app.route("/edit/<int:id>", methods=["GET", "POST"])
@login_required
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
            
                    cover_image_url = os.path.join('uploads', unique_filename)  # Store relative path
                    image.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_filename))  # Save the image to the uploads folder
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

            return redirect("/index")

    # Retrieve the existing book details for the form
    book = conn.execute("SELECT * FROM books WHERE id = ?", (id,)).fetchone()
    conn.close()
    return render_template("edit_book.html", book=book, book_details=book_details)

@app.route("/search", methods=["GET"])
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

@app.route("/book/<int:id>")
@login_required
def show_book(id):
    conn = get_db_connection()
    book = conn.execute("SELECT * FROM books WHERE id = ?", (id,)).fetchone()
    conn.close()
    return render_template("book_detail.html", book=book)

@app.route("/delete/<int:id>")
@login_required
def delete_book(id):
    conn = get_db_connection()
    conn.execute("DELETE FROM books WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return redirect("/")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

from flask import current_app
from werkzeug.utils import secure_filename
from PIL import Image, ImageOps
import requests
import os
import time
from typing import Optional, Dict, Any
from utils.database import get_db_connection
from flask_login import current_user

# Constants
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
MAX_IMAGE_SIZE = (500, 1000)

from typing import Optional, Dict, Any
from flask import current_app
import requests

def fetch_google_books(isbn: str) -> Optional[Dict[str, Any]]:
    """Fetch book details from Google Books API with highest resolution cover."""
    api_url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}&key={os.getenv('GOOGLE_BOOKS_API_KEY')}"
    try:
        response = requests.get(api_url).json()
        if "items" not in response:
            return None
            
        book_data = response["items"][0]["volumeInfo"]
        
        # Get highest resolution cover URL
        cover_url = None
        if "imageLinks" in book_data:
            # Try different image sizes in order of preference
            for size in ["extraLarge", "large", "medium", "small", "thumbnail"]:
                if size in book_data["imageLinks"]:
                    cover_url = book_data["imageLinks"][size]
                    # Clean up URL to get highest resolution
                    cover_url = (cover_url.replace('http:', 'https:')
                                        .split('&zoom=')[0]
                                        .split('&edge=')[0])
                    break

        return {
            "title": book_data.get("title", ""),
            "subtitle": book_data.get("subtitle", ""),
            "author": ", ".join(book_data.get("authors", [])),
            "publisher": book_data.get("publisher", ""),
            "year": book_data.get("publishedDate", "").split("-")[0],
            "isbn": isbn,
            "page_count": book_data.get("pageCount", 0),
            "description": book_data.get("description", ""),
            "cover_image_url": cover_url,
            "genre": ", ".join(book_data.get("categories", [])),
            "source": "Google Books"
        }
    except Exception as e:
        current_app.logger.error(f"Google Books API error: {str(e)}")
        return None

def fetch_open_library(isbn: str) -> Optional[Dict[str, Any]]:
    """Fetch book details from Open Library API."""
    api_url = f"https://openlibrary.org/api/books?bibkeys=ISBN:{isbn}&format=json&jscmd=data"
    try:
        response = requests.get(api_url).json()
        book_key = f"ISBN:{isbn}"
        
        if book_key not in response:
            return None
            
        book_data = response[book_key]
        
        # Extract subjects/genres from Open Library data
        subjects = book_data.get("subjects", [])
        genres = [subject for subject in subjects if isinstance(subject, str)]
        
        return {
            "title": book_data.get("title", ""),
            "subtitle": book_data.get("subtitle", ""),  # Added subtitle field
            "author": ", ".join(author.get("name", "") for author in book_data.get("authors", [])),
            "publisher": ", ".join(book_data.get("publishers", [""])),
            "year": book_data.get("publish_date", "").split()[-1],
            "isbn": isbn,
            "page_count": book_data.get("number_of_pages", 0),
            "description": book_data.get("notes", ""),
            "cover_image_url": book_data.get("cover", {}).get("large", "").replace("http:", "https:"),
            "genre": ", ".join(genres[:3]),  # Added genre field (limited to first 3 for brevity)
            "source": "Open Library"
        }
    except Exception as e:
        current_app.logger.error(f"Open Library API error: {str(e)}")
        return None

def fetch_book_details_from_isbn(isbn: str) -> Optional[Dict[str, Any]]:
    """Try multiple APIs to fetch book details with high-res covers."""
    book_details = fetch_google_books(isbn)
    
    if not book_details:
        book_details = fetch_open_library(isbn)
        # For Open Library, modify URL to get largest available image
        if book_details and book_details.get("cover_image_url"):
            book_details["cover_image_url"] = (
                book_details["cover_image_url"]
                .replace("-M", "-L")  # Try for large image
                .replace("-S", "-L")  # Handle small image URLs
            )
    
    if book_details and book_details.get("cover_image_url"):
        # Clean URL parameters that might limit resolution
        cover_url = book_details["cover_image_url"]
        if "googleusercontent" in cover_url:
            cover_url = cover_url.split('&zoom=')[0].split('&edge=')[0]
            book_details["cover_image_url"] = cover_url
        
        local_cover_url = download_and_save_cover(book_details["cover_image_url"])
        if local_cover_url:
            book_details["local_cover_url"] = local_cover_url
            book_details["thumbnail_url"] = book_details["cover_image_url"]
    
    return book_details

def allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def process_image(image_file, existing_url: Optional[str] = None) -> Optional[str]:
    """Process and save uploaded image."""
    if not image_file or image_file.filename == '':
        return existing_url
        
    if image_file and allowed_file(image_file.filename):
        filename = secure_filename(image_file.filename)
        timestamp = int(time.time())
        unique_filename = f"{filename.split('.')[0]}_{timestamp}.{filename.split('.')[-1]}"
        
        # Use absolute path for saving but return relative path for database
        save_path = os.path.join(current_app.config['UPLOAD_FOLDER'], unique_filename)
        
        # Ensure upload directory exists
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        
        img = Image.open(image_file)
        img.thumbnail(MAX_IMAGE_SIZE)
        img = ImageOps.exif_transpose(img)
        img.save(save_path)
        
        # Return relative path for database storage
        return os.path.join('uploads', unique_filename)
    return existing_url

def download_and_save_cover(url: str) -> Optional[str]:
    """Download and save cover image from URL."""
    if not url:
        current_app.logger.debug("No URL provided for cover download")
        return None
        
    try:
        current_app.logger.debug(f"Starting download from URL: {url}")

        # Create a session with headers to mimic a browser
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        
        # Try to get the image with a timeout
        response = session.get(url, stream=True, timeout=10)
        response.raise_for_status()  # Raise an exception for bad status codes
        
        if response.status_code != 200:
            current_app.logger.error(f"Failed to download cover. Status code: {response.status_code}")
            return None
        
        # Generate unique filename
        timestamp = int(time.time())
        filename = f"cover_{timestamp}.jpg"
        
        # Ensure the upload directory exists
        upload_folder = current_app.config['UPLOAD_FOLDER']
        os.makedirs(upload_folder, exist_ok=True)
        
        save_path = os.path.join(upload_folder, filename)
        current_app.logger.debug(f"Will save image to: {save_path}")
        
        # Save the raw image data first
        with open(save_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        
        # Now process with Pillow
        try:
            with Image.open(save_path) as img:
                # Convert to RGB if necessary
                if img.mode in ('RGBA', 'P'):
                    img = img.convert('RGB')
                
                # Resize while maintaining aspect ratio
                img.thumbnail(MAX_IMAGE_SIZE)
                
                # Handle EXIF orientation
                img = ImageOps.exif_transpose(img)
                
                # Save with optimal settings
                img.save(save_path, 'JPEG', quality=85, optimize=True)
            
            relative_path = os.path.join('uploads', filename)
            current_app.logger.info(f"Successfully saved image at: {relative_path}")
            return relative_path
            
        except Exception as e:
            current_app.logger.error(f"Error processing image with Pillow: {str(e)}")
            # Try to remove the failed file
            if os.path.exists(save_path):
                os.remove(save_path)
            return None
            
    except requests.RequestException as e:
        current_app.logger.error(f"Request error downloading cover: {str(e)}")
        return None
    except Exception as e:
        current_app.logger.error(f"Unexpected error downloading/saving cover: {str(e)}")
        return None

# filter options
def get_filter_options():
    """Fetch available filter options from the database."""
    conn = get_db_connection()
    try:
        # Fetch genres
        genres = [row['genre'] for row in conn.execute("SELECT DISTINCT genre FROM books").fetchall()]

        # Fetch read statuses
        read_statuses = [row['status'] for row in conn.execute("SELECT DISTINCT status FROM collections WHERE user_id = ?", (current_user.id,)).fetchall()]

        # Fetch ratings
        ratings = [row['rating'] for row in conn.execute("SELECT DISTINCT rating FROM read_data WHERE user_id = ?", (current_user.id,)).fetchall()]

        # Fetch tags
        tags = [row['tag_name'] for row in conn.execute("SELECT DISTINCT tag_name FROM book_tags WHERE user_id = ?", (current_user.id,)).fetchall()]

        # Return filter options as a dictionary
        return {
            'genres': genres,
            'read_statuses': read_statuses,
            'ratings': ratings,
            'tags': tags
        }
    finally:
        conn.close()

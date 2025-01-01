from flask import current_app
from werkzeug.utils import secure_filename
from PIL import Image, ImageOps
import requests
import os
import time
from typing import Optional, Dict, Any

# Constants
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
MAX_IMAGE_SIZE = (500, 1000)

def fetch_google_books(isbn: str) -> Optional[Dict[str, Any]]:
    """Fetch book details from Google Books API."""
    api_url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}"
    try:
        response = requests.get(api_url).json()
        if "items" not in response:
            return None
            
        book_data = response["items"][0]["volumeInfo"]
        return {
            "title": book_data.get("title", ""),
            "author": ", ".join(book_data.get("authors", [])),
            "publisher": book_data.get("publisher", ""),
            "year": book_data.get("publishedDate", "").split("-")[0],
            "isbn": isbn,
            "page_count": book_data.get("pageCount", 0),
            "description": book_data.get("description", ""),
            "cover_image_url": book_data.get("imageLinks", {}).get("thumbnail", None),
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
        return {
            "title": book_data.get("title", ""),
            "author": ", ".join(author.get("name", "") for author in book_data.get("authors", [])),
            "publisher": ", ".join(book_data.get("publishers", [""])),
            "year": book_data.get("publish_date", "").split()[-1],
            "isbn": isbn,
            "page_count": book_data.get("number_of_pages", 0),
            "description": book_data.get("notes", ""),
            "cover_image_url": book_data.get("cover", {}).get("large", "").replace("http:", "https:"),
            "source": "Open Library"
        }
    except Exception as e:
        current_app.logger.error(f"Open Library API error: {str(e)}")
        return None

def fetch_book_details_from_isbn(isbn: str) -> Optional[Dict[str, Any]]:
    """Try multiple APIs to fetch book details."""
    # Try Open Library first
    book_details = fetch_open_library(isbn)
    
    # If Open Library fails, try Google Books
    if not book_details:
        book_details = fetch_google_books(isbn)
    
    if book_details and book_details.get("cover_image_url"):
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
        save_path = os.path.join(current_app.config['UPLOAD_FOLDER'], unique_filename)
        
        img = Image.open(image_file)
        img.thumbnail(MAX_IMAGE_SIZE)
        img = ImageOps.exif_transpose(img)
        img.save(save_path)
        
        return os.path.join('uploads', unique_filename)
    return existing_url

def download_and_save_cover(url: str) -> Optional[str]:
    """Download and save cover image from URL."""
    if not url:
        return None
        
    try:
        response = requests.get(url)
        if response.status_code != 200:
            return None
            
        timestamp = int(time.time())
        filename = f"cover_{timestamp}.jpg"
        save_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
        
        img = Image.open(requests.get(url, stream=True).raw)
        img.thumbnail(MAX_IMAGE_SIZE)
        img.save(save_path)
        
        return os.path.join('uploads', filename)
    except Exception as e:
        current_app.logger.error(f"Error downloading cover: {str(e)}")
        return None
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

from typing import Optional, Dict, Any, List
from flask import current_app
import requests

def search_google_books(query: str, max_results: int = 15) -> List[Dict[str, Any]]:
    """Search Google Books API by title/author and return formatted results."""
    api_url = f"https://www.googleapis.com/books/v1/volumes?q={query}&key={os.getenv('GOOGLE_BOOKS_API_KEY')}"
    try:
        response = requests.get(api_url).json()

        if "items" not in response:
            current_app.logger.debug("No items found in Google Books response")
            return []

        processed_items = []
        for item in response["items"][:max_results]:
            volume_info = item.get("volumeInfo", {})

            # Get highest quality image URL
            image_links = volume_info.get("imageLinks", {})
            thumbnail_url = (
                image_links.get("extraLarge") or
                image_links.get("large") or
                image_links.get("medium") or
                image_links.get("small") or
                image_links.get("thumbnail")
            )

            if thumbnail_url:
                thumbnail_url = (thumbnail_url.replace('http:', 'https:')
                               .split('&zoom=')[0]
                               .split('&edge=')[0])

            # Get ISBN
            isbn = next((
                identifier.get("identifier")
                for identifier in volume_info.get("industryIdentifiers", [])
                if identifier.get("type") in ["ISBN_13", "ISBN_10"]
            ), None)

            # Create processed item
            processed_item = {
                "volumeInfo": {
                    "title": volume_info.get("title", ""),
                    "subtitle": volume_info.get("subtitle", ""),
                    "authors": volume_info.get("authors", []),
                    "publisher": volume_info.get("publisher", ""),
                    "publishedDate": volume_info.get("publishedDate", ""),
                    "description": volume_info.get("description", ""),
                    "pageCount": volume_info.get("pageCount", 0),
                    "categories": volume_info.get("categories", []),
                    "industryIdentifiers": [
                        {"type": "ISBN_13" if isbn else "OTHER", "identifier": isbn or ""}
                    ] if isbn else [],
                    "imageLinks": {"thumbnail": thumbnail_url} if thumbnail_url else {}
                }
            }
            processed_items.append(processed_item)

        return processed_items

    except Exception as e:
        current_app.logger.error(f"Google Books search error: {str(e)}")
        return []

def fetch_google_books(isbn: str) -> Optional[Dict[str, Any]]:
    """Fetch book details from Google Books API with highest resolution cover."""
    api_url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}&key={os.getenv('GOOGLE_BOOKS_API_KEY')}"
    try:
        response = requests.get(api_url).json()
        if "items" not in response:
            return None

        book_data = response["items"][0]["volumeInfo"]

        # Get all available image URLs in order of quality
        cover_urls = []
        if "imageLinks" in book_data:
            for size in ["extraLarge", "large", "medium", "small", "thumbnail"]:
                if size in book_data["imageLinks"]:
                    url = book_data["imageLinks"][size]
                    # Clean up URL to get highest resolution
                    url = (url.replace('http:', 'https:')
                              .split('&zoom=')[0]
                              .split('&edge=')[0])
                    cover_urls.append(url)

        # Primary URL is the highest quality available
        cover_url = cover_urls[0] if cover_urls else None
        # Fallback URLs are the rest
        fallback_urls = cover_urls[1:] if len(cover_urls) > 1 else None

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
            "cover_fallback_urls": fallback_urls,  # Store fallback URLs for download function
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

        # Get all available cover sizes from Open Library
        cover_urls = []
        cover_data = book_data.get("cover", {})
        for size in ["large", "medium", "small"]:
            if cover_data.get(size):
                url = cover_data[size].replace("http:", "https:")
                # Also try upgrading resolution by replacing size suffixes
                url_large = url.replace("-S.", "-L.").replace("-M.", "-L.")
                if url_large != url and url_large not in cover_urls:
                    cover_urls.append(url_large)
                if url not in cover_urls:
                    cover_urls.append(url)

        cover_url = cover_urls[0] if cover_urls else None
        fallback_urls = cover_urls[1:] if len(cover_urls) > 1 else None

        return {
            "title": book_data.get("title", ""),
            "subtitle": book_data.get("subtitle", ""),
            "author": ", ".join(author.get("name", "") for author in book_data.get("authors", [])),
            "publisher": ", ".join(book_data.get("publishers", [""])),
            "year": book_data.get("publish_date", "").split()[-1],
            "isbn": isbn,
            "page_count": book_data.get("number_of_pages", 0),
            "description": book_data.get("notes", ""),
            "cover_image_url": cover_url,
            "cover_fallback_urls": fallback_urls,
            "genre": ", ".join(genres[:3]),
            "source": "Open Library"
        }
    except Exception as e:
        current_app.logger.error(f"Open Library API error: {str(e)}")
        return None

def fetch_book_details_from_isbn(isbn: str) -> Optional[Dict[str, Any]]:
    """Try multiple APIs to fetch book details with high-res covers and fallback support."""
    book_details = fetch_google_books(isbn)

    if not book_details:
        book_details = fetch_open_library(isbn)

    if book_details and book_details.get("cover_image_url"):
        # Download cover with fallback URL support
        primary_url = book_details["cover_image_url"]
        fallback_urls = book_details.get("cover_fallback_urls")

        local_cover_url = download_and_save_cover(primary_url, fallback_urls)
        if local_cover_url:
            book_details["local_cover_url"] = local_cover_url
            book_details["thumbnail_url"] = primary_url
        else:
            current_app.logger.warning(f"Failed to download any cover images for ISBN {isbn}")

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

def download_and_save_cover(url: str, fallback_urls: Optional[list] = None) -> Optional[str]:
    """Download and save cover image from URL with fallback support.

    Args:
        url: Primary image URL to download
        fallback_urls: Optional list of fallback URLs to try if primary fails

    Returns:
        Relative path to saved image or None if all attempts fail
    """
    if not url:
        current_app.logger.debug("No URL provided for cover download")
        return None

    # Create list of URLs to try (primary + fallbacks)
    urls_to_try = [url]
    if fallback_urls:
        urls_to_try.extend(fallback_urls)

    # Create a session with headers to mimic a browser
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    })

    # Try each URL in order
    for attempt_num, attempt_url in enumerate(urls_to_try, 1):
        try:
            current_app.logger.debug(f"Download attempt {attempt_num}/{len(urls_to_try)} from: {attempt_url}")

            # Try to get the image with a timeout
            response = session.get(attempt_url, stream=True, timeout=10)
            response.raise_for_status()  # Raise an exception for bad status codes

            if response.status_code != 200:
                current_app.logger.warning(f"Attempt {attempt_num} failed. Status code: {response.status_code}")
                continue  # Try next URL

            # Generate unique filename
            timestamp = int(time.time())
            filename = f"cover_{timestamp}_{attempt_num}.jpg"

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
                resolution = "primary" if attempt_num == 1 else f"fallback #{attempt_num - 1}"
                current_app.logger.info(f"Successfully saved image ({resolution}) at: {relative_path}")
                return relative_path

            except Exception as e:
                current_app.logger.warning(f"Error processing image from attempt {attempt_num}: {str(e)}")
                # Try to remove the failed file
                if os.path.exists(save_path):
                    os.remove(save_path)
                continue  # Try next URL

        except requests.RequestException as e:
            current_app.logger.warning(f"Request error on attempt {attempt_num}: {str(e)}")
            continue  # Try next URL
        except Exception as e:
            current_app.logger.warning(f"Unexpected error on attempt {attempt_num}: {str(e)}")
            continue  # Try next URL

    # All attempts failed
    current_app.logger.error(f"Failed to download cover after {len(urls_to_try)} attempts")
    return None

def fetch_cover_by_isbn_direct(isbn: str) -> Optional[str]:
    """Try to fetch cover directly from Open Library Covers API using ISBN.

    This is a direct cover API that doesn't require the book to be in their database.
    Returns the highest quality cover URL available.
    """
    if not isbn:
        return None

    # Clean ISBN (remove hyphens)
    clean_isbn = isbn.replace("-", "").replace(" ", "")

    # Try different sizes, starting with largest
    for size in ["L", "M", "S"]:
        url = f"https://covers.openlibrary.org/b/isbn/{clean_isbn}-{size}.jpg"
        try:
            # Check if the cover exists (Open Library returns a 1x1 pixel for missing covers)
            response = requests.head(url, timeout=5, allow_redirects=True)
            if response.status_code == 200:
                # Check content length to avoid tiny placeholder images
                content_length = int(response.headers.get('content-length', 0))
                if content_length > 1000:  # More than 1KB suggests real cover
                    current_app.logger.info(f"Found Open Library cover (size {size}): {url}")
                    return url
        except Exception as e:
            current_app.logger.debug(f"Open Library cover check failed for {url}: {str(e)}")
            continue

    return None

def search_covers_multiple_sources(isbn: str = None, title: str = None, author: str = None) -> list:
    """Search multiple sources for book covers and return all found URLs.

    Returns:
        List of tuples: [(url, source_name, priority), ...]
        Priority: lower number = better quality/more reliable
    """
    covers = []

    # Source 1: Open Library direct ISBN lookup (often best quality)
    if isbn:
        ol_direct_url = fetch_cover_by_isbn_direct(isbn)
        if ol_direct_url:
            covers.append((ol_direct_url, "Open Library Direct", 1))

    # Source 2: Google Books via ISBN
    if isbn:
        google_data = fetch_google_books(isbn)
        if google_data and google_data.get("cover_image_url"):
            covers.append((google_data["cover_image_url"], "Google Books (ISBN)", 2))

    # Source 3: Open Library Books API via ISBN
    if isbn:
        ol_data = fetch_open_library(isbn)
        if ol_data and ol_data.get("cover_image_url"):
            covers.append((ol_data["cover_image_url"], "Open Library (ISBN)", 3))

    # Source 4: Google Books via title/author search
    if title:
        query = f"{title} {author}".strip() if author else title
        search_results = search_google_books(query, max_results=3)

        for idx, result in enumerate(search_results):
            thumbnail_url = result.get("volumeInfo", {}).get("imageLinks", {}).get("thumbnail")
            if thumbnail_url:
                # Try to get ISBN from search result for Open Library lookup
                result_isbn = None
                identifiers = result.get("volumeInfo", {}).get("industryIdentifiers", [])
                for identifier in identifiers:
                    if identifier.get("type") in ["ISBN_13", "ISBN_10"]:
                        result_isbn = identifier.get("identifier")
                        break

                # If we found an ISBN in the search result, try Open Library direct
                if result_isbn and not isbn:  # Only if we didn't already try with main ISBN
                    ol_direct_url = fetch_cover_by_isbn_direct(result_isbn)
                    if ol_direct_url:
                        covers.append((ol_direct_url, f"Open Library (Search Result #{idx+1})", 4 + idx))

                covers.append((thumbnail_url, f"Google Books (Search #{idx+1})", 5 + idx))

    # Sort by priority (lower number first)
    covers.sort(key=lambda x: x[2])

    return covers

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

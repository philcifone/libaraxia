from flask import current_app
from werkzeug.utils import secure_filename
from PIL import Image, ImageOps
from io import BytesIO
import re
import requests
import os
import time
import uuid
from typing import Optional, Dict, Any, List, Iterable
from utils.database import get_db_connection
from flask_login import current_user

# Constants
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
MAX_IMAGE_SIZE = (500, 1000)

GOOGLE_BOOKS_URL = "https://www.googleapis.com/books/v1/volumes"
OPEN_LIBRARY_URL = "https://openlibrary.org"
HTTP_TIMEOUT = 8
RETRY_STATUS_CODES = {429, 500, 502, 503, 504}
# Anything smaller than this is a placeholder (e.g. Open Library's 1x1 gif)
MIN_COVER_DIMENSION = 50
# A cover at least this wide is good enough; stop looking for a bigger one
GOOD_COVER_WIDTH = 300
MAX_COVER_BYTES = 10 * 1024 * 1024
# After Google Books fails, skip it for this long instead of retrying every lookup
GOOGLE_COOLDOWN_SECONDS = 60
_google_down_until = 0.0

_session = requests.Session()
_session.headers.update({
    'User-Agent': 'Mozilla/5.0 (compatible; Libaraxia/1.0; personal library catalog)'
})


# ---------------------------------------------------------------------------
# ISBN helpers
# ---------------------------------------------------------------------------

def normalize_isbn(isbn: Optional[str]) -> str:
    """Strip hyphens/spaces so '978-0-670-67190-8' becomes '9780670671908'."""
    return re.sub(r'[^0-9X]', '', (isbn or '').upper())

def isbn_variants(isbn: str) -> List[str]:
    """Return the ISBN plus its ISBN-10/ISBN-13 counterpart when one exists.

    APIs often index an edition under only one form, so trying both helps.
    """
    isbn = normalize_isbn(isbn)
    variants = [isbn] if isbn else []
    if len(isbn) == 10 and isbn[:9].isdigit():
        core = '978' + isbn[:9]
        check = (10 - sum((1 if i % 2 == 0 else 3) * int(d) for i, d in enumerate(core)) % 10) % 10
        variants.append(core + str(check))
    elif len(isbn) == 13 and isbn.startswith('978') and isbn.isdigit():
        core = isbn[3:12]
        check = (11 - sum((10 - i) * int(d) for i, d in enumerate(core)) % 11) % 11
        variants.append(core + ('X' if check == 10 else str(check)))
    return variants


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def _get_json(url: str, params: Optional[dict] = None, retries: int = 1) -> Optional[Any]:
    """GET a JSON API, retrying on rate limits and server errors.

    Returns None on failure. Google Books in particular returns intermittent
    503s, so a couple of quick retries make lookups far more reliable.
    """
    for attempt in range(retries + 1):
        try:
            response = _session.get(url, params=params, timeout=HTTP_TIMEOUT)
            if response.status_code in RETRY_STATUS_CODES and attempt < retries:
                time.sleep(0.5 * (attempt + 1))
                continue
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as e:
            if attempt < retries:
                time.sleep(0.5 * (attempt + 1))
                continue
            # Log the base URL only so the API key never ends up in logs
            current_app.logger.warning(f"Request to {url} failed: {e.__class__.__name__}")
            return None
    return None


# ---------------------------------------------------------------------------
# Google Books
# ---------------------------------------------------------------------------

def _google_volumes(query: str, max_results: int = 10) -> Optional[List[dict]]:
    """Query Google Books. Returns a list of items, or None if the API failed."""
    global _google_down_until
    if time.time() < _google_down_until:
        return None

    params = {"q": query, "maxResults": max(1, min(max_results, 40))}
    api_key = os.getenv('GOOGLE_BOOKS_API_KEY')
    if api_key:
        params["key"] = api_key

    data = _get_json(GOOGLE_BOOKS_URL, params)
    if data is None or "error" in data:
        if data:
            current_app.logger.error(f"Google Books API error: {data['error'].get('message', 'Unknown API error')}")
        current_app.logger.warning(f"Google Books unavailable, using Open Library for {GOOGLE_COOLDOWN_SECONDS}s")
        _google_down_until = time.time() + GOOGLE_COOLDOWN_SECONDS
        return None
    return data.get("items", [])

def _google_cover_urls(volume_info: dict) -> List[str]:
    """All Google cover URLs for a volume, largest first."""
    urls = []
    image_links = volume_info.get("imageLinks", {})
    for size in ["extraLarge", "large", "medium", "small", "thumbnail", "smallThumbnail"]:
        url = image_links.get(size)
        if url:
            url = (url.replace('http:', 'https:')
                      .split('&zoom=')[0]
                      .split('&edge=')[0])
            if url not in urls:
                urls.append(url)
    return urls

def search_google_books(query: str, max_results: int = 15) -> List[Dict[str, Any]]:
    """Search for books by title/author and return Google-Books-shaped results.

    Falls back to Open Library search when Google fails or finds nothing.
    """
    items = _google_volumes(query, max_results)
    if not items:
        current_app.logger.info(f"Google Books returned no results for '{query}', trying Open Library")
        return search_open_library(query, max_results)

    processed_items = []
    for item in items[:max_results]:
        volume_info = item.get("volumeInfo", {})
        cover_urls = _google_cover_urls(volume_info)

        isbn = next((
            identifier.get("identifier")
            for identifier in volume_info.get("industryIdentifiers", [])
            if identifier.get("type") in ["ISBN_13", "ISBN_10"]
        ), None)

        processed_items.append({
            "volumeInfo": {
                "title": volume_info.get("title", ""),
                "subtitle": volume_info.get("subtitle", ""),
                "authors": volume_info.get("authors", []),
                "publisher": volume_info.get("publisher", ""),
                "publishedDate": volume_info.get("publishedDate", ""),
                "description": volume_info.get("description", ""),
                "pageCount": volume_info.get("pageCount", 0),
                "categories": volume_info.get("categories", []),
                "industryIdentifiers": [{"type": "ISBN_13", "identifier": isbn}] if isbn else [],
                "imageLinks": {"thumbnail": cover_urls[0]} if cover_urls else {}
            }
        })

    return processed_items

def fetch_google_books(isbn: str) -> Optional[Dict[str, Any]]:
    """Fetch book details from Google Books by ISBN (tries ISBN-10 and -13)."""
    items = None
    for variant in isbn_variants(isbn):
        items = _google_volumes(f"isbn:{variant}", 1)
        # None means the API itself failed; no point trying the other form
        if items is None or items:
            break
    if not items:
        return None

    book_data = items[0]["volumeInfo"]
    cover_urls = _google_cover_urls(book_data)

    return {
        "title": book_data.get("title", ""),
        "subtitle": book_data.get("subtitle", ""),
        "author": ", ".join(book_data.get("authors", [])),
        "publisher": book_data.get("publisher", ""),
        "year": book_data.get("publishedDate", "").split("-")[0],
        "isbn": normalize_isbn(isbn),
        "page_count": book_data.get("pageCount", 0),
        "description": book_data.get("description", ""),
        "cover_image_url": cover_urls[0] if cover_urls else None,
        "cover_candidates": cover_urls,
        "genre": ", ".join(book_data.get("categories", [])),
        "source": "Google Books"
    }


# ---------------------------------------------------------------------------
# Open Library
# ---------------------------------------------------------------------------

def _names(items) -> List[str]:
    """Open Library returns authors/publishers/subjects as [{"name": ...}]."""
    return [item.get("name", "") if isinstance(item, dict) else str(item) for item in items or []]

def _text(value) -> str:
    """Open Library text fields are either a string or {"type": ..., "value": ...}."""
    if isinstance(value, dict):
        return value.get("value", "")
    return value or ""

def _open_library_cover_url(cover_id) -> Optional[str]:
    return f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg" if cover_id else None

def _open_library_work_description(isbn: str) -> str:
    """The edition record rarely has a description; the work record usually does."""
    edition = _get_json(f"{OPEN_LIBRARY_URL}/isbn/{isbn}.json", retries=0)
    works = (edition or {}).get("works") or []
    if not works:
        return ""
    work = _get_json(f"{OPEN_LIBRARY_URL}{works[0]['key']}.json", retries=0)
    return _text((work or {}).get("description"))

def fetch_open_library(isbn: str) -> Optional[Dict[str, Any]]:
    """Fetch book details from the Open Library Books API by ISBN."""
    for variant in isbn_variants(isbn):
        data = _get_json(f"{OPEN_LIBRARY_URL}/api/books",
                         {"bibkeys": f"ISBN:{variant}", "format": "json", "jscmd": "data"})
        book_data = (data or {}).get(f"ISBN:{variant}")
        if book_data:
            break
    else:
        return None

    cover_data = book_data.get("cover", {})
    cover_urls = [cover_data[size].replace("http:", "https:")
                  for size in ["large", "medium", "small"] if cover_data.get(size)]

    year_match = re.search(r'\d{4}', book_data.get("publish_date", ""))
    description = _text(book_data.get("notes")) or _open_library_work_description(variant)

    return {
        "title": book_data.get("title", ""),
        "subtitle": book_data.get("subtitle", ""),
        "author": ", ".join(_names(book_data.get("authors"))),
        "publisher": ", ".join(_names(book_data.get("publishers"))),
        "year": year_match.group(0) if year_match else "",
        "isbn": normalize_isbn(isbn),
        "page_count": book_data.get("number_of_pages", 0),
        "description": description,
        "cover_image_url": cover_urls[0] if cover_urls else None,
        "cover_candidates": cover_urls,
        "genre": ", ".join(_names(book_data.get("subjects"))[:3]),
        "source": "Open Library"
    }

def search_open_library(query: str = None, max_results: int = 15,
                        title: str = None, author: str = None) -> List[Dict[str, Any]]:
    """Search Open Library and return results in the same shape as search_google_books.

    Pass `query` for a free-text search, or `title`/`author` for a fielded one.
    """
    params = {
        "limit": max_results,
        "fields": "title,subtitle,author_name,publisher,first_publish_year,"
                  "number_of_pages_median,isbn,cover_i,subject"
    }
    # Open Library uses Lucene syntax, where "Stop-Time" means "Stop NOT Time"
    clean = lambda text: re.sub(r'[-:!(){}\[\]^"~*?\\/+]', ' ', text)
    if title:
        params["title"] = clean(title)
        if author:
            params["author"] = clean(author)
    else:
        params["q"] = clean(query or "")
    data = _get_json(f"{OPEN_LIBRARY_URL}/search.json", params)
    if not data:
        return []

    processed_items = []
    for doc in data.get("docs", [])[:max_results]:
        isbns = doc.get("isbn", [])
        isbn = next((i for i in isbns if len(i) == 13), isbns[0] if isbns else None)
        cover_url = _open_library_cover_url(doc.get("cover_i"))

        processed_items.append({
            "volumeInfo": {
                "title": doc.get("title", ""),
                "subtitle": doc.get("subtitle", ""),
                "authors": doc.get("author_name", []),
                "publisher": (doc.get("publisher") or [""])[0],
                "publishedDate": str(doc.get("first_publish_year", "")),
                "description": "",
                "pageCount": doc.get("number_of_pages_median") or 0,
                "categories": doc.get("subject", [])[:3],
                "industryIdentifiers": [{"type": "ISBN_13", "identifier": isbn}] if isbn else [],
                "imageLinks": {"thumbnail": cover_url} if cover_url else {}
            }
        })

    return processed_items

def fetch_cover_by_isbn_direct(isbn: str) -> List[str]:
    """Open Library Covers API URLs for an ISBN (both ISBN-10 and -13 forms).

    Works even when the book isn't in Open Library's catalog. `default=false`
    makes missing covers 404 instead of returning a 1x1 placeholder.
    """
    return [f"https://covers.openlibrary.org/b/isbn/{variant}-L.jpg?default=false"
            for variant in isbn_variants(isbn)]


# ---------------------------------------------------------------------------
# Goodreads (via BookCover API)
# ---------------------------------------------------------------------------

def fetch_goodreads_cover(isbn: str = None, title: str = None, author: str = None) -> Optional[str]:
    """Fetch book cover from Goodreads via BookCover API.

    This uses the free BookCover API that scrapes Goodreads.
    API: https://github.com/w3slley/bookcover-api
    Returns JSON: {"url": "https://..."}
    """
    # The API requires both book_title and author_name (doesn't support ISBN alone)
    if not (title and author):
        return None

    data = _get_json("https://bookcover.longitood.com/bookcover",
                     {"book_title": title, "author_name": author}, retries=0)
    cover_url = (data or {}).get("url")
    if cover_url:
        current_app.logger.info(f"Found Goodreads cover for '{title}' by {author}: {cover_url}")
    return cover_url


# ---------------------------------------------------------------------------
# Cover candidates
# ---------------------------------------------------------------------------

def _title_cover_urls(title: str, author: Optional[str] = None) -> Iterable[str]:
    """Cover URLs found by title/author, for books whose ISBN has no cover.

    A generator so the slower lookups only run if the earlier ones fail.
    """
    for result in search_open_library(title=title, author=author, max_results=3):
        url = result["volumeInfo"]["imageLinks"].get("thumbnail")
        if url:
            yield url
    goodreads_url = fetch_goodreads_cover(title=title, author=author)
    if goodreads_url:
        yield goodreads_url

def search_covers_multiple_sources(isbn: str = None, title: str = None, author: str = None) -> list:
    """Search multiple sources for book covers and return all found URLs.

    Returns:
        List of tuples: [(url, source_name, priority), ...]
        Priority: lower number = better quality/more reliable
    """
    covers = []
    seen = set()

    def add(url, source):
        if url and url not in seen:
            seen.add(url)
            covers.append((url, source, len(covers) + 1))

    if isbn:
        for url in fetch_cover_by_isbn_direct(isbn):
            add(url, "Open Library (ISBN)")

        google_data = fetch_google_books(isbn)
        if google_data and google_data["cover_candidates"]:
            add(google_data["cover_candidates"][0], "Google Books (ISBN)")

        ol_data = fetch_open_library(isbn)
        if ol_data and ol_data["cover_candidates"]:
            add(ol_data["cover_candidates"][0], "Open Library (edition)")

    if title:
        if author:
            add(fetch_goodreads_cover(title=title, author=author), "Goodreads")

        for idx, result in enumerate(search_open_library(title=title, author=author, max_results=3), 1):
            add(result["volumeInfo"]["imageLinks"].get("thumbnail"), f"Open Library (search #{idx})")

        query = f"intitle:{title} inauthor:{author}" if author else f"intitle:{title}"
        google_results = _google_volumes(query, 3) or []
        for idx, item in enumerate(google_results, 1):
            urls = _google_cover_urls(item.get("volumeInfo", {}))
            if urls:
                add(urls[0], f"Google Books (search #{idx})")

    return covers


# ---------------------------------------------------------------------------
# Book lookup
# ---------------------------------------------------------------------------

def _is_missing_details(details: Optional[dict]) -> bool:
    if not details or not details.get("cover_candidates"):
        return True
    return any(not details.get(field) for field in ("author", "publisher", "year", "page_count", "description"))

def fetch_book_details_from_isbn(isbn: str) -> Optional[Dict[str, Any]]:
    """Look a book up by ISBN across Google Books and Open Library.

    Google is tried first; Open Library fills in anything Google is missing
    (or everything, when Google is down). The best available cover is then
    downloaded, falling back to title/author cover searches if needed.
    """
    isbn = normalize_isbn(isbn)
    if not isbn:
        return None

    google = fetch_google_books(isbn)
    open_library = fetch_open_library(isbn) if _is_missing_details(google) else None

    if google and open_library:
        book_details = dict(google)
        for field, value in open_library.items():
            if not book_details.get(field) and value:
                book_details[field] = value
        book_details["source"] = "Google Books + Open Library"
    else:
        book_details = google or open_library
    if not book_details:
        return None

    cover_urls = (
        (google or {}).get("cover_candidates", []) +
        (open_library or {}).get("cover_candidates", []) +
        fetch_cover_by_isbn_direct(isbn)
    )
    local_cover_url = save_best_cover(cover_urls)
    if not local_cover_url and book_details.get("title"):
        current_app.logger.info(f"No ISBN cover for {isbn}, searching by title/author")
        local_cover_url = save_best_cover(_title_cover_urls(book_details["title"], book_details.get("author")))

    book_details.pop("cover_candidates", None)
    if local_cover_url:
        book_details["cover_image_url"] = local_cover_url
        book_details["local_cover_url"] = local_cover_url
        book_details["thumbnail_url"] = f"/static/{local_cover_url}"
    else:
        # Never store a hotlinked remote URL; the UI falls back to no-cover.png
        book_details["cover_image_url"] = None
        current_app.logger.warning(f"Failed to download any cover images for ISBN {isbn}")

    return book_details


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------

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

def _fetch_image(url: str) -> Optional[Image.Image]:
    """Download a URL and return it as a PIL image, or None if it isn't a real cover."""
    try:
        response = _session.get(url, stream=True, timeout=HTTP_TIMEOUT)
        if response.status_code != 200:
            current_app.logger.debug(f"Cover {url} returned {response.status_code}")
            return None
        content = response.raw.read(MAX_COVER_BYTES + 1, decode_content=True)
        if len(content) > MAX_COVER_BYTES:
            current_app.logger.debug(f"Cover {url} is too large, skipping")
            return None
        img = Image.open(BytesIO(content))
        img.load()
    except Exception as e:
        current_app.logger.debug(f"Cover {url} could not be loaded: {e}")
        return None

    if img.width < MIN_COVER_DIMENSION or img.height < MIN_COVER_DIMENSION:
        current_app.logger.debug(f"Cover {url} is a {img.width}x{img.height} placeholder, skipping")
        return None
    return img

def _save_cover_image(img: Image.Image) -> str:
    """Normalize, resize and save a cover image. Returns the path relative to static/."""
    img = ImageOps.exif_transpose(img)
    if img.mode in ('RGBA', 'LA', 'P'):
        img = img.convert('RGBA')
        background = Image.new('RGB', img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[-1])
        img = background
    elif img.mode != 'RGB':
        img = img.convert('RGB')
    img.thumbnail(MAX_IMAGE_SIZE)

    upload_folder = current_app.config['UPLOAD_FOLDER']
    os.makedirs(upload_folder, exist_ok=True)
    filename = f"cover_{uuid.uuid4().hex}.jpg"
    img.save(os.path.join(upload_folder, filename), 'JPEG', quality=85, optimize=True)
    return os.path.join('uploads', filename)

def save_best_cover(urls: Iterable[str]) -> Optional[str]:
    """Download candidate cover URLs in order and save the best one.

    Stops at the first cover that is at least GOOD_COVER_WIDTH wide; otherwise
    keeps the largest valid image seen. Placeholders and broken images are
    skipped. Returns the saved path relative to static/, or None.
    """
    best = None
    tried = set()
    for url in urls:
        if not url or url in tried:
            continue
        tried.add(url)
        img = _fetch_image(url)
        if img is None:
            continue
        current_app.logger.debug(f"Cover candidate {img.width}x{img.height}: {url}")
        if best is None or img.width > best.width:
            best = img
        if img.width >= GOOD_COVER_WIDTH:
            break

    if best is None:
        return None
    relative_path = _save_cover_image(best)
    current_app.logger.info(f"Saved {best.width}x{best.height} cover at: {relative_path}")
    return relative_path

def download_and_save_cover(url: str, fallback_urls: Optional[list] = None) -> Optional[str]:
    """Download and save a cover image, trying fallback URLs if the primary fails.

    Returns:
        Relative path to saved image or None if all attempts fail
    """
    if not url:
        current_app.logger.debug("No URL provided for cover download")
        return None
    return save_best_cover([url] + (fallback_urls or []))


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

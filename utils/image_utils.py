"""
Image management utilities: item photos, file cleanup and orphan detection
"""
import os
import shutil
import uuid

from flask import current_app
from PIL import Image, ImageOps, UnidentifiedImageError


def is_safe_upload_path(image_path):
    """
    Check that a stored image path points inside static/uploads/.

    Cover and avatar paths come back from the browser in hidden form fields,
    so they must be validated before being saved or later passed to os.remove.
    """
    if not image_path or not isinstance(image_path, str):
        return False
    if image_path.startswith('/') or '\\' in image_path or ':' in image_path:
        return False
    normalized = os.path.normpath(image_path).replace(os.sep, '/')
    return normalized.startswith('uploads/') and '..' not in normalized.split('/')


# Where stored paths ('uploads/...') resolve: <project>/static. A module
# value rather than current_app, because cover_missing() runs as an SQL
# function on any connection, request or not; tests point it elsewhere.
STATIC_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static')


def upload_exists(image_path):
    """True when a stored path is an upload whose file is there. Templates
    use it as the `upload_exists` filter on avatars, so a dead link shows
    the letter placeholder instead of a broken image (the browser's "?"):
    {% if user.avatar_url|upload_exists %}."""
    return is_safe_upload_path(image_path) and os.path.isfile(os.path.join(STATIC_ROOT, image_path))


def cover_missing(image_path):
    """1 when a stored cover is an upload whose file is gone, else 0.

    Registered as the SQL function cover_missing() on every connection
    (utils/database.py), so "needs a cover" can be `cover_image_url IS NULL
    OR cover_missing(cover_image_url)` (book_utils.missing_cover_sql). A path
    that isn't an upload is left alone. If the uploads folder is missing or
    empty, nothing counts as missing: that's an unmounted or moved folder,
    not hundreds of lost covers, and the fetcher must not overwrite every
    link in the catalog because of it."""
    if not is_safe_upload_path(image_path):
        return 0
    uploads = os.path.join(STATIC_ROOT, 'uploads')
    try:
        with os.scandir(uploads) as entries:
            if next(entries, None) is None:
                return 0
    except OSError:
        return 0
    return 0 if os.path.isfile(os.path.join(STATIC_ROOT, image_path)) else 1


# Item photos (ROADMAP 16.0a): big enough to read liner notes or see a scuff
# (covers stop at 500x1000), small enough for a phone to load.
PHOTO_MAX_SIDE = 2000


class PhotoError(ValueError):
    """An upload that isn't a usable image; the message is safe to show."""


# The admin's placeholder face images (ROADMAP 16.0c, utils/faces.py)
FACES_FOLDER = 'uploads/faces'


def photo_folder(book_id):
    """The stored prefix of an item's photos: 'uploads/photos/<id>'."""
    return f'uploads/photos/{int(book_id)}'


def save_photo(file, book_id, folder=None, shape=None):
    """Save an uploaded photo of an item; returns its stored path
    ('uploads/photos/<book_id>/<random>.jpg').

    Turned upright (phones store sideways pixels plus an EXIF rotation),
    resized to PHOTO_MAX_SIDE on the long side keeping its aspect (a spine is
    a tall strip and isn't cropped), and saved as a fresh JPEG with **no
    metadata at all**: EXIF carries GPS, and a photo taken at home would
    publish where home is. Copying the pixels into a new image, rather than
    trusting save() to leave EXIF, XMP and comments out, makes that certain.

    `shape` ('wide' or 'tall') turns an image that came in the other way a
    quarter turn anticlockwise: a placeholder for a top or bottom is a wide
    strip and one for a spine or side a tall one, whichever way the phone
    held it (blueprints/faces.add). The crop tool fixes the rare one that
    lands upside down.

    Raises PhotoError for anything Pillow can't read as an image."""
    try:
        img = Image.open(file)
        img.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise PhotoError("That file isn't an image this site can read (use a JPEG, PNG or WebP).")
    img = ImageOps.exif_transpose(img)
    w, h = img.size
    if (shape == 'wide' and h > w) or (shape == 'tall' and w > h):
        img = img.transpose(Image.Transpose.ROTATE_90)
    return save_photo_image(img, book_id, folder)


def save_photo_image(img, book_id, folder=None):
    """save_photo's second half, for an image already open and upright (a
    cropped photo, blueprints/photos.crop): flatten, resize, re-encode with
    no metadata, save under the item's folder, or under `folder` (an
    'uploads/...' prefix: the admin's placeholder faces, FACES_FOLDER).
    Returns the stored path."""
    if img.mode in ('RGBA', 'LA', 'P'):
        rgba = img.convert('RGBA')
        img = Image.new('RGB', rgba.size, (255, 255, 255))
        img.paste(rgba, mask=rgba.split()[-1])
    elif img.mode != 'RGB':
        img = img.convert('RGB')
    img.thumbnail((PHOTO_MAX_SIDE, PHOTO_MAX_SIDE), Image.LANCZOS)

    clean = Image.new('RGB', img.size)
    clean.paste(img)

    rel = f'{folder or photo_folder(book_id)}/{uuid.uuid4().hex}.jpg'
    full = os.path.join(STATIC_ROOT, rel)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    clean.save(full, 'JPEG', quality=85, optimize=True)
    return rel


def delete_photo_folder(book_id):
    """Remove an item's photo folder after the item is deleted (its rows went
    with it, ON DELETE CASCADE). Only ever static/uploads/photos/<int id>."""
    root = os.path.realpath(os.path.join(STATIC_ROOT, 'uploads', 'photos'))
    folder = os.path.realpath(os.path.join(STATIC_ROOT, photo_folder(book_id)))
    if os.path.dirname(folder) != root or not os.path.isdir(folder):
        return False
    try:
        shutil.rmtree(folder)
        return True
    except OSError as e:
        current_app.logger.error(f"Failed to delete photo folder {folder}: {e}")
        return False


def delete_image_file(image_path, static_root=None):
    """
    Safely delete an image file given its relative path from static directory

    Args:
        image_path: Relative path from static directory (e.g., 'uploads/cover_123.jpg')
        static_root: where 'uploads/...' resolves; the app's static/ by
            default. Item photos pass STATIC_ROOT, where save_photo put them
            (the same folder outside tests).

    Returns:
        bool: True if file was deleted, False if it didn't exist or deletion failed
    """
    if not image_path:
        return False

    if not is_safe_upload_path(image_path):
        current_app.logger.warning(f"Refusing to delete image outside uploads: {image_path!r}")
        return False

    # Build full path: static/image_path, and make sure it really is inside uploads/
    static_root = static_root or os.path.join(current_app.root_path, 'static')
    uploads_root = os.path.realpath(os.path.join(static_root, 'uploads'))
    full_path = os.path.realpath(os.path.join(static_root, image_path))
    if not full_path.startswith(uploads_root + os.sep):
        current_app.logger.warning(f"Refusing to delete image outside uploads: {image_path!r}")
        return False

    if os.path.exists(full_path):
        try:
            os.remove(full_path)
            current_app.logger.info(f"Deleted image file: {full_path}")
            return True
        except Exception as e:
            current_app.logger.error(f"Failed to delete image {full_path}: {e}")
            return False
    else:
        current_app.logger.debug(f"Image file does not exist: {full_path}")
        return False


def find_orphaned_images(db_connection):
    """
    Find image files that exist on disk but are not referenced in the database

    Args:
        db_connection: Active database connection

    Returns:
        dict: {
            'orphaned_files': list of relative paths to orphaned files,
            'total_size': total size in bytes of orphaned files,
            'count': number of orphaned files
        }
    """
    # Collect all image paths referenced in database
    db_images = set()

    # Get book cover images
    books = db_connection.execute(
        "SELECT cover_image_url FROM books WHERE cover_image_url IS NOT NULL"
    ).fetchall()
    db_images.update(row['cover_image_url'] for row in books)

    # Get user avatar images
    users = db_connection.execute(
        "SELECT avatar_url FROM users WHERE avatar_url IS NOT NULL"
    ).fetchall()
    db_images.update(row['avatar_url'] for row in users)

    # Item photos (16.0a): back, spine and gallery. Without these the first
    # cleanup after photos shipped would delete every one of them.
    photos = db_connection.execute("SELECT path FROM item_photos").fetchall()
    db_images.update(row['path'] for row in photos)
    # Placeholder faces (16.0c): the admin's library
    faces = db_connection.execute("SELECT path FROM face_placeholders").fetchall()
    db_images.update(row['path'] for row in faces)

    current_app.logger.info(f"Found {len(db_images)} images referenced in database")

    # Scan filesystem for all images in uploads directory
    upload_dir = os.path.join(current_app.root_path, 'static', 'uploads')
    disk_images = []

    if not os.path.exists(upload_dir):
        current_app.logger.warning(f"Upload directory does not exist: {upload_dir}")
        return {
            'orphaned_files': [],
            'total_size': 0,
            'total_size_mb': 0,
            'count': 0
        }

    # Walk through all files in uploads directory and subdirectories
    for root, dirs, files in os.walk(upload_dir):
        for file in files:
            # Skip hidden files and system files
            if file.startswith('.'):
                continue

            full_path = os.path.join(root, file)
            # Get path relative to static directory
            rel_path = os.path.relpath(full_path, os.path.join(current_app.root_path, 'static'))
            # Normalize path separators for cross-platform compatibility
            rel_path = rel_path.replace('\\', '/')
            disk_images.append({
                'path': rel_path,
                'full_path': full_path,
                'size': os.path.getsize(full_path)
            })

    current_app.logger.info(f"Found {len(disk_images)} image files on disk")

    # Find orphans (files on disk but not in database)
    orphaned = []
    total_size = 0

    for img in disk_images:
        if img['path'] not in db_images:
            orphaned.append({
                'path': img['path'],
                'full_path': img['full_path'],
                'size': img['size'],
                'size_kb': round(img['size'] / 1024, 2),
                'size_mb': round(img['size'] / (1024 * 1024), 2)
            })
            total_size += img['size']

    return {
        'orphaned_files': orphaned,
        'total_size': total_size,
        'total_size_mb': round(total_size / (1024 * 1024), 2),
        'count': len(orphaned)
    }


def cleanup_orphaned_images(orphaned_files):
    """
    Delete a list of orphaned image files

    Args:
        orphaned_files: List of file paths to delete (relative to static directory)

    Returns:
        dict: {
            'deleted': number of files successfully deleted,
            'failed': number of files that failed to delete,
            'errors': list of error messages
        }
    """
    deleted = 0
    failed = 0
    errors = []

    for file_path in orphaned_files:
        # If file_path is a dict (from find_orphaned_images), extract the path
        if isinstance(file_path, dict):
            file_path = file_path['path']

        if delete_image_file(file_path):
            deleted += 1
        else:
            failed += 1
            errors.append(f"Failed to delete: {file_path}")

    current_app.logger.info(f"Cleanup complete: {deleted} deleted, {failed} failed")

    return {
        'deleted': deleted,
        'failed': failed,
        'errors': errors
    }

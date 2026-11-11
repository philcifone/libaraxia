"""
Image management utilities for file cleanup and orphan detection
"""
import os
from flask import current_app


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


def delete_image_file(image_path):
    """
    Safely delete an image file given its relative path from static directory

    Args:
        image_path: Relative path from static directory (e.g., 'uploads/cover_123.jpg')

    Returns:
        bool: True if file was deleted, False if it didn't exist or deletion failed
    """
    if not image_path:
        return False

    if not is_safe_upload_path(image_path):
        current_app.logger.warning(f"Refusing to delete image outside uploads: {image_path!r}")
        return False

    # Build full path: app_root/static/image_path, and make sure it really is inside uploads/
    uploads_root = os.path.realpath(os.path.join(current_app.root_path, 'static', 'uploads'))
    full_path = os.path.realpath(os.path.join(current_app.root_path, 'static', image_path))
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

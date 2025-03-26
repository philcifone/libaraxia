import sqlite3
import os

DATABASE = os.getenv('DATABASE_PATH', 'library.db')

# Helper function to connect to the database
def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row  # Allows dict-like access to rows
    return conn
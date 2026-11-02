#!/usr/bin/env python3
"""
Debug script to check library membership status
"""
import sqlite3
import sys

def check_library_membership(db_path='library.db'):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    print("=" * 60)
    print("LIBRARY MEMBERSHIP DEBUG")
    print("=" * 60)

    # Check all users
    users = conn.execute('SELECT id, username FROM users ORDER BY id').fetchall()
    print(f"\n📚 Total Users: {len(users)}")
    for user in users:
        print(f"  - {user['username']} (ID: {user['id']})")

    # Check library members table
    print("\n" + "=" * 60)
    print("LIBRARY GROUPS")
    print("=" * 60)

    members = conn.execute('''
        SELECT
            lm.library_id,
            lm.user_id,
            u.username,
            lm.role,
            lm.added_at
        FROM library_members lm
        JOIN users u ON lm.user_id = u.id
        ORDER BY lm.library_id, lm.user_id
    ''').fetchall()

    if not members:
        print("\n⚠️  No library groups found!")
        print("Users are not assigned to any library groups yet.")
    else:
        # Group by library_id
        current_lib = None
        for member in members:
            if current_lib != member['library_id']:
                current_lib = member['library_id']
                print(f"\n📖 Library Group #{current_lib}")
            print(f"  - {member['username']} (ID: {member['user_id']}, Role: {member['role']})")

    # Check books and who added them
    print("\n" + "=" * 60)
    print("BOOKS BY ADDED_BY")
    print("=" * 60)

    book_counts = conn.execute('''
        SELECT
            b.added_by,
            u.username,
            COUNT(*) as book_count
        FROM books b
        LEFT JOIN users u ON b.added_by = u.id
        GROUP BY b.added_by
        ORDER BY book_count DESC
    ''').fetchall()

    total_books = sum(row['book_count'] for row in book_counts)
    print(f"\n📚 Total Books: {total_books}")

    for row in book_counts:
        username = row['username'] if row['username'] else 'NULL/Unknown'
        print(f"  - {username} (ID: {row['added_by']}): {row['book_count']} books")

    # Test get_library_members function for each user
    print("\n" + "=" * 60)
    print("LIBRARY MEMBERS FUNCTION TEST")
    print("=" * 60)

    for user in users:
        user_id = user['id']
        username = user['username']

        # Simulate get_library_members function
        library = conn.execute('''
            SELECT library_id FROM library_members
            WHERE user_id = ?
        ''', (user_id,)).fetchone()

        if library:
            lib_members = conn.execute('''
                SELECT user_id, username FROM library_members lm
                JOIN users u ON lm.user_id = u.id
                WHERE library_id = ?
            ''', (library['library_id'],)).fetchall()

            member_names = [m['username'] for m in lib_members]
            print(f"\n👤 {username} (ID: {user_id})")
            print(f"   Library Group: #{library['library_id']}")
            print(f"   Shares library with: {', '.join(member_names)}")
            print(f"   Should see books from user IDs: {[m['user_id'] for m in lib_members]}")
        else:
            print(f"\n👤 {username} (ID: {user_id})")
            print(f"   Not in any library group")
            print(f"   Should see only their own books (ID: {user_id})")

    conn.close()

if __name__ == '__main__':
    db_path = sys.argv[1] if len(sys.argv) > 1 else 'library.db'
    print(f"Using database: {db_path}\n")
    check_library_membership(db_path)

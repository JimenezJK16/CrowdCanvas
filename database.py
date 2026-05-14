import io
import sqlite3
from datetime import datetime
from pathlib import Path
import hashlib

DB_PATH = Path(__file__).parent / "gallery.db"

#Initialize database tables
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_gallery (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            image_data BLOB NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (username) REFERENCES users(username)
        )
    """)

    conn.commit()
    conn.close()

#Helper to hash passwords
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

#Sign up function
def create_user(username, password):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (username, hash_password(password))
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

#Sign in function
def verify_user(username, password):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT password_hash FROM users WHERE username = ?",
        (username,)
    )

    row = cursor.fetchone()
    conn.close()

    if row is None:
        return False

    stored_hash = row[0]
    return stored_hash == hash_password(password)

#Save image to database function
def save_image(username, image):
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    image_bytes = buf.getvalue()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO user_gallery (username, image_data, created_at)
        VALUES (?, ?, ?)
        """,
        (
            username,
            image_bytes,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
    )

    conn.commit()
    conn.close()

def delete_image(username, image_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        DELETE FROM user_gallery
        WHERE id = ? AND username = ?
        """,
        (image_id, username)
    )

    conn.commit()
    conn.close()
    
def load_gallery(username):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, image_data, created_at
        FROM user_gallery
        WHERE username = ?
        ORDER BY id DESC
        """,
        (username,)
    )

    rows = cursor.fetchall()
    conn.close()

    return rows
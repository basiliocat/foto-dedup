"""SQLite database module for foto-dedup."""

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY,
    path TEXT UNIQUE,
    dir TEXT,
    filename TEXT,
    size INTEGER,
    md5 TEXT,
    scan_id TEXT,
    scanned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_files_md5_size ON files(md5, size);
CREATE INDEX IF NOT EXISTS idx_files_dir ON files(dir);
CREATE INDEX IF NOT EXISTS idx_files_path_size ON files(path, size);
"""


def get_connection(db_path="files.db"):
    """Open (or create) a SQLite database and return the connection."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db(conn):
    """Create the files table and indexes if they don't exist."""
    conn.executescript(SCHEMA)
    conn.commit()


def insert_file(conn, path, dir_, filename, size, md5, scan_id):
    """Insert or update a file record.

    If the path already exists, update all fields.
    """
    conn.execute(
        """INSERT INTO files (path, dir, filename, size, md5, scan_id, scanned_at)
           VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
           ON CONFLICT(path) DO UPDATE SET
               dir=excluded.dir,
               filename=excluded.filename,
               size=excluded.size,
               md5=excluded.md5,
               scan_id=excluded.scan_id,
               scanned_at=excluded.scanned_at
        """,
        (str(path), str(dir_), filename, size, md5, scan_id),
    )

"""Tests for fotodedup.db module."""

import sqlite3
import tempfile
import os

import pytest

from fotodedup import db


@pytest.fixture
def conn():
    """Create an in-memory database connection."""
    c = db.get_connection(":memory:")
    db.init_db(c)
    yield c
    c.close()


def test_init_db_creates_table(conn):
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='files'"
    ).fetchall()
    assert len(tables) == 1


def test_init_db_schema_columns(conn):
    info = conn.execute("PRAGMA table_info(files)").fetchall()
    columns = {row["name"] for row in info}
    expected = {"id", "path", "dir", "filename", "size", "md5", "scan_id", "scanned_at"}
    assert columns == expected


def test_insert_file(conn):
    db.insert_file(conn, "/a/b/photo.jpg", "/a/b", "photo.jpg", 12345, "abc123", "scan1")
    conn.commit()
    row = conn.execute("SELECT * FROM files WHERE path = '/a/b/photo.jpg'").fetchone()
    assert row is not None
    assert row["size"] == 12345
    assert row["md5"] == "abc123"
    assert row["scan_id"] == "scan1"


def test_insert_file_upsert(conn):
    db.insert_file(conn, "/a/b/photo.jpg", "/a/b", "photo.jpg", 100, "old_md5", "scan1")
    conn.commit()
    db.insert_file(conn, "/a/b/photo.jpg", "/a/b", "photo.jpg", 200, "new_md5", "scan2")
    conn.commit()

    rows = conn.execute("SELECT * FROM files WHERE path = '/a/b/photo.jpg'").fetchall()
    assert len(rows) == 1
    assert rows[0]["size"] == 200
    assert rows[0]["md5"] == "new_md5"
    assert rows[0]["scan_id"] == "scan2"


def test_path_unique_constraint(conn):
    db.insert_file(conn, "/x/y.jpg", "/x", "y.jpg", 10, "aaa", "s1")
    conn.commit()
    # upsert should not raise
    db.insert_file(conn, "/x/y.jpg", "/x", "y.jpg", 20, "bbb", "s2")
    conn.commit()
    count = conn.execute("SELECT COUNT(*) as cnt FROM files").fetchone()["cnt"]
    assert count == 1


def test_parse_extensions_default():
    exts = db.parse_extensions(".jpg,.jpeg,.avi,.mp4,.heic")
    assert exts == {".jpg", ".jpeg", ".avi", ".mp4", ".heic"}


def test_parse_extensions_glob_style():
    exts = db.parse_extensions("*.jpg,*.png")
    assert exts == {".jpg", ".png"}


def test_parse_extensions_no_dot():
    exts = db.parse_extensions("jpg,png")
    assert exts == {".jpg", ".png"}


def test_parse_extensions_star():
    assert db.parse_extensions("*") is None


def test_parse_extensions_empty():
    assert db.parse_extensions("") is None


def test_matches_extension_match():
    exts = {".jpg", ".png"}
    assert db.matches_extension("photo.jpg", exts) is True
    assert db.matches_extension("photo.JPG", exts) is True
    assert db.matches_extension("photo.png", exts) is True


def test_matches_extension_no_match():
    exts = {".jpg", ".png"}
    assert db.matches_extension("photo.avi", exts) is False


def test_matches_extension_none():
    assert db.matches_extension("anything.xyz", None) is True


def test_get_connection_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        c = db.get_connection(db_path)
        db.init_db(c)
        db.insert_file(c, "/test", "/", "test", 1, "x", "s")
        c.commit()
        c.close()

        # Reopen and verify data persists
        c2 = db.get_connection(db_path)
        row = c2.execute("SELECT * FROM files WHERE path = '/test'").fetchone()
        assert row is not None
        c2.close()

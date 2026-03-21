"""Tests for fotodedup.corrupt module."""

import pytest

from fotodedup import db
from fotodedup.corrupt import find_corrupt_candidates, print_corrupt, ensure_deleted_at_column


@pytest.fixture
def conn():
    c = db.get_connection(":memory:")
    db.init_db(c)
    ensure_deleted_at_column(c)
    yield c
    c.close()


def _insert(conn, path, dir_, fname, size, md5, scan_id="s1"):
    db.insert_file(conn, path, dir_, fname, size, md5, scan_id)
    conn.commit()


# --- find_corrupt_candidates ---

def test_find_corrupt_basic(conn):
    """Same name+size, different md5 — corruption candidate."""
    _insert(conn, "/a/photo.jpg", "/a", "photo.jpg", 1000, "aaa111")
    _insert(conn, "/b/photo.jpg", "/b", "photo.jpg", 1000, "bbb222")

    groups = find_corrupt_candidates(conn)
    assert len(groups) == 1
    fname, size, files = groups[0]
    assert fname == "photo.jpg"
    assert size == 1000
    assert len(files) == 2
    md5s = {f["md5"] for f in files}
    assert md5s == {"aaa111", "bbb222"}


def test_find_corrupt_same_md5_not_corrupt(conn):
    """Same name+size+md5 — true duplicate, NOT corruption."""
    _insert(conn, "/a/photo.jpg", "/a", "photo.jpg", 1000, "same_hash")
    _insert(conn, "/b/photo.jpg", "/b", "photo.jpg", 1000, "same_hash")

    groups = find_corrupt_candidates(conn)
    assert len(groups) == 0


def test_find_corrupt_different_size_not_corrupt(conn):
    """Same name but different size — not a corruption pair."""
    _insert(conn, "/a/photo.jpg", "/a", "photo.jpg", 1000, "aaa")
    _insert(conn, "/b/photo.jpg", "/b", "photo.jpg", 2000, "bbb")

    groups = find_corrupt_candidates(conn)
    assert len(groups) == 0


def test_find_corrupt_excludes_deleted(conn):
    """Deleted files should not appear."""
    _insert(conn, "/a/photo.jpg", "/a", "photo.jpg", 1000, "aaa")
    _insert(conn, "/b/photo.jpg", "/b", "photo.jpg", 1000, "bbb")
    conn.execute("UPDATE files SET deleted_at = CURRENT_TIMESTAMP WHERE path = '/b/photo.jpg'")
    conn.commit()

    groups = find_corrupt_candidates(conn)
    assert len(groups) == 0


def test_find_corrupt_empty_db(conn):
    groups = find_corrupt_candidates(conn)
    assert groups == []


def test_find_corrupt_sorted_by_size(conn):
    """Larger files first."""
    _insert(conn, "/a/small.jpg", "/a", "small.jpg", 100, "s1")
    _insert(conn, "/b/small.jpg", "/b", "small.jpg", 100, "s2")
    _insert(conn, "/a/big.jpg", "/a", "big.jpg", 9999, "b1")
    _insert(conn, "/b/big.jpg", "/b", "big.jpg", 9999, "b2")

    groups = find_corrupt_candidates(conn)
    assert len(groups) == 2
    assert groups[0][1] == 9999
    assert groups[1][1] == 100


def test_find_corrupt_three_copies_mixed(conn):
    """Three copies: two identical, one different — still flagged."""
    _insert(conn, "/a/photo.jpg", "/a", "photo.jpg", 1000, "good")
    _insert(conn, "/b/photo.jpg", "/b", "photo.jpg", 1000, "good")
    _insert(conn, "/c/photo.jpg", "/c", "photo.jpg", 1000, "corrupt")

    groups = find_corrupt_candidates(conn)
    assert len(groups) == 1
    assert len(groups[0][2]) == 3


# --- print_corrupt ---

def test_print_corrupt_output(conn, capsys):
    _insert(conn, "/a/photo.jpg", "/a", "photo.jpg", 1000, "aaa111")
    _insert(conn, "/b/photo.jpg", "/b", "photo.jpg", 1000, "bbb222")

    print_corrupt(conn)
    out = capsys.readouterr().out

    assert "photo.jpg" in out
    assert "/a/photo.jpg" in out
    assert "/b/photo.jpg" in out
    assert "aaa111"[:8] in out
    assert "bbb222"[:8] in out
    assert "different hashes" in out
    assert "Total:" in out


def test_print_corrupt_no_results(conn, capsys):
    _insert(conn, "/a/photo.jpg", "/a", "photo.jpg", 1000, "same")
    _insert(conn, "/b/photo.jpg", "/b", "photo.jpg", 1000, "same")

    print_corrupt(conn)
    out = capsys.readouterr().out
    assert "No corruption candidates" in out

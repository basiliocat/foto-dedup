"""Tests for fotodedup.scanner module."""

import hashlib
import os
import tempfile

import pytest

from fotodedup import db
from fotodedup.scanner import compute_md5, file_already_scanned, scan_paths


@pytest.fixture
def conn():
    c = db.get_connection(":memory:")
    db.init_db(c)
    yield c
    c.close()


@pytest.fixture
def sample_dir():
    """Create a temp directory with test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Large file (> 10KB)
        large = os.path.join(tmpdir, "large.bin")
        with open(large, "wb") as f:
            f.write(b"A" * 20000)

        # Small file (< 10KB, should be skipped by default min-size)
        small = os.path.join(tmpdir, "small.txt")
        with open(small, "wb") as f:
            f.write(b"tiny")

        # Subdirectory with a duplicate
        sub = os.path.join(tmpdir, "sub")
        os.makedirs(sub)
        dup = os.path.join(sub, "dup.bin")
        with open(dup, "wb") as f:
            f.write(b"A" * 20000)

        yield tmpdir


def test_compute_md5(sample_dir):
    fpath = os.path.join(sample_dir, "large.bin")
    expected = hashlib.md5(b"A" * 20000).hexdigest()
    assert compute_md5(fpath) == expected


def test_compute_md5_small_block():
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(b"hello world")
        f.flush()
        path = f.name
    try:
        expected = hashlib.md5(b"hello world").hexdigest()
        assert compute_md5(path, block_size=4) == expected
    finally:
        os.unlink(path)


def test_scan_paths_basic(conn, sample_dir):
    scanned, skipped, errors = scan_paths([sample_dir], conn, min_size=10240, scan_id="test1")

    # large.bin + sub/dup.bin should be scanned; small.txt skipped
    assert scanned == 2
    assert skipped == 1
    assert errors == 0

    rows = conn.execute("SELECT * FROM files ORDER BY path").fetchall()
    assert len(rows) == 2
    for row in rows:
        assert row["md5"] == hashlib.md5(b"A" * 20000).hexdigest()
        assert row["size"] == 20000
        assert row["scan_id"] == "test1"


def test_scan_min_size_filter(conn, sample_dir):
    # With min_size=0, all files should be scanned
    scanned, skipped, errors = scan_paths([sample_dir], conn, min_size=0, scan_id="test2")
    assert scanned == 3  # large.bin, small.txt, sub/dup.bin


def test_incremental_scan(conn, sample_dir):
    # First scan
    scan_paths([sample_dir], conn, min_size=0, scan_id="s1")

    # Second scan — same files, same sizes, should be skipped
    scanned, skipped, errors = scan_paths([sample_dir], conn, min_size=0, scan_id="s2")
    assert scanned == 0
    assert skipped == 3


def test_file_already_scanned(conn):
    db.insert_file(conn, "/a/b.jpg", "/a", "b.jpg", 1000, "md5", "s1")
    conn.commit()
    assert file_already_scanned(conn, "/a/b.jpg", 1000) is True
    assert file_already_scanned(conn, "/a/b.jpg", 999) is False
    assert file_already_scanned(conn, "/a/c.jpg", 1000) is False


def test_scan_extension_filter(conn, sample_dir):
    """Only .bin files should be scanned when filtering by extension."""
    exts = db.parse_extensions(".bin")
    scanned, skipped, errors = scan_paths(
        [sample_dir], conn, min_size=0, scan_id="ext1", extensions=exts,
    )
    assert scanned == 2  # large.bin, sub/dup.bin
    assert skipped >= 1  # small.txt filtered out


def test_scan_extension_filter_none(conn, sample_dir):
    """No extension filter — all files scanned (respecting min_size)."""
    scanned, _, _ = scan_paths(
        [sample_dir], conn, min_size=0, scan_id="ext2", extensions=None,
    )
    assert scanned == 3


def test_scan_nonexistent_path(conn):
    scanned, skipped, errors = scan_paths(["/nonexistent/path"], conn)
    assert scanned == 0


def test_scan_single_file(conn):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as f:
        f.write(b"X" * 20000)
        path = f.name
    try:
        scanned, _, _ = scan_paths([path], conn, min_size=0, scan_id="sf")
        assert scanned == 1
        row = conn.execute("SELECT * FROM files").fetchone()
        assert row["filename"] == os.path.basename(path)
    finally:
        os.unlink(path)

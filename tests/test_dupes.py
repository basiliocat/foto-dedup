"""Tests for fotodedup.dupes module."""

import io
import sys

import pytest

from fotodedup import db
from fotodedup.dupes import find_dupes, format_size, print_dupes, compare_dirs, find_file, print_find_results


@pytest.fixture
def conn():
    c = db.get_connection(":memory:")
    db.init_db(c)
    yield c
    c.close()


def _insert(conn, path, dir_, fname, size, md5, scan_id="s1"):
    db.insert_file(conn, path, dir_, fname, size, md5, scan_id)
    conn.commit()


def test_format_size():
    assert format_size(500) == "500.0 B"
    assert format_size(1024) == "1.0 KB"
    assert format_size(1024 * 1024) == "1.0 MB"
    assert format_size(1024 ** 3) == "1.0 GB"


def test_find_dupes_no_dupes(conn):
    _insert(conn, "/a/1.jpg", "/a", "1.jpg", 100, "aaa")
    _insert(conn, "/a/2.jpg", "/a", "2.jpg", 200, "bbb")
    assert find_dupes(conn) == []


def test_find_dupes_with_dupes(conn):
    _insert(conn, "/a/1.jpg", "/a", "1.jpg", 1000, "same_md5")
    _insert(conn, "/b/2.jpg", "/b", "2.jpg", 1000, "same_md5")
    _insert(conn, "/c/3.jpg", "/c", "3.jpg", 500, "other")

    groups = find_dupes(conn)
    assert len(groups) == 1
    md5, size, files = groups[0]
    assert md5 == "same_md5"
    assert size == 1000
    assert len(files) == 2


def test_find_dupes_sorted_by_size(conn):
    _insert(conn, "/a/small1.jpg", "/a", "small1.jpg", 100, "sm")
    _insert(conn, "/b/small2.jpg", "/b", "small2.jpg", 100, "sm")
    _insert(conn, "/a/big1.jpg", "/a", "big1.jpg", 9999, "bg")
    _insert(conn, "/b/big2.jpg", "/b", "big2.jpg", 9999, "bg")

    groups = find_dupes(conn)
    assert len(groups) == 2
    assert groups[0][1] == 9999  # larger group first
    assert groups[1][1] == 100


def test_print_dupes_output(conn, capsys):
    _insert(conn, "/a/1.jpg", "/a", "1.jpg", 5000, "dup_md5")
    _insert(conn, "/b/1.jpg", "/b", "1.jpg", 5000, "dup_md5")

    print_dupes(conn)
    out = capsys.readouterr().out
    assert "Group 1/1" in out
    assert "/a/1.jpg" in out
    assert "/b/1.jpg" in out
    assert "waste" in out.lower() or "Waste" in out


def test_print_dupes_no_dupes(conn, capsys):
    _insert(conn, "/a/1.jpg", "/a", "1.jpg", 100, "unique")
    print_dupes(conn)
    out = capsys.readouterr().out
    assert "No duplicates" in out


def test_compare_dirs(conn, capsys):
    # Dir A: 2 files
    _insert(conn, "/dirA/photo1.jpg", "/dirA", "photo1.jpg", 1000, "aaa")
    _insert(conn, "/dirA/photo2.jpg", "/dirA", "photo2.jpg", 2000, "bbb")
    # Dir B: 1 shared + 1 unique
    _insert(conn, "/dirB/copy1.jpg", "/dirB", "copy1.jpg", 1000, "aaa")
    _insert(conn, "/dirB/unique.jpg", "/dirB", "unique.jpg", 3000, "ccc")

    compare_dirs(conn, "/dirA", "/dirB")
    out = capsys.readouterr().out

    assert "Directory A: /dirA" in out
    assert "Directory B: /dirB" in out
    assert "Common" in out
    assert "Only in A: 1" in out
    assert "Only in B: 1" in out


def test_compare_dirs_subdirs(conn, capsys):
    """Compare should include files in subdirectories."""
    _insert(conn, "/root/sub/a.jpg", "/root/sub", "a.jpg", 500, "x1")
    _insert(conn, "/other/a.jpg", "/other", "a.jpg", 500, "x1")

    compare_dirs(conn, "/root", "/other")
    out = capsys.readouterr().out
    assert "Common" in out


def test_compare_dirs_empty(conn, capsys):
    compare_dirs(conn, "/empty1", "/empty2")
    err = capsys.readouterr().err
    assert "No files found" in err


def test_find_file_by_name(conn):
    _insert(conn, "/a/photo.jpg", "/a", "photo.jpg", 1000, "aaa")
    _insert(conn, "/b/photo.jpg", "/b", "photo.jpg", 2000, "bbb")
    _insert(conn, "/c/other.jpg", "/c", "other.jpg", 500, "ccc")

    results = find_file(conn, "photo.jpg")
    assert len(results) == 2
    assert results[0]["path"] == "/a/photo.jpg"
    assert results[1]["path"] == "/b/photo.jpg"


def test_find_file_by_name_and_size(conn):
    _insert(conn, "/a/photo.jpg", "/a", "photo.jpg", 1000, "aaa")
    _insert(conn, "/b/photo.jpg", "/b", "photo.jpg", 2000, "bbb")

    results = find_file(conn, "photo.jpg", size=1000)
    assert len(results) == 1
    assert results[0]["path"] == "/a/photo.jpg"


def test_find_file_wildcard(conn):
    _insert(conn, "/a/IMG_001.jpg", "/a", "IMG_001.jpg", 100, "x1")
    _insert(conn, "/a/IMG_002.jpg", "/a", "IMG_002.jpg", 200, "x2")
    _insert(conn, "/a/video.mp4", "/a", "video.mp4", 300, "x3")

    results = find_file(conn, "IMG%")
    assert len(results) == 2


def test_find_file_no_results(conn):
    _insert(conn, "/a/photo.jpg", "/a", "photo.jpg", 100, "aaa")
    results = find_file(conn, "missing.jpg")
    assert results == []


def test_print_find_results_output(conn, capsys):
    _insert(conn, "/a/photo.jpg", "/a", "photo.jpg", 1000, "aaa")
    _insert(conn, "/b/photo.jpg", "/b", "photo.jpg", 1000, "aaa")

    print_find_results(conn, "photo.jpg")
    out = capsys.readouterr().out
    assert "/a/photo.jpg" in out
    assert "/b/photo.jpg" in out
    assert "Found: 2" in out


def test_print_find_results_empty(conn, capsys):
    print_find_results(conn, "missing.jpg")
    out = capsys.readouterr().out
    assert "No files found" in out

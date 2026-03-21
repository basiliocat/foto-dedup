"""Tests for fotodedup.cleanup module."""

import os

import pytest

from fotodedup import db
from fotodedup.cleanup import (
    ensure_deleted_at_column,
    find_cross_dir_dupes,
    build_dir_pairs,
    get_dir_stats,
    get_parent_dir_stats,
    print_pair_report,
    delete_files,
    interactive_cleanup,
    report,
)


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


# --- Schema migration ---

def test_ensure_deleted_at_column():
    c = db.get_connection(":memory:")
    db.init_db(c)
    cols = {row[1] for row in c.execute("PRAGMA table_info(files)").fetchall()}
    assert "deleted_at" not in cols

    ensure_deleted_at_column(c)
    cols = {row[1] for row in c.execute("PRAGMA table_info(files)").fetchall()}
    assert "deleted_at" in cols
    c.close()


def test_ensure_deleted_at_column_idempotent():
    c = db.get_connection(":memory:")
    db.init_db(c)
    ensure_deleted_at_column(c)
    ensure_deleted_at_column(c)  # should not raise
    cols = {row[1] for row in c.execute("PRAGMA table_info(files)").fetchall()}
    assert "deleted_at" in cols
    c.close()


# --- find_cross_dir_dupes ---

def test_find_dupes_all_criteria(conn):
    """Same filename, size, md5 in different dirs."""
    _insert(conn, "/a/photo.jpg", "/a", "photo.jpg", 1000, "abc123")
    _insert(conn, "/b/photo.jpg", "/b", "photo.jpg", 1000, "abc123")
    _insert(conn, "/c/unique.jpg", "/c", "unique.jpg", 500, "other")

    groups = find_cross_dir_dupes(conn)
    assert len(groups) == 1
    key, files = groups[0]
    assert key == {"filename": "photo.jpg", "size": 1000, "md5": "abc123"}
    assert len(files) == 2


def test_find_dupes_name_only(conn):
    """Same filename but different size/md5 — match by name only."""
    _insert(conn, "/a/photo.jpg", "/a", "photo.jpg", 1000, "aaa")
    _insert(conn, "/b/photo.jpg", "/b", "photo.jpg", 2000, "bbb")

    groups = find_cross_dir_dupes(conn, by_name=True, by_size=False, by_md5=False)
    assert len(groups) == 1
    key, files = groups[0]
    assert key == {"filename": "photo.jpg"}
    assert len(files) == 2


def test_find_dupes_size_only(conn):
    """Same size but different name/md5 — match by size only."""
    _insert(conn, "/a/photo.jpg", "/a", "photo.jpg", 1000, "aaa")
    _insert(conn, "/b/image.png", "/b", "image.png", 1000, "bbb")

    groups = find_cross_dir_dupes(conn, by_name=False, by_size=True, by_md5=False)
    assert len(groups) == 1
    assert len(groups[0][1]) == 2


def test_find_dupes_same_dir_excluded(conn):
    """Files in the same directory are not cross-dir duplicates."""
    _insert(conn, "/a/photo1.jpg", "/a", "photo.jpg", 1000, "abc")
    _insert(conn, "/a/photo2.jpg", "/a", "photo.jpg", 1000, "abc")

    groups = find_cross_dir_dupes(conn)
    assert len(groups) == 0


def test_find_dupes_excludes_deleted(conn):
    """Deleted files should not appear in results."""
    _insert(conn, "/a/photo.jpg", "/a", "photo.jpg", 1000, "abc")
    _insert(conn, "/b/photo.jpg", "/b", "photo.jpg", 1000, "abc")
    conn.execute("UPDATE files SET deleted_at = CURRENT_TIMESTAMP WHERE path = '/b/photo.jpg'")
    conn.commit()

    groups = find_cross_dir_dupes(conn)
    assert len(groups) == 0


def test_find_dupes_empty_db(conn):
    groups = find_cross_dir_dupes(conn)
    assert groups == []


def test_find_dupes_no_criteria(conn):
    groups = find_cross_dir_dupes(conn, by_name=False, by_size=False, by_md5=False)
    assert groups == []


def test_find_dupes_sorted_by_size(conn):
    """Larger groups should come first."""
    _insert(conn, "/a/small.jpg", "/a", "small.jpg", 100, "sm")
    _insert(conn, "/b/small.jpg", "/b", "small.jpg", 100, "sm")
    _insert(conn, "/a/big.jpg", "/a", "big.jpg", 9999, "bg")
    _insert(conn, "/b/big.jpg", "/b", "big.jpg", 9999, "bg")

    groups = find_cross_dir_dupes(conn)
    assert groups[0][0]["size"] == 9999
    assert groups[1][0]["size"] == 100


# --- build_dir_pairs ---

def test_build_dir_pairs_two_dirs(conn):
    _insert(conn, "/a/f.jpg", "/a", "f.jpg", 1000, "x")
    _insert(conn, "/b/f.jpg", "/b", "f.jpg", 1000, "x")

    groups = find_cross_dir_dupes(conn)
    pairs = build_dir_pairs(groups)
    assert len(pairs) == 1
    (da, db_), entries = pairs[0]
    assert da == "/a"
    assert db_ == "/b"
    assert len(entries) == 1


def test_build_dir_pairs_three_dirs(conn):
    """A group spanning 3 dirs produces 3 pairs."""
    _insert(conn, "/a/f.jpg", "/a", "f.jpg", 1000, "x")
    _insert(conn, "/b/f.jpg", "/b", "f.jpg", 1000, "x")
    _insert(conn, "/c/f.jpg", "/c", "f.jpg", 1000, "x")

    groups = find_cross_dir_dupes(conn)
    pairs = build_dir_pairs(groups)
    assert len(pairs) == 3  # (a,b), (a,c), (b,c)


def test_build_dir_pairs_sorted_by_size(conn):
    _insert(conn, "/a/small.jpg", "/a", "small.jpg", 100, "sm")
    _insert(conn, "/b/small.jpg", "/b", "small.jpg", 100, "sm")
    _insert(conn, "/c/big.jpg", "/c", "big.jpg", 9999, "bg")
    _insert(conn, "/d/big.jpg", "/d", "big.jpg", 9999, "bg")

    groups = find_cross_dir_dupes(conn)
    pairs = build_dir_pairs(groups)
    (da, _), _ = pairs[0]
    assert da == "/c"  # bigger pair first


# --- get_dir_stats ---

def test_get_dir_stats(conn):
    _insert(conn, "/a/1.jpg", "/a", "1.jpg", 1000, "x")
    _insert(conn, "/a/2.jpg", "/a", "2.jpg", 2000, "y")
    _insert(conn, "/b/1.jpg", "/b", "1.jpg", 500, "z")

    cnt, size = get_dir_stats(conn, "/a")
    assert cnt == 2
    assert size == 3000


def test_get_dir_stats_excludes_deleted(conn):
    _insert(conn, "/a/1.jpg", "/a", "1.jpg", 1000, "x")
    _insert(conn, "/a/2.jpg", "/a", "2.jpg", 2000, "y")
    conn.execute("UPDATE files SET deleted_at = CURRENT_TIMESTAMP WHERE path = '/a/2.jpg'")
    conn.commit()

    cnt, size = get_dir_stats(conn, "/a")
    assert cnt == 1
    assert size == 1000


def test_get_dir_stats_empty(conn):
    cnt, size = get_dir_stats(conn, "/nonexistent")
    assert cnt == 0
    assert size == 0


# --- get_parent_dir_stats ---

def test_get_parent_dir_stats(conn):
    _insert(conn, "/root/sub1/a.jpg", "/root/sub1", "a.jpg", 1000, "x")
    _insert(conn, "/root/sub2/b.jpg", "/root/sub2", "b.jpg", 2000, "y")

    parent, cnt, size = get_parent_dir_stats(conn, "/root/sub1")
    assert parent == "/root"
    assert cnt == 2
    assert size == 3000


# --- print_pair_report ---

def test_print_pair_report(conn, capsys):
    _insert(conn, "/a/f.jpg", "/a", "f.jpg", 1000, "x")
    _insert(conn, "/b/f.jpg", "/b", "f.jpg", 1000, "x")

    groups = find_cross_dir_dupes(conn)
    pairs = build_dir_pairs(groups)
    (da, db_), entries = pairs[0]

    print_pair_report(conn, da, db_, entries)
    out = capsys.readouterr().out

    assert "/a" in out
    assert "/b" in out
    assert "Dir A:" in out
    assert "Dir B:" in out
    assert "Duplicates:" in out
    assert "Files:" in out
    assert "Parent" in out


# --- report ---

def test_report_no_dupes(conn, capsys):
    report(conn, [])
    out = capsys.readouterr().out
    assert "No cross-directory duplicates" in out


def test_report_with_dupes(conn, capsys):
    _insert(conn, "/a/f.jpg", "/a", "f.jpg", 1000, "x")
    _insert(conn, "/b/f.jpg", "/b", "f.jpg", 1000, "x")

    groups = find_cross_dir_dupes(conn)
    pairs = build_dir_pairs(groups)
    report(conn, pairs)
    out = capsys.readouterr().out

    assert "Total:" in out
    assert "directory pairs" in out


# --- delete_files ---

def test_delete_files(conn, tmp_path):
    # Create real files
    f1 = tmp_path / "a.jpg"
    f1.write_bytes(b"x" * 1000)
    path_str = str(f1)

    _insert(conn, path_str, str(tmp_path), "a.jpg", 1000, "x")
    rows = conn.execute("SELECT id, path, dir, filename, size, md5 FROM files").fetchall()

    deleted, errors = delete_files(conn, rows)
    assert deleted == 1
    assert errors == 0
    assert not f1.exists()

    # Check DB marking
    row = conn.execute("SELECT deleted_at FROM files WHERE path = ?", (path_str,)).fetchone()
    assert row["deleted_at"] is not None


def test_delete_files_missing_file(conn):
    _insert(conn, "/nonexistent/file.jpg", "/nonexistent", "file.jpg", 100, "x")
    rows = conn.execute("SELECT id, path, dir, filename, size, md5 FROM files").fetchall()

    deleted, errors = delete_files(conn, rows)
    assert errors == 1
    assert deleted == 0

    # Still marked in DB
    row = conn.execute("SELECT deleted_at FROM files WHERE path = '/nonexistent/file.jpg'").fetchone()
    assert row["deleted_at"] is not None


# --- interactive_cleanup ---

def test_interactive_skip(conn, monkeypatch, capsys):
    _insert(conn, "/a/f.jpg", "/a", "f.jpg", 1000, "x")
    _insert(conn, "/b/f.jpg", "/b", "f.jpg", 1000, "x")

    groups = find_cross_dir_dupes(conn)
    pairs = build_dir_pairs(groups)

    monkeypatch.setattr("builtins.input", lambda _: "s")
    monkeypatch.setattr("sys.stdin", type("FakeTTY", (), {"isatty": lambda self: True})())

    total_deleted, total_errors = interactive_cleanup(conn, pairs)
    assert total_deleted == 0


def test_interactive_delete_a(conn, monkeypatch, tmp_path, capsys):
    fa = tmp_path / "a" / "f.jpg"
    fb = tmp_path / "b" / "f.jpg"
    fa.parent.mkdir()
    fb.parent.mkdir()
    fa.write_bytes(b"x" * 1000)
    fb.write_bytes(b"x" * 1000)

    _insert(conn, str(fa), str(fa.parent), "f.jpg", 1000, "x")
    _insert(conn, str(fb), str(fb.parent), "f.jpg", 1000, "x")

    groups = find_cross_dir_dupes(conn)
    pairs = build_dir_pairs(groups)

    monkeypatch.setattr("builtins.input", lambda _: "a")
    monkeypatch.setattr("sys.stdin", type("FakeTTY", (), {"isatty": lambda self: True})())

    total_deleted, _ = interactive_cleanup(conn, pairs)
    assert total_deleted == 1
    assert not fa.exists()
    assert fb.exists()


def test_interactive_quit(conn, monkeypatch, capsys):
    _insert(conn, "/a/f1.jpg", "/a", "f1.jpg", 1000, "x")
    _insert(conn, "/b/f1.jpg", "/b", "f1.jpg", 1000, "x")
    _insert(conn, "/c/f2.jpg", "/c", "f2.jpg", 2000, "y")
    _insert(conn, "/d/f2.jpg", "/d", "f2.jpg", 2000, "y")

    groups = find_cross_dir_dupes(conn)
    pairs = build_dir_pairs(groups)

    monkeypatch.setattr("builtins.input", lambda _: "q")
    monkeypatch.setattr("sys.stdin", type("FakeTTY", (), {"isatty": lambda self: True})())

    total_deleted, _ = interactive_cleanup(conn, pairs)
    assert total_deleted == 0


# --- CLI ---

def test_main_no_criteria(monkeypatch):
    monkeypatch.setattr("sys.argv", ["cleanup", "--no-name", "--no-size", "--no-md5"])
    with pytest.raises(SystemExit) as exc_info:
        from fotodedup.cleanup import main
        main()
    assert exc_info.value.code == 2

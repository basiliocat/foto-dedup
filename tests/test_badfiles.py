"""Tests for fotodedup.badfiles — finding good analogues of corrupted files."""

import os
import tempfile

import pytest

from fotodedup import badfiles
from fotodedup.badfiles import FileInfo, collect_files, match_files, print_matches


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def dirs():
    """Create good/ and bad/ temp directories with test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        good = os.path.join(tmpdir, "good")
        bad = os.path.join(tmpdir, "bad")
        os.makedirs(good)
        os.makedirs(bad)
        yield good, bad


def _mkfile(directory, name, content=b"data", subdir=None):
    """Create a file, optionally in a subdirectory. Returns full path."""
    if subdir:
        directory = os.path.join(directory, subdir)
        os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, name)
    with open(path, "wb") as f:
        f.write(content)
    return path


# ── collect_files ─────────────────────────────────────────────────────


def test_collect_files_basic(dirs):
    good, _ = dirs
    _mkfile(good, "a.txt", b"hello")
    _mkfile(good, "b.txt", b"world!")

    files = collect_files(good)
    assert len(files) == 2
    names = {f.filename for f in files}
    assert names == {"a.txt", "b.txt"}
    for f in files:
        assert isinstance(f, FileInfo)
        assert f.size > 0
        assert f.mtime > 0


def test_collect_files_recursive(dirs):
    good, _ = dirs
    _mkfile(good, "top.txt", b"x")
    _mkfile(good, "deep.txt", b"y", subdir="sub")

    files = collect_files(good)
    assert len(files) == 2

    deep = [f for f in files if f.filename == "deep.txt"][0]
    assert deep.parent_dir == "sub"

    top = [f for f in files if f.filename == "top.txt"][0]
    assert top.parent_dir == os.path.basename(good)


def test_collect_files_skips_symlinks(dirs):
    good, _ = dirs
    real = _mkfile(good, "real.txt", b"content")
    link = os.path.join(good, "link.txt")
    os.symlink(real, link)

    files = collect_files(good)
    assert len(files) == 1
    assert files[0].filename == "real.txt"


def test_collect_files_empty_dir(dirs):
    good, _ = dirs
    assert collect_files(good) == []


# ── match_files ───────────────────────────────────────────────────────


def test_match_by_size():
    bad = [FileInfo("/bad/a.txt", "a.txt", "bad", 100, 1.0)]
    good = [
        FileInfo("/good/b.txt", "b.txt", "good", 100, 2.0),
        FileInfo("/good/c.txt", "c.txt", "good", 200, 3.0),
    ]
    results = match_files(bad, good, by_size=True)
    assert len(results) == 1
    _, candidates = results[0]
    assert len(candidates) == 1
    assert candidates[0].filename == "b.txt"


def test_match_by_name():
    bad = [FileInfo("/bad/photo.jpg", "photo.jpg", "bad", 100, 1.0)]
    good = [
        FileInfo("/good/photo.jpg", "photo.jpg", "good", 200, 2.0),
        FileInfo("/good/other.jpg", "other.jpg", "good", 100, 1.0),
    ]
    results = match_files(bad, good, by_name=True)
    _, candidates = results[0]
    assert len(candidates) == 1
    assert candidates[0].path == "/good/photo.jpg"


def test_match_by_name_date():
    bad = [FileInfo("/bad/img.jpg", "img.jpg", "bad", 100, 1000.0)]
    good = [
        FileInfo("/good/img.jpg", "img.jpg", "good", 200, 1000.0),  # same name+mtime
        FileInfo("/good/img.jpg", "img.jpg", "x", 200, 9999.0),     # same name, diff mtime
    ]
    results = match_files(bad, good, by_name_date=True)
    _, candidates = results[0]
    assert len(candidates) == 1
    assert candidates[0].mtime == 1000.0


def test_match_same_dir_filter():
    bad = [FileInfo("/bad/photos/a.jpg", "a.jpg", "photos", 100, 1.0)]
    good = [
        FileInfo("/good/photos/a.jpg", "a.jpg", "photos", 100, 1.0),
        FileInfo("/good/other/a.jpg", "a.jpg", "other", 100, 1.0),
    ]
    results = match_files(bad, good, by_name=True, same_dir=True)
    _, candidates = results[0]
    assert len(candidates) == 1
    assert candidates[0].parent_dir == "photos"


def test_match_combined_name_and_size():
    bad = [FileInfo("/bad/f.txt", "f.txt", "bad", 100, 1.0)]
    good = [
        FileInfo("/good/f.txt", "f.txt", "good", 100, 2.0),  # same name+size
        FileInfo("/good/f.txt", "f.txt", "good", 999, 3.0),  # same name, diff size
    ]
    results = match_files(bad, good, by_name=True, by_size=True)
    _, candidates = results[0]
    assert len(candidates) == 1
    assert candidates[0].size == 100


def test_match_no_candidates():
    bad = [FileInfo("/bad/unique.dat", "unique.dat", "bad", 42, 1.0)]
    good = [FileInfo("/good/other.dat", "other.dat", "good", 99, 2.0)]
    results = match_files(bad, good, by_name=True)
    _, candidates = results[0]
    assert candidates == []


def test_match_multiple_candidates():
    bad = [FileInfo("/bad/photo.jpg", "photo.jpg", "bad", 100, 1.0)]
    good = [
        FileInfo("/good/a/photo.jpg", "photo.jpg", "a", 100, 2.0),
        FileInfo("/good/b/photo.jpg", "photo.jpg", "b", 100, 3.0),
    ]
    results = match_files(bad, good, by_name=True)
    _, candidates = results[0]
    assert len(candidates) == 2


# ── print_matches ─────────────────────────────────────────────────────


def test_print_matches_output(capsys):
    matches = [
        (FileInfo("/bad/a.jpg", "a.jpg", "bad", 1024, 1.0),
         [FileInfo("/good/a.jpg", "a.jpg", "good", 1024, 1.0)]),
    ]
    print_matches(matches)
    out = capsys.readouterr().out
    assert "BAD: /bad/a.jpg" in out
    assert "-> /good/a.jpg" in out
    assert "1 matched" in out
    assert "0 unmatched" in out


def test_print_matches_no_match(capsys):
    matches = [
        (FileInfo("/bad/x.dat", "x.dat", "bad", 500, 1.0), []),
    ]
    print_matches(matches)
    out = capsys.readouterr().out
    assert "(no match)" in out
    assert "0 matched" in out
    assert "1 unmatched" in out


# ── CLI main ──────────────────────────────────────────────────────────


def test_main_no_strategy_flag(dirs):
    good, bad = dirs
    _mkfile(bad, "f.txt")
    _mkfile(good, "f.txt")

    import sys
    old_argv = sys.argv
    sys.argv = ["matcher", bad, good]
    try:
        with pytest.raises(SystemExit) as exc_info:
            badfiles.main()
        assert exc_info.value.code != 0
    finally:
        sys.argv = old_argv


def test_main_runs_successfully(dirs, capsys):
    good, bad = dirs
    _mkfile(bad, "f.txt", b"corrupted")
    _mkfile(good, "f.txt", b"good_data")

    import sys
    old_argv = sys.argv
    sys.argv = ["matcher", bad, good, "--by-name"]
    try:
        badfiles.main()
    finally:
        sys.argv = old_argv

    out = capsys.readouterr().out
    assert "f.txt" in out
    assert "1 matched" in out

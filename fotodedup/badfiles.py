"""Badfiles — finds good analogues of corrupted files by filesystem metadata."""

import argparse
import os
import sys
from collections import defaultdict, namedtuple
from pathlib import Path

from .utils import DEFAULT_EXTENSIONS, format_size, matches_extension, parse_extensions

FileInfo = namedtuple("FileInfo", ["path", "filename", "parent_dir", "size", "mtime"])


def collect_files(directory, extensions=None):
    """Walk directory recursively, return list of FileInfo for regular files."""
    result = []
    for dirpath, _dirnames, filenames in os.walk(directory, followlinks=False):
        for fname in filenames:
            fpath = Path(dirpath) / fname
            if fpath.is_symlink():
                continue
            if not matches_extension(fname, extensions):
                continue
            try:
                st = fpath.stat()
            except (PermissionError, OSError) as e:
                print(f"Warning: {e}", file=sys.stderr)
                continue
            result.append(FileInfo(
                path=str(fpath.resolve()),
                filename=fname,
                parent_dir=Path(dirpath).name,
                size=st.st_size,
                mtime=st.st_mtime,
            ))
    return result


def match_files(bad_files, good_files, by_size=False, by_name=False,
                by_name_date=False, same_dir=False):
    """For each bad file, find matching good file candidates.

    Returns list of (bad_file, [good_candidates]) tuples.
    """
    # Build indexes for efficient lookup
    by_name_index = defaultdict(list)
    by_size_index = defaultdict(list)
    for gf in good_files:
        by_name_index[gf.filename].append(gf)
        by_size_index[gf.size].append(gf)

    results = []
    for bf in sorted(bad_files, key=lambda f: f.path):
        # Start with all good files, narrow by primary key
        if by_name or by_name_date:
            candidates = list(by_name_index.get(bf.filename, []))
        elif by_size:
            candidates = list(by_size_index.get(bf.size, []))
        else:
            candidates = []

        # Apply additional filters
        if by_size and (by_name or by_name_date):
            candidates = [c for c in candidates if c.size == bf.size]

        if by_name_date:
            candidates = [c for c in candidates if c.mtime == bf.mtime]

        if same_dir:
            candidates = [c for c in candidates if c.parent_dir == bf.parent_dir]

        results.append((bf, candidates))

    return results


def print_matches(matches):
    """Print match results to stdout with summary."""
    matched = 0
    for bf, candidates in matches:
        print(f"BAD: {bf.path} ({format_size(bf.size)})")
        if candidates:
            matched += 1
            for gf in candidates:
                print(f"  -> {gf.path} ({format_size(gf.size)})")
        else:
            print("  (no match)")
        print()

    total = len(matches)
    unmatched = total - matched
    print(f"Total: {total} bad files, {matched} matched, {unmatched} unmatched")


def main():
    parser = argparse.ArgumentParser(
        description="Find good analogues of corrupted files by filesystem metadata."
    )
    parser.add_argument("bad_dir", help="Directory with corrupted files")
    parser.add_argument("good_dir", help="Directory with intact files")
    parser.add_argument("--by-size", action="store_true",
                        help="Match by file size")
    parser.add_argument("--by-name", action="store_true",
                        help="Match by filename")
    parser.add_argument("--by-name-date", action="store_true",
                        help="Match by filename and modification date")
    parser.add_argument("--same-dir", action="store_true",
                        help="Additionally require same parent directory name")
    parser.add_argument(
        "--ext",
        default=DEFAULT_EXTENSIONS,
        help="Comma-separated file extensions to include (default: %(default)s). Use '*' for all files.",
    )

    args = parser.parse_args()

    if not (args.by_size or args.by_name or args.by_name_date):
        parser.error("At least one of --by-size, --by-name, --by-name-date is required")

    bad_dir = Path(args.bad_dir)
    good_dir = Path(args.good_dir)

    for d, label in [(bad_dir, "Bad"), (good_dir, "Good")]:
        if not d.is_dir():
            parser.error(f"{label} directory does not exist: {d}")

    extensions = parse_extensions(args.ext)

    print(f"Collecting files from bad dir: {bad_dir}", file=sys.stderr)
    bad_files = collect_files(str(bad_dir), extensions=extensions)
    print(f"Collecting files from good dir: {good_dir}", file=sys.stderr)
    good_files = collect_files(str(good_dir), extensions=extensions)

    print(f"Bad: {len(bad_files)} files, Good: {len(good_files)} files\n",
          file=sys.stderr)

    matches = match_files(
        bad_files, good_files,
        by_size=args.by_size,
        by_name=args.by_name,
        by_name_date=args.by_name_date,
        same_dir=args.same_dir,
    )

    print_matches(matches)


if __name__ == "__main__":
    main()

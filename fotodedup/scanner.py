"""File scanner — walks directories, computes MD5, writes to SQLite."""

import argparse
import hashlib
import os
import sys
import uuid
from pathlib import Path

from . import db


def compute_md5(filepath, block_size=1024 * 1024):
    """Compute MD5 hash of a file, reading in 1 MB blocks."""
    h = hashlib.md5()
    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(block_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def file_already_scanned(conn, path, size):
    """Check if a file with the same path and size is already in the DB."""
    row = conn.execute(
        "SELECT 1 FROM files WHERE path = ? AND size = ?", (str(path), size)
    ).fetchone()
    return row is not None


def scan_paths(paths, conn, min_size=10240, scan_id=None, extensions=None):
    """Scan given paths recursively and insert files into the database.

    Returns (scanned_count, skipped_count, error_count).
    """
    if scan_id is None:
        scan_id = uuid.uuid4().hex[:12]

    scanned = 0
    skipped = 0
    errors = 0

    for root_path in paths:
        root_path = Path(root_path).resolve()
        if not root_path.exists():
            print(f"WARNING: path does not exist: {root_path}", file=sys.stderr)
            continue

        if root_path.is_file():
            entries = [(str(root_path.parent), [], [root_path.name])]
        else:
            entries = os.walk(root_path, followlinks=False)

        for dirpath, _dirs, filenames in entries:
            for fname in filenames:
                fpath = Path(dirpath) / fname
                try:
                    if fpath.is_symlink():
                        continue
                    if not db.matches_extension(fname, extensions):
                        skipped += 1
                        continue
                    stat = fpath.stat()
                    if stat.st_size < min_size:
                        skipped += 1
                        continue

                    abs_path = str(fpath.resolve())
                    if file_already_scanned(conn, abs_path, stat.st_size):
                        skipped += 1
                        continue

                    md5 = compute_md5(fpath)
                    db.insert_file(
                        conn,
                        path=abs_path,
                        dir_=str(fpath.resolve().parent),
                        filename=fname,
                        size=stat.st_size,
                        md5=md5,
                        scan_id=scan_id,
                    )
                    scanned += 1

                    if scanned % 100 == 0:
                        conn.commit()
                        print(f"\r  scanned: {scanned}", end="", file=sys.stderr)

                except (PermissionError, OSError) as e:
                    print(f"\nERROR: {fpath}: {e}", file=sys.stderr)
                    errors += 1

    conn.commit()
    print(f"\r  scanned: {scanned}, skipped: {skipped}, errors: {errors}", file=sys.stderr)
    print(file=sys.stderr)
    return scanned, skipped, errors


def main():
    parser = argparse.ArgumentParser(
        description="Scan directories and record file metadata + MD5 in SQLite."
    )
    parser.add_argument("paths", nargs="+", help="Directories or files to scan")
    parser.add_argument("--db", default="files.db", help="SQLite database path (default: files.db)")
    parser.add_argument(
        "--min-size",
        type=int,
        default=10240,
        help="Minimum file size in bytes (default: 10240 = 10KB)",
    )
    parser.add_argument(
        "--ext",
        default=db.DEFAULT_EXTENSIONS,
        help="Comma-separated file extensions to include (default: %(default)s). Use '*' for all files.",
    )
    args = parser.parse_args()

    extensions = db.parse_extensions(args.ext)

    conn = db.get_connection(args.db)
    db.init_db(conn)

    scan_id = uuid.uuid4().hex[:12]
    print(f"Scan ID: {scan_id}", file=sys.stderr)
    print(f"Database: {args.db}", file=sys.stderr)
    print(f"Min size: {args.min_size} bytes", file=sys.stderr)
    print(f"Extensions: {args.ext}", file=sys.stderr)
    print(f"Paths: {args.paths}", file=sys.stderr)
    print(file=sys.stderr)

    scanned, skipped, errors = scan_paths(
        args.paths, conn, min_size=args.min_size, scan_id=scan_id,
        extensions=extensions,
    )

    conn.close()
    print(f"Done. Scanned: {scanned}, Skipped: {skipped}, Errors: {errors}", file=sys.stderr)


if __name__ == "__main__":
    main()

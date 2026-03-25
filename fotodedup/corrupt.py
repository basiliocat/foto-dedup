"""Corruption detector — finds files with same name+size but different MD5."""

import argparse
import sys

from . import db
from .utils import format_size


def _ext_filter_sql(extensions):
    """Build SQL WHERE clause fragment for extension filtering.

    Returns (sql_fragment, params) tuple.
    """
    if extensions is None:
        return "", []
    conditions = []
    params = []
    for ext in extensions:
        conditions.append("LOWER(filename) LIKE ?")
        params.append("%" + ext)
    return "AND (" + " OR ".join(conditions) + ") ", params


def find_corrupt_candidates(conn, extensions=None):
    """Find groups of files with same filename+size but different md5.

    Returns list of (filename, size, [file_rows]) sorted by size descending.
    Each group contains files that *should* be identical but have divergent hashes.
    """
    ext_sql, ext_params = _ext_filter_sql(extensions)
    cursor = conn.execute(
        "SELECT filename, size, COUNT(*) as cnt, COUNT(DISTINCT md5) as md5_cnt "
        "FROM files "
        "WHERE deleted_at IS NULL " + ext_sql +
        "GROUP BY filename, size "
        "HAVING cnt > 1 AND md5_cnt > 1 "
        "ORDER BY size DESC",
        ext_params,
    )

    groups = []
    for row in cursor:
        files = conn.execute(
            "SELECT path, dir, filename, size, md5, scan_id FROM files "
            "WHERE filename = ? AND size = ? AND deleted_at IS NULL "
            "ORDER BY md5, path",
            (row["filename"], row["size"]),
        ).fetchall()
        groups.append((row["filename"], row["size"], files))
    return groups


def print_corrupt(conn, extensions=None):
    """Print corruption report to stdout."""
    groups = find_corrupt_candidates(conn, extensions=extensions)
    if not groups:
        print("No corruption candidates found.")
        return

    total_files = 0
    for i, (filename, size, files) in enumerate(groups, 1):
        md5s = sorted({f["md5"] for f in files})
        total_files += len(files)
        print(f"--- {i}/{len(groups)}: {filename} ({format_size(size)}), "
              f"{len(files)} copies, {len(md5s)} different hashes ---")
        for f in files:
            print(f"  [{f['md5'][:8]}] {f['path']}")
        print()

    print(f"Total: {len(groups)} groups, {total_files} files with potential corruption")


def ensure_deleted_at_column(conn):
    """Add deleted_at column to files table if missing."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(files)").fetchall()}
    if "deleted_at" not in cols:
        conn.execute("ALTER TABLE files ADD COLUMN deleted_at TIMESTAMP DEFAULT NULL")
        conn.commit()


def main():
    parser = argparse.ArgumentParser(
        description="Find files with same name and size but different MD5 (potential corruption)."
    )
    parser.add_argument("--db", default="files.db", help="SQLite database path (default: files.db)")
    parser.add_argument(
        "--ext",
        default=db.DEFAULT_EXTENSIONS,
        help="Comma-separated file extensions to include (default: %(default)s). Use '*' for all files.",
    )

    args = parser.parse_args()

    extensions = db.parse_extensions(args.ext)

    conn = db.get_connection(args.db)
    db.init_db(conn)
    ensure_deleted_at_column(conn)

    print_corrupt(conn, extensions=extensions)

    conn.close()


if __name__ == "__main__":
    main()

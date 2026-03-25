"""Duplicate finder — queries SQLite database for duplicate and overlapping files."""

import argparse
import sys

from . import db
from .utils import DEFAULT_EXTENSIONS, format_size, parse_extensions  # noqa: F401 — re-exported for backward compat


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


def find_dupes(conn, ext=None, min_size=0):
    """Find groups of files with the same md5+size.

    Args:
        conn: SQLite connection.
        ext: Set of lowercase extensions (e.g. {'.jpg', '.mp4'}) or None for all files.
        min_size: Minimum file size in bytes (default 0).

    Returns list of (md5, size, [rows]) sorted by size descending.
    """
    ext_sql, ext_params = _ext_filter_sql(ext)
    params = [min_size] + ext_params

    cursor = conn.execute(
        "SELECT md5, size, COUNT(*) as cnt "
        "FROM files "
        "WHERE size >= ? " + ext_sql +
        "GROUP BY md5, size "
        "HAVING cnt > 1 "
        "ORDER BY size DESC",
        params,
    )
    groups = []
    for row in cursor:
        files = conn.execute(
            "SELECT path, dir, filename, size, md5, scan_id FROM files WHERE md5 = ? AND size = ?",
            (row["md5"], row["size"]),
        ).fetchall()
        groups.append((row["md5"], row["size"], files))
    return groups


def print_dupes(conn, ext=None, min_size=0):
    """Print duplicate groups to stdout."""
    groups = find_dupes(conn, ext=ext, min_size=min_size)
    if not groups:
        print("No duplicates found.")
        return

    total_waste = 0
    total_groups = len(groups)

    for i, (md5, size, files) in enumerate(groups, 1):
        waste = size * (len(files) - 1)
        total_waste += waste
        print(f"--- Group {i}/{total_groups}: {format_size(size)} x {len(files)} copies, "
              f"waste: {format_size(waste)} [md5: {md5}]")
        for f in files:
            print(f"  {f['path']}")
        print()

    print(f"Total: {total_groups} duplicate groups, wasted space: {format_size(total_waste)}")


def compare_dirs(conn, dir_a, dir_b, ext=None, min_size=0):
    """Compare two directories by their file contents (md5+size)."""
    ext_sql, ext_params = _ext_filter_sql(ext)

    def get_dir_files(dir_path):
        params = [dir_path.rstrip("/") + "/%", dir_path.rstrip("/"), min_size] + ext_params
        return conn.execute(
            "SELECT path, md5, size FROM files "
            "WHERE (dir LIKE ? OR dir = ?) AND size >= ? " + ext_sql,
            params,
        ).fetchall()

    files_a = get_dir_files(dir_a)
    files_b = get_dir_files(dir_b)

    if not files_a:
        print(f"No files found in DB for: {dir_a}", file=sys.stderr)
        return
    if not files_b:
        print(f"No files found in DB for: {dir_b}", file=sys.stderr)
        return

    set_a = {(r["md5"], r["size"]) for r in files_a}
    set_b = {(r["md5"], r["size"]) for r in files_b}
    common = set_a & set_b
    only_a = set_a - set_b
    only_b = set_b - set_a

    size_a = sum(r["size"] for r in files_a)
    size_b = sum(r["size"] for r in files_b)

    # Size of duplicate content (sum of sizes of common md5+size pairs)
    common_size = sum(s for _, s in common)

    print(f"Directory A: {dir_a}")
    print(f"  Files: {len(files_a)}, Total size: {format_size(size_a)}")
    print(f"  Unique content keys (md5+size): {len(set_a)}")
    print()
    print(f"Directory B: {dir_b}")
    print(f"  Files: {len(files_b)}, Total size: {format_size(size_b)}")
    print(f"  Unique content keys (md5+size): {len(set_b)}")
    print()
    print(f"Common (same md5+size): {len(common)} files, {format_size(common_size)}")
    print(f"Only in A: {len(only_a)}")
    print(f"Only in B: {len(only_b)}")

    if set_a:
        pct = len(common) / len(set_a) * 100
        print(f"\nOverlap: {pct:.1f}% of A is in B")
    if set_b:
        pct = len(common) / len(set_b) * 100
        print(f"Overlap: {pct:.1f}% of B is in A")


def find_file(conn, name, size=None):
    """Find files in the database matching by filename and optionally size.

    Args:
        conn: SQLite connection.
        name: Filename to search (supports SQL LIKE patterns with %).
        size: Exact file size in bytes, or None to skip size filter.

    Returns list of rows sorted by path.
    """
    has_wildcard = "%" in name or "_" in name
    if has_wildcard:
        where = "WHERE filename LIKE ?"
    else:
        where = "WHERE filename = ?"
    params = [name]

    if size is not None:
        where += " AND size = ?"
        params.append(size)

    return conn.execute(
        "SELECT path, dir, filename, size, md5, scan_id FROM files "
        + where + " ORDER BY path",
        params,
    ).fetchall()


def print_find_results(conn, name, size=None):
    """Print file search results to stdout."""
    results = find_file(conn, name, size=size)
    if not results:
        print("No files found.")
        return

    for f in results:
        print(f"  {f['path']}  ({format_size(f['size'])})  [md5: {f['md5']}]")

    print(f"\nFound: {len(results)} file(s)")


def main():
    parser = argparse.ArgumentParser(
        description="Find duplicate files and compare directories using SQLite database."
    )
    parser.add_argument("--db", default="files.db", help="SQLite database path (default: files.db)")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    p_dupes = subparsers.add_parser("dupes", help="Show groups of duplicate files")
    p_dupes.add_argument(
        "--ext",
        default=DEFAULT_EXTENSIONS,
        help=(
            "Comma-separated file extensions to include "
            f"(default: {DEFAULT_EXTENSIONS}). Use '*' for all files."
        ),
    )
    p_dupes.add_argument("--min-size", type=int, default=0, help="Minimum file size in bytes (default: 0)")

    p_cmp = subparsers.add_parser("compare", help="Compare two directories")
    p_cmp.add_argument("dir_a", help="First directory path")
    p_cmp.add_argument("dir_b", help="Second directory path")
    p_cmp.add_argument(
        "--ext",
        default=DEFAULT_EXTENSIONS,
        help=(
            "Comma-separated file extensions to include "
            f"(default: {DEFAULT_EXTENSIONS}). Use '*' for all files."
        ),
    )
    p_cmp.add_argument("--min-size", type=int, default=0, help="Minimum file size in bytes (default: 0)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    conn = db.get_connection(args.db)
    db.init_db(conn)

    if args.command == "dupes":
        print_dupes(conn, ext=parse_extensions(args.ext), min_size=args.min_size)
    elif args.command == "compare":
        compare_dirs(conn, args.dir_a, args.dir_b, ext=parse_extensions(args.ext), min_size=args.min_size)

    conn.close()


if __name__ == "__main__":
    main()

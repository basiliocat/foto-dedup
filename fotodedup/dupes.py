"""Duplicate finder — queries SQLite database for duplicate and overlapping files."""

import argparse
import sys

from . import db


def format_size(size_bytes):
    """Format bytes as human-readable string."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size_bytes) < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


def find_dupes(conn):
    """Find groups of files with the same md5+size.

    Returns list of (md5, size, [rows]) sorted by size descending.
    """
    cursor = conn.execute(
        """SELECT md5, size, COUNT(*) as cnt
           FROM files
           GROUP BY md5, size
           HAVING cnt > 1
           ORDER BY size DESC"""
    )
    groups = []
    for row in cursor:
        files = conn.execute(
            "SELECT path, dir, filename, size, md5, scan_id FROM files WHERE md5 = ? AND size = ?",
            (row["md5"], row["size"]),
        ).fetchall()
        groups.append((row["md5"], row["size"], files))
    return groups


def print_dupes(conn):
    """Print duplicate groups to stdout."""
    groups = find_dupes(conn)
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


def compare_dirs(conn, dir_a, dir_b):
    """Compare two directories by their file contents (md5+size)."""
    def get_dir_files(dir_path):
        return conn.execute(
            "SELECT path, md5, size FROM files WHERE dir LIKE ? OR dir = ?",
            (dir_path.rstrip("/") + "/%", dir_path.rstrip("/")),
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


def main():
    parser = argparse.ArgumentParser(
        description="Find duplicate files and compare directories using SQLite database."
    )
    parser.add_argument("--db", default="files.db", help="SQLite database path (default: files.db)")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    subparsers.add_parser("dupes", help="Show groups of duplicate files")

    cmp_parser = subparsers.add_parser("compare", help="Compare two directories")
    cmp_parser.add_argument("dir_a", help="First directory path")
    cmp_parser.add_argument("dir_b", help="Second directory path")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    conn = db.get_connection(args.db)
    db.init_db(conn)

    if args.command == "dupes":
        print_dupes(conn)
    elif args.command == "compare":
        compare_dirs(conn, args.dir_a, args.dir_b)

    conn.close()


if __name__ == "__main__":
    main()

"""Cross-directory duplicate finder — find and optionally delete cross-dir duplicates."""

import argparse
import os
import sys
from collections import defaultdict
from itertools import combinations

from . import db
from .utils import DEFAULT_EXTENSIONS, format_size, parse_extensions


def ensure_deleted_at_column(conn):
    """Add deleted_at column to files table if missing."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(files)").fetchall()}
    if "deleted_at" not in cols:
        conn.execute("ALTER TABLE files ADD COLUMN deleted_at TIMESTAMP DEFAULT NULL")
        conn.commit()


def _ext_filter_sql(ext):
    """Build SQL WHERE clause fragment for extension filtering.

    Returns (sql_fragment, params) tuple.
    """
    if ext is None:
        return "", []
    conditions = []
    params = []
    for e in ext:
        conditions.append("LOWER(filename) LIKE ?")
        params.append("%" + e)
    return "AND (" + " OR ".join(conditions) + ") ", params


def find_cross_dir_dupes(conn, by_name=True, by_size=True, by_md5=True, ext=None, min_size=0):
    """Find file groups matching on selected criteria across 2+ directories.

    Returns list of (group_key, [file_rows]) sorted by total size desc.
    group_key is a dict like {"filename": "x.jpg", "size": 1234, "md5": "abc"}.

    Parameters
    ----------
    conn:       SQLite connection
    by_name:    match by filename
    by_size:    match by file size
    by_md5:     match by MD5 hash
    ext:        set of extensions (from parse_extensions) or None for all
    min_size:   minimum file size in bytes (default 0 = no filter)
    """
    col_map = []
    if by_name:
        col_map.append("filename")
    if by_size:
        col_map.append("size")
    if by_md5:
        col_map.append("md5")

    if not col_map:
        return []

    group_cols = ", ".join(col_map)

    ext_sql, ext_params = _ext_filter_sql(ext)

    size_sql = ""
    size_params = []
    if min_size > 0:
        size_sql = "AND size >= ? "
        size_params = [min_size]

    params = ext_params + size_params

    cursor = conn.execute(
        f"SELECT {group_cols}, COUNT(*) as cnt, COUNT(DISTINCT dir) as dir_cnt "
        f"FROM files "
        f"WHERE deleted_at IS NULL "
        f"{ext_sql}"
        f"{size_sql}"
        f"GROUP BY {group_cols} "
        f"HAVING dir_cnt > 1 "
        f"ORDER BY SUM(size) DESC",
        params,
    )

    groups = []
    for row in cursor:
        where_parts = [f"{col} = ?" for col in col_map]
        where_parts.append("deleted_at IS NULL")
        where_clause = " AND ".join(where_parts)
        row_params = [row[col] for col in col_map]

        files = conn.execute(
            f"SELECT id, path, dir, filename, size, md5 FROM files WHERE {where_clause}",
            row_params,
        ).fetchall()

        group_key = {col: row[col] for col in col_map}
        groups.append((group_key, files))

    return groups


def build_dir_pairs(groups):
    """Group duplicate files by directory pairs.

    Returns sorted list of ((dir_a, dir_b), [(group_key, files_in_a, files_in_b), ...])
    sorted by total duplicate size descending.
    """
    pair_data = defaultdict(list)

    for group_key, files in groups:
        # Group files by directory
        by_dir = defaultdict(list)
        for f in files:
            by_dir[f["dir"]].append(f)

        dirs = sorted(by_dir.keys())
        for da, db_ in combinations(dirs, 2):
            pair_data[(da, db_)].append((group_key, by_dir[da], by_dir[db_]))

    # Sort pairs by total duplicate size descending
    def pair_size(item):
        _, entries = item
        total = 0
        for _, files_a, files_b in entries:
            # Count the smaller side as the "duplicate" size
            total += min(
                sum(f["size"] for f in files_a),
                sum(f["size"] for f in files_b),
            )
        return total

    sorted_pairs = sorted(pair_data.items(), key=pair_size, reverse=True)
    return sorted_pairs


def get_dir_stats(conn, dir_path):
    """Return (file_count, total_size) for exact directory."""
    row = conn.execute(
        "SELECT COUNT(*) as cnt, COALESCE(SUM(size), 0) as total_size "
        "FROM files WHERE dir = ? AND deleted_at IS NULL",
        (dir_path,),
    ).fetchone()
    return row["cnt"], row["total_size"]


def get_parent_dir_stats(conn, dir_path):
    """Return (file_count, total_size) for parent directory tree (recursive)."""
    parent = os.path.dirname(dir_path)
    if not parent:
        return get_dir_stats(conn, dir_path)
    row = conn.execute(
        "SELECT COUNT(*) as cnt, COALESCE(SUM(size), 0) as total_size "
        "FROM files WHERE (dir = ? OR dir LIKE ?) AND deleted_at IS NULL",
        (parent, parent.rstrip("/") + "/%"),
    ).fetchone()
    return parent, row["cnt"], row["total_size"]


def print_pair_report(conn, dir_a, dir_b, shared_groups):
    """Print analysis for one directory pair. Returns (dup_count_a, dup_size_a, dup_count_b, dup_size_b)."""
    count_a = sum(len(files_a) for _, files_a, _ in shared_groups)
    size_a = sum(sum(f["size"] for f in files_a) for _, files_a, _ in shared_groups)
    count_b = sum(len(files_b) for _, _, files_b in shared_groups)
    size_b = sum(sum(f["size"] for f in files_b) for _, _, files_b in shared_groups)

    dir_cnt_a, dir_size_a = get_dir_stats(conn, dir_a)
    dir_cnt_b, dir_size_b = get_dir_stats(conn, dir_b)

    parent_a, par_cnt_a, par_size_a = get_parent_dir_stats(conn, dir_a)
    parent_b, par_cnt_b, par_size_b = get_parent_dir_stats(conn, dir_b)

    print(f"=== {dir_a}  vs  {dir_b} ===")
    print(f"  Dir A: {dir_a}")
    print(f"    Files: {dir_cnt_a}, Size: {format_size(dir_size_a)}")
    print(f"    Parent ({parent_a}): {par_cnt_a} files, {format_size(par_size_a)}")
    print(f"    Duplicates: {count_a} files, {format_size(size_a)}")
    print()
    print(f"  Dir B: {dir_b}")
    print(f"    Files: {dir_cnt_b}, Size: {format_size(dir_size_b)}")
    print(f"    Parent ({parent_b}): {par_cnt_b} files, {format_size(par_size_b)}")
    print(f"    Duplicates: {count_b} files, {format_size(size_b)}")
    print()

    return count_a, size_a, count_b, size_b


def delete_files(conn, file_rows):
    """Delete files from disk and mark deleted_at in DB.

    Returns (deleted_count, error_count).
    """
    deleted = 0
    errors = 0
    for f in file_rows:
        path = f["path"]
        try:
            os.remove(path)
        except OSError as e:
            print(f"  Error deleting {path}: {e}", file=sys.stderr)
            errors += 1
        # Mark in DB regardless — if file is already gone, still mark it
        conn.execute(
            "UPDATE files SET deleted_at = CURRENT_TIMESTAMP WHERE id = ?",
            (f["id"],),
        )
    conn.commit()
    return deleted + (len(file_rows) - errors), errors


def interactive_cleanup(conn, dir_pairs, dry_run=False):
    """Interactive loop: for each dir pair, show report and prompt for action.

    Parameters
    ----------
    conn:      SQLite connection
    dir_pairs: list of ((dir_a, dir_b), shared_groups) from build_dir_pairs()
    dry_run:   if True, show what would be deleted without actually deleting

    Returns (total_deleted, total_errors).
    """
    if not sys.stdin.isatty():
        print("Error: --delete requires an interactive terminal.", file=sys.stderr)
        return 0, 0

    total_deleted = 0
    total_errors = 0

    for i, ((dir_a, dir_b), shared_groups) in enumerate(dir_pairs, 1):
        print(f"\n--- Pair {i}/{len(dir_pairs)} ---")
        print_pair_report(conn, dir_a, dir_b, shared_groups)

        while True:
            try:
                choice = input("Action? [a] Delete from A  [b] Delete from B  [s] Skip  [q] Quit: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print()
                return total_deleted, total_errors

            if choice == "a":
                files_to_delete = []
                for _, files_a, _ in shared_groups:
                    files_to_delete.extend(files_a)
                if dry_run:
                    print(f"  [DRY-RUN] Would delete {len(files_to_delete)} files from {dir_a}")
                else:
                    d, e = delete_files(conn, files_to_delete)
                    total_deleted += d
                    total_errors += e
                    print(f"  Deleted {d} files from {dir_a}")
                break
            elif choice == "b":
                files_to_delete = []
                for _, _, files_b in shared_groups:
                    files_to_delete.extend(files_b)
                if dry_run:
                    print(f"  [DRY-RUN] Would delete {len(files_to_delete)} files from {dir_b}")
                else:
                    d, e = delete_files(conn, files_to_delete)
                    total_deleted += d
                    total_errors += e
                    print(f"  Deleted {d} files from {dir_b}")
                break
            elif choice == "s":
                break
            elif choice == "q":
                return total_deleted, total_errors
            else:
                print("  Invalid choice. Use a, b, s, or q.")

    return total_deleted, total_errors


def report(conn, dir_pairs):
    """Print report for all directory pairs."""
    if not dir_pairs:
        print("No cross-directory duplicates found.")
        return

    total_dup_size = 0
    total_dup_count = 0

    for (dir_a, dir_b), shared_groups in dir_pairs:
        count_a, size_a, count_b, size_b = print_pair_report(conn, dir_a, dir_b, shared_groups)
        total_dup_count += min(count_a, count_b)
        total_dup_size += min(size_a, size_b)

    print(f"Total: {len(dir_pairs)} directory pairs, "
          f"{total_dup_count} duplicate files, "
          f"potential savings: {format_size(total_dup_size)}")


def main():
    parser = argparse.ArgumentParser(
        description="Find cross-directory duplicates and optionally delete them."
    )
    parser.add_argument("--db", default="files.db", help="SQLite database path (default: files.db)")
    parser.add_argument("--no-name", dest="by_name", action="store_false", default=True,
                        help="Disable matching by filename")
    parser.add_argument("--no-size", dest="by_size", action="store_false", default=True,
                        help="Disable matching by file size")
    parser.add_argument("--no-md5", dest="by_md5", action="store_false", default=True,
                        help="Disable matching by MD5 hash")
    parser.add_argument("--delete", action="store_true", default=False,
                        help="Interactive deletion mode")
    parser.add_argument(
        "--ext",
        default=DEFAULT_EXTENSIONS,
        help=(
            "Comma-separated file extensions to include "
            f"(default: {DEFAULT_EXTENSIONS}). Use '*' for all files."
        ),
    )
    parser.add_argument(
        "--min-size",
        type=int,
        default=0,
        help="Minimum file size in bytes (default: 0)",
    )
    parser.add_argument("--dry-run", action="store_true", default=False,
                        help="Show what would be deleted without actually deleting")

    args = parser.parse_args()

    if not any([args.by_name, args.by_size, args.by_md5]):
        parser.error("At least one matching criterion must be enabled.")

    ext = parse_extensions(args.ext)

    conn = db.get_connection(args.db)
    db.init_db(conn)
    ensure_deleted_at_column(conn)

    groups = find_cross_dir_dupes(
        conn,
        args.by_name,
        args.by_size,
        args.by_md5,
        ext=ext,
        min_size=args.min_size,
    )
    dir_pairs = build_dir_pairs(groups)

    if args.delete or args.dry_run:
        total_deleted, total_errors = interactive_cleanup(conn, dir_pairs, dry_run=args.dry_run)
        if args.dry_run:
            print(f"\nTotal: {total_deleted} files would be deleted (dry-run)")
        else:
            print(f"\nTotal: deleted {total_deleted} files, {total_errors} errors")
    else:
        report(conn, dir_pairs)

    conn.close()


if __name__ == "__main__":
    main()

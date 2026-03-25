"""Unified CLI entry point for foto-dedup."""

import argparse
import sys
import uuid

from .utils import DEFAULT_DB, DEFAULT_EXTENSIONS, add_db_arg, add_ext_arg, add_min_size_arg


def _cmd_scan(args):
    from . import db as dbmod
    from .scanner import scan_paths
    from .utils import parse_extensions

    extensions = parse_extensions(args.ext)

    conn = dbmod.get_connection(args.db)
    dbmod.init_db(conn)

    scan_id = uuid.uuid4().hex[:12]
    print(f"Scan ID: {scan_id}", file=sys.stderr)
    print(f"Database: {args.db}", file=sys.stderr)
    print(f"Min size: {args.min_size} bytes", file=sys.stderr)
    print(f"Extensions: {args.ext}", file=sys.stderr)
    print(f"Paths: {args.paths}", file=sys.stderr)
    print(file=sys.stderr)

    scanned, skipped, errors = scan_paths(
        args.paths, conn, min_size=args.min_size, scan_id=scan_id, extensions=extensions
    )

    conn.close()
    print(f"Done. Scanned: {scanned}, Skipped: {skipped}, Errors: {errors}", file=sys.stderr)


def _cmd_dupes(args):
    from . import db as dbmod
    from .dupes import print_dupes
    from .utils import parse_extensions

    conn = dbmod.get_connection(args.db)
    dbmod.init_db(conn)
    print_dupes(conn, ext=parse_extensions(args.ext), min_size=args.min_size)
    conn.close()


def _cmd_compare(args):
    from . import db as dbmod
    from .dupes import compare_dirs
    from .utils import parse_extensions

    conn = dbmod.get_connection(args.db)
    dbmod.init_db(conn)
    compare_dirs(conn, args.dir_a, args.dir_b, ext=parse_extensions(args.ext), min_size=args.min_size)
    conn.close()


def _cmd_cross_dupes(args):
    from . import db as dbmod
    from .crossdupes import (
        ensure_deleted_at_column,
        find_cross_dir_dupes,
        build_dir_pairs,
        report,
        interactive_cleanup,
    )
    from .utils import parse_extensions

    conn = dbmod.get_connection(args.db)
    dbmod.init_db(conn)
    ensure_deleted_at_column(conn)

    groups = find_cross_dir_dupes(
        conn,
        args.by_name,
        args.by_size,
        args.by_md5,
        ext=parse_extensions(args.ext),
        min_size=args.min_size,
    )
    dir_pairs = build_dir_pairs(groups)

    if args.delete:
        interactive_cleanup(conn, dir_pairs, dry_run=args.dry_run)
    else:
        report(conn, dir_pairs)

    conn.close()


def _cmd_find(args):
    from . import db as dbmod
    from .dupes import print_find_results

    conn = dbmod.get_connection(args.db)
    dbmod.init_db(conn)
    print_find_results(conn, args.name, size=args.size)
    conn.close()


def _cmd_corrupt(args):
    from . import db as dbmod
    from .corrupt import ensure_deleted_at_column, print_corrupt
    from .utils import parse_extensions

    conn = dbmod.get_connection(args.db)
    dbmod.init_db(conn)
    ensure_deleted_at_column(conn)
    print_corrupt(conn, extensions=parse_extensions(args.ext))
    conn.close()


def _cmd_match_bad(args):
    from .badfiles import collect_files, match_files, print_matches
    from .utils import parse_extensions
    from pathlib import Path

    bad_dir = Path(args.damaged)
    good_dir = Path(args.source)

    for d, label in [(bad_dir, "Damaged"), (good_dir, "Source")]:
        if not d.is_dir():
            print(f"Error: {label} directory does not exist: {d}", file=sys.stderr)
            sys.exit(1)

    extensions = parse_extensions(args.ext)

    print(f"Collecting files from damaged dir: {bad_dir}", file=sys.stderr)
    bad_files = collect_files(str(bad_dir), extensions=extensions)
    print(f"Collecting files from source dir: {good_dir}", file=sys.stderr)
    good_files = collect_files(str(good_dir), extensions=extensions)

    print(f"Damaged: {len(bad_files)} files, Source: {len(good_files)} files\n", file=sys.stderr)

    matches = match_files(
        bad_files,
        good_files,
        by_size=args.by_size,
        by_name=args.by_name,
        by_name_date=args.by_name_date,
        same_dir=args.same_dir,
    )
    print_matches(matches)


def build_parser():
    parser = argparse.ArgumentParser(
        prog="fotodedup",
        description="Photo deduplication toolkit.",
    )
    subs = parser.add_subparsers(dest="command", metavar="<command>")
    subs.required = True

    # --- scan ---
    p_scan = subs.add_parser("scan", help="Scan directories and record MD5 in SQLite")
    p_scan.add_argument("paths", nargs="+", help="Directories or files to scan")
    add_db_arg(p_scan)
    add_ext_arg(p_scan)
    add_min_size_arg(p_scan, default=10240)
    p_scan.set_defaults(func=_cmd_scan)

    # --- dupes ---
    p_dupes = subs.add_parser("dupes", help="Show groups of duplicate files")
    add_db_arg(p_dupes)
    add_ext_arg(p_dupes)
    add_min_size_arg(p_dupes)
    p_dupes.set_defaults(func=_cmd_dupes)

    # --- compare ---
    p_cmp = subs.add_parser("compare", help="Compare two directories")
    p_cmp.add_argument("dir_a", help="First directory path")
    p_cmp.add_argument("dir_b", help="Second directory path")
    add_db_arg(p_cmp)
    add_ext_arg(p_cmp)
    add_min_size_arg(p_cmp)
    p_cmp.set_defaults(func=_cmd_compare)

    # --- cross-dupes ---
    p_cd = subs.add_parser("cross-dupes", help="Find cross-directory duplicates")
    add_db_arg(p_cd)
    add_ext_arg(p_cd)
    add_min_size_arg(p_cd)
    p_cd.add_argument(
        "--no-name",
        dest="by_name",
        action="store_false",
        default=True,
        help="Disable matching by filename",
    )
    p_cd.add_argument(
        "--no-size",
        dest="by_size",
        action="store_false",
        default=True,
        help="Disable matching by file size",
    )
    p_cd.add_argument(
        "--no-md5",
        dest="by_md5",
        action="store_false",
        default=True,
        help="Disable matching by MD5 hash",
    )
    p_cd.add_argument(
        "--delete",
        action="store_true",
        default=False,
        help="Interactive deletion mode",
    )
    p_cd.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Show what would be deleted without deleting",
    )
    p_cd.set_defaults(func=_cmd_cross_dupes)

    # --- corrupt ---
    p_cor = subs.add_parser(
        "corrupt", help="Find files with same name+size but different MD5"
    )
    add_db_arg(p_cor)
    add_ext_arg(p_cor)
    p_cor.set_defaults(func=_cmd_corrupt)

    # --- find ---
    p_find = subs.add_parser("find", help="Search for a file in the database by name")
    p_find.add_argument("name", help="Filename to search (supports %% wildcards)")
    p_find.add_argument("--size", type=int, default=None,
                        help="Filter by exact file size in bytes")
    add_db_arg(p_find)
    p_find.set_defaults(func=_cmd_find)

    # --- match-bad ---
    p_mb = subs.add_parser("match-bad", help="Find intact copies of damaged files")
    p_mb.add_argument("damaged", help="Directory with damaged files")
    p_mb.add_argument("source", help="Directory with intact files")
    p_mb.add_argument("--by-size", action="store_true", help="Match by file size")
    p_mb.add_argument("--by-name", action="store_true", help="Match by filename")
    p_mb.add_argument(
        "--by-name-date",
        action="store_true",
        help="Match by filename and modification date",
    )
    p_mb.add_argument(
        "--same-dir",
        action="store_true",
        help="Require same parent directory name",
    )
    add_ext_arg(p_mb)
    p_mb.set_defaults(func=_cmd_match_bad)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "match-bad":
        if not (args.by_size or args.by_name or args.by_name_date):
            parser.error(
                "At least one of --by-size, --by-name, --by-name-date is required"
            )

    if args.command == "cross-dupes":
        if not any([args.by_name, args.by_size, args.by_md5]):
            parser.error("At least one matching criterion must be enabled.")

    args.func(args)


if __name__ == "__main__":
    main()

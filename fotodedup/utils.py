"""Shared utilities for foto-dedup."""

from pathlib import Path

DEFAULT_DB = "files.db"
DEFAULT_EXTENSIONS = ".jpg,.jpeg,.avi,.mp4,.heic"


def format_size(size_bytes):
    """Format bytes as human-readable string."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size_bytes) < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


def parse_extensions(ext_string):
    """Parse comma-separated extension string into a set of lowercase extensions.

    Returns None if ext_string is empty or '*' (meaning no filtering).
    Each extension is normalized to lowercase with a leading dot.
    """
    if not ext_string or ext_string.strip() == "*":
        return None
    exts = set()
    for e in ext_string.split(","):
        e = e.strip().lower()
        if e.startswith("*."):
            e = e[1:]  # "*.jpg" -> ".jpg"
        elif not e.startswith("."):
            e = "." + e  # "jpg" -> ".jpg"
        exts.add(e)
    return exts


def matches_extension(filename, extensions):
    """Check if filename matches any of the extensions (case-insensitive).

    If extensions is None, all files match.
    """
    if extensions is None:
        return True
    return Path(filename).suffix.lower() in extensions


def add_db_arg(parser):
    """Add --db argument to an argparse parser."""
    parser.add_argument(
        "--db",
        default=DEFAULT_DB,
        help=f"SQLite database path (default: {DEFAULT_DB})",
    )


def add_ext_arg(parser):
    """Add --ext argument to an argparse parser."""
    parser.add_argument(
        "--ext",
        default=DEFAULT_EXTENSIONS,
        help=(
            "Comma-separated file extensions to include "
            f"(default: {DEFAULT_EXTENSIONS}). Use '*' for all files."
        ),
    )


def add_min_size_arg(parser, default=0):
    """Add --min-size argument to an argparse parser."""
    parser.add_argument(
        "--min-size",
        type=int,
        default=default,
        help=f"Minimum file size in bytes (default: {default})",
    )

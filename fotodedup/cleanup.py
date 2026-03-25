"""Backward-compatible wrapper — use 'fotodedup crossdupes' instead."""

from .crossdupes import (  # noqa: F401
    build_dir_pairs,
    delete_files,
    ensure_deleted_at_column,
    find_cross_dir_dupes,
    get_dir_stats,
    get_parent_dir_stats,
    interactive_cleanup,
    print_pair_report,
    report,
)


def main():
    from .crossdupes import main as _main
    _main()


if __name__ == "__main__":
    main()

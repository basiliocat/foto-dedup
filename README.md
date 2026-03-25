# foto-dedup

[![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**English** | [Русский](README.ru.md)

A command-line toolkit for finding duplicate files on NAS storage with metadata stored in SQLite. Designed for managing large photo and media libraries spread across multiple directories or backup copies.

## Features

- **File scanning** with MD5 hashing and SQLite storage
- **Duplicate detection** by md5+size with waste calculation
- **Directory comparison** showing overlap percentages
- **Cross-directory cleanup** with configurable matching criteria and interactive deletion
- **Corruption detection** for files with matching name+size but different hashes
- **Bad file recovery** — finding intact copies of corrupted files

Zero external dependencies — uses only Python standard library.

## Quick Start

```bash
# Setup virtual environment
./setup.sh

# Scan directories
./run.sh scan /path/to/photos /path/to/backup

# Find duplicates
./run.sh dupes --db files.db

# Check for corruption
./run.sh corrupt --db files.db
```

## Installation

```bash
git clone https://github.com/basiliocat/foto-dedup.git
cd foto-dedup
./setup.sh
source .venv/bin/activate
```

Requirements: Python 3.8+ (only stdlib is used: `hashlib`, `sqlite3`, `argparse`, `pathlib`).

## Usage

All commands are run via `./run.sh <command> [args...]` or directly with `python -m fotodedup <command> [args...]`.

### 1. Scanning Files

Recursively scans directories, computes MD5 hashes, and stores metadata in SQLite.

```bash
./run.sh scan /path/to/dir1 /path/to/dir2 --db files.db --min-size 10240
```

| Option | Default | Description |
|--------|---------|-------------|
| `--db` | `files.db` | SQLite database path |
| `--min-size` | `10240` (10 KB) | Minimum file size in bytes to include |

**How it works:**
- Walks directories recursively, skipping symlinks
- Computes MD5 in 1 MB blocks to keep RAM usage low on large files
- Incremental: skips files already in DB with the same path and size
- Each run gets a unique `scan_id` for tracking
- Read errors are logged to stderr; scanning continues

### 2. Finding Duplicates

Groups files by identical md5+size, sorted by wasted space (largest first).

```bash
./run.sh dupes --db files.db
./run.sh dupes --db files.db --ext jpg,png --min-size 10240
```

| Option | Default | Description |
|--------|---------|-------------|
| `--db` | `files.db` | SQLite database path |
| `--ext` | all | Comma-separated list of extensions to include (e.g. `jpg,png`) |
| `--min-size` | `0` | Minimum file size in bytes to include |

Example output:
```
--- Group 1/3: 15.2 MB x 3 copies, waste: 30.4 MB [md5: a1b2c3d4...]
  /photos/2020/vacation/IMG_001.jpg
  /backup/photos/IMG_001.jpg
  /nas/unsorted/IMG_001.jpg

Total: 3 duplicate groups, wasted space: 45.6 MB
```

### 3. Comparing Directories

Shows overlap between two directory trees — how many files they share and what's unique to each.

```bash
./run.sh compare /photos /backup --db files.db
./run.sh compare /photos /backup --db files.db --ext jpg,png --min-size 10240
```

| Option | Default | Description |
|--------|---------|-------------|
| `--db` | `files.db` | SQLite database path |
| `--ext` | all | Comma-separated list of extensions to include (e.g. `jpg,png`) |
| `--min-size` | `0` | Minimum file size in bytes to include |

Example output:
```
Directory A: /photos
  Files: 1200, Total size: 18.5 GB
  Unique content keys (md5+size): 1100

Directory B: /backup
  Files: 800, Total size: 12.0 GB
  Unique content keys (md5+size): 750

Common (same md5+size): 600 files, 9.2 GB
Only in A: 500
Only in B: 150

Overlap: 54.5% of A is in B
Overlap: 80.0% of B is in A
```

### 4. Cross-Directory Cleanup

Finds duplicates across directories with configurable matching criteria and provides an interactive deletion workflow.

```bash
# Report only (default)
./run.sh cross-dupes --db files.db

# Dry run (no actual deletion)
./run.sh cross-dupes --db files.db --dry-run

# Interactive deletion
./run.sh cross-dupes --db files.db --delete

# Disable specific criteria
./run.sh cross-dupes --db files.db --no-name --delete

# Filter by extension and minimum size
./run.sh cross-dupes --db files.db --ext jpg,png --min-size 10240
```

| Option | Default | Description |
|--------|---------|-------------|
| `--db` | `files.db` | SQLite database path |
| `--no-name` | enabled | Disable matching by filename |
| `--no-size` | enabled | Disable matching by file size |
| `--no-md5` | enabled | Disable matching by MD5 hash |
| `--ext` | all | Comma-separated list of extensions to include (e.g. `jpg,png`) |
| `--min-size` | `0` | Minimum file size in bytes to include |
| `--dry-run` | off | Show what would be deleted without actually deleting |
| `--delete` | off | Enable interactive deletion mode |

By default, all three criteria are combined with AND logic: files must match on filename, size, and MD5 to be considered duplicates. You can relax matching by disabling criteria with `--no-name`, `--no-size`, or `--no-md5`.

**Report mode** shows directory pairs with context:

```
=== /photos/2020  vs  /backup/2020 ===
  Dir A: /photos/2020
    Files: 150, Size: 2.3 GB
    Parent (/photos): 1200 files, 18.5 GB
    Duplicates: 45 files, 800.0 MB

  Dir B: /backup/2020
    Files: 200, Size: 3.1 GB
    Parent (/backup): 800 files, 12.0 GB
    Duplicates: 45 files, 800.0 MB

Total: 5 directory pairs, 120 duplicate files, potential savings: 1.8 GB
```

**Interactive mode** (`--delete`) prompts for each directory pair:

```
Action? [a] Delete from A  [b] Delete from B  [s] Skip  [q] Quit
```

- Files are removed from disk
- Deleted files are marked in the database (`deleted_at` timestamp) for audit trail
- Re-running after partial deletion is safe — already-deleted files are excluded

### 5. Corruption Detection

Finds files with the same filename and size but different MD5 hashes — a sign of data corruption, silent bitrot, or incomplete transfers.

```bash
./run.sh corrupt --db files.db
```

Example output:
```
--- 1/2: photo.jpg (4.9 KB), 3 copies, 2 different hashes ---
  [a1b2c3d4] /photos/2020/photo.jpg
  [a1b2c3d4] /backup/2020/photo.jpg
  [e5f6a7b8] /nas/unsorted/photo.jpg

Total: 2 groups, 5 files with potential corruption
```

Files are grouped by name+size and sorted by size (largest first). The truncated MD5 prefix lets you quickly see which copies match and which diverge.

### 6. Bad File Recovery

Finds intact copies of corrupted files by matching on filesystem metadata (no database required).

```bash
./run.sh match-bad /bad/dir /good/dir --by-name --by-size --same-dir
```

| Option | Description |
|--------|-------------|
| `--by-name` | Match by filename |
| `--by-size` | Match by file size |
| `--by-name-date` | Match by filename and modification time |
| `--same-dir` | Additionally require same parent directory name |

At least one of `--by-name`, `--by-size`, or `--by-name-date` is required.

## Database Schema

All file metadata is stored in a single `files` table:

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Primary key |
| `path` | TEXT (UNIQUE) | Absolute file path |
| `dir` | TEXT | Parent directory path |
| `filename` | TEXT | File name |
| `size` | INTEGER | File size in bytes |
| `md5` | TEXT | MD5 hash |
| `scan_id` | TEXT | Unique scan run identifier |
| `scanned_at` | TIMESTAMP | When the file was scanned |
| `deleted_at` | TIMESTAMP | When the file was deleted (NULL if not deleted) |

**Indexes:** `(md5, size)`, `(dir)`, `(path, size)`.

## Testing

```bash
source .venv/bin/activate
pytest tests/ -v
```

## Project Structure

```
fotodedup/
├── utils.py       # Utilities: format_size, parse_extensions, DEFAULT_DB/EXTENSIONS
├── cli.py         # Unified entry point (subcommands)
├── db.py          # SQLite schema, init_db(), insert_file(), get_connection()
├── scanner.py     # Command scan: recursive walk, MD5 in 1MB blocks, incremental scanning
├── dupes.py       # Commands dupes and compare
├── crossdupes.py  # Command cross-dupes: cross-directory duplicates
├── cleanup.py     # Backward compatibility wrapper → crossdupes
├── corrupt.py     # Command corrupt: corruption detection (same name+size, different md5)
└── badfiles.py    # Command match-bad: find intact copies of corrupted files
tests/
├── test_db.py     # Schema, insert, upsert, persistence
├── test_scanner.py # MD5, scanning, min-size filter, incrementality
├── test_dupes.py  # Duplicates, sorting, compare, empty directories
├── test_badfiles.py # collect_files, matching criteria, CLI
├── test_cleanup.py # Backward compatibility
├── test_crossdupes.py # Cross-dir dupes, dir pairs, deletion, interactive
└── test_corrupt.py # Corruption detector
```

## License

MIT

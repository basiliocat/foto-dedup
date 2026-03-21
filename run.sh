#!/bin/bash
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
source "$DIR/.venv/bin/activate"

MODULE="$1"
if [ -z "$MODULE" ]; then
    echo "Usage: ./run.sh <module> [args...]"
    echo ""
    echo "Modules:"
    echo "  scanner   - Scan directories and compute MD5 hashes"
    echo "  dupes     - Find duplicates or compare directories"
    echo "  cleanup   - Cross-directory duplicate cleanup"
    echo "  corrupt   - Detect data corruption"
    echo "  badfiles  - Find intact copies of corrupted files"
    exit 1
fi

shift
python -m "fotodedup.$MODULE" "$@"

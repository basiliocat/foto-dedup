#!/bin/bash
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$DIR/.venv/bin/python"

if [ ! -x "$PYTHON" ]; then
    echo "Error: virtualenv not found. Run ./setup.sh first." >&2
    exit 1
fi

if [ -z "$1" ]; then
    "$PYTHON" -m fotodedup --help
    exit 0
fi

# Backward-compatible aliases for old command names
case "$1" in
    scanner)  shift; exec "$PYTHON" -m fotodedup scan "$@" ;;
    cleanup)  shift; exec "$PYTHON" -m fotodedup cross-dupes "$@" ;;
    badfiles) shift; exec "$PYTHON" -m fotodedup match-bad "$@" ;;
    *)        exec "$PYTHON" -m fotodedup "$@" ;;
esac

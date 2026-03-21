#!/bin/bash
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

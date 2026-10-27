#!/bin/bash
set -e
SCRIPT_DIR=$(cd `dirname "$0"` && pwd)
PROJECT_DIR=$(dirname "$SCRIPT_DIR")
cd "$PROJECT_DIR"

mkdir -p data
python3 -m product_kb.cli --db ./data/product_kb.db init
echo "Database initialized at ./data/product_kb.db"

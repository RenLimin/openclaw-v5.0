#!/bin/bash
set -e
SCRIPT_DIR=$(cd `dirname "$0"` && pwd)
PROJECT_DIR=$(dirname "$SCRIPT_DIR")
cd "$PROJECT_DIR"

python3 -m product_kb.cli --db ./data/product_kb.db build-index "$@"

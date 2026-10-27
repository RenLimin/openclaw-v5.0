#!/bin/bash
set -e
SCRIPT_DIR=$(cd `dirname "$0"` && pwd)
PROJECT_DIR=$(dirname "$SCRIPT_DIR")
cd "$PROJECT_DIR"

if [ $# -ne 1 ]; then
    echo "Usage: $0 <path-to-price-xlsx>"
    exit 1
fi

python3 -m product_kb.cli --db ./data/product_kb.db import-price --xlsx "$1"

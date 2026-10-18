#!/bin/bash
# AI Knowledge Base Instance Scaffolding Script
# Usage: ./init_kb.sh <domain_code> <domain_name> [description]
# Example: ./init_kb.sh product-kb "产品知识库" "Bangcle产品服务知识库"

set -e

DOMAIN_CODE="$1"
DOMAIN_NAME="$2"
DESCRIPTION="${3:-企业AI知识库}"

if [ -z "$DOMAIN_CODE" ] || [ -z "$DOMAIN_NAME" ]; then
    echo "Usage: $0 <domain_code> <domain_name> [description]"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
KB_ROOT="$(dirname "$SCRIPT_DIR")"
INSTANCE_DIR="$KB_ROOT/instances/$DOMAIN_CODE"
DATA_DIR="$INSTANCE_DIR/data"
DOCS_DIR="$INSTANCE_DIR/docs"

echo "=== AI KB Instance Scaffolding ==="
echo "Domain Code:    $DOMAIN_CODE"
echo "Domain Name:    $DOMAIN_NAME"
echo "Description:    $DESCRIPTION"
echo "Instance Path:  $INSTANCE_DIR"
echo ""

# Create directory structure
mkdir -p "$DATA_DIR"
mkdir -p "$DOCS_DIR"
echo "✓ Directory structure created"

# Initialize database
python3 << PYEOF
import sys
sys.path.insert(0, "$KB_ROOT")
from ai_kb.db import AIKB

db = AIKB("$DATA_DIR/$DOMAIN_CODE.db")
db.connect()
db.init_db()

# Create domain
domain_id = db.get_or_create_domain("$DOMAIN_NAME", "$DOMAIN_CODE", "$DESCRIPTION")
print(f"✓ Database initialized (domain_id={domain_id})")

db.close()
PYEOF

# Create config placeholder
cat > "$INSTANCE_DIR/config.json" << JSONEOF
{
  "domain_code": "$DOMAIN_CODE",
  "domain_name": "$DOMAIN_NAME",
  "description": "$DESCRIPTION",
  "db_path": "data/$DOMAIN_CODE.db",
  "embedding": {
    "provider": "local",
    "model": "ggml-org/embeddinggemma-300m"
  },
  "permissions": {
    "default_clearance": "internal",
    "mode": "permissive"
  },
  "chunking": {
    "max_tokens": 512,
    "overlap": 64
  }
}
JSONEOF
echo "✓ Config created"

# Create README
cat > "$INSTANCE_DIR/README.md" << MDEOF
# $DOMAIN_NAME ($DOMAIN_CODE)

AI Knowledge Base instance powered by L2 ai-knowledge-base component.

## Quick Start

\`\`\`bash
# Import documents
python3 -m ai_kb.cli --config config.json import ./docs/

# Search
python3 -m ai_kb.cli --config config.json query "your question"

# List entities
python3 -m ai_kb.cli --config config.json list
\`\`\`

## Structure

- \`data/\` — SQLite database and indexes
- \`docs/\` — Source documents to ingest
- \`config.json\` — Instance configuration
MDEOF
echo "✓ README created"

echo ""
echo "=== Done! Instance created at $INSTANCE_DIR ==="
echo ""
echo "Next steps:"
echo "  1. Put your documents in $DOCS_DIR/"
echo "  2. Run: python3 -m ai_kb.cli --config $INSTANCE_DIR/config.json import"
echo "  3. Test query: python3 -m ai_kb.cli --config $INSTANCE_DIR/config.json query <question>"

#!/usr/bin/env bash
# FIN-L4 数据备份脚本
# 用法: ./deploy/backup.sh [目标目录]
# 默认备份到 ./backups/

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="${FIN4_DB_DIR:-${HOME}/.fin-l4}"
BACKUP_DIR="${1:-${PROJECT_DIR}/backups}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
DB_FILE="${DATA_DIR}/fin_l4.db"

mkdir -p "${BACKUP_DIR}"

if [ ! -f "${DB_FILE}" ]; then
    echo "[WARN] 数据库不存在: ${DB_FILE}"
    exit 1
fi

# 使用 sqlite 在线备份(VACUUM INTO 避免 WAL 不一致)
BACKUP_FILE="${BACKUP_DIR}/fin_l4_${TIMESTAMP}.db"
python3 -c "
import sqlite3, sys
src = sqlite3.connect('${DB_FILE}')
dst = sqlite3.connect('${BACKUP_FILE}')
src.backup(dst)
dst.close(); src.close()
print('backup done')
"

# 保留最近 14 份
ls -1t "${BACKUP_DIR}"/fin_l4_*.db 2>/dev/null | tail -n +15 | xargs -r rm -f

echo "[OK] 备份完成: ${BACKUP_FILE}"
echo "[OK] 已保留最近 14 份备份"

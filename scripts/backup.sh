#!/usr/bin/env bash
# =============================================================================
# scripts/backup.sh — 综合备份脚本
#
# 设计依据（业界 3-2-1 最佳实践 + 官方 docs/cli/backup.md）:
#   1. SQLite 快照（每日，gateway 运行时可用）:
#      - `openclaw backup sqlite create --agent main`   会话数据库
#      - `openclaw backup sqlite create --global`       全局状态（含 delivery 队列清理）
#   2. workspace 敏感内容（memory/ skills/）: AES-256-CBC 加密
#      （memory 含个人上下文，skills 含方法论，均敏感；密钥分离存储）
#   3. 官方深度全量备份（可选，需 gateway 停止）:
#      `openclaw backup create --verify` — 含配置/凭据/会话/workspace 便携归档
#      ⚠️ 官方 backup 无法在 gateway 持有 lock 数据库时运行（SQLite lock），
#         所以作为 --full 模式，在更新/维护前手动触发
#   4. 多版本保留 + 自动清理（默认 14 份）
#
# 用法:
#   ./scripts/backup.sh              # 默认 = --daily
#   ./scripts/backup.sh --daily      # 每日：SQLite 快照 + memory/skills 加密
#   ./scripts/backup.sh --full       # 深度：官方全量（需先停 gateway）
#   ./scripts/backup.sh --verify     # 验证最近一次加密备份 + SQLite 快照
#   ./scripts/backup.sh --keep 14    # 保留最近 14 份（默认 14）
#
# 密钥管理:
#   加密密钥存 ~/.openclaw/secrets/backup.key（600 权限，与凭据同级隔离）
#   首次运行自动生成；可通过环境变量 BACKUP_KEY 覆盖
#   ⚠️ backup.key 丢失 = 加密备份永久不可解 → 需同步备份该 key（建议密码管理器）
# =============================================================================

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# 备份根目录放 ~/Backups/openclaw（官方 backup 拒绝写入 ~/.openclaw 源路径内）
BACKUP_ROOT="${OPENCLAW_BACKUP_ROOT:-$HOME/Backups/openclaw}"
SQLITE_DIR="$BACKUP_ROOT/sqlite"              # SQLite 快照仓库
OFFICIAL_DIR="$BACKUP_ROOT/official"          # 官方深度全量备份
ENCRYPTED_DIR="$BACKUP_ROOT/memory-snapshot"  # memory/skills 加密备份
KEY_FILE="$HOME/.openclaw/secrets/backup.key"
KEEP="${BACKUP_KEEP:-14}"                     # 保留最近 N 份

mkdir -p "$SQLITE_DIR" "$OFFICIAL_DIR" "$ENCRYPTED_DIR"
chmod 700 "$BACKUP_ROOT" "$SQLITE_DIR" "$OFFICIAL_DIR" "$ENCRYPTED_DIR"

# ---------------------------------------------------------------------------
# 密钥管理
# ---------------------------------------------------------------------------
get_or_create_key() {
  if [[ -n "${BACKUP_KEY:-}" ]]; then
    printf '%s' "$BACKUP_KEY" > "$KEY_FILE"
    chmod 600 "$KEY_FILE"
    return
  fi
  if [[ ! -f "$KEY_FILE" ]]; then
    echo "🔑 生成备份密钥: $KEY_FILE"
    openssl rand -base64 48 > "$KEY_FILE"
    chmod 600 "$KEY_FILE"
    echo "⚠️  请将 backup.key 内容同步到密码管理器（丢失=加密备份永久不可解）"
  fi
}

# ---------------------------------------------------------------------------
# SQLite 快照（每日，gateway 运行时可用）
# ---------------------------------------------------------------------------
sqlite_snapshot() {
  echo "=== [1/3] SQLite 快照 ==="
  echo "  → agent:main 会话数据库"
  openclaw backup sqlite create --agent main --repository "$SQLITE_DIR" 2>&1 | sed 's/^/    /'
  echo "  → global 全局状态"
  openclaw backup sqlite create --global --repository "$SQLITE_DIR" 2>&1 | sed 's/^/    /'
}

# ---------------------------------------------------------------------------
# memory/skills 加密备份（AES-256-CBC）
# ---------------------------------------------------------------------------
encrypted_backup() {
  echo "=== [2/3] workspace 敏感内容加密备份 ==="
  local ts
  ts="$(date +%Y%m%d-%H%M%S)"
  get_or_create_key
  local key
  key="$(cat "$KEY_FILE")"

  # memory/ 加密
  if [[ -d "$REPO_ROOT/memory" ]]; then
    ( cd "$REPO_ROOT" && tar czf - memory/ 2>/dev/null ) \
      | openssl enc -aes-256-cbc -salt -pbkdf2 -iter 100000 -pass pass:"$key" \
      > "$ENCRYPTED_DIR/memory-$ts.tar.gz.enc"
    echo "✅ memory/ → $(basename "$ENCRYPTED_DIR/memory-$ts.tar.gz.enc")"
  fi

  # skills/ 加密（workspace 自建技能，含方法论）
  if [[ -d "$REPO_ROOT/skills" ]]; then
    ( cd "$REPO_ROOT" && tar czf - skills/ 2>/dev/null ) \
      | openssl enc -aes-256-cbc -salt -pbkdf2 -iter 100000 -pass pass:"$key" \
      > "$ENCRYPTED_DIR/skills-$ts.tar.gz.enc"
    echo "✅ skills/ → $(basename "$ENCRYPTED_DIR/skills-$ts.tar.gz.enc")"
  fi

  # 配置快照（脱敏后明文，方便快速对比）
  if [[ -f "$REPO_ROOT/config-snapshots/openclaw.json" ]]; then
    cp "$REPO_ROOT/config-snapshots/openclaw.json" "$ENCRYPTED_DIR/config-snapshot-$ts.json" 2>/dev/null || true
  fi
}

# ---------------------------------------------------------------------------
# 官方深度全量备份（需 gateway 停止；仅 --full 模式）
# ---------------------------------------------------------------------------
official_full_backup() {
  echo "=== 官方深度全量备份 ==="
  echo "⚠️  官方 backup create 需要 gateway 停止（SQLite lock 限制）"
  if ! openclaw gateway status >/dev/null 2>&1; then
    if openclaw backup create --output "$OFFICIAL_DIR" --verify >/tmp/openclaw-backup.log 2>&1; then
      echo "✅ 官方全量备份完成"
      local archive
      archive="$(ls -t "$OFFICIAL_DIR"/*-openclaw-backup.tar.gz 2>/dev/null | head -1 || true)"
      [[ -n "$archive" ]] && echo "  → $archive"
    else
      echo "❌ 官方备份失败:" >&2
      tail -5 /tmp/openclaw-backup.log >&2
      rm -f /tmp/openclaw-backup.log
      return 1
    fi
  else
    echo "❌ Gateway 正在运行，跳过官方全量备份（请先停止 gateway 或使用 --daily）"
    return 1
  fi
}

# ---------------------------------------------------------------------------
# 验证最近备份
# ---------------------------------------------------------------------------
verify_backups() {
  echo "=== [验证] 备份完整性 ==="
  get_or_create_key
  local key
  key="$(cat "$KEY_FILE")"

  # 加密备份解密抽查
  local latest_memory
  latest_memory="$(ls -t "$ENCRYPTED_DIR"/memory-*.tar.gz.enc 2>/dev/null | head -1 || true)"
  if [[ -n "$latest_memory" ]]; then
    if openssl enc -d -aes-256-cbc -pbkdf2 -iter 100000 -pass pass:"$key" \
        -in "$latest_memory" 2>/dev/null | tar tzf - 2>/dev/null | head -3 >/dev/null; then
      echo "✅ 加密备份解密验证通过: $(basename "$latest_memory")"
    else
      echo "❌ 加密备份解密验证失败（密钥不匹配或损坏）" >&2
      return 1
    fi
  fi

  # SQLite 快照验证（最新 agent 快照）
  local latest_snapshot
  latest_snapshot="$(ls -td "$SQLITE_DIR"/* 2>/dev/null | head -1 || true)"
  if [[ -n "$latest_snapshot" ]]; then
    if openclaw backup sqlite verify "$latest_snapshot" >/dev/null 2>&1; then
      echo "✅ SQLite 快照验证通过: $(basename "$latest_snapshot")"
    else
      echo "❌ SQLite 快照验证失败" >&2
      return 1
    fi
  fi
}

# ---------------------------------------------------------------------------
# 保留策略（清理旧版本）
# ---------------------------------------------------------------------------
cleanup_old() {
  echo "=== [3/3] 清理旧备份（保留最近 $KEEP 份）==="

  # SQLite 快照（按修改时间，保留 KEEP 份）
  local snap_count
  snap_count="$(ls -td "$SQLITE_DIR"/* 2>/dev/null | wc -l | tr -d ' ' || true)"
  if [[ "$snap_count" -gt "$((KEEP*2))" ]]; then
    ls -td "$SQLITE_DIR"/* 2>/dev/null | tail -n +$((KEEP*2+1)) | while read -r d; do
      rm -rf "$d"
      echo "  🗑️  SQLite 快照: $(basename "$d")"
    done
  fi

  # 加密备份（按 ts 分组，memory-*.enc / skills-*.enc 配对）
  local groups
  groups="$(ls "$ENCRYPTED_DIR" 2>/dev/null | grep -oE '[0-9]{8}-[0-9]{6}' | sort -r | uniq || true)"
  if [[ -n "$groups" ]]; then
    local group_count
    group_count="$(echo "$groups" | wc -l | tr -d ' ')"
    if [[ "$group_count" -gt "$KEEP" ]]; then
      echo "$groups" | tail -n +$((KEEP+1)) | while read -r ts; do
        rm -f "$ENCRYPTED_DIR"/*"$ts"* 2>/dev/null
        echo "  🗑️  加密组: $ts"
      done
    fi
  fi

  echo "  当前: SQLite 快照 $(ls -td "$SQLITE_DIR"/* 2>/dev/null | wc -l | tr -d ' ') 份, 加密 $(ls "$ENCRYPTED_DIR"/*.enc 2>/dev/null | wc -l | tr -d ' ') 份"
}

# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
main() {
  local mode="daily"
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --daily) mode="daily" ;;
      --full) mode="full" ;;
      --verify) mode="verify" ;;
      --keep) KEEP="$2"; shift ;;
      *) echo "未知参数: $1" >&2; exit 1 ;;
    esac
    shift
  done

  case "$mode" in
    verify)
      verify_backups
      ;;
    full)
      official_full_backup
      encrypted_backup
      verify_backups
      cleanup_old
      ;;
    daily)
      sqlite_snapshot
      encrypted_backup
      verify_backups
      cleanup_old
      ;;
  esac
  echo ""
  echo "✅ 备份完成: $(date '+%Y-%m-%d %H:%M:%S')"
}

main "$@"

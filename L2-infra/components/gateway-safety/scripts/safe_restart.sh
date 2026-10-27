#!/usr/bin/env bash
# safe_restart.sh — restart the Gateway only if the pre-restart guard passes.
#
# Usage:
#   safe_restart.sh [--force] [--strict] [restart args...]
#
#   --force   restart even if the guard returns a non-fatal error (rc=2).
#             A hard block (rc=1, in-flight compaction) is NEVER overridden.
#   --strict  treat indeterminate guard state as a block.
#
# Every agent-initiated restart MUST go through this wrapper so an in-flight
# compaction / active critical work is not interrupted (see 2026-10-27 incident).
# This cannot intercept an internal config-patch auto-restart — for that, run
# the guard manually before editing config and prefer hot reload.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GUARD="python3 ${SCRIPT_DIR}/pre_restart_guard.py"

force=0
strict=0
args=()
for a in "$@"; do
  case "$a" in
    --force) force=1 ;;
    --strict) strict=1 ;;
    *) args+=("$a") ;;
  esac
done

echo "=== pre-restart guard ==="
guard_rc=0
if [[ $strict -eq 1 ]]; then
  $GUARD --strict || guard_rc=$?
else
  $GUARD || guard_rc=$?
fi

case $guard_rc in
  0)
    echo "guard: SAFE — proceeding with restart"
    ;;
  1)
    echo "guard: BLOCKED — in-flight critical work. Restart aborted." >&2
    exit 1
    ;;
  2)
    if [[ $force -eq 1 ]]; then
      echo "guard: INDETERMINATE — --force given, proceeding anyway" >&2
    else
      echo "guard: INDETERMINATE — restart aborted (re-run with --force to override)." >&2
      exit 2
    fi
    ;;
  *)
    echo "guard: unexpected rc=$guard_rc — aborting" >&2
    exit "$guard_rc"
    ;;
esac

echo "=== restarting gateway ==="
exec openclaw gateway restart "${args[@]}"

---
name: compaction-guard
description: "Track in-flight compaction to a state file so a pre-restart guard can block unsafe restarts; observe pre-restart"
metadata:
  { "openclaw": { "events": ["session:compact:before", "session:compact:after", "gateway:pre-restart"] } }
---

# Compaction Guard

OpenClaw logs only compaction **end** events, so an external guard cannot tell
from logs whether a compaction is currently running. This hook closes that gap:

- `session:compact:before` → mark the session `running` in the state file
- `session:compact:after`  → mark it `done`
- `gateway:pre-restart`   → append an observation record (cannot veto restart)

State file: `~/.openclaw/state/compaction-state.json`. The pre-restart guard
(`L2-infra/components/gateway-safety/scripts/pre_restart_guard.py`) reads it and
blocks a restart while any compaction is freshly `running`.

Note: in-process hooks cannot cancel a restart. The hard block lives in the
`safe_restart.sh` wrapper, which must be used for every agent-initiated restart.

// compaction-guard handler
// Maintains ~/.openclaw/state/compaction-state.json with in-flight compaction
// markers so the pre-restart guard can reliably block unsafe restarts.
//
// Hooks run as trusted Gateway code and may use node built-ins. No model calls,
// no network. All file ops are best-effort and must never throw into the host.

import { mkdirSync, readFileSync, writeFileSync, renameSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

const STATE_DIR = join(homedir(), ".openclaw", "state");
const STATE_FILE = join(STATE_DIR, "compaction-state.json");
const OBS_LOG = join(STATE_DIR, "pre-restart-observations.log");

// A compaction that reported `before` but never `after` is only treated as
// live within this many seconds. Beyond that it is considered stale (crash /
// hard kill) so a restart is not blocked forever.
const FRESH_MS = 6 * 60 * 1000;

function readState() {
  try {
    return JSON.parse(readFileSync(STATE_FILE, "utf8")) || {};
  } catch {
    return {};
  }
}

function writeStateAtomic(state) {
  try {
    mkdirSync(STATE_DIR, { recursive: true });
    const tmp = `${STATE_FILE}.tmp`;
    writeFileSync(tmp, JSON.stringify(state, null, 2));
    renameSync(tmp, STATE_FILE);
  } catch {
    /* best effort */
  }
}

function appendObservation(line) {
  try {
    mkdirSync(STATE_DIR, { recursive: true });
    writeFileSync(OBS_LOG, `${line}\n`, { flag: "a" });
  } catch {
    /* best effort */
  }
}

export default function handler(event) {
  try {
    const action = event?.action;
    const ctx = event?.context || {};
    const sessionKey = event?.sessionKey || ctx.sessionKey || "unknown";
    const now = new Date().toISOString();

    if (action === "compact:before") {
      const state = readState();
      state.running = state.running || {};
      state.running[sessionKey] = {
        since: now,
        messageCount: ctx.messageCount ?? null,
        tokenCount: ctx.tokenCount ?? null,
      };
      writeStateAtomic(state);
    } else if (action === "compact:after") {
      const state = readState();
      state.running = state.running || {};
      delete state.running[sessionKey];
      state.lastDone = {
        at: now,
        sessionKey,
        tokensBefore: ctx.tokensBefore ?? null,
        tokensAfter: ctx.tokensAfter ?? null,
      };
      writeStateAtomic(state);
    } else if (action === "pre-restart") {
      const state = readState();
      const live = Object.keys(state.running || {});
      appendObservation(
        `${now} reason=${ctx.reason ?? "?"} restartExpectedMs=${
          ctx.restartExpectedMs ?? "null"
        } inFlightCompaction=${live.length ? live.join(",") : "none"}`
      );
    }
  } catch {
    /* never let a guard hook disrupt the host */
  }
}

export const FRESH_WINDOW_MS = FRESH_MS;

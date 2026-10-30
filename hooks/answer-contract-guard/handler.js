// answer-contract-guard handler
// Runtime delivery guard for ADR-035 P1/P2 answer contract (observation only).
//
// Subscribes to `message:sent`. When an outbound message carries answer-contract
// evidence markers (【已验证/【推断/【缺失), it audits whether the mandatory
// P1 signals are present (source timestamp on 【已验证, degradation marker when
// non-real-time data is referenced, trace chain) and appends one line to
// ~/.openclaw/state/answer-contract-audit.log.
//
// Deliberately observation-only: it never cancels or rewrites delivery. The hard
// gate stays in pre-commit golden tests + check_answer_contract.py; this hook
// closes the loop on what actually leaves the agent.
//
// Trusted Gateway code, node built-ins only, no model calls, no network.
// All file ops best-effort; must never throw into the host.

import { mkdirSync, appendFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

const AUDIT_DIR = process.env.OPENCLAW_ANSWER_AUDIT_DIR
  ? process.env.OPENCLAW_ANSWER_AUDIT_DIR
  : join(homedir(), ".openclaw", "state");
const AUDIT_FILE = join(AUDIT_DIR, "answer-contract-audit.log");

// Evidence markers that identify an answer-contract-bearing delivery.
// These are deliberately specific to the P1 contract vocabulary so ordinary
// chat (which never uses 【已验证/【推断/【缺失) is not flagged.
const MARKER = /【已验证|【推断|【缺失/;
const VERIFIED_TS = /【已验证\s*\d{4}-\d{2}-\d{2}/;
const TRACE = /溯源|数据源\s*→|查询条件/;
const DEGRADE_WORDS = /(非实时|旧报告|历史报告|导出数据|降级)/;
const DEGRADE_FLAG = /⚠️[^\n]*(数据源|可能过期|降级)/;
// Claim binding: an 【推断】 must be followed (nearby) by a derivation word.
const INFER_BIND = /【推断】[^】\n]{0,40}(据|由|匹配|推导|因为)/;

export default function handler(event) {
  try {
    const action = event?.action;
    if (action !== "sent") return;
    const ctx = event?.context || {};
    const content = String(ctx.content || "");
    if (!MARKER.test(content)) return; // not an answer-contract delivery

    const sessionKey = ctx.sessionKey || "unknown";
    const channelId = ctx.channelId || "unknown";
    const now = new Date().toISOString();

    const problems = [];
    const hasVerified = /【已验证/.test(content);
    if (hasVerified && !VERIFIED_TS.test(content))
      problems.push("no_source_timestamp"); // P1 §2
    if (!hasVerified) problems.push("no_verified"); // evidence grade missing
    if (INFER_BIND.test(content) === false && /【推断/.test(content))
      problems.push("infer_not_traceable"); // P1 §2
    if (DEGRADE_WORDS.test(content) && !DEGRADE_FLAG.test(content))
      problems.push("silent_degrade"); // P1 §3
    if (!TRACE.test(content)) problems.push("no_trace"); // P1 §4.5

    const verdict = problems.length ? "WARN " + problems.join(",") : "PASS";
    const line = `${now} ${verdict} session=${sessionKey} channel=${channelId} chars=${content.length}`;
    try {
      mkdirSync(AUDIT_DIR, { recursive: true });
      appendFileSync(AUDIT_FILE, line + "\n");
    } catch {
      /* best effort */
    }
  } catch {
    /* never let a guard hook disrupt the host */
  }
}

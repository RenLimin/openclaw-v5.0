/**
 * session-boundary-guard — 核心逻辑（零依赖，可单测）
 *
 * 判据：sessionKey 前缀（OpenClaw 稳定契约），不依赖实时状态查询。
 * 决策：approve（软闸门，requireApproval）/ block（硬闸门，直接拒绝）。
 */

import fs from "node:fs";
import path from "node:path";
import os from "node:os";

const AUDIT_DIR = path.join(os.homedir(), ".openclaw", "state");
const AUDIT_FILE = path.join(AUDIT_DIR, "session-boundary-guard.jsonl");
const AUDIT_MAX_BYTES = 1024 * 1024; // 1MB 轮转
const AUDIT_KEEP = 5;

/** 会话 key 前缀分类（agent:<agentId>:<kind>[:...]） */
export function classifyTarget(sessionKey) {
  if (typeof sessionKey !== "string" || sessionKey.length === 0) return "unknown";
  const parts = sessionKey.split(":");
  if (parts.length < 3) return "unknown";
  switch (parts[2]) {
    case "dashboard": return "dashboard"; // pinned/live 会话 → 拦截
    case "subagent":  return "subagent";  // 一次性子会话 → 放行
    case "main":      return "main";      // 主会话 → 放行
    case "cron":      return "cron";      // cron 会话 → 放行
    case "wecom":     return "wecom";     // 渠道会话 → 放行
    default:          return "unknown";
  }
}

/** 审计写入（同步 append，决策优先，失败降级 warn） */
export function audit(sourceSessionKey, toolName, targetSessionKey, decision, mode) {
  try {
    fs.mkdirSync(AUDIT_DIR, { recursive: true });
    if (fs.existsSync(AUDIT_FILE)) {
      const st = fs.statSync(AUDIT_FILE);
      if (st.size > AUDIT_MAX_BYTES) {
        const archive = `${AUDIT_FILE}.${Date.now()}`;
        fs.renameSync(AUDIT_FILE, archive);
        const backups = fs
          .readdirSync(AUDIT_DIR)
          .filter((f) => f.startsWith("session-boundary-guard.jsonl."))
          .sort();
        while (backups.length > AUDIT_KEEP) {
          fs.unlinkSync(path.join(AUDIT_DIR, backups.shift()));
        }
      }
    }
    const line = JSON.stringify({
      ts: new Date().toISOString(),
      sourceSessionKey,
      toolName,
      targetSessionKey,
      decision,
      mode,
    }) + "\n";
    fs.appendFileSync(AUDIT_FILE, line, "utf8");
  } catch (err) {
    console.warn("[session-boundary-guard] audit write failed:", err.message);
  }
}

/** 构造闸门返回（approve / block） */
export function gate(tool, target, config, source) {
  audit(source, tool, target, config.mode === "block" ? "blocked" : "approval", config.mode);
  if (config.mode === "block") {
    return {
      block: true,
      blockReason: `跨会话注入被 session-boundary-guard 拦截：目标 ${target} 是 pinned/live 会话。旁路排查请改用 sessions_spawn(isolated)。`,
    };
  }
  return {
    requireApproval: {
      title: "跨会话注入拦截",
      description: `${tool} → ${target}（pinned/live 会话）。旁路排查请改用 sessions_spawn(isolated)；确需发送请 allow-once 放行。`,
      severity: "warning",
      timeoutMs: 60_000,
      allowedDecisions: ["allow-once", "deny"],
    },
  };
}

/** 决策主函数：输入事件 + 配置，输出 hook 返回或 undefined（放行） */
export function decide(event, config, sourceSessionKey) {
  const tool = event?.toolName;
  const params = event?.params ?? {};
  const allowTargets = Array.isArray(config.allowTargets) ? config.allowTargets : [];

  if (tool === "sessions_send") {
    const target = typeof params.sessionKey === "string" ? params.sessionKey : "";
    if (!target) {
      // 无 sessionKey（label/agentId 定向）→ 目标不可判，保守拦截
      return gate("sessions_send", "(label/agentId 定向，无 sessionKey)", config, sourceSessionKey);
    }
    if (allowTargets.includes(target)) return undefined; // 白名单放行
    const cls = classifyTarget(target);
    if (cls === "dashboard") return gate("sessions_send", target, config, sourceSessionKey);
    return undefined; // subagent/main/cron/wecom → 放行
  }

  if (tool === "sessions_spawn") {
    if (params.visible === true) {
      return gate("sessions_spawn(visible=true)", "(新持久 dashboard 会话)", config, sourceSessionKey);
    }
    return undefined; // 普通 isolated subagent → 放行
  }

  return undefined;
}

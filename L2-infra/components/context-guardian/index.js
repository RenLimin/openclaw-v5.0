import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";
import {
  roughTokenCount,
  extractResultContent,
  estimateParamsTokens,
  middleTruncate,
  shouldMicroCompact,
  getMicroCompactThreshold,
  pressureLevel,
  estimateMessagesTokens,
} from "./core.js";

/**
 * context-guardian v6 — 上下文保护插件（修复版）
 *
 * 修复要点（DESIGN-DETAIL v1.0 §1）：
 *   v5 把微压缩写在 `after_tool_call`，而 host 对该钩子按 Observe 语义处理：
 *   runVoidHook 派发 + emitToolResultOutput 先行 + 返回值不回读 → 改写永远丢弃。
 *   v6 把结果改写迁到 `tool_result_persist`：host 用 `result.message ?? message`
 *   写 transcript，是唯一真正生效的改写点。
 *
 *   `after_tool_call` 保留为纯观测（压力统计），不再做任何 result 改写。
 */

const DEFAULT_EFFECTIVE_CONTEXT_WINDOW = 200_000;
const MAX_EFFECTIVE_CONTEXT_WINDOW = 200_000;
// 会话状态 Map 上限，防止长跑进程内存泄漏（v5 缺陷之一）
const MAX_TRACKED_SESSIONS = 200;

export default definePluginEntry({
  id: "context-guardian",
  name: "Context Guardian",
  description:
    "智能上下文保护插件（修复版）：微压缩作用于 tool_result_persist，结果真正进入 transcript",
  configSchema: {
    type: "object",
    properties: {
      maxToolResultChars: {
        type: "number",
        default: 8000,
        description: "单个 tool result 字符告警阈值",
      },
      compactionThreshold: {
        type: "number",
        default: 0.45,
        description: "estimated tokens 达到窗口此比例时触发 /compact",
      },
      warnThreshold: {
        type: "number",
        default: 0.3,
        description: "warn 压力比例（低于 host 结果上限才有意义）",
      },
      autoLimitExecOutput: {
        type: "boolean",
        default: true,
        description: "exec 自动追加 head 限流",
      },
      execMaxLines: {
        type: "number",
        default: 200,
        description: "exec 默认最大输出行数",
      },
      pressureMonitorEnabled: {
        type: "boolean",
        default: true,
        description: "启用压力监控与提示注入",
      },
      effectiveContextWindow: {
        type: "number",
        default: 0,
        description: "手动指定窗口（0=自动读取）",
      },
      baseOverheadTokens: {
        type: "number",
        default: 15000,
        description: "系统提示等固定开销预估",
      },
      perTurnOverheadTokens: {
        type: "number",
        default: 1200,
        description: "每轮对话开销预估",
      },
      compactionCooldownMs: {
        type: "number",
        default: 60000,
        description: "两次自动压缩的最短间隔（毫秒）",
      },
      microCompactEnabled: {
        type: "boolean",
        default: true,
        description: "启用实时微压缩",
      },
      microCompactMaxChars: {
        type: "number",
        default: 3000,
        description:
          "critical 字符阈值；warn 为此值 ×2.5。必须低于 host 持久化 cap（当前 32000，随上下文窗口分档 16k/32k/64k）",
      },
      microCompactPreserveEditTools: {
        type: "boolean",
        default: true,
        description: "保留 edit/write 等修改类工具完整结果",
      },
      debug: {
        type: "boolean",
        default: false,
        description: "调试日志",
      },
    },
  },
  register(api) {
    const pluginConfig = api.pluginConfig || {};
    const cfg = {
      maxToolResultChars: pluginConfig.maxToolResultChars ?? 8000,
      compactionThreshold: pluginConfig.compactionThreshold ?? 0.45,
      warnThreshold: pluginConfig.warnThreshold ?? 0.3,
      autoLimitExecOutput: pluginConfig.autoLimitExecOutput ?? true,
      execMaxLines: pluginConfig.execMaxLines ?? 200,
      pressureMonitorEnabled:
        pluginConfig.pressureMonitorEnabled ?? pluginConfig.autoCompactEnabled ?? true,
      effectiveContextWindow: pluginConfig.effectiveContextWindow ?? 0,
      baseOverheadTokens: pluginConfig.baseOverheadTokens ?? 15000,
      perTurnOverheadTokens: pluginConfig.perTurnOverheadTokens ?? 1200,
      compactionCooldownMs: pluginConfig.compactionCooldownMs ?? 60000,
      microCompactEnabled: pluginConfig.microCompactEnabled ?? true,
      microCompactMaxChars: pluginConfig.microCompactMaxChars ?? 3000,
      microCompactPreserveEditTools: pluginConfig.microCompactPreserveEditTools ?? true,
      debug: pluginConfig.debug ?? false,
    };
    const logger = api.logger;
    const dbg = cfg.debug
      ? (msg) => logger.info(`[ContextGuardian] ${msg}`)
      : () => {};

    // ── 上下文窗口 ──
    function resolveEffectiveContextWindow() {
      let resolved;
      if (cfg.effectiveContextWindow > 0) {
        resolved = cfg.effectiveContextWindow;
      } else {
        try {
          const runtimeCfg = api.runtime?.config?.current?.();
          resolved = runtimeCfg?.agents?.defaults?.contextTokens;
        } catch {
          /* ignore */
        }
      }
      if (resolved === undefined) resolved = DEFAULT_EFFECTIVE_CONTEXT_WINDOW;
      if (resolved > MAX_EFFECTIVE_CONTEXT_WINDOW) {
        dbg(`contextWindow capped: ${resolved.toLocaleString()} → ${MAX_EFFECTIVE_CONTEXT_WINDOW.toLocaleString()}`);
        resolved = MAX_EFFECTIVE_CONTEXT_WINDOW;
      }
      return resolved;
    }

    // ── 会话状态（有界） ──
    const sessionState = new Map();
    function getOrInitSession(sessionKey) {
      let state = sessionState.get(sessionKey);
      if (!state) {
        if (sessionState.size >= MAX_TRACKED_SESSIONS) {
          const oldest = sessionState.keys().next().value;
          sessionState.delete(oldest);
        }
        state = {
          estimatedTokens: cfg.baseOverheadTokens,
          lastCompactedAt: 0,
          turnCount: 0,
          toolCallsInCurrentTurn: 0,
          pressure: "low",
        };
        sessionState.set(sessionKey, state);
      }
      return state;
    }

    function currentPressure(sessionKey) {
      const state = getOrInitSession(sessionKey);
      return pressureLevel(state.estimatedTokens, resolveEffectiveContextWindow(), cfg);
    }

    // ── before_tool_call：exec 输出限流（防患于未然） ──
    api.on(
      "before_tool_call",
      (event) => {
        if (!cfg.autoLimitExecOutput) return;
        if (event.toolName !== "exec") return;
        const command = event.params?.command;
        if (!command) return;
        if (/\|\s*\b(head|tail|less|more)\b/.test(command)) return;
        if (/--\b(max-results|limit|max-count)\b/.test(command)) return;
        const heavyPattern = /^(ls|find|grep|cat|ps|docker\s+ps|docker\s+logs|kubectl)\b/;
        if (heavyPattern.test(command)) {
          const limited = `${command} | head -${cfg.execMaxLines}`;
          dbg(`auto-limited: "${command.slice(0, 60)}..."`);
          return { params: { ...event.params, command: limited } };
        }
      },
      { priority: 100 },
    );

    // ── before_prompt_build：压力基线 + 临界注入 ──
    api.on(
      "before_prompt_build",
      async (event, ctx) => {
        if (!cfg.pressureMonitorEnabled) return;
        const sessionKey = ctx?.sessionKey;
        if (!sessionKey) return;
        const cw = resolveEffectiveContextWindow();
        const state = getOrInitSession(sessionKey);
        state.turnCount++;
        state.toolCallsInCurrentTurn = 0;

        const messages = event?.messages ?? [];
        const totalTokens =
          messages.length > 0
            ? estimateMessagesTokens(messages, cfg.baseOverheadTokens)
            : state.estimatedTokens;
        state.estimatedTokens = totalTokens;
        state.pressure = pressureLevel(totalTokens, cw, cfg);

        const ratio = (totalTokens / cw) * 100;
        dbg(
          `session=${sessionKey} turn=${state.turnCount} totalTokens=${totalTokens} ` +
            `ctx=${cw} ratio=${ratio.toFixed(1)}% level=${state.pressure}`,
        );

        if (state.pressure !== "critical") return;

        const now = Date.now();
        if (now - state.lastCompactedAt <= cfg.compactionCooldownMs) {
          return {
            appendContext: `[Context Guard] ⚠️ 上下文压力已达 ${ratio.toFixed(1)}%，压缩已排队，请等待下一轮执行。`,
          };
        }
        state.lastCompactedAt = now;
        logger.warn(
          `[ContextGuardian] Critical pressure: ~${totalTokens} tokens (${ratio.toFixed(1)}% of ${cw}). Auto-triggering /compact.`,
        );
        const idempotencyKey = `ctx-guardian-compact-${sessionKey}-${Math.floor(now / cfg.compactionCooldownMs)}`;
        try {
          await api.enqueueNextTurnInjection({
            sessionKey,
            text: "/compact",
            idempotencyKey,
            ttlMs: cfg.compactionCooldownMs,
          });
          return {
            appendContext: `[Context Guard] ⚠️ 上下文已达 ${ratio.toFixed(1)}%，已自动触发 /compact，下一轮开始前将执行压缩。`,
          };
        } catch (err) {
          logger.warn(`[ContextGuardian] Failed to enqueue /compact: ${err}`);
          return {
            appendContext: `[Context Guard] ⚠️ 上下文压力已达 ${ratio.toFixed(1)}%，自动压缩失败，请手动发送 /compact。`,
          };
        }
      },
      { priority: 50 },
    );

    // ── after_tool_call：纯观测（不做 result 改写） ──
    // host 对该钩子按 Observe 处理（runVoidHook，返回值不回读），任何 event.result 赋值都是 no-op。
    api.on(
      "after_tool_call",
      (event, ctx) => {
        const toolName = event.toolName || "?";
        const sessionKey = ctx?.sessionKey;
        if (!sessionKey) return;
        const state = getOrInitSession(sessionKey);
        state.toolCallsInCurrentTurn++;
        state.pressure = currentPressure(sessionKey);

        const paramsTokens = estimateParamsTokens(event.params || {});
        const resultTokens = roughTokenCount(extractResultContent(event.result) ?? "");
        state.estimatedTokens += paramsTokens + resultTokens;
        dbg(
          `tool=${toolName} params=${paramsTokens} result=${resultTokens} ` +
            `contrib=${paramsTokens + resultTokens} running_est=${state.estimatedTokens} ` +
            `pressure=${state.pressure}`,
        );
      },
      { priority: 50 },
    );

    // ── tool_result_persist：真正生效的结果改写点 ──
    // host: transformToolResultForPersistence → runToolResultPersist(...)?.message ?? message
    // 返回 { message } 才会写回 transcript；返回 undefined 保持原样。
    api.on(
      "tool_result_persist",
      (event, ctx) => {
        if (!cfg.microCompactEnabled) return;
        const toolName = event?.toolName || event?.message?.toolName || "?";
        const sessionKey = ctx?.sessionKey;
        const pressure = sessionKey ? currentPressure(sessionKey) : "low";

        if (!shouldMicroCompact(toolName, pressure, cfg)) return;

        const message = event?.message;
        if (!message || message.role !== "toolResult") return;

        const maxChars = getMicroCompactThreshold(pressure, cfg);
        const content = Array.isArray(message.content) ? message.content : [];
        let changed = false;
        let originalTotal = 0;
        let finalTotal = 0;

        const nextContent = content.map((block) => {
          if (!block || block.type !== "text" || typeof block.text !== "string") return block;
          const originalChars = block.text.length;
          if (originalChars <= maxChars) {
            originalTotal += originalChars;
            finalTotal += originalChars;
            return block;
          }
          const compressed = middleTruncate(block.text, maxChars, 0.4, 0.2);
          changed = true;
          originalTotal += originalChars;
          finalTotal += compressed.length;
          return { ...block, text: compressed };
        });

        if (!changed) return;

        const savedPct = Math.round(((originalTotal - finalTotal) / originalTotal) * 100);
        logger.info(
          `[ContextGuardian] Persist-compressed ${toolName}: ${originalTotal.toLocaleString()} → ` +
            `${finalTotal.toLocaleString()} chars (-${savedPct}%) [pressure=${pressure}]`,
        );
        dbg(
          `persist-rewrite tool=${toolName} pressure=${pressure} maxChars=${maxChars} ` +
            `toolCallId=${event?.toolCallId ?? "(none)"}`,
        );
        return { message: { ...message, content: nextContent } };
      },
      { priority: 50 },
    );

    logger.info(
      `[ContextGuardian] v6 loaded: effectiveCtxWin=${resolveEffectiveContextWindow()} ` +
        `compThreshold=${cfg.compactionThreshold} warnThreshold=${cfg.warnThreshold} ` +
        `baseOverhead=${cfg.baseOverheadTokens} perTurn=${cfg.perTurnOverheadTokens} ` +
        `maxResultChars=${cfg.maxToolResultChars} autoLimitExec=${cfg.autoLimitExecOutput} ` +
        `execMaxLines=${cfg.execMaxLines} microCompact=${cfg.microCompactEnabled} ` +
        `low=off warn=${Math.floor(cfg.microCompactMaxChars * 2.5)} crit=${cfg.microCompactMaxChars} ` +
        `rewrite=tool_result_persist debug=${cfg.debug}`,
    );
  },
});

// context-guardian — 纯逻辑核心（零依赖，可单测）
//
// 设计要点（DESIGN-DETAIL v1.0 §2）：
//   - 工具三分类：QUERY（可激进压缩）/ EDIT（保留审计）/ PRESERVE（保留信号）
//   - 截断策略：中间省略，保留头 40% + 尾 20%，并插入可操作提示
//   - 压力阈值：warn = base × 2.5，critical = base
//   - 阈值必须低于 host 持久化 cap，否则永不触发：
//     cap = min(floor(ctxWindow × 0.3) × 4, hardCap)，hardCap 按窗口分档
//     16k / 32k / 64k（ctx<100k / 100k–200k / ≥200k）
//     当前 ctxWindow=196608 → cap=32000（实测 resolveLiveToolResultMaxChars）

// ── 工具分类 ──
// 仅"查询"类工具可截断：结果丢了可以缩小范围重查
export const QUERY_TOOLS = new Set([
  "exec",
  "read",
  "web_fetch",
  "ls",
  "find",
  "grep",
  "cat",
  "head",
  "tail",
]);

// "修改"类工具保留完整结果：审计线索不可丢
export const EDIT_TOOLS = new Set(["edit", "write", "apply_edit", "apply_diff"]);

// 明确保护：搜索结果经过策展，压缩会丢信号
export const PRESERVE_TOOLS = new Set(["web_search"]);

// ── 基础估算 ──
// 中文感知的粗略 token 估算：混合文本约 2 chars/token
export function roughTokenCount(text) {
  if (!text || text.length === 0) return 0;
  return Math.ceil(text.length / 2);
}

// 从任意 result 形态中取出可压缩文本
export function extractResultContent(result) {
  if (typeof result === "string") return result;
  if (typeof result === "object" && result !== null) {
    const r = result;
    if (typeof r.content === "string") return r.content;
    if (typeof r.text === "string") return r.text;
    if (typeof r.output === "string") return r.output;
    if (Array.isArray(r.content)) {
      return r.content
        .map((block) => (typeof block?.text === "string" ? block.text : ""))
        .join("");
    }
    try {
      return JSON.stringify(result);
    } catch {
      return null;
    }
  }
  return null;
}

export function estimateResultChars(result) {
  const content = extractResultContent(result);
  return content ? content.length : 0;
}

// 估算工具参数 token（用于同一轮内的压力增量）
export function estimateParamsTokens(params) {
  try {
    return roughTokenCount(JSON.stringify(params));
  } catch {
    return 200; // 保守兜底
  }
}

// ── 截断原语 ──
/**
 * 中间省略截断：保留头 headRatio、尾 tailRatio，中间插入明确提示。
 * 提示告知被截断的字符数与重试方法（缩小范围）。
 */
export function middleTruncate(text, maxChars, headRatio = 0.4, tailRatio = 0.2) {
  if (text.length <= maxChars) return text;
  const noticeFor = (n) =>
    `\n\n[ContextGuardian: 上下文压力过高，中间 ${n.toLocaleString()} 个字符已被截断。` +
    `如需完整内容，请缩小查询范围（如加 grep 过滤、指定行号、拆分为多次请求）后重试。]\n\n`;
  // 提示长度依赖截断数、截断数依赖提示长度 → 迭代收敛，保证输出总长 ≤ maxChars
  let truncatedCount = text.length;
  let headChars = 0;
  let tailChars = 0;
  for (let i = 0; i < 5; i++) {
    const budget = Math.max(1, maxChars - noticeFor(truncatedCount).length);
    headChars = Math.floor(budget * headRatio);
    tailChars = Math.floor(budget * tailRatio);
    const next = text.length - headChars - tailChars;
    if (next === truncatedCount) break;
    truncatedCount = next;
  }
  return text.slice(0, headChars) + noticeFor(truncatedCount) + text.slice(-tailChars);
}

/**
 * 结构化结果压缩：
 *   - 长数组：保留首尾若干项，中间插入总条数提示
 *   - 其他：退化为对提取文本做 middleTruncate，并保持原结构
 */
export function compressStructuredResult(result, maxChars, preserveRatio) {
  if (Array.isArray(result) && result.length > 10) {
    const headCount = Math.max(3, Math.floor(result.length * preserveRatio * 0.6));
    const tailCount = Math.max(2, Math.floor(result.length * preserveRatio * 0.3));
    const skipped = result.length - headCount - tailCount;
    return [
      ...result.slice(0, headCount),
      `[ContextGuardian: 共 ${result.length} 条，中间 ${skipped} 条已截断。如需完整列表，请添加过滤条件缩小结果范围后重试。]`,
      ...result.slice(-tailCount),
    ];
  }
  const content = extractResultContent(result);
  if (content && content.length > maxChars) {
    const truncated = middleTruncate(content, maxChars, 0.4, 0.2);
    if (typeof result === "string") return truncated;
    if (typeof result === "object" && result !== null) {
      const r = result;
      if (typeof r.content === "string") return { ...r, content: truncated };
      if (typeof r.text === "string") return { ...r, text: truncated };
      if (typeof r.output === "string") return { ...r, output: truncated };
    }
    return truncated;
  }
  return result;
}

// ── 决策 ──
/**
 * 是否应压缩该工具结果。
 *   low：不压缩（避免低压丢信息）
 *   warn：仅 QUERY
 *   critical：QUERY + 未知工具（EDIT / PRESERVE 永不动）
 */
export function shouldMicroCompact(toolName, pressure, cfg) {
  if (!cfg.microCompactEnabled) return false;
  if (pressure === "low") return false;
  if (cfg.microCompactPreserveEditTools && EDIT_TOOLS.has(toolName)) return false;
  if (PRESERVE_TOOLS.has(toolName)) return false;
  if (QUERY_TOOLS.has(toolName)) return true;
  return pressure === "critical";
}

/** 压力级别对应的字符阈值 */
export function getMicroCompactThreshold(pressure, cfg) {
  const base = cfg.microCompactMaxChars;
  if (pressure === "critical") return base;
  if (pressure === "warn") return Math.floor(base * 2.5);
  return Infinity;
}

/**
 * 对文本做压缩，返回 { text, wasCompacted, originalChars, finalChars }。
 * 保持调用方提供的容器结构由 index.js 负责。
 */
export function microCompactText(text, maxChars) {
  const originalChars = text.length;
  if (originalChars <= maxChars) {
    return { text, wasCompacted: false, originalChars, finalChars: originalChars };
  }
  const compressed = middleTruncate(text, maxChars, 0.4, 0.2);
  return {
    text: compressed,
    wasCompacted: true,
    originalChars,
    finalChars: compressed.length,
  };
}

/** 压力级别：estimatedTokens / contextWindow */
export function pressureLevel(estimatedTokens, contextWindow, cfg) {
  const ratio = contextWindow > 0 ? estimatedTokens / contextWindow : 0;
  if (ratio >= cfg.compactionThreshold) return "critical";
  if (ratio >= cfg.warnThreshold) return "warn";
  return "low";
}

/**
 * 从 transcript messages 估算总 token（含系统开销）。
 * 与 host 实际计费可能有偏差，但用于压力分级足够。
 */
export function estimateMessagesTokens(messages, baseOverheadTokens) {
  let total = baseOverheadTokens;
  for (const msg of messages) {
    if (!msg || !msg.content) continue;
    if (typeof msg.content === "string") {
      total += roughTokenCount(msg.content);
    } else if (Array.isArray(msg.content)) {
      for (const block of msg.content) {
        if (!block) continue;
        if (block.type === "text" && typeof block.text === "string") {
          total += roughTokenCount(block.text);
        } else if (block.type === "tool_result") {
          const result =
            typeof block.result === "string"
              ? block.result
              : JSON.stringify(block.result ?? block.content ?? "");
          total += roughTokenCount(result);
        } else if (block.type === "thinking" && block.thinking) {
          total += roughTokenCount(block.thinking);
        }
      }
    }
  }
  return total;
}

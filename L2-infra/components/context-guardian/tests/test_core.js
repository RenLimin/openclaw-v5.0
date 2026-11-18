import { test } from "node:test";
import assert from "node:assert/strict";
import {
  QUERY_TOOLS,
  EDIT_TOOLS,
  PRESERVE_TOOLS,
  roughTokenCount,
  extractResultContent,
  middleTruncate,
  compressStructuredResult,
  shouldMicroCompact,
  getMicroCompactThreshold,
  pressureLevel,
  estimateMessagesTokens,
} from "../core.js";

// 默认配置（与 index.js 对齐）
const CFG = {
  microCompactEnabled: true,
  microCompactMaxChars: 3000,
  microCompactPreserveEditTools: true,
  compactionThreshold: 0.45,
  warnThreshold: 0.3,
};

// ---- 分类与决策 ----

test("G1 QUERY 工具 + warn → 压缩", () => {
  assert.equal(shouldMicroCompact("exec", "warn", CFG), true);
  assert.equal(shouldMicroCompact("read", "warn", CFG), true);
  assert.equal(shouldMicroCompact("web_fetch", "warn", CFG), true);
});

test("G2 EDIT 工具 + critical → 不压缩（审计保留）", () => {
  for (const t of ["edit", "write", "apply_edit", "apply_diff"]) {
    assert.equal(shouldMicroCompact(t, "critical", CFG), false, t);
  }
});

test("G3 PRESERVE 工具 + critical → 不压缩", () => {
  assert.equal(shouldMicroCompact("web_search", "critical", CFG), false);
});

test("G4 low 压力 → 永不压缩", () => {
  for (const t of ["exec", "read", "unknown_tool"]) {
    assert.equal(shouldMicroCompact(t, "low", CFG), false, t);
  }
});

test("G5 未知工具 + warn → 不压缩", () => {
  assert.equal(shouldMicroCompact("mystery_tool", "warn", CFG), false);
});

test("G6 未知工具 + critical → 压缩", () => {
  assert.equal(shouldMicroCompact("mystery_tool", "critical", CFG), true);
});

test("G7 禁用开关 → 全不压缩", () => {
  const off = { ...CFG, microCompactEnabled: false };
  assert.equal(shouldMicroCompact("exec", "critical", off), false);
});

// ---- 阈值 ----

test("G8 阈值：warn = base×2.5，critical = base", () => {
  assert.equal(getMicroCompactThreshold("critical", CFG), 3000);
  assert.equal(getMicroCompactThreshold("warn", CFG), 7500);
  assert.equal(getMicroCompactThreshold("low", CFG), Infinity);
});

test("G9 阈值必须低于 host 持久化 cap（否则永不触发）", () => {
  // host cap = min(floor(ctxWindow*0.3)*4, hardCap)；hardCap 分档 16k/32k/64k
  // 实测：ctxWindow=196608 → cap=32000；ctxWindow=200000 → cap=64000
  // 约束：插件阈值必须 < cap，否则输入永远到不了阈值
  const hostCapFor = (ctx) => {
    const hard = ctx >= 200_000 ? 64_000 : ctx >= 100_000 ? 32_000 : 16_000;
    return Math.min(Math.floor(ctx * 0.3) * 4, hard);
  };
  for (const ctx of [196608, 200000, 128000]) {
    const cap = hostCapFor(ctx);
    assert.ok(getMicroCompactThreshold("warn", CFG) < cap, `warn 阈值必须低于 ctx=${ctx} 的 cap=${cap}`);
    assert.ok(getMicroCompactThreshold("critical", CFG) < cap, `critical 阈值必须低于 ctx=${ctx} 的 cap=${cap}`);
  }
});

// ---- 截断原语 ----

test("G10 middleTruncate 保留头尾并插入提示，且总长不超预算", () => {
  const text = "A".repeat(2000) + "B".repeat(2000) + "C".repeat(2000);
  const out = middleTruncate(text, 1000, 0.4, 0.2);
  assert.ok(out.length <= 1000, `输出长度应 ≤ 预算，实际 ${out.length}`);
  assert.ok(out.startsWith("A".repeat(100)), "头部应保留");
  assert.ok(out.endsWith("C".repeat(50)), "尾部应保留");
  assert.match(out, /ContextGuardian/);
  assert.match(out, /已被截断/);
  assert.match(out, /中间 [\d,]+ 个字符已被截断/);
});

test("G11 middleTruncate 短文本原样返回", () => {
  const text = "short";
  assert.equal(middleTruncate(text, 1000), text);
});

test("G12 数组压缩保留首尾并提示总数", () => {
  const arr = Array.from({ length: 50 }, (_, i) => ({ i }));
  const out = compressStructuredResult(arr, 1000, 0.6);
  assert.ok(Array.isArray(out));
  // headCount = max(3, floor(50*0.6*0.6)) = 18；tailCount = max(2, floor(50*0.6*0.3)) = 9
  assert.equal(out.length, 18 + 1 + 9);
  assert.ok(out.some((x) => typeof x === "string" && x.includes("已截断")));
  assert.deepEqual(out[0], { i: 0 });
  assert.deepEqual(out[out.length - 1], { i: 49 });
});

test("G13 对象结果保持结构", () => {
  const result = { content: "X".repeat(5000), meta: { a: 1 } };
  const out = compressStructuredResult(result, 1000, 0.6);
  assert.equal(typeof out, "object");
  assert.equal(out.meta.a, 1);
  assert.ok(out.content.length < 5000);
  assert.ok(out.content.length > 0);
});

// ---- 估算 ----

test("G14 roughTokenCount 与 extractResultContent", () => {
  assert.equal(roughTokenCount(""), 0);
  assert.equal(roughTokenCount(null), 0);
  assert.equal(roughTokenCount("abcd"), 2);
  assert.equal(extractResultContent("hello"), "hello");
  assert.equal(extractResultContent({ content: "hi" }), "hi");
  assert.equal(extractResultContent({ text: "yo" }), "yo");
  assert.equal(extractResultContent({ content: [{ text: "a" }, { text: "b" }] }), "ab");
});

test("G15 estimateMessagesTokens 含 baseOverhead", () => {
  const msgs = [
    { content: [{ type: "text", text: "x".repeat(100) }] },
    { content: [{ type: "tool_result", result: "y".repeat(100) }] },
  ];
  const total = estimateMessagesTokens(msgs, 1000);
  assert.equal(total, 1000 + 50 + 50);
});

// ---- 压力分级 ----

test("G16 pressureLevel 边界", () => {
  const cw = 100_000;
  assert.equal(pressureLevel(45_000, cw, CFG), "critical");
  assert.equal(pressureLevel(30_000, cw, CFG), "warn");
  assert.equal(pressureLevel(29_999, cw, CFG), "low");
});

// ---- 分类集合不变量 ----

test("G17 三分类互斥（web_search 不在 QUERY）", () => {
  assert.ok(!QUERY_TOOLS.has("web_search"));
  assert.ok(PRESERVE_TOOLS.has("web_search"));
  for (const t of QUERY_TOOLS) assert.ok(!EDIT_TOOLS.has(t), t);
  for (const t of QUERY_TOOLS) assert.ok(!PRESERVE_TOOLS.has(t), t);
});

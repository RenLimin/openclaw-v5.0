// answer-contract-guard 单元测试（版本化，可被 pre-commit 调用）
// 用法: node hooks/answer-contract-guard/test.mjs
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { readFileSync, rmSync } from "node:fs";
import { homedir } from "node:os";

const here = dirname(fileURLToPath(import.meta.url));
const { default: handler } = await import(join(here, "handler.js"));

const AUDIT = join(homedir(), ".openclaw", "state", "answer-contract-audit.log");
try { rmSync(AUDIT); } catch {}

const send = (content) => handler({ action: "sent", context: { content, sessionKey: "s1", channelId: "webchat" } });

send("今天天气不错，晚上吃什么？");                    // 1) 普通聊天 → 不记录
send("【已验证 2026-10-30|ONES】工作项 264 条。\n【推断】合同映射（据编号匹配）。\n溯源链: ONES GraphQL -> items -> 结论"); // 2) 合规 → PASS
send("【已验证|ONES】264 条。\n溯源链: ONES -> 结论");  // 3) 无时间戳 → no_source_timestamp
send("【已验证 2026-09-28|OA】金额 346 万。\n历史报告数据未标注。\n溯源链: OA -> 结论"); // 4) 静默降级 → silent_degrade
send("【已验证 2026-10-30|ONES】264 条。");            // 5) 无溯源链 → no_trace

const lines = readFileSync(AUDIT, "utf8").trim().split("\n").filter(Boolean);
if (lines.length !== 4) { console.error(`❌ 期望 4 条审计，实际 ${lines.length}`); process.exit(1); }
const expect = [["PASS", 2], ["no_source_timestamp", 3], ["silent_degrade", 4], ["no_trace", 5]];
let ok = true;
for (const [tag, ln] of expect) {
  if (!lines.find(l => l.includes(tag))) { console.error(`❌ 行 ${ln} 应含 ${tag}`); ok = false; }
}
console.log(ok ? "✅ answer-contract-guard 单元测试通过" : "❌ 判定不符");
process.exit(ok ? 0 : 1);

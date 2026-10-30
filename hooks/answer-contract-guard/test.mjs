// answer-contract-guard 单元测试（版本化；隔离审计路径，不污染真实日志）
// 用法: node hooks/answer-contract-guard/test.mjs
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { readFileSync, rmSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";

const auditDir = mkdtempSync(join(tmpdir(), "acg-test-"));
process.env.OPENCLAW_ANSWER_AUDIT_DIR = auditDir;          // 接缝：重定向审计输出
const here = dirname(fileURLToPath(import.meta.url));
const { default: handler } = await import(join(here, "handler.js"));
const AUDIT = join(auditDir, "answer-contract-audit.log");

const send = (content) => handler({ action: "sent", context: { content, sessionKey: "s1", channelId: "webchat" } });

send("今天天气不错，晚上吃什么？");                    // 1) 普通聊天 → 不记录
send("【已验证 2026-10-30|ONES】工作项 264 条。\n【推断】合同映射（据编号匹配）。\n溯源链: ONES GraphQL -> items -> 结论"); // 2) 合规 → PASS
send("【已验证|ONES】264 条。\n溯源链: ONES -> 结论");  // 3) 无时间戳
send("【已验证 2026-09-28|OA】金额 346 万。\n历史报告数据未标注。\n溯源链: OA -> 结论"); // 4) 静默降级
send("【已验证 2026-10-30|ONES】264 条。");            // 5) 无溯源链

let ok = true;
let lines;
try { lines = readFileSync(AUDIT, "utf8").trim().split("\n").filter(Boolean); }
catch { lines = []; }
if (lines.length !== 4) { console.error(`❌ 期望 4 条审计，实际 ${lines.length}`); ok = false; }
for (const tag of ["PASS", "no_source_timestamp", "silent_degrade", "no_trace"])
  if (!lines.find(l => l.includes(tag))) { console.error(`❌ 缺少判定 ${tag}`); ok = false; }

rmSync(auditDir, { recursive: true, force: true });       // 清自己的临时目录
console.log(ok ? "✅ answer-contract-guard 单元测试通过（隔离，未触碰真实日志）" : "❌ 判定不符");
process.exit(ok ? 0 : 1);

# Bangcle 合同管理专家 — 开发计划（IMPLEMENTATION-PLAN）

| 项 | 值 |
|---|---|
| 文档 | IMPLEMENTATION-PLAN |
| 版本 | v1.0 |
| 组件编码 | bangcle-contract（CLM-BANGCLE-001） |
| 依据 | PRD §10 / OUTLINE §13 / DETAIL / VERIFICATION v1.0 |
| 前置 | DETAIL 已审；product-kb 已迁入权威仓库（commit 8a6ae5e0） |
| 范围 | MVP 四步分析闭环；OA 回写/多级编排/docx/Web 仅留接口 |

---

## 1. Phase 拆分

| Phase | 内容 | 产出 | 验收 | 工时(h) |
|---|---|---|---|---|
| L4-P1 | 骨架 + 持久化 | `contract_review/` 包、`repository/db.py`（reviews/kb_matches/audit_logs） | init-db 可建表 | 1.5 |
| L4-P2 | 获取 + 数字化 | ingest.py、digitize.py（PDF/docx 直读 + L2 OCR 兜底） | TC digitize 三类文件 | 2.5 |
| L4-P3 | 风险编排 | parser.py（浅解析兜底）、risk.py 调 L3 scan_text | 风险 finding 法条来源受控 | 1.5 |
| L4-P4 | product-kb 满足度 | kb_match.py 接 ContractMatcher，满足度判定 | KB-01~06 | 2.0 |
| L4-P5 | 报告 | report.py（md/xlsx，免责声明） | report 双格式回读 | 1.5 |
| L4-P6 | OA Cube + 浏览器兜底 | services/oa/cube.py、browser_fallback.py（复用 BDMS） | TC-OA-01~04 | 4.0 |
| L4-P7 | CLI + 进度 | cli/contractctl.py 三命令 + 分步进度 | AC-7 | 1.5 |
| L4-P8 | E2E + 安全 + 自测 | tests/e2e、test_no_exfil、黄金样例、幂等 | VERIFICATION §10 | 3.0 |

合计：**17.5h**（建议分 3 个工作段：P1-P3 / P4-P5 / P6-P8）

---

## 2. 依赖与并行

```
P1 ── P2 ── P3 ── P4 ── P5 ── P7 ── P8
                  P6(OA) 可与 P4/P5 并行（独立边界）
```
- P6 依赖：有效 OA storage_state（侦察已产出 state.json）+ BDMS browser_adapter 可引用。
- P8 依赖全部功能完成；黄金样例在 P2 后即可准备。

---

## 3. 复用清单（不重造）

| 能力 | 来源 |
|---|---|
| 风险规则/状态机/金额 | L3 contract-management |
| 产品/SKU/红线匹配 | product-kb ContractMatcher（已在权威仓库） |
| IAM 登录/CDP/iframe 导航 | BDMS browser_adapter / oa_export_playwright |
| OCR | L2 OCR-001 |
| 持久化约定 | L2 SQLite repository 规范 |

---

## 4. 风险与对策

| 风险 | 对策 |
|---|---|
| Cube 附件字段懒加载拿不到 URL | API→浏览器双路径；TC-OA-02 强制验证降级 |
| OA 会话 12h 过期 | storage_state + IAM headless 自愈（TC-OA-03） |
| product-kb 浅解析标的名称对不上 FTS | 低置信标人工确认；aliases 字段兜底，不强行判满足 |
| 原文外泄 | test_no_exfil 出口断言；语义轨默认关 |
| 长任务无进度 | job/分步输出，>10s 必显进度 |

---

## 5. 里程碑

| 里程碑 | 含 | 判定 |
|---|---|---|
| M1 分析闭环（本地文件） | P1-P5+P7+P8 本地部分 | 上传合同出报告，单测全绿 |
| M2 OA 接入 | P6 + OA E2E | 真实 billid 拉取 + 浏览器兜底 |
| M3 验收 | VERIFICATION §10 全部门槛 | 交付 7 步法 + Rex 验收 |

---

## 6. 完成定义

VERIFICATION §10 全部达成；安全测试通过；黄金样例风险项 100% 匹配；CLI 三命令实跑；覆盖率 ≥85%。未达标不报"完成"。

---

## 7. 变更历史

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-10-27 | v1.0 | 初版：8 Phase / 17.5h / 3 里程碑，最大化复用 |

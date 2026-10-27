# Bangcle 合同管理专家 — 验证方案（VERIFICATION）

| 项 | 值 |
|---|---|
| 文档 | VERIFICATION（测试方案，开发前冻结） |
| 版本 | v1.0 |
| 组件编码 | bangcle-contract（CLM-BANGCLE-001） |
| 依据 | PRD-v1.0 §10 + DESIGN-DETAIL-v1.0 |
| 状态 | 待审核 |

> 范围 = **MVP 四步分析闭环**。验收铁律：E2E 用真实文件/真实 product-kb DB/真实（或录制回放的）OA 会话，不用 mock 冒充业务结论；合同原文不外发。

---

## 1. 验收标准（Definition of Done）

| # | 标准 | 验证手段 |
|---|---|---|
| AC-1 | 真实合同（含扫描页）跑通 ingest→digitize→risk→kb_match→report | E2E §3 TC-E2E-01 |
| AC-2 | 风险点结构化：rule_id + 命中原文片段 + 法条依据（仅来自 L3 受控库） | 报告字段断言 |
| AC-3 | 标的清单 → product-kb 真实 DB 匹配 → 满足/部分/不满足 + 红线预警 | 单测+E2E §4 |
| AC-4 | OA Cube 拉取：API 路径与浏览器兜底都验证（真实登录态） | E2E §5 |
| AC-5 | 合同原文全程本地，无外发；公网模型只见脱敏文本（本期语义轨关闭则不调） | 出口流量/调用断言 §6 |
| AC-6 | 审计 append-only；审查记录/匹配落 SQLite | DB 断言 §7 |
| AC-7 | CLI 三命令真实执行，>10s 操作有分步进度 | 实跑 §8 |
| AC-8 | 幂等：同一文件连审 3 次，风险结论/满足度稳定 | 幂等测试 |
| AC-9 | L4→L3 单向依赖；不重写 L3 规则 | grep/AST |

---

## 2. 测试分层

| 层 | 文件 | 说明 |
|---|---|---|
| 单元 | `tests/test_kb_match.py` | 满足度判定，喂真实 product_kb.db（只读） |
| 单元 | `tests/test_parser.py` | 标的/金额/甲乙方浅解析 |
| 单元 | `tests/test_report.py` | 报告结构 + 免责声明必含 |
| 集成 | `tests/test_digitize.py` | PDF 直读 / docx 直读 / 扫描走 OCR（真实 L2） |
| E2E | `tests/e2e/test_review_flow.py` | 完整 CLI 跑真实样例合同 |
| E2E | `tests/e2e/test_oa_cube.py` | storage_state 真连 OA；API 失败自动降级浏览器 |
| 安全 | `tests/test_no_exfil.py` | 原文不离开本机 |

运行：
```bash
python3 -m pytest L4-proprietary/components/bangcle-contract/tests/unit -q
python3 -m pytest .../tests/e2e -q        # 需本地 db + OA 会话，标记 @pytest.mark.e2e
```

---

## 3. 主流程 E2E（AC-1/2）

**TC-E2E-01 扫描合同全流程**（黄金样例：一份含 ≥1 扫描页的真实采购/销售合同，脱敏副本存 `tests/fixtures/`）：

1. `contractctl review --file <fixture.pdf> --source upload`
2. 断言：
   - `digitize.method` 对扫描页为 `ocr`，文本页为 `native_pdf`，`ocr_confidence` 有值
   - 产出的风险 finding 每条含 `id/category/item/status/risk/law`，且 `law` 能在 L3 `CHECK_RULES` 中找到（不允许报告里冒出 L3 规则库之外的法条）
   - `overall_risk ∈ {high,medium,low}`
   - 报告文件落盘（md），含固定免责声明文案
3. 黄金基准：对该 fixture 冻结一份期望风险项集合（rule_id 列表），回归比对。

**TC-E2E-02 docx 合同**：直读路径，`method=docx`，结论结构与 PDF 一致。

---

## 4. product-kb 满足度（AC-3，连真实 DB）

| 用例 | 输入标的 | 期望 satisfaction | 关键断言 |
|---|---|---|---|
| KB-01 | 全部命中在售 SKU、价≥红线 | satisfied | 每项 matched=True，alert 为空 |
| KB-02 | 名称近似但 score≈0.5 | partial | alert 含"需人工确认" |
| KB-03 | 虚构产品（FTS 无候选） | unsatisfied | matched=False |
| KB-04 | 命中但报价低于折扣红线 | unsatisfied/partial | alert 含"价格低于折扣红线" |
| KB-05 | 命中停售 SKU | unsatisfied | alert 含 SKU 状态 |
| KB-06 | product-kb DB 不可达 | 流程不中断 | 报告标注"未做参照"，不静默通过 |

DB 路径默认指向权威仓库 `L4-proprietary/components/product-kb/data/product_kb.db`（gitignored，缺失时用例 skip 并提示）。

---

## 5. OA Cube 拉取（AC-4，真实登录态）

> 不允许用 mock 断言"能拉到合同"。两路径都要真实验证；无网/会话失效时用例标记 skip 并记录原因，不得伪造通过。

- **TC-OA-01 API 路径**：用有效 storage_state，对一个已知 `billid` 调 `cube.get_contract(billid)`，断言能取到主表字段与附件字段引用；附件能下载到本地且字节数>0。
- **TC-OA-02 浏览器兜底**：令 API 路径返回 403/异常（注入故障），断言自动降级 `browser_fallback`，经 CDP + `iframe#mainFrame` 取到同样附件。
- **TC-OA-03 会话过期自愈**：storage_state 失效 → 触发 IAM headless 重登（IMAP 验证码）→ 重试成功，全程无需人工。
- **TC-OA-04 权限不足**：账号无该卡片权限 → 明确报"账号权限"阻塞，**不返回伪造合同数据**。

凭据一律来自 `~/.openclaw/secrets/`，测试不打印 cookie/验证码。

---

## 6. 原文不外发（AC-5）

- 静态：grep 确认 ingest/digitize/parser/risk 链路无指向公网模型 endpoint 的调用。
- 运行期：在测试夹具的网络出口层断言，包含合同原文的请求字节不离开本机（允许 OA 域名拉取附件这一入站方向；禁止把正文 POST 到外部 LLM）。
- 本期语义轨默认关闭；若开启，断言外发内容经脱敏（无甲乙方名称/金额/合同号）。

---

## 7. 持久化与审计（AC-6）

- 一次审查后 `reviews` 1 行 + 每标的 1 行 `kb_matches` + 关键动作有 `audit_logs`。
- append-only：以仅追加方式尝试，断言无 UPDATE/DELETE 审计表的代码路径（grep 仓库对 audit_logs 的写操作只有 INSERT）。
- 重复审查幂等：不产生重复主记录冲突（按内容哈希/合同引用去重）。

---

## 8. CLI 与进度（AC-7）

```bash
contractctl review --file <path>
contractctl review --oa-billid <billid>
contractctl report <review_id> --format md
contractctl report <review_id> --format xlsx
```

- 三命令实跑退出码 0（OA 命令在有会话时）。
- OCR/大文件等 >10s 步骤，stdout 必须出现当前步骤提示（分步进度，遵守进度条铁律）。
- `report --format xlsx` 真实产出可打开文件（用 openpyxl 回读校验）。

---

## 9. 层级与回归（AC-8/9）

- 幂等：TC-E2E-01 连跑 3 次，风险 rule_id 集合与 satisfaction 三次完全一致（时间戳字段除外）。
- 依赖：grep 确认 L4 仅 `import contract_management`(L3) 与 `product_kb`(同级)；L3 目录无 L4 引用。
- 回归：新增测试数 ≥ 本期修复 bug 数（交付 7 步法第 7 条）。

---

## 10. 准入门槛

- 单元测试全绿；E2E 在具备 db/OA 会话的环境全绿（无法满足的环境显式 skip + 留证，禁止伪 pass）
- 黄金样例风险项集合 100% 匹配
- 安全测试（不外发/无凭据泄漏）必须通过
- 覆盖率：L4 编排代码行覆盖 ≥ 85%

---

## 11. 变更历史

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-10-27 | v1.0 | 初版：MVP 四步闭环 E2E + Cube/浏览器双路径 + 不外发安全测试 |

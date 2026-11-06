# VERIFICATION — Palantir Oncology P4：审批链读取器 + 外部写连接器 + 定时对账 v1.0

> L4 · bangcle-contract · Contract Ontology Bridge **P4**（读路径 + 写连接器契约）验收记录
> 版本 v1.0 · 状态：**已验收（Rex 2026-11-06 按实测结果通过）** · Jerry 🦞
> 对应详设：`docs/DESIGN-DETAIL-palantir-p4-reader-v1.0.md`
> 实现提交：`b32cb1f`（7 files, +1312）

---

## 0. 验收结论

Rex 于 2026-11-06 明确验收：**"验收版本 - 按照你的实测结果通过"**。
- P4.1 审批链读取器（浏览器驱动 + 归一化 + 黄金夹具）— **通过**
- P4.3 OaWritebackConnector 契约（dry-run 审计 / 真实写冻结 / 补偿恒不可用）— **通过**
- P4.4 定时对账（只读四态判定，依赖注入）— **通过**
- P4.2 真实写端点 — **暂缓**，作为人工验收测试一环，待测试流程单据 + Rex 二次授权

---

## 1. 验收依据（实测证据链）

### 1.1 单元测试（自动化，全程不触网）
```
$ python3 -m pytest tests/unit/test_oa_approval_log.py -v
19 passed in 0.19s
```
覆盖（19 用例）：
- 黄金夹具归一化：10 条 entries + OA 原始顺序
- 关键业务断言：阚志刚/批准、王仙仙/退回/「请修改产品版本」、何钰其/提交
- opinion 归一化：去 HTML + `&nbsp;` 压缩为单空格
- `current_node` 跳过「抄送」（只读真实流转节点）
- 空 loglist → `ApprovalLogUnavailable`（不伪造审批链）
- 会话失效 → 自动 `refresh_oa_session` 重试一次；重试失败 → 降级
- `OaWritebackConnector`：dry-run apply 零 HTTP、dry_run=False 硬拒绝（RuntimeError）、compensate 恒抛 `CompensationUnavailable`、无 target 抛错
- `reconcile`：四态判定（in_sync/oa_ahead/local_ahead/oa_unknown）+ 只读保证

### 1.2 L4 全量回归
```
$ python3 -m pytest tests/ -x -q
213 passed, 3 skipped in 20.37s
```
既有 `ContractWritebackConnector`（P2 本地表可逆写回）行为不变。

### 1.3 真实环境实测（2026-11-06 午后，P4.0/P4.1 验证）
| 验证项 | 结果 | 证据 |
|---|---|---|
| ecology 会话无人值守重建 | ✅ | `contractctl oa-login`（IAM headless + BDMS IMAP 取码）→ SSO 换票 → state 落盘 → 探针 billid 15134 只读通过 |
| 纯 HTTP 重放 `getRequestLogList` | ❌ 否决 | 5 种 body/头组合均被 `LoadRequestLogDataCmd` 拦截或返回空；4 个签名令牌中 `detailData` 签发源返 500 |
| 浏览器驱动读审批链 | ✅ 定为读路径 | requestid 882663 拿到完整 10 条（节点/处理人/动作/意见/时间） |

### 1.4 安全/卫生审计
- 5 个新文件 + 夹具 grep 敏感字段（signature/secret/authstr/cookie/jsession/token/password/captcha）→ **零命中**
- 无新增第三方依赖（Playwright 为既有依赖，方法内懒加载）
- pre-commit 密钥扫描通过、资产清单自动重生成、知识库 schema 校验通过

---

## 2. 验收范围与冻结点（明确边界）

| 项 | 状态 | 解锁条件 |
|---|---|---|
| P4.1 审批链读取器（读路径） | ✅ 验收 | — |
| P4.3 连接器契约（dry-run / 补偿语义） | ✅ 验收 | — |
| P4.4 对账函数（只读） | ✅ 验收 | 挂 cron 需 OPERATIONS + Rex 拍板频率 |
| P4.2 真实写端点 | ⏸ 暂缓 | 测试流程单据（人工验收一环）+ Rex 二次授权 + 增量文档 `p4-write-v1.1` |
| OaWritebackConnector 接入 ProposalService 编排 | ⏸ 冻结 | 涉及 P3 核心路径，独立详设 + Rex 评审 |

---

## 3. 后续动作

1. P4.2：等测试流程单据后，抓包写端点契约 → 增量 `p4-write-v1.1` → 测试单据白名单验证 → 人工验收。
2. P4.4：对账业务口径确认后（见对账语义说明），挂 cron（默认每 30 分钟、只读、偏差仅报告 + 落审计，不自动写）。
3. 审批人身份映射（OA 工号 ↔ L3 reviewer）：P4.2 落地时按 OA 流程图/节点实现。

---

## 变更历史

- v1.0（2026-11-06）：初版验收记录，Rex 按实测结果通过。

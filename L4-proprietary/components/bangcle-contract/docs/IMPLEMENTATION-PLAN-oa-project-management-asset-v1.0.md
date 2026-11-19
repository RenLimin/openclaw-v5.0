# IMPLEMENTATION-PLAN — OA 项目实施管理批注建议资产 v1.0（待执行）

> 元信息：Jerry 2026-11-19；L4 CME-001；上游 PRD / DESIGN-OUTLINE / DESIGN-DETAIL 三份。
> 执行纪律：先写权威源（`L4-proprietary/skills/...` / `L4-proprietary/components/...`），
> 提交用隔离 index；sandbox `skills/` 只读镜像，不作编辑目标。

## 0. 依赖顺序

```
P1 license_period 修复（独立，可单独上线）
  └─> P2 三流程解析（fields/order）
        └─> P3 ONES 参考项目 + 风险 + 渲染
              └─> P4 757 异常备注（仅 916）
                    └─> P5 CLI + E2E
```

P1 阻塞 P3（授权期限是渲染必填项）；P2 阻塞 P3/P4；P4 依赖 P2（要 13682 rid）。

## 1. P1 — `license_period` 修复（D1）

**文件**：`L4-proprietary/skills/ones-browser-export/scripts/oa_workflow_ones.py`

**现状**（第 95-103 行 + `LICENSE_RANGE` 第 93 行）：
```python
LICENSE_RANGE = re.compile(r"授权(?:时间|期限)\s*[:：]\s*(\d{4}[.\-/]\d{1,2}[.\-/]\d{1,2})\s*[-~至到]\s*(\d{4}[.\-/]\d{1,2}[.\-/]\d{1,2})")
```
只认 ISO，中文日期全丢；且命中首个任务即返回（未取最晚）。

**改法**：
1. 新增 `_CN_DATE` / `_ISO_DATE` 两个正则 + `_pick_dates(text)`（按出现位置排序收集）。
2. `license_period(tasks)` 改为**跨任务聚合**：定位「授权时间/授权期限/授权周期/授权区间」关键字后的日期段 → 取首日为起、末日为止 → 多任务按结束日取**最晚**。
3. 返回签名不变 `(区间文本, 证据号)`，`build_block` 无需改。

**回归（2026-11-19 实测，单测 20/20）**：
| 输入文本 | 期望 |
|---|---|
| `授权时间：2026年8月11日 至 2027年8月11日` | `2026-08-11 ~ 2027-08-11` |
| `授权时间：2026年11月18号至2026年11月30号` | `2026-11-18 ~ 2026-11-30` |
| `授权期限：2026-08-11 ~ 2027-08-11` | 回归不破 |
| `服务期：2026年10月14日-2026年11月14日` | `2026-10-14 ~ 2026-11-14`（服务期兜底） |
| 5 个参考项目实测 | **3/5 非空**（858/2598 无授权记录 → 【缺失】） |

**实测证据**：
| 参考项目 | 类型 | 结果 |
|---|---|---|
| SSXM-2026-0810-2066 | 签约 | `2026-08-11 ~ 2027-08-14`（#385446） |
| SSXM-2026-0624-1641 | 提前实施 | `2026-11-18 ~ 2026-11-30`（#399765） |
| SSXM-2026-1014-2727 | POC | `2026-10-14 ~ 2026-11-14`（#392586，服务期兜底） |
| SSXM-2025-0403-0858 | 安全服务 | 【缺失】（无 license 任务） |
| SSXM-2026-0924-2598 | 结算 | 【缺失】（无 license 任务） |

**测试**：`tests/unit/test_license_period.py`（纯函数离线，20 用例）。

## 2. P2 — 三流程解析

**文件**：`services/oa/enhance/pm/fields.py`、`order.py`

- `fields.py`：三份映射常量（§3 表）+ `resolve(workflow_id) -> FieldMap`。
- `order.py`：`parse(raw_dir, request_id, workflow_id)` → `ProjectOrder`；
  浏览框取值复制 `oa_form._value` 语义（优先 `specialobj[0].name`）；
  `xhrs.json` 多 `loadForm` 响应取 **body 最大**者（实测 886453：402542 vs 12 字节）。
- 回归：886453/886362/886314 三单字段全对。

## 3. P3 — ONES 参考项目 + 风险 + 渲染

**文件**：`pm/ones_refs.py`、`pm/risk.py`、`pm/render.py`

- `ones_refs` 复用 `ones_client`（已封装 `gql`/`project_by_code`/`project_tasks`），**不重写自动化**。
- 状态推断规则表（DETAIL §5.1）；授权期限调用修复后的 `license_period`。
- `risk.py` 6 个风险码（DETAIL §7），纯函数。
- `render.py` 三段式（DETAIL §8），纯函数。
- 回归：886362/886404/886368/886314 回放与 Rex 批注同构。

## 4. P4 — 757 异常备注（仅 916）

**文件**：`pm/approval_notes.py`

- 复用 `approval_log.ApprovalLogReader`；`ApprovalLogUnavailable` → `degraded`。
- 回归：885637 无权限不抛错；885641/885784 提取 AI 意见。

## 5. P5 — CLI + E2E

**文件**：`cli/contractctl.py`（子命令 `oa-project-mgmt`）

```
contractctl oa-project-mgmt --requestid <rid> [--pm <名>] [--raw-dir <dir>]
contractctl oa-project-mgmt --discover
```
E2E：真实 OA 只读捕获 + ONES 真实 HTTP；禁止 TestClient 式伪请求。

## 6. 每 Phase 出口（Definition of Done）

| Phase | DoD |
|---|---|
| P1 | 单测全绿 + 5 项目实测非空 + `git show --stat` 仅含目标文件 |
| P2 | 3 单回放字段比对通过 |
| P3 | 4 单渲染同构 + 风险码命中 |
| P4 | 无权限降级 + 2 单提取成功 |
| P5 | CLI 跑通 + AC1~AC8 全绿 |

## 7. 风险与回滚

- P1 改的是已交付脚本 → 只加正则与聚合，**不动** `build_block`/`gql`/捕获逻辑，可整体回滚。
- 每 Phase 独立提交，出问题按 commit 回退。
- 提交前 secret scan + 隔离 index；不夹带他人改动。

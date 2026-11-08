---
name: bangcle-project-report
description: "Bangcle 项目汇报材料生成：输入「客户 + 周期 + 受众」，从 ONES/合同台账取数，经完整取数→口径清洗→多维汇总→目标闭环→溯源审计→受众适配，产出数字可点账、结论可溯源的项目汇报材料（Markdown，可导出 docx）。当用户要求生成/整理某客户或项目集的年度/季度汇报材料、服务情况汇报、交付总结时使用。"
user-invocable: true
metadata:
  openclaw:
    layer: L3
    domain: project-management
---

# Bangcle 项目汇报材料生成技能

> **业务目标**：把建行年度汇报实战的取数与成文做法固化为可复用技能——输入「客户 + 周期 + 受众」，产出**数字可逐行点账、结论可溯源、适配受众**的项目汇报材料。
>
> 本技能复用 `bangcle-project-summary` 的台账与 ONES 取数方法，不重造数据底座。

> **统一入口**：本技能是 L4 层 **Bangcle 项目管理专家**（`bangcle-project-manager-expert`，PJME-001）路由的专项能力之一。

## When to Use

- 年度/季度向**甲方**汇报某客户整体项目服务情况（对外版）
- 向**公司管理层/销售负责人**汇报某大客户在手合同的交付进展与目标达成（内部版）
- 单个重大项目**验收前**，汇总交付记录并闭合到立项目标实现情况

## Hard Rules

1. **完整性可举证**：取数先枚举项目、分页取全、校验触顶；禁止单次全局查询作为最终口径。
2. **口径正确**：严格区分"实际工作"（5 类）与"履约范围/建档记录"（6 类）；严格限定统计周期（按 createTime）。
3. **账账可反推**：所有汇总数量均可由明细行筛选精确反推；明细每个数量逐条罗列。
4. **零编造**：每个数字/名词/日期机器溯源；价值论述明确标"基于事实的推断"。
5. **受众适配**：对外版自动脱敏内部系统名/编号/商务条款，名称一律取官方正式名。
6. **fail-closed**：溯源审计 exit≠0 不得交付。
7. **不自动外发**：邮件/群发等外发副作用必须人工确认（红线）。
8. **凭据/账号/密码绝不写入产出**。

## Workflow（S1→S8）

### S1 范围界定
- 按"签约 + 服务期内 / 到期未验收未结项"规则圈定合同与项目。
- 输出范围清单与排除项理由。
- **完成判据**：项目清单（编号/合同/服务期）确认无遗漏。

### S2 完整取数
- 逐项目枚举 + 分页取全 + 触顶校验。
- 合并实时 `Project._7KF6tXvk` 合同字段。
- 产出快照与完整性证据。
- **完成判据**：`fetched == total`，`hitCap=false`。

### S3 口径清洗
- 时间戳归一（微秒/毫秒/秒 → Asia/Shanghai）。
- 剔除 6 类建档/范围记录（`isWork=false`）。
- 按 createTime 卡周期（`inPeriod`）。
- **完成判据**：剔除记录数与黄金基准一致（64 条）。

### S4 多维汇总
- 按工作类别 / 产品方向 / 时间周期三维汇总。
- 明细逐条罗列（时间排序）。
- **完成判据**：三维 total 相等且 = 明细数；done+wip=total。

### S5 目标闭环
- 维保类目标挂服务事项、采购新建类目标挂部署/授权交付记录。
- 逐条给目标实现状态（受控枚举）。
- 在途事项按方向归并，写进展+方案。
- **完成判据**：每个签约方向都有 realizationLevel，无悬空格。

### S6 价值论述
- 基于真实交付的价值提炼，明确"基于事实的推断"。
- 措辞可配置（保留/降级）。
- **完成判据**：价值论述句均在标注区。

### S7 溯源审计
- 机器核对全文数字/名词/日期是否命中原始数据。
- 输出无源项清单（fail-closed）。
- **完成判据**：`audit_provenance.py` exit=0（PASS）。

### S8 受众适配
- 内部版/对外版切换。
- 对外脱敏内部系统名编号与商务条款，名称取官方名。
- **完成判据**：对外版脱敏词表 grep=0。

## 标准操作流程

```bash
cd L3-business/skills/bangcle-project-report

# 1) 取数
echo '{"customer":"中国建设银行股份有限公司",
       "period":{"start":"2026-01-01","end":"2026-12-31"},
       "audience":"external"}' \
 | python3 scripts/fetch_project_tasks.py > /tmp/stage1.json

# 2) 清洗分类
python3 scripts/normalize_and_classify.py < /tmp/stage1.json > /tmp/stage2.json

# 3) 汇总明细（含对账，失败 exit 2）
python3 scripts/aggregate.py < /tmp/stage2.json > /tmp/stage3.json

# 4) 目标矩阵
python3 scripts/build_goal_matrix.py < /tmp/stage3.json > /tmp/stage4.json

# 5) 渲染 + 脱敏
python3 scripts/render_report.py --audience external --output /tmp/report.md < /tmp/stage4.json

# 6) 溯源审计（fail-closed）
echo '{"report_md":"/tmp/report.md","detail":[...],"contracts":[],"audience":"external"}' \
 | python3 scripts/audit_provenance.py
```

## 黄金基准

| 项 | 基准值 |
|---|---|
| 原始任务（16 项目） | 907 条 |
| 建档/范围记录（剔除） | 64 条 |
| 实际工作 | 113 |
| 已完成 / 在途 | 104 / 9 |
| 类别账 | 66/17/19/7/4 |
| 产品账 | 44/34/19/10/3/2/1 |
| 季度账 | 76/5/32 |

> 任一版本回归必须先复现该表，再允许新增能力。基准文件：`assets/golden/golden-baseline.json`。

## 相关技能

- 数据获取：`ones-browser-export`、`bangcle-project-summary`
- 标准产品基线：`product-kb`
- PPT 生成：`bangcle-ppt`
- 履约义务汇总：`bangcle-obligation-summary`
- 项目复盘：`bangcle-project-retrospective`
- 客户画像：`bangcle-customer-profile`

## 验证

- [ ] 取数 `fetched == total`，`hitCap=false`
- [ ] 三维汇总 total 相等且 = 明细数
- [ ] 溯源审计 exit=0
- [ ] 对外版脱敏词表 grep=0
- [ ] 黄金基准 8 行全部复现
- [ ] 全流程无外发副作用

## 应答规范（ADR-035 强制引用）

> 本技能输出口径必须遵循以下应答契约：
>
> 1. **P1 通用应答契约**：`../../../L2-infra/prompts/answer-spec-base.md`
> 2. **P2 域应答契约**：`../../prompts/project-answer-spec.md`
>
> 契约优先于本 SKILL 内任何自定义口径。
>
> **fail-closed 机器校验（强制）**：报告落盘后运行
> `python3 ../../../L2-infra/prompts/tools/check_answer_contract.py <报告路径>`
> exit≠0（BLOCK）→ 修正后重跑，禁止交付。

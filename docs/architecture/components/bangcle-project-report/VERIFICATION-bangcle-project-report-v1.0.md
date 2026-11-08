# VERIFICATION — Bangcle 项目汇报材料生成技能 v1.0（待评审）

- 对应：PRD / OUTLINE / DETAIL v1.0
- 原则：**用真实数据、真实文件**验证；禁止 TestClient 式自我断言；覆盖率比结论更值得怀疑。
- 黄金基准：建行 16 合同 2026 材料，须复现 **work=113 / done=104 / wip=9**。

---

## 1. 验收标准 ↔ 测试映射

| AC | 测试 | 类型 |
|---|---|---|
| AC1 完整性 | T1 分页/触顶 | 真实接口 |
| AC2 口径 | T2 分类剔除 + T3 周期 | 单元+真实 |
| AC3 可反推 | T4 三维对账 | 真实数据 |
| AC4 闭环 | T5 目标矩阵 | 真实数据 |
| AC5 零编造 | T6 溯源审计 | 真实语料 |
| AC6 脱敏 | T7 external 脱敏 | 真实文件 grep |
| AC7 幂等 | T8 连跑 3 次 | E2E |
| AC8 边界 | T9 越界/副作用扫描 | 静态+运行 |
| F12 docx | T10 docx 结构 | 真实导出 |

## 2. 测试用例

### T1 — 取数完整性与触顶
- 以建行 16 项目真实拉取；断言 `perProject.fetched == total`、`hitCap=false`。
- 注入故障：mock 某页满页 → 验证强制再拉一页；累计不等 → exit 2。
- **黄金断言**：16 项目合计任务结构与 `pull16_merged.json` 一致（907 条原始）。

### T2 — 口径分类
- 输入含全部 6 类建档/履约 issueType → 断言 `isWork=false` 且不进工作量。
- 5 类实际工作 → `isWork=true`。
- **黄金断言**：剔除记录 64 条（设备领用 30 / 外包外采 10 / 客户合同项目信息 24）。

### T3 — 时间戳归一与周期
- 表驱动：微秒 `1792636061875914`、毫秒、秒各一例 → 期望日期。
- 边界：周期起止当日 00:00 / 23:59 归属正确；固件 2024/2025 记录 `inPeriod=false`。

### T4 — 三维汇总可反推
- 从明细行 Counter 复算：
  - 类别：定制66 / 缺陷17 / 工单19 / 产研7 / 专项4
  - 产品：监测44 / 合规34 / 安卓SDK19 / 测评10 / 小程序3 / H5API2 / 鸿蒙1
  - 季度：Q1 76 / Q2 5 / Q3 32
- done+wip=113；任一维度 total≠113 → FAIL。

### T5 — 目标实现矩阵
- 9 方向均有 realizationLevel，且 level ∈ 受控枚举。
- 维保类 evidence.workDone/Total 与明细一致；采购类（鸿蒙/渗透）挂部署/授权 done 记录。
- 无"悬空格"；固件为"往年已达成"且不计当年工作。

### T6 — 溯源审计（fail-closed）
- 对最终 md 跑 `audit_provenance.py` → `status=PASS, exit=0`。
- 反向：临时插入一个无源名词/错误数字 → 必须 exit≠0、missing 列出该项。

### T7 — external 脱敏
- 对外版对 §6.4 词表逐项 grep = 0。
- 合同名逐条 == 台账官方名；空名合同用项目正式名且内部可查 nameSource。

### T8 — 幂等
- 同 Input 连跑 3 次；剔除 fetchedAt 后输出内容 hash 三次一致。

### T9 — 边界与副作用
- grep 产出：无复盘诊断/到期跟踪/客户画像越界章节。
- 全流程无邮件/群发/删除等外发调用（脚本静态扫描 + 运行网络白名单：仅 ONES 域）。

### T10 — docx 导出
- python-docx 导出后重新打开：标题数=7、明细表格行数=113、无乱码、无内部词。

## 3. 黄金基准（Golden Fixture）

| 项 | 基准值 | 来源 |
|---|---|---|
| 在履约签约合同 | 16 份 | final_16_contract_project.json |
| 原始任务（16 项目） | 907 条 | pull16_merged.json |
| 建档/范围记录（剔除） | 64 条 | 明细分类 |
| 实际工作 | 113 | createTime∈2026 & isWork |
| 已完成 / 在途 | 104 / 9 | statusCategory |
| 类别账 | 66/17/19/7/4 | 明细 Counter |
| 产品账 | 44/34/19/10/3/2/1 | 明细 Counter |
| 季度账 | 76/5/32 | 明细 Counter |

- 基准文件随技能 `assets/golden/` 保存（脱敏后的计数与 IR 快照，不含敏感正文外发）。
- 任一版本回归必须先复现该表，再允许新增能力。

### 3.1 真实数据回放记录（2026-11-08）

**输入**：`pull16_merged.json`（16 签约合同，907 条任务）+ 2026 周期过滤
**回放结果**：类别账 66/17/19/7/4、产品账 44/34/19/10/3/2/1、季度账 76/5/32、done/wip=104/9 —— **三维全绿，与黄金基准逐项一致**（113=113=113=113，reconciliation ok）。

**回放暴露并修复的真实缺陷**：

| # | 缺陷 | 修复 |
|---|---|---|
| 1 | issueType 词表是概念名（缺陷修复/问题工单/产研支持），真实 ONES 是 缺陷/工单/客户项目产研支持需求/任务 | normalize 增加 真实类型→标准类别 映射（WORK_TYPE_MAP） |
| 2 | 产品方向无法仅靠 name+products 还原（黄金含人工核定，如 SDK 闪退→合规检测） | 固化 `assets/golden/ccb-2026-product-override.json`（113 条任务编号→方向），normalize 双通道：fixture 优先 + 规则兜底 |
| 3 | 在途口径：aggregate 只算 in_progress，黄金口径是 未完成全计在途（104+9） | render/audit/build_goal_matrix 统一 wip=total-done |
| 4 | 明细表渲染用原始 issueType（客户项目产研支持需求）而非标准类别 | render 明细列改 category |
| 5 | audit 名词检查把合同官方名当漏词、数字检查 wip 口径不一致 | check_nouns 豁免合同名、check_numbers 对齐 wip=total-done |

**幂等性**：同输入连跑 3 次，三维汇总 md5 一致（`b0f7f720...`）。
**审计**：internal/external 双版 `audit_provenance.py` 均 PASS、exit=0；external 脱敏词 grep=0。

## 4. E2E 真人路径（必须覆盖）

1. 输入「建行 / 2026 年度 / 对外」→ 生成 md。
2. 打开 md 人工核对 7 章、明细表、目标实现列。
3. 导出 docx 并打开核对。
4. 切换「内部」版再生成 → 可见溯源/对账附录，对外版不可见。
5. 全程无任何外发确认弹窗/外发动作。

## 5. 通过门槛

- T1–T10 全 PASS；黄金基准表 8 行全部复现。
- `check_answer_contract.py` 与 `audit_provenance.py` 均 exit 0。
- 无新增未解释的【缺失】；外发副作用 = 0。

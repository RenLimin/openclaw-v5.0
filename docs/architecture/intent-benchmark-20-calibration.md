# 意图基准集 20 条 · 定标说明（待 Rex 备注）

> 产物：能力路由与编排层（ADR-037 / PRD §4.2 / DESIGN-OUTLINE fixtures）
> 定标人：**Rex**（gateway-owner / Limin Ren，2026-11-27 拍板「由我来确定」）
> 日期：2026-11-27
> 本文件用途：**逐条确认 `expected_top1` / `expected_set` / `expected_mode`**；Rex 直接在每条 `备注` 列填写裁决，或在本文件末尾「整体口径备注」补充。
> 最终 YAML 落点：`L2-infra/components/capability-router/tests/fixtures/intent-benchmark-20.yaml`

---

## 1. 定标口径（请先确认这一节）

| 字段 | 含义 | 取值 |
|---|---|---|
| `expected_top1` | 该意图下**应当排第一**的能力（skill id 或组件 id） | 真实存在的 id |
| `expected_set` | 该意图下**允许进入候选集**的 id 集合（top-k 期望命中集） | id 列表 |
| `expected_mode` | planner 应判定的执行模式 | `skill` / `agent` / `dag` |

三类覆盖（PRD §4.2 硬要求）：
- **A 类 · 单 skill 直达**：意图清晰、单一 skill 可满足
- **B 类 · 多 skill 竞争**：同一意图命中 ≥3 个候选，考精排（**争议集中在这一类**）
- **C 类 · 需 DAG 编排**：需 ≥2 步且有依赖

裁决原则：
1. **业务口径优先于名称相似度**——以「用户真正想拿到的产出物」为准。
2. 同类多入口时，**统一入口优先于子能力**（`*-manager-expert` > 具体子技能）。
3. 命中 ≥3 候选且产出物不同 → 视为**真竞争**（B 类）；产出物相同/近似 → 归并为同一 `expected_set`，取更权威者作 top1。
4. B 类存在无法用规则判定、需人工语义判断的条目 → **必须由 Rex 明确系统口径**，不得由实现方自定。

---

## 2. A 类 · 单 skill 直达（7 条）

| # | 意图 | expected_top1 | expected_mode | 备注 |
|---|---|---|---|---|
| A-1 | 「把这段会议录音整理成正式纪要」 | `meeting-minutes` | skill | |
| A-2 | 「把这份扫描件 OCR 成文字并检出签名印章」 | `ocr-digitalization` | skill | |
| A-3 | 「把这个 PDF 拆成两半并加水印」 | `pdf-toolkit` | skill | |
| A-4 | 「查一下张三的企业微信联系方式」 | `wecomcli-contact` | skill | 另有同名 plugin skill，口径待定：走自建还是 plugin？ |
| A-5 | 「生成本月家庭记账报表」 | `fin-l4` | skill | |
| A-6 | 「查一下『合同』相关的能力和权威入口」 | `capability-registry`（组件） | skill | 用于验证 `--strict` 权威仲裁（Lane A） |
| A-7 | 「评估一下当前系统健康状态」 | `system-health-check` | skill | |

---

## 3. B 类 · 多 skill 竞争（7 条，**争议区**）

| # | 意图 | 候选（≥3） | expected_top1（建议） | 备注 |
|---|---|---|---|---|
| B-1 | 「生成项目复盘报告」 | bangcle-project-retrospective / customer-rectification-report / system-governor | `bangcle-project-retrospective` | PRD 原例。区别：retrospective=内部分析型复盘；rectification=对外承诺型整改 Word；governor=系统治理 |
| B-2 | 「汇总某客户全部交付记录」 | bangcle-project-summary / customer-delivery-intelligence / bangcle-customer-profile | `bangcle-project-summary` | summary=台账导出；delivery-intelligence=统一入口含验收回款；profile=画像分析 |
| B-3 | 「汇总某客户履约义务与授权/维保到期」 | bangcle-obligation-summary / customer-delivery-intelligence / bangcle-project-summary | `bangcle-obligation-summary` | 唯一定位到「授权/维保到期日期提取」 |
| B-4 | 「梳理系统架构缺陷并出整改方案」 | system-governor / system-health-check / dag-orchestrator | `system-governor` | health-check 只读体检；governor 出治理方案；dag 是引擎不是结论 |
| B-5 | 「生成项目汇报材料」 | bangcle-project-report / bangcle-project-summary / customer-delivery-intelligence | `bangcle-project-report` | report=汇报材料生成；summary=台账汇总 |
| B-6 | 「设计一个多步骤工作流」 | dag-orchestrator / system-governor / role-library | `dag-orchestrator` | 编排器本身 |
| B-7 | 「查某个产品/功能的官方口径与 SKU 信息」 | product-kb / product-manager-expert / bangcle-ppt | `product-kb` | 统一入口 vs 底层组件口径：建议 top1=`product-kb`（直达），入口类降权 |

> **需你拍板的争议项**：B-1（rectification 是否算竞品）、B-4（governor vs dag）、B-7（入口是否应优先于组件）。

---

## 4. C 类 · 需 DAG 编排（6 条）

| # | 意图 | expected_top1 | 编排步骤 | expected_mode |
|---|---|---|---|---|
| C-1 | 「生成交付月报」 | `customer-delivery-intelligence` | 采集×N → 关联 → 分析 → 报告 | dag |
| C-2 | 「按客户出交付汇报包（含验收+回款）」 | `customer-delivery-intelligence` | 取原始文件 → 人工闸 → 渲染包 | dag |
| C-3 | 「生成项目汇报材料并溯源」 | `bangcle-project-report` | ONES 取数 → 口径清洗 → 汇总 → 受众适配 | dag |
| C-4 | 「合同审查并走审批框架」 | `contract-approval` | 解析 → 风险扫描 → 审批链 | dag |
| C-5 | 「做 BDMS 确收预算预测」 | `bdms-revenue-forecast` | 财报输入 → 口径 → 预测表 | dag |
| C-6 | 「跑一遍系统全量审计」 | `system-governor` | 多层探针 → 汇总 → 缺陷台账 | dag |

---

## 5. 备注区（请在此直接写）

### 5.1 整体口径备注
<!-- 例：B 类一律以「产出物形态」而非「关键词命中」判定；入口类 skill 的权重规则为…… -->

### 5.2 逐条裁决
<!-- 格式：B-1 = 同意 / 改为 customer-rectification-report，理由：…… -->

### 5.3 缺失意图（如需增删条目）
<!-- 例：缺「跨平台消息发送」类；缺「PPT 生成」类（现仅 A 类有 bangcle-ppt 隐含） -->

---

## 6. 参考取证

- 28 个自建 skill 实测清单（`ls L{2,3,4}-*/skills/*/`）：bangcle-customer-profile / bangcle-obligation-summary / bangcle-ppt / bangcle-project-manager-expert / bangcle-project-report / bangcle-project-retrospective / bangcle-project-summary / bdms-revenue-forecast / bdms-web-ui-design / contract-approval / contract-manager-expert / customer-delivery-intelligence / customer-rectification-report / dag-orchestrator / fin-l4 / meeting-minutes / model-scheduling / ocr-digitalization / ones-browser-export / ontology-identity-gate / pdf-toolkit / product-kb / product-manager-expert / role-library / system-governor / system-health-check / web-ui-design / wecomcli-contact
- mode 枚举依据：DESIGN-OUTLINE §模块表 `planner | 判定 mode ∈ {skill, agent, dag}`
- 定标人拍板记录：2026-11-27 gateway-owner（Limin Ren）「Q-2 20 条意图基准集由谁定标：由我来确定」

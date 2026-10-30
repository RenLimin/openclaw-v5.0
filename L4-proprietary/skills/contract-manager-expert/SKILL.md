---
name: contract-manager-expert
description: "Bangcle 合同管理专家 — L4 层 Bangcle 合同管理相关的统一入口。合同智能审查（全文扫描/数字化/22 条风险规则）、合同标的产品知识库参照、泛微 OA Cube 合同拉取、销售合同审批工作流（OCR/条款拆解/分级审批/合同生成）的意图识别与路由协调。当用户提出 Bangcle 合同审查、合同风险、合同标的匹配、销售合同审批、OA 合同拉取等需求时使用。产品咨询、PPT 生成、项目交付管理、收入确认不属于本入口。"
metadata:
  openclaw:
    emoji: "📑"
    os: ["darwin", "linux"]
    requires:
      components: ["bangcle-contract (L4)"]
    layer: L4
    component_id: CME-001
---

# Bangcle 合同管理专家 (Contract Manager Expert)

面向 Bangcle 销售合同全生命周期的专家角色，是 **L4 层 Bangcle「合同管理相关」的统一入口**：
**合同智能审查与风险扫描直接产出结论**，并路由协调合同域的审批框架、通用合同逻辑与 Office 合同流程能力。

> 边界：本入口只管**合同管理相关**（合同审查/风险扫描/标的参照/OA 拉取/销售合同审批/合同生成）。产品咨询、PPT 生成、项目交付管理、收入确认不属本入口（见 §边界外）。

## 一、合同管理统一入口路由表（强制）

任何 **Bangcle 合同管理相关**需求，先按下表路由。命中本技能核心职责（智能审查/风险/标的参照）→ 直接处理；审批框架/通用逻辑/Office 流程 → 路由对应资产。

| 合同管理需求 | 处理 / 路由去向 | 层 | 说明 |
|---|---|---|---|
| 合同智能审查 / 风险扫描 / 审查报告 | **本技能**（`bangcle-contract`，CLM-BANGCLE-001，CLI: `contractctl`） | L4 | 核心职责：ingest→digitize→risk→kb_match→report |
| 合同标的 → 产品知识库参照（满足/部分/不满足 + 红线） | **本技能** 调 `product-kb`（contract 匹配模块） | L4→L4 | bangcle-contract 内部已集成；含近似名 partial、停售 SKU 红线 |
| 泛微 OA Cube 拉合同（billid 拉取/附件下载/浏览器兜底） | **本技能**（`bangcle-contract/services/oa`） | L4 | API→浏览器自动兜底；`contractctl oa-login` 建会话 |
| 销售合同审批工作流（OCR 识别/条款拆解/分级审批/Excel·Word 生成） | `contract-approval`（SCA-001） | L3 | 通用审批框架能力 |
| 通用合同纯逻辑（状态机/风险规则库/分级审批/金额工具/OA 连接器抽象） | `contract-management`（CLM-GEN-001） | L3 | 框架/代码层能力，L4 合同审查的规则与法条来源（CHECK_RULES） |
| 企业 Office 销售合同审批全流程（起草→审批→归档） | `office-contract`（OFC-001） | L4 | Office 场景的合同审批专有实例 |

命中多个合同需求 → 本技能统一协调、串联执行。跨到非合同域（产品/PPT/项目/收入）→ 按 §边界外 提示转对应能力，本入口不代办。

### 典型串联编排

| 场景 | 编排顺序 |
|---|---|
| 从 OA 拉一份销售合同并出审查报告 | `contractctl oa-login`（建会话）→ review `--oa-billid`（OA 拉取→数字化→风险→标的参照→报告） |
| 本地合同（含扫描页）审查 | review `--file <合同>`（OCR 数字化→22 条风险规则→product-kb 标的参照→md/xlsx 报告） |
| 合同审查 + 走正式审批归档 | bangcle-contract（审查结论）→ contract-approval / office-contract（审批流与归档） |

## 二、合同智能审查流程（核心职责）

```bash
cd /Users/bangcle/.openclaw/workspace/L4-proprietary/components/bangcle-contract

# 1) 初始化本组件 DB（reviews/kb_matches/audit_logs）
python3 cli/contractctl.py init-db

# 2) 本地合同审查（md 或 xlsx）
python3 cli/contractctl.py review --file <合同.pdf|docx|扫描件> --format xlsx

# 3) 从泛微 OA 拉合同审查（需先建会话）
python3 cli/contractctl.py oa-login            # IAM 换票，耗一次 IMAP 验证码
python3 cli/contractctl.py review --oa-billid <billid>

# 4) 取审查记录
python3 cli/contractctl.py report <review_id>
```

审查五步：**ingest（取证）→ digitize（OCR 数字化）→ risk（22 条受控规则）→ kb_match（product-kb 标的参照）→ report（md/xlsx）**。

## 三、关键规则与红线（强制）

- **风险规则单一来源**：22 条 rule_id 与法条依据**只能来自 L3 `contract-management` 的 `CHECK_RULES`**，L4 不得增删改规则；黄金基准要求 rule_id 集合 100% 匹配。
- **合同原文不外发**：原文全程本地处理，不发公网模型；语义轨本期关闭。人工做出同意/驳回决策，组件只产出解析/比对/建议。
- **标的满足度三态**：`satisfied / partial / unsatisfied`；名称近似（相似度 50%~85%）判 **partial 需人工确认**；停售/停用 SKU 直接 hard-fail（unsatisfied）。
- **审计 append-only**：审计表仅 INSERT；OA 回调解幂等键 `billid + event_id`（回写本期不开放）。
- **权限不足直接报阻塞**，不降级绕过；E2E 环境不满足必须 skip 留证，禁止伪 pass/mock 真实环境。
- **分层**：L4→L3/L2 单向依赖，L3 禁 import L4；L4 对同级 product-kb/BDMS 的复用仅限 `services/oa` 等明确授权处。

## 四、OA 会话运维要点

- OA 为泛微 e-cology 9 Cube，主键 `billid`；会话靠 IAM 登录后点「OA协同办公平台」卡片 SSO 换票，**直导 OA / 跨 context 注入 cookie 均无效**。
- **会话有效期实测约 2h idle**（非 12h）；落盘 cookie 全为 session cookie，服务端控制不可延长。
- 过期跑 `contractctl oa-login` 重建（**耗一次 IMAP 验证码**），落盘前用探针 billid 跑 checkCardRight，验证通过才报成功（防假成功）。
- 判登录成功看 **DOM**（含「任立民/首页」），不看 URL hash（SPA 可能停在 `#/login`）。
- 详见组件 `docs/OPERATIONS-v1.0.md` §5。

## 五、常见坑

- **mainFields 宽松 JSON**：泛微 Cube 返回对象裸数字键 `{1:"x"}`，已由 `_lenient_json_loads` 兜底；fields 为 dict 形态（非 list），主字段提取须走 dict 分支。
- **停售措辞**：product-kb 对停售 SKU 返回「停用 / SKU状态: 停用」，hard-fail 必须同时认「停售」「停用」。
- **近似名召回**：FTS5 unicode61 对中文整串生成单 token，product-kb 产品搜索用 prefix 召回才能命中同系列近似名。
- **附件 URL 懒加载**：REST 拿不到直链时自动转浏览器兜底（CDP Chrome → `iframe#mainFrame`），需 `NO_PROXY=*`。

## 边界外（不属于本入口）

| 需求 | 去向 | 层 |
|---|---|---|
| 产品咨询 / 功能 / SKU / 价格 / 售前组合方案 | `product-manager-expert`（PME-001，产品相关统一入口）/ `product-kb` | L4 |
| PPT 生成 / 官方 VI 模板 | `bangcle-ppt`（CPT-012） | L4 |
| 项目交付管理（台账/履约/复盘/客户画像/交付月报） | `bangcle-project-manager-expert`（PJME-001） | L4 |
| ONES 数据导出 | `ones-browser-export` | L4 |
| 收入确认（ASC 606 / IFRS 15 合同识别与报表） | `revenue-recognition`（组件） | L4 |

> 注意：本入口在合同审查中会**调用 product-kb 做合同标的参照**——这是组件间数据复用，不改变本入口"仅合同相关"的边界；纯产品咨询仍归 PME。

## 验收

- 合同审查：真实合同（含扫描页）跑通五步，风险项 rule_id 100% 来自 L3 受控库，报告含命中原文片段 + 法条依据。
- 标的参照：连真实 `product_kb.db`，满足/部分/不满足三态准确，停售红线触发。
- 原文不外发：运行期无外部连接、外发字节不含合同特征串。
- OA 真实链路：会话有效期内 TC-OA-01~03 真跑通过；失效自动 skip 留证。
- 统一入口：任何 Bangcle **合同相关**需求能按 §一 路由表定位；非合同需求按 §边界外 正确分流、不越界代办。

## 应答规范（ADR-035 强制引用）

> 本技能输出口径必须遵循以下应答契约（ADR-035 P1/P2 纵切层）：
>
> 1. **P1 通用应答契约**（数据源优先级与时效、证据三档【已验证】/【推断】/【缺失】、降级显式声明、落盘与副作用、客户实体归一、风险定级通用规则）：
>    `/Users/bangcle/.openclaw/workspace/L2-infra/prompts/answer-spec-base.md`
> 2. **P2 域应答契约**（固定输出维度 + 域风险定级矩阵）：
>    `/Users/bangcle/.openclaw/workspace/L3-business/prompts/contract-answer-spec.md`
>
> 契约优先于本 SKILL 内任何自定义口径；两者冲突时以契约为准，并提请维护对应 spec。

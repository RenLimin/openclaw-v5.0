# Bangcle 合同管理专家 — 设计大纲（DESIGN-OUTLINE）

| 项 | 值 |
|---|---|
| 文档 | DESIGN-OUTLINE |
| 版本 | v1.0 |
| 层级 | L4 专有业务层 |
| 组件编码 | bangcle-contract（SCA-BANGCLE-001） |
| 状态 | 待审核 |
| 依据 | PRD-v1.0 + L3 contract-management OUTLINE-v1.0 + product-kb（ContractMatcher）+ 业界调研 tmp/clm-best-practices.md |

---

## 1. 设计原则

1. **编排优先**：L4 不做规则计算，只做持久化 + 编排 + 外部集成（调用 L3 状态机/风险引擎）
2. **OA 抽象隔离**：OaProvider 接口屏蔽厂商差异，模拟/钉钉先行，泛微/飞书按需接入
3. **复用不重造**：知识库参照直接复用 product-kb ContractMatcher，不重复实现 SKU 匹配
4. **事件驱动同步**：OA 回调 → 本地状态推进；本地操作 → OA 回写
5. **可审计**：全操作 append-only 审计日志

---

## 2. 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│  L4 bangcle-contract                                        │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  CLI (contractctl)  ←→  ContractService（编排核心）   │  │
│  └───────────────────────────────────────────────────────┘  │
│   │              │                │                │        │
│   ▼              ▼                ▼                ▼        │
│  OaProvider   RiskOrchestrator   KBMatcher        Repo      │
│  (模拟/钉钉)   (L3 risk_engine)  (product-kb)   (SQLite)    │
│   │                                            │            │
│   └──── OA API / 附件下载 / 回调     ┌──────────┘            │
└───────────────────────────────────────┼──────────────────────┘
                                        │
              ┌─────────────────────────┼─────────────────────────┐
              ▼                         ▼                         ▼
        L3 contract-management   L4 product-kb             L2 OCR/持久化/Office
        (状态机/风险/金额工具)     (ContractMatcher)        (ocr / sqlite / docx)
```

---

## 3. 模块划分

| 模块 | 职责 |
|---|---|
| `config/settings.py` | Bangcle 场景配置：默认甲方、金额分级表、审批角色映射、SLA、数据库路径 |
| `services/contract_service.py` | 业务编排核心：创建/提交/审批/签署/归档 + 审计持久化 + 幂等 |
| `services/risk_orchestrator.py` | 编排 L3 风险扫描 + product-kb 知识库比对 → 合并风险报告 |
| `services/oa/` | OA 适配器：`base.py`(OaProvider 抽象) + `mock.py`(模拟 OA) + `dingtalk.py`(钉钉) |
| `services/oa_callback.py` | OA 事件回调处理：验签 → 幂等 → 状态机推进/回写 |
| `services/ocr_gateway.py` | 复用 L2 OCR 兼容层，PDF/docx/扫描件 → 文本 |
| `services/doc_generator.py` | 模板生成 docx + Excel 报告导出 |
| `repository/` | SQLite 持久化（合同/审批/审计/知识比对记录） |
| `cli/contractctl.py` | 命令行入口 |
| `tests/test_e2e.py` | 端到端测试（覆盖完整闭环） |

**目录结构**：

```
L4-proprietary/components/bangcle-contract/
├── config/settings.py
├── services/
│   ├── contract_service.py
│   ├── risk_orchestrator.py
│   ├── oa/{base,mock,dingtalk}.py
│   ├── oa_callback.py
│   ├── ocr_gateway.py
│   └── doc_generator.py
├── repository/
├── cli/contractctl.py
├── tests/
├── docs/          # PRD / OUTLINE / DETAIL / VERIFICATION / OPERATIONS / IMPLEMENTATION-PLAN
└── README.md
```

---

## 4. OaProvider 接口契约（抽象）

```python
class OaProvider(ABC):
    """OA 适配器抽象，屏蔽厂商差异"""

    @abstractmethod
    def get_contract_attachment(self, process_instance_id: str) -> Attachment:
        """从审批实例获取合同附件（文件流 + 元数据）"""

    @abstractmethod
    def query_process(self, process_instance_id: str) -> ProcessInfo:
        """查询审批实例当前节点/状态"""

    @abstractmethod
    def push_result(self, process_instance_id: str, action: str,
                    comment: str, approver: str) -> bool:
        """回写审批结果（同意/驳回）到 OA"""

    @abstractmethod
    def register_callback(self, handler) -> None:
        """注册审批事件回调（任务变更/实例变更）"""
```

**实现**：
- `MockOaProvider`：本地目录模拟 OA（测试/离线兜底），目录放入合同文件 → 视为审批附件
- `DingTalkOaProvider`：钉钉开放平台（获取实例详情 / 附件授权下载 / 同意拒绝 / 事件订阅）
- 泛微/飞书：后续按 OaProvider 接口接入

---

## 5. 知识库参照分析（复用 product-kb）

| 步骤 | 实现 |
|---|---|
| 合同标的提取 | L3 contract_parser 解析服务内容/产品清单 |
| SKU 匹配 | product-kb `ContractMatcher.match_items()`（名称相似度 + 版本 + 分类加权） |
| 价格/折扣校验 | 标准单价对比 → 偏差率 + 折扣红线预警 + SKU 状态校验 |
| 输出 | 标的一致性报告（匹配度/标准名/标准单价/合同单价/偏差/红线/预警） |
| 免责 | 低匹配度/待确认项标记"需人工确认" |

---

## 6. 审批流编排（双向同步）

```
OA 发起审批 ──回调──▶ OaProvider.register_callback
                       │
                       ▼
              [oa_callback] 验签 + 幂等
                       │ 映射 OA 节点 → review1/2/3
                       ▼
              L3 state_machine.next_approval_status()
                       │
                       ▼
              [contract_service] 持久化状态 + 审计日志
                       │
                       ▼
              approve/reject ──push_result──▶ OA 回写
```

- **幂等键**：`oa_process_id + event_id`，重复回调不产生重复记录
- **驳回**：OA 驳回 → 本地回 draft；本地驳回 → OA 回写驳回意见

---

## 7. 状态机 / 数据模型

- 复用 L3 `core/models.py` 的 Contract / ApprovalRecord / AuditLogEntry / RiskReport
- 扩展字段（`extra` dict 透传）：`oa_process_id`、`oa_attachment_path`、`kb_report_path`、`risk_report_path`、`doc_path`

---

## 8. 数据库 Schema（扩展既有 SCA-001）

| 表 | 新增字段 |
|---|---|
| contracts | + `oa_process_id` / `oa_status` / `attachment_path` / `risk_report_path` / `kb_report_path` / `doc_path` |
| approvals | 不变（既有） |
| audit_logs | 不变（既有） |
| **oa_events**（新增） | `id` / `process_id` / `event_id`(唯一幂等键) / `event_type` / `payload` / `handled_at` |
| **kb_matches**（新增） | `id` / `contract_id` / `input_name` / `matched_product` / `matched_sku` / `score` / `price_deviation` / `alert` |

---

## 9. 关键设计决策

| 决策 | 选择 | 理由 |
|---|---|---|
| OA 集成 | OaProvider 接口 + 模拟先行 + 钉钉实现 | 屏蔽厂商差异；钉钉"附件下载"仅限企业内部应用 → 模拟兜底 |
| 知识库参照 | 复用 product-kb ContractMatcher | 不重复实现，接口契约对接 |
| 风险合并 | risk_orchestrator 合并法律风险 + 知识库风险 | 一份报告看全 |
| 状态同步 | 事件驱动 + 幂等键 | 对齐业界"checkpointer + 事件回调"；防重复 |
| 交互 | CLI（本期） | 无 Web UI，最小可用闭环 |

---

## 10. 演进方向

1. 泛微/飞书 OaProvider
2. 企业微信审批通知
3. Web UI / Dashboard
4. 印章检测（L2 OCR 扩展）

---

## 11. 变更历史

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-10-27 | v1.0 | 初稿 |

---

## 12. 修订 v1.1（2026-10-27，基于 28 来源调研补充）

### 12.1 OaProvider 实现分层调整

- **L3**：`core/oa/base.py` 抽象基类（通用模式）
- **L4**：`services/oa/` 放具体厂商实现（mock / dingtalk / 泛微 / 飞书）
- **注入**：ContractService 初始化时注入具体 OaProvider 实例

### 12.2 双轨风险扫描

```
风险输入
  ├── 阈值规则轨（确定性，22条《民法典》+ 自定义）→ 高置信度
  └── 语义判断轨（LLM，可开关）            → 需人工复核
       ↓
  合并 + 去重 + 分级（high/medium/low/info）
       ↓
  每条发现：原文位置 + 规则ID + 法条依据 + 修改建议 + 置信度
```

- 法条依据只能来自本地受控规则库（rule_id 关联 legal_basis 表）
- LLM 轨输出标记 `needs_human_review=true`，不作为独立判定依据

### 12.3 规则库版本化

- 规则表带 `version` 字段（语义化版本）
- 每次规则变更生成新版本，旧版本归档
- 风险报告记录所用规则库版本号，可复现
- 法务反馈通过 `feedback` 表收集，定期纳入规则迭代

### 12.4 数据隐私实现

| 措施 | 位置 |
|---|---|
| 合同原文本地存储 | SQLite BLOB 或文件系统（L4 本地） |
| OCR 本地执行 | L2 OCR-001（本地模型优先） |
| LLM 调用脱敏 | 调用公网模型前，移除甲乙方名称/金额/身份证等 PII |
| 审计记录 | 所有外部调用（OA/LLM）全量审计 |

---

## 13. 范围定稿 v1.2（2026-10-27，Rex 确认）

### 13.1 OA 适配器实现调整

| 实现 | 状态 | 说明 |
|---|---|---|
| `services/oa/mock.py` | MVP | 本地/企微上传文件 → 模拟流程（离线兜底） |
| `services/oa/weaver.py` | P1 | 泛微 e-cology：requestid→docid→imagefileid→下载附件；WorkflowService 查节点；需先确认版本与开放权限 |
| `services/oa/browser_fallback.py` | P1 | **浏览器自动化兜底**（API 不可用/权限不足时）：复用 BDMS `browser_adapter.py`（Playwright CDP + IAM Cookie pool + connect_over_cdp 复用登录态 Chrome）+ `oa_export_playwright.py` 模式，导航 OA 合同详情页提取附件与字段 |
| `services/wecom/` | P1 | 企业微信自建应用：sp_no 详情、open_approval_change 回调、应用消息推报告 |
| ~~`dingtalk.py`~~ | 取消 | 范围改为泛微 + 企微，不做钉钉 |

### 13.2 MVP 模块（只保留分析闭环）

```
contract_review/   （OA 集成失败时依赖 BDMS browser_adapter 兜底，MVP 阶段 ingest 优先走手动/企微上传）

├── ingest.py      # 合同获取：上传 / OA附件（mock 优先）
├── digitize.py    # L2 OCR 兼容层：PDF/docx/扫描件 → 全文文本
├── parser.py      # L3 contract_parser：全文 → 结构化条款
├── risk.py        # L3 双轨风险：22条规则 + 语义判断
├── kb_match.py    # product-kb ContractMatcher + 产品管理专家建议
│                  #   合同要求产品/服务 vs 产品库 → 满足度 + 偏差 + 风险点
└── report.py      # 《合同智能审查报告》：风险点 + 满足度结论 + 建议 + 免责
```

**满足度判定输出（kb_match）**：
| 结论 | 条件 |
|---|---|
| 满足 | 合同标的全部匹配到在售 SKU，价格/折扣在红线内 |
| 部分满足 | 部分匹配 / 有偏差 / 低匹配度需人工确认 |
| 不满足 | 关键标的无匹配 / 已停售 / 价格超红线 |

### 13.3 MVP 不做（保留接口，后续迭代）

- OA 双向审批回写、多级状态机流转编排
- docx 合同文档生成
- Web UI
- 这些在 OUTLINE 前述章节已设计，作为 P1/P2 演进，不阻塞 MVP 分析闭环

### 13.4 数据流（MVP）

```
合同文件 ─▶ ingest ─▶ digitize ─▶ parser ─┬─▶ risk (L3) ─────────────┐
                                         └─▶ kb_match (product-kb) ─┤
                                                                     ▼
                                                          report 智能审查报告
```

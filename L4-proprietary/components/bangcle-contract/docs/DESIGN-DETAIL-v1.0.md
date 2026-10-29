# Bangcle 合同管理专家 — 详细设计（DESIGN-DETAIL）

| 项 | 值 |
|---|---|
| 文档 | DESIGN-DETAIL |
| 版本 | v1.0 |
| 层级 | L4 专有业务层 |
| 组件编码 | bangcle-contract（CLM-BANGCLE-001） |
| 状态 | ✅ 通过（Rex 2026-10-29 拍板，详见 VERIFICATION §0） |
| 依据 | PRD-v1.0 §10 + OUTLINE-v1.0 §13 + L3 DESIGN-DETAIL-v1.0 + OA 侦察（2026-10-27） |

> **本期范围 = MVP 四步分析闭环**（PRD §10.2）。OA 双向回写 / 多级状态编排 / docx 生成 / Web UI 仅保留接口，不在本期实现。

---

## 1. 总体架构

```
合同文件(PDF/docx/扫描件)
   │
   ▼
┌─────────────── L4 bangcle-contract (MVP) ───────────────┐
│ ingest.py    获取：手动/企微上传，或 OA Cube 拉取        │
│ digitize.py  L2 OCR/直读 → 全文文本                     │
│ parser.py    L3 contract_parser → 结构化条款(本期复用)  │
│ risk.py      L3 scan_text 双轨 → 法律风险点             │
│ kb_match.py  product-kb ContractMatcher → 满足度/偏差   │
│ report.py    《合同智能审查报告》(Markdown/Excel)        │
│ repository/  SQLite：审查记录/KB匹配/审计(append-only)  │
│ cli/contractctl.py  命令行入口                           │
└─────────────────────────────────────────────────────────┘
        │ L4→L3                │ L4→L4(product-kb)    │ L4→L2
        ▼                       ▼                       ▼
   L3 contract-management   product-kb (PKB-001)    OCR / SQLite / Office
```

**依赖方向铁律**：仅 L4→L3/L2、L4→同级 product-kb；禁止反向。L4 不重写任何 L3 规则/状态计算。

---

## 2. 模块清单与文件契约（MVP）

| 文件 | 职责 | 副作用 |
|---|---|---|
| `contract_review/ingest.py` | 接收上传文件 / 从 OA Cube 拉合同附件，落本地暂存，返回 `IngestedFile` | 文件写、(可选)网络 |
| `contract_review/digitize.py` | PDF/docx 直读 + 扫描件走 L2 OCR → `DigitizedText` | 调 L2，本地缓存 |
| `contract_review/parser.py` | 调 L3 条款解析（L3 该模块在 DETAIL §3 范围外时，本期以正则最小解析兜底，见 §6） | 纯编排 |
| `contract_review/risk.py` | 调 L3 `scan_text`，附加双轨语义开关（语义轨本期可关闭） | 纯编排 |
| `contract_review/kb_match.py` | 从合同提取标的清单 → 调 product-kb `ContractMatcher.match_items` → 满足度判定 | 读 product-kb DB |
| `contract_review/report.py` | 汇总风险+满足度 → Markdown/Excel 报告（含免责声明） | 文件写 |
| `repository/db.py` | SQLite：reviews / kb_matches / audit_logs | DB |
| `services/oa/cube.py` | e-cology 9 Cube 内部 REST 客户端（storage_state 会话） | 网络 |
| `services/oa/browser_fallback.py` | 复用 BDMS `browser_adapter`，CDP+IAM 登录态兜底 | 拉起 Chrome |
| `cli/contractctl.py` | CLI 入口 | — |

---

## 3. 数据契约（L4 内部模型）

纯数据 dataclass，仅 L4 内部使用；与 L3 模型转换在边界完成。

```python
@dataclass
class IngestedFile:
    source: str            # "upload" | "wecom" | "oa_cube"
    original_name: str
    local_path: str
    file_type: str         # "pdf" | "docx" | "image"
    oa_ref: Optional[str] = None   # OA 来源时承载 billid

@dataclass
class DigitizedText:
    full_text: str
    method: str            # "native_pdf" | "docx" | "ocr"
    ocr_confidence: Optional[float] = None

@dataclass
class ContractItem:       # 从合同标的/产品清单提取，喂给 product-kb
    name: str
    model: Optional[str] = None
    price: Optional[float] = None
    quantity: Optional[float] = None

@dataclass
class ReviewRecord:       # 持久化
    id: Optional[int]
    contract_ref: str
    source: str
    overall_risk: str
    satisfaction: str     # "satisfied" | "partial" | "unsatisfied"
    report_path: str
    created_at: str
```

**与 L3 边界**：`risk.py` 输出 L3 `RiskReport`；`report.py` 只读其 `to_dict()`，不回改 L3 对象。

---

## 4. OA 集成契约（e-cology 9 Cube）

> 基于 2026-10-27 实测。**关键修正：Bangcle 合同不是标准工作流，是建模引擎 Cube 记录。**

### 4.1 实测事实

| 项 | 值 |
|---|---|
| 平台 | 泛微 e-cology 9（登录后 `spa=True`；未登录 `/spa/404` 为假象） |
| 合同卡片 | `/spa/cube/index.html#/main/cube/card?type=0&modeId=112&formId=-249&billid=<id>&customid=179` |
| 主键 | `billid`（建模记录 ID），**无 requestid/docid** |
| 主表 / 明细表 | `uf_xsht_xxb` / `uf_xsht_xxb_dt2,dt3,dt5,dt8` |
| 附件 | 建模上传字段，按"新签产品/新签服务"等分组，`maxUploadSize=5` MB |
| 认证 | IAM SSO → 点 OA 卡片换票 → ecology 会话；可用 Playwright `storage_state` 持久化 |

### 4.2 Cube 内部 REST（浏览器会话内，已验证返回 200）

| 接口 | 用途 |
|---|---|
| `GET /api/cube/new/card/initDetail` | 卡片明细结构（明细表/表名） |
| `GET /api/cube/new/card/mainFields` | 主字段 |
| `GET /api/cube/new/card/getDetailFields?tablename=<dt>&groupid=<n>` | 明细数据（含上传字段/`maxUploadSize`） |
| `GET /api/cube/new/card/innerTabs` | 关联台账（项目台账/开票/回款等） |
| `GET /api/cube/new/card/checkCardRight` | 当前账号对卡片的权限 |

调用方式：携带 storage_state 的 cookie（含 ecology 会话）+ 卡片 URL 同款 query（`modeId/formId/billid/_key`）。`services/oa/cube.py` 只做"带会话 GET + JSON 解析 + 附件字段 URL 提取"，**不实现开放平台 token 流程**（实测 `/api/ec/dev/auth/apply` 需应用凭证，本期不走）。

### 4.3 附件下载

- 优先解析 `getDetailFields` 返回的上传字段文件引用（Cube 附件通常经 `/api/docs/...` 或 `imagefile`/`openimg` 类 URL），在同会话内下载。
- 若字段引用无法直接构造下载 URL（懒加载/加密传输 `/api/encryptedTrans/...`），降级到 `browser_fallback.py`。

### 4.4 浏览器自动化兜底（复用 BDMS，零重造）

直接引用 BDMS 已验证资产，**不复制实现**：

| 复用 | 路径 |
|---|---|
| IAM 全自动登录（含 IMAP 验证码） | `L4.../bdms/src/bdms/modules/integration/adapters/browser_adapter.py::login_iam` |
| CDP 复用登录态 Chrome | 同模块 `connect_over_cdp` + `oa_click_card_iam` |
| OA 页面/iframe 导航模式 | `bdms/scripts/oa_export_playwright.py`；主内容 `iframe#mainFrame` |

`browser_fallback.py` 职责：连接/启动 CDP Chrome → 导航 Cube 卡片 → 在 `iframe#mainFrame` 内提取字段与附件 → 落盘。会话有效期 12h，用 storage_state 复用，避免重复登录。

---

## 5. product-kb 参照契约（复用 PKB-001）

### 5.1 调用接口（实测，非假设）

```python
from product_kb.db import ProductKBDB
from product_kb.contract import ContractMatcher

matcher = ContractMatcher(ProductKBDB(db_path))          # threshold 默认 0.5
results = matcher.match_items([
    {"name": item.name, "model": item.model, "price": item.price}
])
# 每项返回 dict:
# {input_name, input_model, input_price, matched: bool, score,
#  product: dict|None, sku: dict|None, alert: str|None}
```

`alert` 已内置：价格低于折扣红线（解析 SKU `discount_type` 中 `N折`）、SKU 状态非「启用」、低匹配度需人工确认、产品无 SKU。

### 5.2 满足度判定（kb_match.py）

| 结论 | 条件 |
|---|---|
| `satisfied` 满足 | 所有标的 `matched=True` 且 `alert` 为空（SKU 在售、价格在红线内） |
| `partial` 部分满足 | 任一低匹配度/价格偏差/需人工确认，但无关键标的缺失 |
| `unsatisfied` 不满足 | 关键标的 `matched=False` / SKU 停售 / 价格低于红线 |

低置信（score 接近阈值）一律标"需人工确认"，不自动判满足。

### 5.3 ⚠️ 落位问题（必须 Rex 拍板）

**product-kb 组件只存在于沙箱副本，未进权威仓库 `main`：**

- 实际位置：`~/.openclaw/sandboxes/workspace-.../L4-proprietary/components/product-kb`（含 `data/product_kb.db`，8 产品线/385 SKU）
- 权威仓库 `/Users/bangcle/.openclaw/workspace/L4-proprietary/components/` 下**无 product-kb**
- 与此前合同资产误落沙箱同源；`product-kb` skill 里的绝对路径也指向沙箱

**建议**：将 product-kb 组件迁移到权威仓库 L4（同合同资产迁移做法），再由 bangcle-contract 依赖。迁移前 L4 集成测试只能在沙箱路径跑。**此项阻塞 kb_match 的正式联调，需要 Rex 确认迁移授权。**

---

## 6. digitize / parser 兜底口径

| 环节 | 主路径 | 兜底 |
|---|---|---|
| PDF | 文本层直读（无文本层判定为扫描件） | L2 OCR（本地模型优先） |
| docx | 文本/表格直读 | — |
| 扫描图片 | L2 OCR-001 | 失败标 `ocr_confidence` 低 + 人工 |
| 条款解析 | L3 `contract_parser`（若该模块本期未随 L3 落地） | `parser.py` 内置最小正则：标的清单/金额/甲乙方/服务期，输出标注"浅解析" |

合同原文**全程本地**，不发公网模型（隐私红线）。

---

## 7. 持久化 Schema（SQLite）

| 表 | 字段 |
|---|---|
| `reviews` | `id` PK · `contract_ref` · `source` · `overall_risk` · `satisfaction` · `rule_set_version` · `report_path` · `created_at` |
| `kb_matches` | `id` PK · `review_id` FK · `input_name` · `matched_product` · `matched_sku` · `score` · `alert` |
| `audit_logs` | `id` PK · `review_id` · `action` · `operator` · `detail` · `created_at`（**append-only**） |

迁移：DB 文件由 L2 持久化组件管理；表结构变更走版本化迁移脚本，不整库重建。

---

## 8. CLI 契约（contractctl）

```bash
contractctl review --file <path> [--source upload]     # 完整跑 MVP 1-4 步
contractctl review --oa-billid <billid>                # 从 Cube 拉取（API→浏览器兜底）
contractctl report <review_id> [--format md|xlsx]      # 取报告
```

输出：分步进度（>10s 操作展示当前步骤，遵守进度条铁律）+ 最终 `overall_risk / satisfaction / report_path`。

---

## 9. 错误与边界

| 情形 | 行为 |
|---|---|
| OA 会话过期 | 自动 storage_state 失效 → 走 IAM 重登（headless + IMAP 验证码），不询问 |
| Cube 接口 403/权限不足 | 降级 browser_fallback；仍失败则报"账号权限"阻塞，不伪造数据 |
| OCR 不可用 | 明确报错 + 该合同标记未数字化，不继续风险扫描 |
| product-kb 不可达 | kb_match 跳过并在报告标注"未做参照"，不静默通过 |
| 回调（本期不做） | 预留幂等键 `billid + event_id`，append-only 审计 |

---

## 10. 验收对齐（MVP，详见后续 VERIFICATION）

1. 上传含扫描页真实合同 → 跑通 ingest→digitize→risk→kb_match→report
2. 风险点结构化：rule_id + 原文位置 + 法条依据（仅来自 L3 受控规则库）
3. 产品/服务清单 → product-kb 匹配 → 满足/部分/不满足 + 红线预警
4. 报告含免责声明；合同原文不外发
5. CLI 三命令实跑；幂等（同文件重复审查结果稳定）

---

## 11. 变更历史

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-10-27 | v1.0 | 初版：MVP 分析闭环 + e-cology 9 Cube 契约 + product-kb 复用与落位问题 |

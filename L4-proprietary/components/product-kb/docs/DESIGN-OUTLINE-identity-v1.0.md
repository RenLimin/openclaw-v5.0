# DESIGN-OUTLINE — product-kb 权威身份层（自然键 / 跨源解析 / 软归并）

| 项 | 值 |
|---|---|
| 文档 | DESIGN-OUTLINE（identity 专项） |
| 版本 | v1.0 |
| 层级 | L4 专有业务层 |
| 组件 | product-kb（权威主数据） |
| 状态 | 待 Rex 审核 |
| 依据 | product-kb PRD §Q3 / OUTLINE §5 + L2 ont_identity 模式（DESIGN-DETAIL-operational-ontology v1.0 §2.1/§3.1）+ bangcle-contract MVP 实证（KBMatcher 0.5 阈值误报"API安全平司"） |

> 范围：**只改身份层**（product/sku 主档的身份、别名、归并、解析），不动价格/文档/检索。
> 前置：本 OUTLINE 审核通过 → 再出 DESIGN-DETAIL → IMPLEMENTATION-PLAN → 分 Phase 自测 → VERIFICATION。

---

## 1. 问题陈述（实证，非假设）

product-kb 当前**以 `id` 为关联主键，无稳定自然键**，导致三类问题：

| # | 问题 | 实证 |
|---|---|---|
| P1 | 同名不同版本产品被规范化自然键合并成 2 个冲突组 | "移动应用安全监测标准版V4.0/增强版V5.0…维保服务"（4 条，两两同根） |
| P2 | 跨源标识（合同文本/价格表/文档/外部系统）无法稳定解析到同一产品 | bangcle-contract OCR"API安全平司"→0.5 阈值直接判 unsatisfied（无别名容错） |
| P3 | 重导入/多源入库无法幂等去重 | `io.py` 导入按"名称+版本"去重，但无全局唯一约束，重复导入可能生成双记录 |

另有两个数据质量事实（本设计要一并解决）：
- `product.code` 全 193 条非空且唯一，**但编码含业务语义（版本/形态），改名即变**，不配做跨期稳定主键；
- `status='未知'` 3 条（id 191-193，非梆梆产品占位）；`version_latest` 仅 55/193 覆盖。

---

## 2. 设计目标

1. **稳定权威主键**：product 获得不可变 `canonical_key`（自然键），sku 获得 `sku_code` 自然键（已唯一，转正为主键语义）；
2. **跨源别名解析**：合同文本/价格表/文档/外部系统的标识 → 同一产品（别名表 + 相似度辅助）；
3. **软归并可审计**：重复/疑似重复产品软归并（merged_into + alias 转移），不物理删，可回滚；
4. **CWA 封闭世界**：resolve 命中即"存在"，未命中即"不存在"——匹配失败如实报告，不硬猜；
5. **零破坏**：不改价格/文档/检索表；L2 模式复用（ont_identity 表结构与 IdentityService 语义对齐）。

---

## 3. 方案对比（拍板点）

### 方案 A：L2 ont_identity 表承载 product-kb 身份（推荐）
product-kb 直接用 L2 `ont_identity` + `ont_identity_alias`（domain=product-kb），
`product.id` 作为 `object_id` 外联，别名/归并/解析全走 L2 IdentityService。

| 优势 | 劣势 |
|---|---|
| 复用成熟实现（register/resolve/merge 已测，114 测试锁定） | product-kb 依赖 L2 本体 DB（与现有独立 product_kb.db 分离） |
| 跨组件统一身份语义（合同/产品/项目同一种"对象+身份"） | 需要 L2 装配 domain=product-kb 白名单 |
| 归并/别名天然可审计、可回滚 | 首次落地要建 L2 ↔ product-kb 的 DB 连接契约 |

### 方案 B：product-kb 自建 identity 表（本地权威）
在 product_kb.db 内新增 `product_identity` / `product_alias`，语义仿 L2 但自持。

| 优势 | 劣势 |
|---|---|
| 组件自包含，不依赖 L2 本体 DB | 重复实现 L2 已验证的归并/别名/审计逻辑（违反复用原则） |
| 改 product_kb.db 单文件 | 与 L2 身份语义分叉，未来合同域/产品域身份无法互通 |

### 方案 C：只加 canonical_key 列（最小）
product 表加 `canonical_key TEXT UNIQUE`，不做别名/归并，别名仍走 `aliases` JSON 列。

| 优势 | 劣势 |
|---|---|
| 改动最小（单列） | 无法软归并（JSON 别名无跨源解析、无审计）；不解决 P2/P3 的归并诉求 |

**推荐：方案 A**（复用 L2 IdentityService）+ **方案 C 的 canonical_key 落 product 表**（作为展示/联调键）。
理由：身份是"跨组件通用问题"，L2 已建好并 114 测试锁定，product-kb 不应再造；canonical_key 落本表便于 product 自描述。

---

## 4. 身份模型

### 4.1 canonical_key 生成规则（product）

```
canonical_key = normalize(name)
normalize:
  1. NFKC 全角→半角
  2. 去空白/标点（空格 - _ （）【】· 等）
  3. 小写
  4. 版本号保留在键内（如 V4.0 / V5.0 直接构成不同键）
```
- **选型依据（实测，2026-11-02）**：193 条产品全量跑规范化——
  - 保留版本号：**0 冲突组**（V4.0/V5.0 维保服务名称自带版本，天然区分）；
  - 剥离版本号再拼 version_latest：**2 冲突组**（V4/V5 同根），且 `version_latest` 仅覆盖 55/193，引入脆弱依赖。
  → 定稿：**保留版本号，不依赖 version_latest**。
- 不可变：一经生成，永不因改名/改版本而变化（新版本 = 新 canonical_key，旧键保持可解析）。

### 4.2 表结构（L2 ont_identity 语义，product_kb.db 内落地）

```
product_identity (
  id, product_id UNIQUE FK, canonical_key UNIQUE,
  display_name, status(active|merged), merged_into, created_at, updated_at
)
product_alias (
  id, identity_id FK, source_system, source_key, confidence,
  UNIQUE(source_system, source_key)
)
```

> 若选方案 A：这两张表放 L2 本体 DB，product_id 作为 object_id 关联；若方案 B：放 product_kb.db。
> OUTLINE 阶段**推荐 A**，DETAIL 定稿表归属。

### 4.3 sku 身份

- `sku_code` 已全量唯一 → 直接作为 sku 的自然键（无需新列）；
- sku 归并/别名本期不做（sku 变更走 product 层，SKU 级差异靠 model/price_base 区分）。

---

## 5. 解析与匹配改造

### 5.1 别名解析（resolve）
```
resolve(source_system, source_key) -> product_id | None
```
- 命中 alias → 返回对应 product_id（CWA：未命中返回 None）；
- 别名来源（source_system 枚举）：
  | system | 键 | 举例 |
  |---|---|---|
  | price_excel | 价格表原始名称 | "全渠道应用安全监测软件 V6.0" |
  | contract_text | 合同/OCR 标的原词 | "API安全平司软件V3.0"（OCR 噪声） |
  | doc_asset | 文档文件名提取 | "AS-AIOTP-6.0-EA-SAP-021" |
  | internal | code / 旧 id | "AS-AIOTP-6.0-EA-SAP-021" |

### 5.2 ContractMatcher 增强（配合 MVP 实证的误报）
- 匹配前先 `resolve('contract_text', item.raw_name)`：命中别名 → 直接取 product_id，跳过相似度阈值；
- 未命中 → 现有 FTS+相似度路径，但**低相似度（<0.5）不再直接判 unsatisfied**，而是标 `needs_human_review`（partial 语义），由别名表人工确认后补录——把"查不到"从硬失败改成"待确认"，堵住 OCR 噪声误判。
- ⚠️ 本期 bangcle-contract MVP 已交付（commit 3f73075），**contract.py 的改造放 product-kb 身份层落地时一起做**，不单独改已交付组件（避免与验证会话冲突）。

---

## 6. 迁移策略（增量、幂等、可回滚）

| Phase | 内容 | 触碰 |
|---|---|---|
| P1 | product_identity/product_alias 建表 + canonical_key 回填（193 产品全量生成，实测 0 冲突；重复键留人工裁定兜底）+ resolve API | product_kb.db + 新模块 identity.py |
| P2 | ContractMatcher 接入 resolve + needs_human_review 语义 | contract.py |
| P3 | 导入去重走 canonical_key（io.py 幂等）+ 别名管理 CLI（alias add/list/merge/rollback） | io.py + cli.py |
| P4 | 审计/回滚（decision_record 关联，对齐 L2 P3）+ 文档/价格表批量别名回填 | 新表 + 脚本 |

- 每个 Phase 独立 VERIFICATION；**P1 落地前先冻结 product_kb.db 写入**（对齐案例验证会话只读窗口）；
- 全部增量 migration，`CREATE TABLE IF NOT EXISTS`，可回滚（soft merge 不物理删）。

---

## 7. 边界与红线

- 不改 product/sku 价格、状态、文档、检索表结构（只加身份相关表/列）；
- 不物理删除任何产品记录（软归并）；
- canonical_key 一经生成不可变（改名只改 display_name，键保持）；
- L4 不重写 L2 IdentityService（复用，仅装配 domain 白名单）；
- 与案例验证会话冲突最小化：P1 只读 product_kb.db 的 product 表（加表不迁移旧数据），迁移类操作 P1 之后单独窗口执行。

---

## 8. 验收标准（对齐 PRD Q3 + MVP 实证）

1. 193 产品全部生成 canonical_key，无重复、无空值；V4/V5 同根冲突组正确区分（P1 解决）；
2. `resolve('contract_text','API安全平司软件V3.0')`（别名已录）→ 命中 API安全平台软件V3.0；未录 → None（CWA）；
3. ContractMatcher 低相似度输出 `needs_human_review` 而非直接 unsatisfied；
4. 重复导入同一价格表 → 幂等去重，不产生双记录；
5. 软归并后 alias 全部转移、旧身份 merged 可查、可回滚；
6. L2 114 / L3 42 / L4 20 测试零破坏（身份层落地后新增用例）。

---

## 9. 变更历史
| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-11-02 | v1.0 | 初稿（基于实测：193 产品 code 全唯一、规范化自然键 2 冲突组、status 分布、版本覆盖） |

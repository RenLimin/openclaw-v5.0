# DESIGN-DETAIL — product-kb 权威身份层（自然键 / 跨源解析 / 软归并）

| 项 | 值 |
|---|---|
| 文档 | DESIGN-DETAIL（identity 专项） |
| 版本 | v1.0 |
| 层级 | L4 专有业务层 |
| 组件 | product-kb |
| 状态 | 待 Rex 审核 |
| 依据 | OUTLINE-identity-v1.0（已出）+ L2 ont_identity v8 表结构（实测）+ product_kb.db 现状（实测） |

> 前置：本 DETAIL 审核通过 → IMPLEMENTATION-PLAN → 分 Phase 自测 → VERIFICATION → 验收。
> 本期**零运行时改动**：全部为设计文档（与 BDMS 调试 / 合同案例验证两会话零碰撞）。

---

## 1. 身份表归属（拍板项 O1）

OUTLINE 曾推荐"方案 A：身份表放 L2 本体 DB"。**DETAIL 定稿前实测复核，改为推荐方案 B+（本地表、算法对齐 L2）**：

| 方案 | 结构 | 实测判定 |
|---|---|---|
| A | product_identity 放 L2 本体 DB，product_kb 跨 DB join | ❌ 打破 product_kb 自包含单文件边界（OPERATIONS 明确"单文件方便迁移"）；每次解析跨 DB；案例验证会话正读 product_kb.db，引 L2 DB 依赖徒增碰撞面 |
| B+ | **product_identity / product_alias 落在 product_kb.db 内**，schema 与 L2 v8 语义对齐（UNIQUE 约束、软归并 merged_into、alias UNIQUE(source_system,source_key)），IdentityService 本地实现复用 L2 的算法模式（register/resolve/merge/add_alias/list） | ✅ 自包含、单文件、最小侵入；语义与 L2 统一（同一种"对象+身份"模型），未来如需跨域解析可再桥接 |

**O1 结论：方案 B+。**（若 Rex 坚持方案 A 跨 DB 统一，可改——但需接受 product_kb 依赖 L2 DB 文件路径。）

---

## 2. 表结构（migration v12，增量幂等）

```sql
CREATE TABLE IF NOT EXISTS product_identity (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  product_id    INTEGER NOT NULL UNIQUE REFERENCES product(id),
  canonical_key TEXT NOT NULL UNIQUE,
  display_name  TEXT,
  status        TEXT DEFAULT 'active',        -- active | merged
  merged_into   INTEGER REFERENCES product_identity(id),
  metadata      TEXT,                          -- JSON：生成规则版本/原始名称/旧 code
  created_at    DATETIME NOT NULL,
  updated_at    DATETIME NOT NULL
);
CREATE TABLE IF NOT EXISTS product_alias (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  identity_id   INTEGER NOT NULL REFERENCES product_identity(id),
  source_system TEXT NOT NULL,                 -- price_excel|contract_text|doc_asset|internal
  source_key    TEXT NOT NULL,
  confidence    REAL,
  created_at    DATETIME NOT NULL,
  UNIQUE (source_system, source_key)
);
CREATE INDEX IF NOT EXISTS idx_product_alias_identity ON product_alias(identity_id);
```

- 增量：`CREATE TABLE IF NOT EXISTS`，不动既有 product/sku 表结构与数据；
- 幂等：重复执行无副作用；migration 版本登记沿用 L2 `kb_migration` 模式（product_kb.db 内新增 `kb_migration` 表登记 v12，若已存在则跳过）。

---

## 3. canonical_key 生成算法（定稿：保留版本号）

```
canonical_key = normalize(name)
normalize:
  1. NFKC 全角→半角（unicodedata.normalize）
  2. 去空白与标点：空格 - _ （）【】[] · ,，。等
  3. 小写
  4. 版本号保留（V4.0 / V5.0 直接构成不同键）
```

**选型依据（实测，193 条全量）**：
- 保留版本号 → **0 冲突组**；
- 剥离版本号再拼 version_latest → 2 冲突组 + 依赖仅 55/193 覆盖的 version_latest（脆弱）。
→ 定稿保留版本号。

**不可变性**：canonical_key 一经生成永不改写；产品改名只更新 display_name；新版本产品 = 新 canonical_key（旧键保持可解析、可归并）。

**兜底**：生成后若仍有重复键（未来新增数据），冲突组进 `metadata.conflict=true` 并**留人工裁定**（不自动合并），报告列出待裁定清单。

---

## 4. IdentityService 本地实现（API 契约，语义对齐 L2 v8）

```python
class ProductIdentityService:
    def __init__(self, db: ProductKBDB): ...

    def register(self, product_id: int, canonical_key: str,
                 display_name: str = None) -> int:
        """建权威身份；UNIQUE(product_id) / UNIQUE(canonical_key) 冲突抛 IntegrityError。"""

    def add_alias(self, identity_id: int, source_system: str,
                  source_key: str, confidence: float = None) -> int:
        """绑定跨源标识；UNIQUE(source_system, source_key) 冲突抛 IntegrityError。"""

    def resolve(self, source_system: str, source_key: str) -> Optional[int]:
        """CWA：命中 alias -> 权威 product_id（跟随 merged_into 防御性指针）；
        未命中 -> None（封闭世界，调用方据此拒绝/待确认）。"""

    def merge(self, from_id: int, into_id: int, actor: str) -> dict:
        """软归并：from 方 status='merged' + merged_into；alias 全部转移；
        重复 (source_system, source_key) 删除以满足 UNIQUE；
        写审计（product_kb 新增 identity_audit 表或复用 audit_log）；
        返回归并决策记录。不物理删除，可回滚。"""

    def list(self, status: str = None) -> List[dict]: ...
    def get_by_product_id(self, product_id: int) -> Optional[dict]: ...
```

**与 L2 的差异（仅实现载体，非语义）**：
- L2 用 `AIKB` 实例 + `ont_identity` 表；本地用 `ProductKBDB` + `product_identity` 表；
- resolve/merge 算法（alias 转移、merged_into 跟随、UNIQUE 冲突处理）逐条对齐 L2 `IdentityService` 实现（已在 L2 P1 测试锁定）。

---

## 5. ContractMatcher 增强（P2 落地，配合 MVP 实证）

现状（bangcle-contract MVP 实证）：OCR"API安全平司软件V3.0"→ 0.5 阈值下直接 unsatisfied（无别名容错）。

改造 `contract.py`：

```python
def match_item(self, input_name, input_model=None, input_price=None):
    # 1) 别名解析优先（CWA）
    identity = self.identity.resolve("contract_text", input_name)
    if identity is not None:
        product_id = identity  # 直接命中权威产品，跳过相似度阈值
        # ... 走 SKU 匹配 + 价格/折扣红线（现有逻辑）
    # 2) 未命中 -> 现有 FTS+相似度路径
    # 3) 低相似度 (<0.5) 不再直接 unsatisfied：
    #    改标 needs_human_review（partial 语义），报告提示"待人工确认"
```

- `needs_human_review` 是**新增第四态**（satisfied/partial/unsatisfied/needs_human_review），
  报告与 bangcle-contract 满足度映射同步更新（本期只设计，落 P2 时与合同组件一起改，避免碰验证会话）；
- 人工确认后 `add_alias("contract_text", 原词, confidence)` 补录 → 下次自动命中。

---

## 6. 导入幂等改造（P3）

`io.py` 现状：按"名称+版本"去重，无全局唯一约束。

改造：
- `create_product` 前先 `resolve("price_excel", 价格表原始名称)` 或按 canonical_key 查 `product_identity`；
- 命中 → 更新既有 product（update_product），不新增；未命中 → 新建 product + register + add_alias("price_excel", 原词)；
- 同一价格表重复导入 → 全幂等，不产生双记录（验收标准 4）。

---

## 7. CLI 扩展（P3）

```bash
python3 product_kb/cli.py identity-backfill          # P1: 为 193 产品生成 canonical_key
python3 product_kb/cli.py alias-add <product_id> --system contract_text --key <原词>
python3 product_kb/cli.py alias-list [--product <id>]
python3 product_kb/cli.py merge <from_id> <into_id> --actor <谁>      # 软归并
python3 product_kb/cli.py resolve --system contract_text --key <原词> # 返回 product_id
python3 product_kb/cli.py identity-conflicts         # 列出待人工裁定冲突组
```

---

## 8. 迁移策略与碰撞规避（对齐案例验证会话）

| Phase | 内容 | 触碰 | 碰撞风险 |
|---|---|---|---|
| P1 | 建表 + backfill 193 + resolve API + 单测 | product_kb.db（加表不迁旧数据） | 🟡 加表不删改，读路径零变化；等验证会话收口后执行 |
| P2 | ContractMatcher 接入 resolve + needs_human_review | contract.py | 🟠 与 bangcle-contract 报告联改；**在验证会话收口后**执行 |
| P3 | io.py 幂等 + CLI | io.py + cli.py | 🟡 |
| P4 | 审计/回滚（identity_audit）+ 批量别名回填 | 新表 + 脚本 | 🟢 |

- **P1 只加表不迁移旧数据**：product_kb.db 现有 193 产品零改动，案例验证会话读路径不受影响；
- 全部增量幂等；软归并不物理删；每个 Phase 独立 VERIFICATION。

---

## 9. 测试计划

| 层 | 用例 |
|---|---|
| 单测 canonical_key | 193 条全量生成无空值无重复；V4/V5 同根区分；全角/标点/大小写归一 |
| 单测 IdentityService | register 冲突抛错；resolve CWA 命中/未命中；merge alias 转移+去重+可回滚；list 过滤 |
| 单测 ContractMatcher | 别名命中跳阈值；低相似度 -> needs_human_review；红线/停售逻辑不变 |
| 集成 | 价格表重复导入幂等；报告满足度四态映射 |
| 回归 | L2 114 / L3 42 / L4 20 零破坏（P2 落地后新增用例） |

---

## 10. 验收标准（对齐 OUTLINE §8）

1. 193 产品 canonical_key 全量生成，0 冲突（实测规则），无空值；
2. `resolve('contract_text','API安全平司软件V3.0')` 别名已录 → 命中 API安全平台软件V3.0；未录 → None；
3. ContractMatcher 低相似度输出 needs_human_review，不再硬判 unsatisfied；
4. 重复导入同一价格表幂等，无双记录；
5. 软归并 alias 全转移、旧身份 merged 可查、可回滚；
6. 三层测试零破坏。

---

## 11. 变更历史
| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-11-02 | v1.0 | 初稿（O1 定稿方案 B+：本地表、算法对齐 L2；canonical_key 保留版本号实测 0 冲突） |

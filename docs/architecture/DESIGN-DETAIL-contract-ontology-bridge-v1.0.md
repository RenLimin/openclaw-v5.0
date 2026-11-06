# DESIGN-DETAIL — Contract Ontology Bridge v1.0（P1/P2 范围）

> 前置：OUTLINE v1.0 已获 Rex 评审通过（`ac9faff`，2026-11-04）。
> 范围：**P1 只读桥 + P2 持久化/状态机接线**。P3（审批节点映射+push_result）/P4（回调/真写回）**冻结**，待泛微 workflow 数据源确认。
> 依据：真实代码通读（L3 785 行 / L4 oa 1571 行 / db.py 227 行）+ 既有测试契约（`test_oa_helpers` / `test_state_machine` / `test_oa_base`）+ 黄金夹具 `golden_expected.json`。
> 日期：2026-11-04 · Jerry 🦞
>
> 📌 **关系指针（2026-11-06 追加）**：本文档属 11-04 只读/持久化桥旧路线；与 11-05 Palantir 动词桥（L4 `contract_review/ontology_bridge/`，`a1efeb4`）并存。旧桥=读得准/对得齐，动词桥=可审计写回。详见同目录 `DESIGN-OUTLINE-contract-ontology-bridge-v1.0.md` 顶部关系指针。

## 1. 设计目标与边界

| 目标 | 说明 |
|---|---|
| 桥接 | 泛微 Cube 合同卡片 ↔ L3 `Contract` 领域模型的可复现纯映射 |
| 适配 | `CubeClient` 实现 L3 `OaProvider`（只读方法先行，写方法显式拒绝） |
| 接线 | L4 `contract_service` 调用 L3 状态机推进**本地**合同生命周期并持久化 |
| 不碰 | L3/L2 源码与测试；不做泛微真写回；不物理删除；不加第三方依赖 |

**红线重申**：`validated ≠ committed`；审批态无数据源时一律 `unknown`；迁移增量幂等；审计 append-only。

---

## 2. 接口契约

### 2.1 P1 — `ontology/mapper.py`（纯函数，零副作用）

```python
# 输入：Cube 卡片主字段 dict（extract_main_fields 输出，{显示名: str}）
# 输出：L3 Contract 实例（id=None, status="draft" 占位——审查域不推进审批）

FIELD_ALIASES = {
    "contract_no":  ("合同编号", "合同号", "编号"),
    "title":       ("合同名称", "标题", "合同标题"),
    "contract_type": ("合同类型", "类型"),
    "party_a":     ("甲方", "委托方", "客户名称"),
    "party_b":     ("乙方", "受托方", "供应商名称"),
    "amount":      ("合同金额", "金额", "合同总金额", "含税金额"),
    "effective_date": ("生效日期", "合同生效日"),
    "expiry_date": ("到期日期", "合同到期日", "截止日期"),
}

def map_card_to_contract(main_fields: dict) -> Contract:
    """确定性映射：按 FIELD_ALIASES 取首个命中标签的值。
    amount 解析：剥离 '¥','元','人民币','万' 等；含 '万' 按 1e4 换算。
    未命中字段留默认值；不抛错（字段缺失 ≠ 失败）。"""

def map_contract_to_card(contract: Contract) -> dict:
    """反向映射（用于未来展示/写回，P1 仅测试用）。"""

# 状态映射（P1 无 workflow 数据源 → 恒 unknown）
def map_oa_status(status_payload: Any, available: bool = False) -> dict:
    """返回 {"l3_status": str, "confidence": float, "source": str}
    available=False 时恒为 {"l3_status": "unknown", "confidence": 0.0, "source": "unavailable"}。"""
```

### 2.2 P1 — `services/oa/cube_provider.py`（适配 OaProvider）

```python
class CubeOaProvider(OaProvider):
    """把既有 CubeClient 适配为 L3 OaProvider。

    - get_contract_attachment(pid) -> ContractData（复用 cube.get_contract）
    - query_process(pid)          -> {"process_status": "unknown", "node": None,
                                      "confidence": 0.0, "source": "workflow-api-unavailable"}
                                    （泛微 workflow 审批流未接入，绝不伪造）
    - push_result(...)            -> raise NotImplementedError（P4 前冻结）
    - register_callback(handler)  -> raise NotImplementedError（P4 前冻结）
    """

def build_cube_provider(storage_state=None, **kw) -> CubeOaProvider: ...
```

### 2.3 P2 — `services/contract_service.py`

```python
def create_contract_from_card(card_main_fields: dict, *, db_path=None) -> Contract:
    """映射 + 落库（状态恒 draft）+ 审计（action='create'）。返回带 id 的 Contract。"""

def apply_action(contract_id: int, action: str, *, operator: str,
                 approver_role: str = "", comment: str = "",
                 db_path=None) -> dict:
    """读合同 → 调 L3 next_approval_status/ApprovalStateMachine 计算 → 校验合法 →
    落库（新状态 + approval_record + audit_log）→ 返回结果 dict（含 next_status）。

    规则：只接受 submit/approve/reject/sign/archive；
    状态非法 → 抛 ContractStateError，不落任何行（原子）。"""

def list_contracts(status=None, *, db_path=None) -> list[dict]: ...
def get_contract(contract_id: int, *, db_path=None) -> dict: ...   # 含审批记录+审计
```

### 2.4 P2 — `repository/db.py` 增量迁移

```python
# 新表（幂等 CREATE TABLE IF NOT EXISTS；与既有 reviews 三表共存）
SCHEMA_V2 = SCHEMA_STATEMENTS + (
    """
    CREATE TABLE IF NOT EXISTS contracts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        contract_no TEXT, title TEXT, contract_type TEXT,
        party_a TEXT, party_b TEXT, amount REAL,
        status TEXT NOT NULL DEFAULT 'draft',
        current_approver TEXT,
        effective_date TEXT, expiry_date TEXT,
        oa_billid TEXT,                 -- 泛微卡片主键（唯一，可空）
        extra TEXT,                     -- JSON dict
        created_at TEXT NOT NULL, created_by TEXT,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS approval_instances (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        contract_id INTEGER NOT NULL REFERENCES contracts(id),
        level INTEGER, status TEXT, action TEXT,
        approver_role TEXT, approver_name TEXT, comment TEXT,
        created_at TEXT NOT NULL
    )
    """,
)
# 索引：contracts(oa_billid) UNIQUE WHERE oa_billid IS NOT NULL（幂等 IF NOT EXISTS）
# Repository 增：add_contract / update_contract_status / add_approval_instance /
#               list_contracts / get_contract_with_history（JOIN 两表）
# audit_logs 保持 append-only：新增 action 名 'create'/'submit'/'approve'/'reject'/'sign'/'archive'/'state_error'
```

---

## 3. 数据流

```
[泛微 Cube 卡片] --CubeClient.get_contract--> ContractData
  -> H.extract_main_fields -> {合同编号:..., 合同金额:...}
  -> mapper.map_card_to_contract -> L3 Contract(status=draft)
  -> contract_service.create_contract_from_card -> Repository.add_contract + append_audit_log
  -> 后续本地动作 -> L3 next_approval_status(amount,status,action) -> 合法则
     update_contract_status + add_approval_instance + append_audit_log（单事务）
```

**状态推进只由 L3 状态机裁决**；L4 只做读库/落库/编排，不做规则计算（OUTLINE §4 分层原则）。

---

## 4. 测试方案（真实执行）

### P1 单元（`tests/unit/`）
| 用例 | 断言 |
|---|---|
| `test_mapper_card_to_contract` | 用 `test_oa_helpers` 真实形态（`{"fields":[{"fieldlabelname":"合同编号","fieldvalue":"XSZS001"}]}`）→ Contract 字段映射正确 |
| 金额解析 | "人民币 12.5 万元" → 125000.0；"¥1,000,000" → 1000000.0；缺失 → 0.0 |
| 别名优先级 | 多标签命中取 FIELD_ALIASES 首个 |
| 缺失字段 | 不抛错，留默认值 |
| `test_cube_provider_implements_oa` | `issubclass(CubeOaProvider, OaProvider)`；`query_process` 返 unknown 信封；`push_result`/`register_callback` 抛 NotImplementedError |
| `test_map_oa_status` | `available=False` 恒 unknown/0.0/unavailable |

### P2 单元 + 集成（`tests/unit/` + `tests/integration/`）
| 用例 | 断言 |
|---|---|
| 迁移幂等 | `init_db()` 连跑 3 次：表结构一致、无重复索引、既有 reviews 表不受影响 |
| create 闭环 | 映射→落库→audit `create`；返回 id；状态 draft |
| 状态机接线 | 4 级合同 submit→review1→…→approved→signed→archived 全路径真实 SQLite 走通；每步 approval_instance + audit 落行 |
| 非法动作 | 非法 transition 抛错且**无任何行落库**（原子性） |
| 审计 append-only | Repository 无 update/delete 审计方法（接口级断言）；audit 行数只增 |
| 幂等 ×3 | 同输入连跑 3 次结果一致（验收 7 步法） |
| 黄金基准 | 映射结果与冻结 fixture（`tests/fixtures/card_golden.json` 新增）逐字段比对 |

### 不纳入
- 真实泛微 HTTP（无凭据/内网，P3 起）；visual/E2E 沿用既有 run-visual-tests.sh 隔离。

---

## 5. 文件清单（新增/修改）

```
L4-proprietary/components/bangcle-contract/
├── ontology/__init__.py            A
├── ontology/mapper.py              A
├── services/oa/cube_provider.py    A
├── services/contract_service.py    A
├── repository/db.py                M（V2 增量，不破坏既有）
├── tests/unit/test_mapper.py       A
├── tests/unit/test_cube_provider.py A
├── tests/unit/test_contract_service.py A
├── tests/integration/test_bridge_e2e.py A
└── tests/fixtures/card_golden.json A
```

**不修改**：L3 全部；L4 `cube.py`/`helpers.py`/`entry.py`/`browser_fallback.py`/`contract_review/*`（只 import 复用）。

---

## 6. 验收标准（出口）

1. P1+P2 全量测试真实执行通过（新增 ≥ 25 用例），L4 bangcle-contract 既有 127 passed 不回退；
2. 迁移幂等 ×3、审计 append-only 有测试锁定；
3. 状态机全路径在真实 SQLite 上跑通，非法动作零落库；
4. 审批状态映射无数据源时恒 unknown（有测试断言）；
5. 全仓跨层回归 L2/L3 不受影响（提交后复跑抽查）。

## 7. 待确认
- `oa_billid` 唯一索引：同一泛微卡片重复导入 → 抛错还是 upsert？**默认抛错（幂等导入由调用方去重）**，如需 upsert 请指出。

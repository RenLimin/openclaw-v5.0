# L3 通用合同管理专家 — 详细设计（DESIGN-DETAIL）

| 项 | 值 |
|---|---|
| 文档 | DESIGN-DETAIL |
| 版本 | v1.0 |
| 层级 | L3 通用业务层 |
| 组件编码 | contract-management（CLM-GEN-001） |
| 状态 | 待审核 |
| 依据 | PRD-v1.0 + DESIGN-OUTLINE-v1.0 + 旧 core 742 行已验证实现 + OA 侦察结论（2026-10-27） |

> **契约性质**：本文档冻结公开 API 签名与数据模型字段。L4 依赖其稳定演进；签名变更须升 major 版本并经 Rex 审核。

---

## 1. 模块清单与文件契约

| 文件 | 职责 | 公开符号 |
|---|---|---|
| `core/models.py` | 数据模型 + 状态常量 | 见 §2 |
| `core/state_machine.py` | 分级配置 + 状态机函数 + OO 包装 | 见 §3 |
| `core/risk_engine.py` | 风险规则 + 扫描引擎 | 见 §4 |
| `core/amount_utils.py` | 金额中文大写 | 见 §5 |
| `core/oa/base.py` | OA 连接器抽象（ABC，零实现） | 见 §6 |
| `core/__init__.py` | 公共 API 导出 | 见 §7 |

**依赖铁律**：模块间仅允许 `state_machine/risk_engine → models`、`__init__ → 全部`。禁止反向、禁止任何 import L4、禁止 import `os/sys/subprocess/socket/urllib/sqlite3`（`oa/base.py` 仅允许 `abc`/`typing`）。

---

## 2. 数据模型契约（`core/models.py`）

仅依赖 `dataclasses` / `typing` / `datetime`。所有 dataclass 为可变 dataclass 但语义上 L3 函数**不修改入参**。

### 2.1 状态常量

```python
CONTRACT_STATUSES: dict[str, str] = {
    "draft": "起草", "review1": "一级审批", "review2": "二级审批",
    "review3": "三级审批", "approved": "审批通过", "signed": "已签署",
    "archived": "已归档", "rejected": "已驳回",
}

VALID_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"review1"},
    "review1": {"draft", "review2", "approved"},
    "review2": {"draft", "review3", "approved"},
    "review3": {"draft", "approved"},
    "approved": {"signed"},
    "signed": {"archived"},
    "archived": set(),
    "rejected": {"draft"},
}
```

### 2.2 dataclass 字段（冻结）

| 类 | 字段（名: 类型 = 默认） |
|---|---|
| `ApprovalConfig` | `level: int` · `roles: List[str]` · `sla_days: Optional[int] = None` |
| `Contract` | `id: Optional[int] = None` · `contract_no: str = ""` · `title: str = ""` · `contract_type: str = "tech_service"` · `party_a: str = ""` · `party_b: str = ""` · `amount: float = 0.0` · `status: str = "draft"` · `current_approver: Optional[str] = None` · `created_by: str = ""` · `effective_date: Optional[str] = None` · `expiry_date: Optional[str] = None` · `extra: Dict[str, Any] = field(default_factory=dict)` |
| `ApprovalRecord` | `id: Optional[int] = None` · `contract_id: int = 0` · `approval_level: int = 0` · `approver_role: str = ""` · `approver_name: str = ""` · `action: str = ""` · `comment: str = ""` · `created_at: str = ""` |
| `AuditLogEntry` | `id: Optional[int] = None` · `contract_id: int = 0` · `action: str = ""` · `operator: str = ""` · `from_status: Optional[str] = None` · `to_status: Optional[str] = None` · `detail: Optional[Dict[str, Any]] = None` · `created_at: str = ""` |
| `RiskFinding` | `id: str` · `category: str` · `item: str` · `status: str`（pass/warning/fail）· `risk: str`（high/medium/low）· `law: str` |
| `RiskReport` | `overall_risk: str` · `summary: Dict[str,int]` · `findings: List[RiskFinding]` · `scan_time: str = ""` + 方法 `to_dict() -> Dict[str, Any]` |

**契约扩展规则**：新增字段只能带默认值追加到末尾（不破坏 L4 既有构造）；`extra` 是 L4 透传 OA/KB 等专有字段的唯一通道，L3 不读取其内容。

---

## 3. 状态机契约（`core/state_machine.py`）

### 3.1 分级表类型与默认值

```python
LevelTable = List[Tuple[float, float, int, List[str]]]

DEFAULT_APPROVAL_LEVELS: LevelTable = [
    (0,        100_000,   1, ["销售经理"]),
    (100_000,  500_000,   2, ["销售经理", "法务审查员"]),
    (500_000,  2_000_000, 3, ["销售总监", "法务审查员", "财务经理"]),
    (2_000_000, float("inf"), 4, ["VP/CEO", "法务总监", "财务总监"]),
]
```

边界口径：左闭右开 `[min, max)`；命中区间的 `roles` 为**该金额需要经过的全部角色序列**。

### 3.2 纯函数签名（冻结）

```python
def get_approval_config(amount: float,
                        level_table: Optional[LevelTable] = None
                        ) -> ApprovalConfig: ...

def can_transition(from_status: str, to_status: str) -> bool: ...

def next_approval_status(amount: float, current_status: str, action: str,
                         level_table: Optional[LevelTable] = None
                         ) -> Tuple[str, Optional[str], int]:
    """返回 (next_status, next_approver_role, current_level)。
    action ∈ {"submit","approve","reject","sign","archive"}。
    非法 action/状态组合 → raise ValueError。"""
```

**动作→状态映射**（与 §2.1 `VALID_TRANSITIONS` 一致，二者由测试锁定一致）：

| action | 前置状态 | 下一状态 | 备注 |
|---|---|---|---|
| submit | draft | review1 | next_role = roles[0] |
| approve | reviewN | N<level → review(N+1)；N==level → approved | next_role = roles[N] 或 None |
| reject | reviewN | draft | — |
| sign | approved | signed | — |
| archive | signed | archived | — |

### 3.3 OO 包装 `ApprovalStateMachine`

```python
class ApprovalStateMachine:
    def __init__(self, contract: Contract,
                 level_table: Optional[LevelTable] = None): ...
    # 只读属性: level, roles
    # 布尔判定: can_submit/can_approve/can_reject/can_sign/can_archive
    # 动作方法（不修改 self.contract，返回 dict）:
    def submit(self, operator: str) -> dict: ...
    def approve(self, approver_name: str, approver_role: str,
                comment: str = "") -> dict: ...
    def reject(self, approver_name: str, approver_role: str,
               comment: str) -> dict: ...
    def sign(self, operator: str) -> dict: ...
    def archive(self, operator: str) -> dict: ...
```

返回 dict 固定键：

| 方法 | 键 |
|---|---|
| submit | `next_status`, `next_approver_role`, `audit_log`(AuditLogEntry), `detail`, `total_steps` |
| approve | `next_status`, `next_approver_role`, `approval_record`(ApprovalRecord), `audit_log`, `step`, `total_steps` |
| reject | `next_status`, `approval_record`, `audit_log`, `rejected_at_level` |
| sign/archive | `next_status`, `audit_log` |

---

## 4. 风险引擎契约（`core/risk_engine.py`）

### 4.1 规则类型

```python
@dataclass
class RiskRule:
    id: str
    category: str
    item: str
    risk: str            # high / medium / low
    law: str             # 法条依据，如 "§585"；无则 "—"
    check: Callable[[str], bool]   # True=通过
```

### 4.2 默认规则集 `CHECK_RULES`

22 条，按类别组织（id 沿用旧实现，迁移时**保持 id 不变**以维持报告可追溯）：

| 类别 | 条目数 | id 前缀 | 覆盖要点 |
|---|---|---|---|
| 主体信息 | 4 | 1.x | 名称/地址/联系方式/签字盖章 |
| 合同标的 | 2 | 2.x | 服务内容/期限 |
| 金额与支付 | 4 | 3.x | 大小写金额/税率/支付方式/发票 |
| 验收标准 | 1 | 5.x | 验收方式 |
| 违约责任 | 2 | 6.x | 违约条款/违约金 ≤30% |
| 争议解决 | 2 | 7.x | 管辖明确/方式唯一 |
| 知识产权 | 1 | 8.x | 归属 |
| 保密条款 | 2 | 9.x | 条款/期限 |
| 不可抗力 | 1 | 10.x | 条款 |
| 合同解除 | 1 | 11.x | 解除条件 |
| 其他 | 2 | 13.x | 份数/生效条件 |

辅助函数 `_check_penalty_reasonable(text) -> bool`：匹配 `违约金/百分之/按…%`，任一比例 >30 即不通过。

### 4.3 扫描函数（冻结）

```python
def scan_text(text: str,
              custom_rules: Optional[List[RiskRule]] = None
              ) -> RiskReport: ...

def scan_text_dict(text: str,
                   custom_rules: Optional[List[RiskRule]] = None
                   ) -> Dict[str, Any]: ...
```

判定口径：
- 规则通过 → `status="pass"`；不通过且 `risk=="high"` → `"fail"`；其余不通过 → `"warning"`
- 综合评级：有 fail → `high`；warning > 2 → `medium`；否则 `low`
- `custom_rules` 语义为**整体替换**默认集（非追加），由 L4 自行决定合并策略
- `RiskReport.to_dict()`：findings 展开为 dict 列表（键 `id/category/item/status/risk/law`），不暴露嵌套对象

---

## 5. 金额工具契约（`core/amount_utils.py`）

```python
def amount_to_chinese(amount: float) -> str: ...
```

| 输入 | 输出 |
|---|---|
| `0` | `零元整` |
| `12345.67` | `壹万贰仟叁佰肆拾伍元陆角柒分` |
| 负数 | `负` + 绝对值大写 |
| 整数（小数为 0） | 末尾加 `整` |

口径：整数部分按 拾/佰/仟/万/亿 位；小数保留两位（角/分）；连续零合并为单个「零」。

---

## 6. OA 连接器抽象（`core/oa/base.py`）

仅用 `abc` + `typing`，**无任何实现、无网络/文件调用**。厂商实现放 L4。

```python
from abc import ABC, abstractmethod

class OaProvider(ABC):
    @abstractmethod
    def get_contract_attachment(self, process_instance_id: str) -> "Attachment": ...
    @abstractmethod
    def query_process(self, process_instance_id: str) -> "ProcessInfo": ...
    @abstractmethod
    def push_result(self, process_instance_id: str, action: str,
                    comment: str, approver: str) -> bool: ...
    @abstractmethod
    def register_callback(self, handler) -> None: ...
```

`Attachment` / `ProcessInfo` 的数据结构定义放 `models.py` 时若引入须保持纯数据；本期 L3 仅以字符串注解引用，具体结构在 L4 DETAIL 定义。

---

## 7. 公共 API 导出（`core/__init__.py`）

```python
__all__ = [
    # models
    "Contract", "ApprovalRecord", "AuditLogEntry", "RiskReport",
    "RiskFinding", "ApprovalConfig", "CONTRACT_STATUSES",
    "VALID_TRANSITIONS",
    # state_machine
    "ApprovalStateMachine", "get_approval_config",
    "can_transition", "next_approval_status",
    # risk_engine
    "scan_text", "scan_text_dict", "RiskRule", "CHECK_RULES",
    # amount_utils
    "amount_to_chinese",
    # oa
    "OaProvider",
]
```

---

## 8. 错误与边界约定

| 情形 | 行为 |
|---|---|
| 非法状态/动作组合 | `raise ValueError`，消息含当前状态 |
| 未知 action | `raise ValueError(f"未知操作: {action}")` |
| 金额未命中任何区间（不应发生） | fallback 最低级（level=1，roles=首行角色） |
| `custom_rules=None` | 使用 `CHECK_RULES`；空列表 `[]` 为合法（产出 0 finding 的 low 报告） |

---

## 9. 与 OA 侦察事实的对齐（2026-10-27）

> 侦察结论影响 **L4** 实现，不改变 L3 纯逻辑契约；此处记录以保证 L3 不为不存在的标准工作流假设提供耦合。

1. Bangcle OA 实测为 **泛微 e-cology 9 + 建模引擎 Cube 自定义应用**（未登录指纹误指向 E8，登录后 `spa=True` 翻转）。
2. 合同数据主键是建模记录 **`billid`**（卡片 URL `/spa/cube/card?modeId=112&formId=-249&billid=...`），**无标准工作流 `requestid/docid`**。
3. 主表 `uf_xsht_xxb`，明细表 `uf_xsht_xxb_dt2/dt3/dt5/dt8`；附件为建模上传字段（`maxUploadSize=5` MB/项，按"新签产品/新签服务"等选项分组）。
4. Cube 内部 REST 接口（`/api/cube/new/card/initDetail|getDetailFields|mainFields` 等）在浏览器会话内可用 → L4 可走"内部接口 + storage_state 复用"或浏览器自动化兜底，**详见 L4 DESIGN-DETAIL**。
5. 结论：L3 的 `OaProvider` 抽象保持厂商中立；`process_instance_id` 在 Bangcle 实现里实际承载 `billid`（字符串透传，L3 不解释）。

---

## 10. 变更历史

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-10-27 | v1.0 | 初版：冻结 6 模块契约 + 对齐旧 core 742 行 + OA Cube 侦察事实 |

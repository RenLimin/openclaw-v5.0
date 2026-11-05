# VERIFICATION — P2 动力学层 + 注册中心（operational-ontology v1.0）

> 日期：2026-10-31 · 对应 IMPLEMENTATION-PLAN P2（T2.1–T2.5）
> 依据：DESIGN-DETAIL-operational-ontology-v1.0 §2.2（DDL）、§3.2（ActionRegistry）
> 前置：P1 身份层（migration v8，ai_kb/ontology/identity.py）已完成

## 1. 改动 / 新增文件

| 文件 | 类型 | 说明 |
|---|---|---|
| `ai_kb/db.py` | 修改（纯增量） | 新增 `init_ontology_kinetic_tables()`：创建 `ont_action_type`、`ont_function_def` 两表，并幂等登记 migration v9（name=`operational_ontology_kinetic`）。未改动任何既有表与只读路径。 |
| `ai_kb/ontology/actions.py` | 新增 | `AssemblyGate`、`ActionRegistry`、`parse_handler_ref`、`load_handler`。DI db、全量类型注解、snake_case。 |
| `ai_kb/ontology/__init__.py` | 修改（增量导出） | 导出 `ActionRegistry` / `AssemblyGate` / `load_handler` / `parse_handler_ref`；P1 导出保持不变。 |
| `tests/test_ontology_actions.py` | 新增 | 24 个用例，临时 SQLite 真实跑通（无 DB mock）。 |

红线遵守：未触碰 L3/L4（BDMS/product-kb）、未修改 `api.py`、`mcp/`；未引入第三方依赖（仅标准库 importlib/json/sqlite3/contextlib）；无凭据。

## 2. 新增表（DDL 严格按 §2.2）

- **`ont_action_type`**：`domain_id`（FK→domain）、`name`、`object_type`、`params_schema`、`precondition`、`required_approval NOT NULL DEFAULT 'none'`、`writeback_target`、`version DEFAULT 1`、`status DEFAULT 'active'`、时间戳；`UNIQUE(domain_id, name, version)`。
- **`ont_function_def`**：`domain_id`（FK→domain）、`name`、`kind`、`handler_ref NOT NULL`、`io_schema`、`deterministic INTEGER DEFAULT 1`、`version DEFAULT 1`、`status DEFAULT 'active'`、时间戳；`UNIQUE(domain_id, name, version)`。

## 3. 新增方法 / 行为

| 成员 | 行为 |
|---|---|
| `ActionRegistry.register_action_type(...)` | 装配期；返回 id；重复 (domain,name,version) → `sqlite3.IntegrityError`；校验 approval 取值与 params_schema JSON。 |
| `ActionRegistry.register_function(...)` | 装配期；返回 id；校验 kind（rule/state_machine/risk/compute）与 handler_ref 语法；不立即 import。 |
| `get_action` / `get_function` | 读通道，运行期可用；默认取最高版本，可指定 version；未命中返回 None。 |
| `list_actions(domain)` | MCP 工具发现用；JSON 字段反序列化；按 name,version 排序。 |
| `validate_function_handler(domain, name, *, version=None, for_write=False)` | 注册后惰性加载并返回可调用对象；`for_write=True` 时 deterministic≠1 抛 ValueError。 |
| `load_handler(ref)` | `importlib.import_module` + 属性链解析；模块缺失→ImportError、属性缺失→AttributeError、不可调用→TypeError（fail-fast）。 |
| `AssemblyGate` | 默认关闭（运行期），register_* 入口 `require_open()` 抛 RuntimeError；`gate.open()/close()` 与 `with gate.assembly():` 供 CLI/装配脚本显式开启。 |

domain 同时接受 id（int）与 code（str），`_resolve_domain_id` 风格与 identity.py 一致；actions.py 不反向依赖 identity 模块。

## 4. 测试命令与实际结果

```bash
cd L2-infra/components/ai-knowledge-base
python3 -m pytest tests/ -q
python3 -m pytest tests/integration/ -q
```

实际结果（2026-10-31，本机 Python 3 / SQLite）：

- `tests/test_db.py` + `tests/test_ontology_identity.py` + `tests/test_ontology_actions.py`：**39 passed**（其中 P2 新增 24 个）
- `python3 -m pytest tests/ -q`：**46 passed**
- `python3 -m pytest tests/integration/ -q`：**5 passed**
- 全部合计 **51 passed，0 failed**

P2 用例覆盖：注册 action_type/function（id 与 code 两种 domain 形式）、重复 (domain,name,version) 冲突、同名多版本共存与默认取最高版、get/list 与未命中、handler 惰性加载成功（临时目录真实模块）、坏 handler（模块不存在→ImportError / 属性不存在→AttributeError / 不可调用→TypeError / 格式非法注册即拒）、deterministic=0 禁止写校验路径但读路径可用、AssemblyGate 运行期拒绝 register_* 且读路径正常、装配上下文 with 块与显式 open/close。

验收门核对：
- ✅ 运行期无法注册结构（RuntimeError）
- ✅ 非 deterministic function 不可用于写路径（ValueError）
- ✅ 既有测试无回归

## 5. 遗留 TODO

1. **P3**：`ont_proposal` / `ont_decision_record`、ProposalService（propose/validate/review/commit）、OutputGuard、MCP 三分类与 REST `/ontology/proposals`。
2. handler 执行沙箱与"以调用者权限执行"约束在 P3 OutputGuard 内落地；当前仅完成加载与 fail-fast，未执行 handler。
3. `precondition` 中引用 function 的绑定解析（action→function 的装配期一致性校验）留待 P3 校验链实现。
4. identity.merge 中的 `ont_decision_record` 占位记录待 P3 表建立后替换为实写（P1 已标注 TODO(P3)）。

# L3 通用合同管理专家 — 操作手册（OPERATIONS）

| 项 | 值 |
|---|---|
| 文档 | OPERATIONS |
| 版本 | v1.0 |
| 组件编码 | contract-management（CLM-GEN-001） |
| 依据 | PRD / DESIGN-DETAIL / VERIFICATION v1.0 |

> L3 是**纯逻辑库**，无独立进程、无配置文件、无外部依赖。操作仅涉及：作为依赖被引用、跑测试、版本管理。

---

## 1. 环境要求

| 项 | 要求 |
|---|---|
| Python | ≥ 3.10 |
| 第三方依赖 | **无**（仅 stdlib：dataclasses/typing/re/datetime/abc） |
| 测试 | pytest（开发期） |
| 网络/DB/文件 | 不需要 |

---

## 2. 目录结构

```
contract-management/
├── core/
│   ├── __init__.py        # 公共 API 导出
│   ├── models.py
│   ├── state_machine.py
│   ├── risk_engine.py
│   ├── amount_utils.py
│   └── oa/base.py
├── tests/
└── docs/                  # PRD/OUTLINE/DETAIL/VERIFICATION/OPERATIONS
```

---

## 3. 作为依赖引用

```python
from contract_management import (
    Contract, ApprovalStateMachine, scan_text, amount_to_chinese,
)
```

- 由 L4 把 `core/` 所在路径加入 `sys.path`（或组件以包方式安装）；L3 自身不提供 setup 安装脚本，沿用工作区分层直接引用约定。
- 调用方负责传入数据、持久化结果；L3 不做任何 I/O。

---

## 4. 运行测试

```bash
cd <repo>
python3 -m pytest L3-business/components/contract-management/tests/ -q
# 纯净性
python3 -m pytest L3-business/components/contract-management/tests/test_purity.py -q
```

异常排查：

| 现象 | 原因 / 处理 |
|---|---|
| import 失败 | L4 未把组件路径加入 PYTHONPATH；检查调用脚本的 path 注入 |
| test_purity 报黑名单 import | 有人在 core 引入 os/sqlite3/网络等 → 必须移出到 L4 |
| ValueError「未知操作/状态」 | 调用方传入非法状态组合；核对 DETAIL §3/§8 |

---

## 5. 升级与兼容

- 公开 API 签名冻结；新增字段只能带默认值末尾追加。
- 破坏性变更升 major 版本并经 Rex 审核；纯增补升 minor。
- 22 条规则 `id` 不得改（报告可追溯性）；新增规则用新 id。

---

## 6. 变更历史

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-10-27 | v1.0 | 初版 |

# Tool Policy — 工具策略与权限

> **状态**: 📐 骨架阶段 (v0.1)
> **所属层**: L1 Runtime
> **依赖**: L1 RuntimeAdapter（提供工具执行）

---

## 1. 职责

统一管理**工具可见性、调用权限与执行策略**。

- 工具白/黑名单：哪些 Agent / 用户 / 角色可以调用哪些工具
- 策略评估：调用前检查权限，返回 allow / deny / need-approval
- 速率限制：按工具 / 按用户 / 按角色的调用频率限制
- 调用审计：所有工具调用全量记录
- 策略分级：全局策略 < 层策略 < 组件策略 < 实例策略（后者覆盖前者）

## 2. 核心接口

### 2.1 ToolPolicyEngine (ABC)

```python
class ToolPolicyEngine(ABC):
    def evaluate(self, request: ToolAccessRequest) -> PolicyDecision: ...
    def add_policy(self, policy: ToolPolicy) -> None: ...
    def remove_policy(self, policy_id: str) -> bool: ...
    def list_policies(self, scope: str | None = None) -> list[ToolPolicy]: ...
    def record_usage(self, request: ToolAccessRequest, decision: PolicyDecision) -> None: ...
    def check_rate_limit(self, key: str, tool: str) -> bool: ...
```

### 2.2 策略模型

| 策略维度 | 说明 |
|---|---|
| `scope` | global / layer / component / agent / user |
| `effect` | allow / deny |
| `tools` | 工具名匹配（支持通配符） |
| `conditions` | 附加条件（时间/IP/配额等） |
| `priority` | 优先级（数字大的先评估） |

### 2.3 PolicyDecision

| 结果 | 说明 |
|---|---|
| `ALLOW` | 允许调用 |
| `DENY` | 拒绝调用，附原因 |
| `NEED_APPROVAL` | 需要人工审批 |
| `RATE_LIMITED` | 被限流 |

---

## 3. 状态

| 模块 | 状态 | 说明 |
|---|---|---|
| 策略数据模型 | ✅ 骨架 | `models.py` |
| PolicyEngine ABC | ✅ 骨架 | `policy_engine.py` |
| 内存实现 | 📋 待开发 | InMemoryPolicyEngine |
| YAML 配置加载 | 📋 待开发 | 从配置文件加载策略 |
| 与 RuntimeAdapter 集成 | 📋 待开发 | 工具调用前钩子 |

## 4. 测试

| 测试文件 | 用例数 | 覆盖 |
|---|---|---|
| `test_tool_policy_skeleton.py` | 7 | ABC 契约 / 策略模型 / 决策逻辑 |

> 注：L2-infra 已有一个 `tool-policy` 组件（audit 脚本），两者职责不同。
> L1 版本是**策略引擎**（决策 + 权限模型），L2 版本是**运行时策略审计工具**（检测配置是否合规）。

# Agent Registry — Agent 注册与发现

> **状态**: 📐 骨架阶段 (v0.1)
> **所属层**: L1 Runtime
> **依赖**: L1 RuntimeAdapter（提供底层执行能力）

---

## 1. 职责

管理系统中所有 Agent 的**注册、发现、元数据与生命周期**。

- Agent 注册：声明式注册 Agent（名称 / 描述 / 能力标签 / 配置 schema）
- Agent 发现：按能力 / 角色 / 标签查询可用 Agent
- Agent 实例化：根据注册信息创建 Agent 实例（通过 RuntimeAdapter）
- Agent 元数据：描述、版本、作者、输入输出 schema、依赖声明
- Agent 健康：Agent 可用性探测

## 2. 核心接口

### 2.1 AgentRegistry (ABC)

```python
class AgentRegistry(ABC):
    def register(self, spec: AgentSpec) -> None: ...
    def unregister(self, agent_id: str) -> bool: ...
    def get(self, agent_id: str) -> AgentSpec | None: ...
    def find_by_capability(self, capability: str) -> list[AgentSpec]: ...
    def find_by_tag(self, tag: str) -> list[AgentSpec]: ...
    def list(self) -> list[AgentSpec]: ...
    def instantiate(self, agent_id: str, **kwargs) -> AgentHandle: ...
    def health_check(self, agent_id: str) -> HealthStatus: ...
```

### 2.2 AgentSpec (dataclass)

| 字段 | 类型 | 说明 |
|---|---|---|
| `agent_id` | str | 全局唯一标识 |
| `name` | str | 显示名称 |
| `description` | str | 描述 |
| `version` | str | 语义化版本 |
| `capabilities` | list[str] | 能力标签（用于发现） |
| `tags` | list[str] | 自定义标签 |
| `runtime` | str | 所需运行时（openclaw / claude-code / ...） |
| `model` | str \| None | 绑定的模型（可选） |
| `entrypoint` | str | 入口（skill 路径 / agent ID / 指令文件） |
| `input_schema` | dict | 输入参数 JSON Schema |
| `output_schema` | dict | 输出 JSON Schema |

### 2.3 AgentHandle (dataclass)

已实例化的 Agent 句柄，含运行时引用 + 状态。

---

## 3. 状态

| 模块 | 状态 | 说明 |
|---|---|---|
| AgentSpec 数据模型 | ✅ 骨架 | `models.py` |
| AgentRegistry ABC | ✅ 骨架 | `registry.py` |
| AgentHandle | ✅ 骨架 | `models.py` |
| 内存实现 | 📋 待开发 | InMemoryAgentRegistry |
| RuntimeAdapter 集成 | 📋 待开发 | 通过 RuntimeAdapter 实际实例化 |

## 4. 测试

| 测试文件 | 用例数 | 覆盖 |
|---|---|---|
| `test_agent_registry_skeleton.py` | 7 | ABC 契约 / 模型 / 注册发现接口 |

# L1 运行时抽象层 — 设计文档

> L1 层的核心是**运行时抽象契约**：将 Agent 运行时（OpenClaw / Claude Code / CrewAI 等）
> 的差异封装在适配层内，L2-L4 只依赖抽象接口，与具体运行时解耦。
>
> 本文档是 L1 层的单一事实来源。
>
> **状态**: ✅ 已上线 (v2.0, 2026-09-10)
> **对应 ADR**: ADR-012（Agent 运行时作为可变因素）

---

## 1. 设计目标

| 目标 | 说明 |
|---|---|
| **运行时无关** | L2-L4 代码不直接依赖任何具体运行时 API |
| **最小契约** | 只抽象当前实际需要的能力，不为未来假设过度设计 |
| **可替换性** | 切换运行时只改适配层，上层代码零修改 |
| **向后兼容** | 新 ABC 架构不破坏现有 OpenClawAdapter 直接实现 |
| **可测试** | 接口契约可通过自动化测试验证 |

---

## 2. 架构总览

```
┌──────────────────────────────────────────────────────┐
│                   L2 / L3 / L4                        │
│  只依赖 RuntimeAdapter ABC，不感知具体运行时           │
└──────────────────────────┬───────────────────────────┘
                           │ 依赖
┌──────────────────────────▼───────────────────────────┐
│             RuntimeAdapter (ABC)                      │
│  ┌─────────┬──────────┬───────────┬──────────────┐   │
│  │ Memory  │ Channel  │ Sandbox   │ Credential   │   │
│  │Interface│Interface │ Interface │  Interface   │   │
│  └─────────┴──────────┴───────────┴──────────────┘   │
│  统一数据模型 + 统一错误码 + 工厂注册机制              │
└──────────────────────────┬───────────────────────────┘
                           │ 继承
           ┌───────────────┼───────────────┐
           ▼               ▼               ▼
    ┌───────────┐   ┌─────────────┐   ┌──────────┐
    │ OpenClaw  │   │ Claude Code │   │  CrewAI  │
    │  Adapter  │   │   Adapter   │   │ Adapter  │
    └───────────┘   └─────────────┘   └──────────┘
```

### 2.1 核心设计决策

1. **ABC 而非 Protocol** — 使用 `abc.ABC` 定义抽象基类，强制继承关系，
   提供运行时类型检查和更好的 IDE 支持。

2. **子系统分离** — RuntimeAdapter 是主入口，通过 `get_memory()` / `get_channel()`
   等方法返回子系统接口实例，而非把所有方法堆在一个类上。

3. **组合模式适配** — OpenClawRuntimeAdapter 内部组合了已有的 OpenClawAdapter，
   不重写实现，只做接口映射，保持向后兼容。

4. **能力声明机制** — `capabilities` 字典 + `supports()` 方法，允许运行时
   明确声明支持/不支持的子能力，上层可据此做降级处理。

5. **工厂注册 + 懒加载** — RuntimeRegistry 支持手动注册和配置驱动的懒加载，
   可选运行时不需要在启动时全部 import。

---

## 3. 接口契约清单

### 3.1 RuntimeAdapter（主适配器）

| 方法 / 属性 | 签名 | 说明 |
|---|---|---|
| `name` | `str` | 运行时名称（kebab-case） |
| `version` | `str` | 运行时版本号 |
| `capabilities` | `Dict[str, Any]` | 能力声明字典（嵌套结构） |
| `health_check()` | `→ HealthStatus` | 运行时健康检查 |
| `get_config(key)` | `→ Optional[Any]` | 读取配置 |
| `set_config(key, value)` | `→ bool` | 写入配置 |
| `execute_tool(name, params)` | `→ ToolResult` | 调用工具 |
| `get_memory(scope)` | `→ MemoryInterface` | 获取记忆子系统 |
| `get_channel(name)` | `→ ChannelInterface` | 获取消息通道 |
| `get_sandbox()` | `→ SandboxInterface` | 获取沙箱子系统 |
| `get_credentials()` | `→ CredentialInterface` | 获取凭据子系统 |
| `supports(capability)` | `→ bool` | 检查是否支持某项能力 |
| `list_capabilities()` | `→ List[str]` | 列出所有能力路径 |

### 3.2 MemoryInterface（记忆）

| 方法 | 签名 | 说明 |
|---|---|---|
| `search(query, limit)` | `→ List[MemoryItem]` | 语义搜索 |
| `get(key)` | `→ Optional[str]` | 按键读取 |
| `put(key, value)` | `→ bool` | 写入 |
| `delete(key)` | `→ bool` | 删除 |
| `list(prefix)` | `→ List[str]` | 前缀列举 |

### 3.3 ChannelInterface（通道）

| 方法 | 签名 | 说明 |
|---|---|---|
| `name` | `str` | 通道名称 |
| `send(target, message)` | `→ SendResult` | 发送消息 |
| `receive(timeout)` | `→ Optional[Message]` | 接收消息 |
| `list_conversations(limit)` | `→ List[Conversation]` | 会话列表 |

### 3.4 SandboxInterface（沙箱）

| 方法 | 签名 | 说明 |
|---|---|---|
| `exec(command, timeout)` | `→ ExecResult` | 执行命令 |
| `read_file(path)` | `→ Optional[str]` | 读取文件 |
| `write_file(path, content)` | `→ bool` | 写入文件 |
| `list_dir(path)` | `→ List[str]` | 列举目录 |

### 3.5 CredentialInterface（凭据）

| 方法 | 签名 | 说明 |
|---|---|---|
| `get(name)` | `→ Optional[str]` | 获取凭据值 |
| `list()` | `→ List[str]` | 列举凭据名称 |
| `has(name)` | `→ bool` | 检查是否存在 |

---

## 4. 数据模型

所有数据模型定义在 `adapters/base/models.py`，使用 Python dataclass。

### 4.1 返回值模型

| 模型 | 核心字段 | 用途 |
|---|---|---|
| `HealthStatus` | `status` / `message` / `details` | 健康检查结果 |
| `ToolResult` | `success` / `output` / `error` / `error_code` | 工具调用结果 |
| `ExecResult` | `success` / `exit_code` / `stdout` / `stderr` / `error_code` | 沙箱执行结果 |
| `SendResult` | `success` / `message_id` / `error` / `error_code` | 消息发送结果 |
| `MemoryItem` | `key` / `value` / `score` / `metadata` | 记忆条目 |
| `Message` | `id` / `channel` / `sender` / `content` / `timestamp` | 通道消息 |
| `Conversation` | `id` / `channel` / `title` / `participants` / `unread_count` | 会话摘要 |

### 4.2 统一错误码（ErrorCode）

枚举类，格式 `ERR_<类别>_<具体错误>`。所有适配器必须使用这些错误码。

| 类别 | 错误码示例 |
|---|---|
| 通用 | `OK` / `ERR_UNKNOWN` / `ERR_NOT_IMPLEMENTED` / `ERR_INVALID_PARAM` / `ERR_TIMEOUT` |
| 运行时 | `ERR_RUNTIME_UNAVAILABLE` / `ERR_RUNTIME_ERROR` |
| 工具 | `ERR_TOOL_NOT_FOUND` / `ERR_TOOL_EXECUTION_FAILED` |
| 记忆 | `ERR_MEMORY_KEY_NOT_FOUND` / `ERR_MEMORY_READ_FAILED` / `ERR_MEMORY_WRITE_FAILED` |
| 通道 | `ERR_CHANNEL_NOT_FOUND` / `ERR_CHANNEL_SEND_FAILED` / `ERR_CHANNEL_RECEIVE_FAILED` |
| 沙箱 | `ERR_SANDBOX_UNAVAILABLE` / `ERR_SANDBOX_EXEC_FAILED` / `ERR_SANDBOX_FILE_NOT_FOUND` |
| 凭据 | `ERR_CREDENTIAL_NOT_FOUND` / `ERR_CREDENTIAL_ACCESS_DENIED` |
| 配置 | `ERR_CONFIG_KEY_NOT_FOUND` / `ERR_CONFIG_SET_FAILED` / `ERR_CONFIG_VALIDATION_FAILED` |

---

## 5. 工厂注册机制

### 5.1 RuntimeRegistry

定义在 `adapters/registry.py`，提供以下能力：

| 功能 | 方法 | 说明 |
|---|---|---|
| 注册 | `register(name, adapter_class)` | 手动注册适配器类 |
| 注销 | `unregister(name)` | 移除注册 |
| 获取类 | `get_adapter_class(name)` | 获取类对象（支持懒加载） |
| 获取实例 | `get_adapter(name, **kwargs)` | 获取实例（默认单例） |
| 列表 | `list_adapters()` | 列出所有已注册 |
| 配置加载 | `load_from_config(config)` | 从配置字典批量注册 |

### 5.2 模块级便捷函数

```python
from L1_runtime.adapters import register_adapter, get_adapter, is_registered

# 注册
register_adapter("my-runtime", MyRuntimeAdapter)

# 获取
adapter = get_adapter("my-runtime")
```

### 5.3 配置驱动加载

支持通过配置文件声明适配器，运行时懒加载：

```yaml
adapters:
  openclaw:
    import_path: "adapters.openclaw.openclaw.OpenClawRuntimeAdapter"
    enabled: true
  claude-code:
    import_path: "adapters.claude_code.ClaudeCodeAdapter"
    enabled: false
```

---

## 6. OpenClaw 适配层

### 6.1 代码组织

```
adapters/openclaw/openclaw/
├── __init__.py            # 导出所有公共类
├── adapter.py             # 原有 OpenClawAdapter（向后兼容）
├── config.py              # 配置映射
├── health.py              # 健康检查
└── runtime_adapter.py     # RuntimeAdapter ABC 实现（推荐）
```

### 6.2 实现策略

使用**组合模式**而非继承：

- `OpenClawRuntimeAdapter` 内部持有 `OpenClawAdapter` 实例
- 将 ABC 方法翻译为 OpenClawAdapter 的对应方法
- 子系统接口（Memory/Channel/Sandbox/Credential）各用独立类实现
- 不支持的能力明确 `raise NotImplementedError`，同时在 `capabilities` 中声明为 `False`

### 6.3 能力矩阵

| 子系统 | 能力 | 支持状态 | 说明 |
|---|---|---|---|
| 工具 | execute | ✅ | 通过 call_tool |
| 记忆 | get | ✅ | 通过 memory_read |
| 记忆 | put | ✅ | 通过 memory_write |
| 记忆 | search | ✅ | 通过 memory_search |
| 记忆 | delete | ❌ | 运行时不支持 |
| 记忆 | list | ❌ | 运行时不支持 |
| 通道 | send | ✅ | 通过 send_message |
| 通道 | receive | ❌ | 推送模式，不支持主动拉取 |
| 通道 | list_conversations | ❌ | 暂不支持 |
| 沙箱 | exec | ✅ | 通过 sandbox_execute |
| 沙箱 | read_file | ✅ | 间接通过 exec |
| 沙箱 | write_file | ✅ | 间接通过 exec |
| 沙箱 | list_dir | ✅ | 间接通过 exec |
| 凭据 | get | ✅ | 通过 credential_get |
| 凭据 | has | ✅ | 基于 get 封装 |
| 凭据 | list | ❌ | 安全设计，不列举 |
| 配置 | get | ✅ | 通过 config_get |
| 配置 | set | ✅ | 通过 config_set（四步保护） |
| 配置 | validate | ✅ | 通过 config_validate |

---

## 7. 测试

测试位于 `L1-runtime/tests/`，共 52 个用例，覆盖：

| 测试文件 | 用例数 | 覆盖内容 |
|---|---|---|
| `test_abc_contract.py` | 22 | ABC 不可实例化、抽象方法清单、数据模型序列化 |
| `test_registry.py` | 12 | 注册/获取/注销/懒加载/配置加载/类型校验 |
| `test_openclaw_adapter.py` | 18 | 继承关系、子系统类型、能力声明、健康检查 |

运行测试：

```bash
cd openclaw-v5.0
python3 -m pytest L1-runtime/tests/ -v
```

---

## 8. 新增运行时适配开发指南

### 8.1 步骤

1. **在 `adapters/` 下创建目录**，如 `adapters/my-runtime/`

2. **创建适配器类**，继承 `RuntimeAdapter` ABC：

   ```python
   from adapters.base import RuntimeAdapter

   class MyRuntimeAdapter(RuntimeAdapter):
       name = "my-runtime"
       version = "1.0.0"
       capabilities = {...}

       def health_check(self):
           ...
       # 实现所有抽象方法
   ```

3. **实现子系统接口**（Memory / Channel / Sandbox / Credential）

4. **注册到全局注册表**（在包的 `__init__.py` 中）：

   ```python
   from adapters import register_adapter
   register_adapter("my-runtime", MyRuntimeAdapter)
   ```

5. **编写契约测试**，确保所有接口签名正确

6. **更新能力矩阵**，声明支持/不支持的子能力

### 8.2 注意事项

- ❌ 不要修改 ABC 基类来适配你的运行时 — ABC 是契约，不可轻易变更
- ✅ 不支持的能力用 `raise NotImplementedError` + `capabilities` 声明为 False
- ✅ 所有返回值使用 base/models.py 中定义的数据类
- ✅ 错误使用统一的 `ErrorCode` 枚举
- ✅ 不要在适配器中引入业务逻辑 — 只做 API 翻译

### 8.3 契约变更流程

如果确实需要修改 ABC（新增方法、修改签名）：

1. 提出 ADR，说明变更原因和影响范围
2. 评估所有已有适配器的改造成本
3. 更新 ABC + 所有适配层 + 测试
4. 更新架构文档和能力矩阵
5. 更新版本号

---

## 9. 目录结构

```
L1-runtime/
├── DESIGN.md                          # 本文档
├── adapters/
│   ├── __init__.py                    # 统一入口（注册 + 导出）
│   ├── registry.py                    # 工厂注册机制
│   ├── base/                          # 抽象基类（ABC）
│   │   ├── __init__.py
│   │   ├── models.py                  # 统一数据模型 + 错误码
│   │   ├── runtime.py                 # RuntimeAdapter（主适配器 ABC）
│   │   ├── memory.py                  # MemoryInterface（记忆 ABC）
│   │   ├── channel.py                 # ChannelInterface（通道 ABC）
│   │   ├── sandbox.py                 # SandboxInterface（沙箱 ABC）
│   │   └── credential.py              # CredentialInterface（凭据 ABC）
│   └── openclaw/                      # OpenClaw 适配层
│       ├── __init__.py
│       └── openclaw/
│           ├── __init__.py            # 导出所有公共类
│           ├── adapter.py             # 原有直接实现（向后兼容）
│           ├── runtime_adapter.py     # RuntimeAdapter ABC 实现
│           ├── config.py              # 配置映射
│           └── health.py              # 健康检查
└── tests/
    ├── __init__.py
    ├── conftest.py                    # 测试配置（path 注入）
    ├── test_abc_contract.py           # ABC 契约测试
    ├── test_registry.py               # 工厂注册测试
    └── test_openclaw_adapter.py       # OpenClaw 适配测试
```

---

## 10. 版本历史

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-09-10 | **2.0** | **ABC 架构重构**：新增 `adapters/base/` 定义 5 个核心抽象基类 + 统一数据模型 + 统一错误码；新增 `registry.py` 工厂注册机制；新增 `OpenClawRuntimeAdapter` 标准适配；新增 52 个契约测试；首版 DESIGN.md |
| 2026-08-24 | 1.0 | 初始版本：OpenClawAdapter 直接实现 L1 十项能力契约 |

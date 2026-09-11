# 内存嵌入计算组件设计

> L2 基础设施层 · 纯嵌入计算能力
>
> **2026-09-11 创建**：本地 embedding 模型管理 + 向量计算 + 知识库索引（向后兼容层）。

## 1. 定位

| 维度 | 值 |
|---|---|
| 层级 | L2 基础设施层 |
| 组件类 | 基础能力组件 |
| 状态 | ✅ 已建设 (2026-08) — 2026-09-10 职责精简 |
| ADR | ADR-009 (本地语义召回)、ADR-010 (知识库工具链) |
| 验证 | smoke test |

## 2. 设计约束

1. **纯嵌入计算**：本组件只负责文本→向量计算，不负责文档解析/分块/索引/检索（已迁移到 knowledge-base）。
2. **向后兼容**：`kb_index.py` 保留为 wrapper，转发到 knowledge-base 组件，避免破坏现有引用。
3. **本地优先**：使用本地 GGUF 嵌入模型，零 API 成本，数据不出机器。
4. **可降级**：模型不可用时自动降级为 MockEmbedder（基于文本哈希的伪向量）。
5. **模型路径不可重命名**：GGUF 模型路径与索引身份绑定，重命名会导致索引失效。

## 3. 架构

```
┌──────────────────────────────────────────────────────┐
│                  memory-embedding                     │
│              （纯嵌入计算 + 向后兼容层）                │
├──────────────────────────────────────────────────────┤
│                                                      │
│  ┌─────────────────┐    ┌──────────────────────────┐ │
│  │ 本地 GGUF 模型   │    │   llama-cpp-provider     │ │
│  │ embeddinggemma  │◄───│   (OpenClaw 内置)        │ │
│  │ 300m-qat-Q8_0   │    │                          │ │
│  └─────────────────┘    └──────────────────────────┘ │
│                                                      │
│  ┌─────────────────────────────────────────────────┐ │
│  │              kb_index.py (wrapper)               │ │
│  │  脚本调用 → subprocess 转发                      │ │
│  │  模块导入 → importlib 重导出                     │ │
│  │  实际实现 → knowledge-base/kb_index.py           │ │
│  └─────────────────────────────────────────────────┘ │
│                                                      │
└──────────────────────────────────────────────────────┘
```

### 3.1 模块职责

| 模块 | 文件 | 职责 |
|---|---|---|
| 向后兼容 wrapper | `kb_index.py` | 转发到 knowledge-base/kb_index.py，脚本调用与模块导入均兼容 |
| 文档 | `README.md` | 组件定位、职责范围、嵌入模型说明 |
| 故障排查 | `TROUBLESHOOTING.md` | 本地 embedding 常见问题与修复方法 |
| 测试 | `tests/test_smoke.py` | 组件目录结构和 Python 文件存在性验证 |

## 4. 嵌入模型

### 4.1 模型规格

| 属性 | 值 |
|---|---|
| 模型 | embeddinggemma-300m |
| 量化 | Q8_0 |
| 维度 | 768 |
| 格式 | GGUF |
| 路径 | `~/.node-llama-cpp/models/hf_ggml-org_embeddinggemma-300m-qat-Q8_0.gguf` |
| 供应方 | 本地 llama-cpp-provider（OpenClaw 内置） |
| 成本 | 零 API 成本 |
| 数据流向 | 不出机器 |

### 4.2 服务配置

```json
{
  "localService": {
    "command": "/path/to/llama-server",
    "healthUrl": "http://127.0.0.1:19433/health",
    "args": [
      "--host", "127.0.0.1",
      "--port", "19433",
      "--models-preset", "/Users/bangcle/.openclaw/tools/llama.cpp/models.ini",
      "--models-max", "2",
      "--metrics",
      "--no-ui"
    ]
  }
}
```

### 4.3 降级策略

```
模型可用 → LocalEmbedder（真实向量，768 维）
  └── 不可用 → MockEmbedder（基于文本哈希的伪向量）
                └── 系统仍可用，但检索质量下降
```

## 5. kb_index.py 向后兼容 Wrapper

### 5.1 脚本调用模式

```python
# 作为脚本运行时，转发所有参数
subprocess.call([sys.executable, str(_KB_INDEX)] + sys.argv[1:])
```

### 5.2 模块导入模式

```python
# 作为模块导入时，重导出所有公共符号
_spec = importlib.util.spec_from_file_location("kb_index_actual", _KB_INDEX)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
for _name in dir(_mod):
    if not _name.startswith("_"):
        globals()[_name] = getattr(_mod, _name)
```

### 5.3 迁移状态

| 原文件 | 当前位置 | 实际实现 |
|---|---|---|
| `memory-embedding/kb_index.py` | 保留为 wrapper | `knowledge-base/kb_index.py` |
| `knowledge-base/kb_index.py` | 新建 | 完整实现 |

**新代码请直接引用 `knowledge-base` 组件**，本 wrapper 将在未来版本中移除。

## 6. 故障排查

### 6.1 常见问题

| 问题 | 根因 | 修复 |
|---|---|---|
| `local service did not become ready` | `localService.args` 缺失 | 补齐标准参数（见 §4.2） |
| `Managed local embeddings unavailable` | 默认从 huggingface.co 下载超时 | 设置 `modelPath` 为本地绝对路径 |
| `openclaw configure` 不提示配置 | provider 已配置完成 | 检查 args/端口/模型路径 |
| 端口被占用 | 其他进程占用 llama-server 端口 | `lsof -i :19433` 排查 |
| 模型路径不存在 | models.ini 中路径错误 | 检查 `~/.openclaw/tools/llama.cpp/models.ini` |

### 6.2 关键路径备忘

- 插件安装路径：`~/.openclaw/tools/llama.cpp/`（由 `resolveStateDir()` 决定）
- 二进制路径：`~/.openclaw/llama-cpp/`（仅放二进制，不影响服务）
- `prepareManagedLlamaServer` 只在首次配置时生成 args，后续手动改配置需手动补全

## 7. 依赖

| 依赖 | 类型 | 说明 |
|---|---|---|
| python3 | 运行时 | kb_index.py 纯标准库（subprocess / importlib） |
| llama-cpp-provider | 运行时 | OpenClaw 内置本地 embedding 服务 |
| llama-server | 外部工具 | 提供 embedding HTTP 服务 |
| knowledge-base | 功能依赖 | kb_index.py 的实际实现 |

## 8. 上游调用方

| 调用方 | 使用方式 |
|---|---|
| `memory_search` | 主会话语义搜索工具，使用相同嵌入模型 |
| `knowledge-base` | 通用知识库组件，依赖本组件的嵌入计算能力 |
| `system_full_audit.py` | 通过 kb_index.py wrapper 调用 |

## 9. 演进方向

| 方向 | 优先级 | 触发条件 |
|---|---|---|
| wrapper 移除 | 中 | 所有调用方迁移到 knowledge-base 后 |
| 模型热切换 | 低 | 需要切换不同 embedding 模型时 |
| 批量嵌入优化 | 低 | 大量文本向量化性能瓶颈 |
| GPU 加速 | 低 | llama-server 支持 GPU 推理后 |

## 10. 变更记录

| 日期 | 变更 |
|---|---|
| 2026-08 | 本地 GGUF embedding 模型接入，768 维语义召回上线 |
| 2026-08 | kb_index.py 首版（知识库 frontmatter 索引工具） |
| 2026-09-10 | 知识库能力迁移到 knowledge-base 组件，本组件职责精简为纯嵌入计算 + wrapper |
| 2026-09-11 | 编写 DESIGN.md |

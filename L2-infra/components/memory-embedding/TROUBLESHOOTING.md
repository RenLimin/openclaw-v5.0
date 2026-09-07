# 本地 llama-cpp embedding 故障排查指南

## 常见问题

### 问题：`llama-cpp local service did not become ready at http://127.0.0.1:XXXX/health`

#### 可能原因

| 原因 | 现象 | 排查点 |
|---|---|---|
| `localService.args` 缺失 | 服务启动后立即退出，`llama-server` 日志为空，`ps` 看到进程短暂存在后消失 | 查看 `openclaw config get models.providers.llama-cpp.localService.args`，输出 `None` → 缺参数 |
| 端口被占用 | 启动失败，报错 "address already in use" | `lsof -i :XXXX` 看哪个进程占了端口 |
| 模型路径不存在 | `llama-server` 输出 "model not found" | 检查 `~/.openclaw/tools/llama.cpp/models.ini` 里 `model` 路径是否存在 |

#### 根因确认（本次修复场景）

当 `localService.args` 缺失时，主程序 `provider-local-service` 会以 **空参数列表** 启动 `llama-server`：
```
llama-server → 没有 --models-preset → 不会加载任何模型 → 立即退出
```

修复方式：在 `localService` 配置中补齐标准参数：

```json
"localService": {
  "command": "/path/to/llama-server",
  "healthUrl": "http://127.0.0.1:19433/health",
  "args": [
    "--host",
    "127.0.0.1",
    "--port",
    "19433",
    "--models-preset",
    "/Users/bangcle/.openclaw/tools/llama.cpp/models.ini",
    "--models-max",
    "2",
    "--metrics",
    "--no-ui"
  ]
}
```

### 问题：`Managed local embeddings are unavailable. ... connect ETIMEDOUT`

#### 可能原因

插件默认模型路径为 `hf:` 源，需要从 huggingface.co 下载，网络不通导致超时。

#### 修复方式

1. 提前下载好本地 `.gguf` 模型文件
2. 修改 `llama-cpp` 配置中 embedding 模型的 `modelPath` 为**本地绝对路径**
3. 将模型软链到 `~/.openclaw/llama-cpp/models/llama.cpp/`（满足聊天模型占位需求，避免插件报错）
4. 确认 `~/.openclaw/tools/llama.cpp/models.ini` 中 `model` 路径已写对本地文件

### 问题：`openclaw configure` 不提示配置 llama.cpp

#### 原因

因为插件检查到 `llama-cpp` provider 已经配置完成，会跳过配置引导——如果提示不出来，说明配置实际上已经存在，检查其他问题（如上述 args/端口/模型路径问题）。

## 验证方式

手动启动验证配置是否正确：
```bash
~/.openclaw/llama-cpp/b10534/darwin-arm64/llama-server \
  --port 19433 \
  --model /Users/bangcle/.openclaw/models/llama.cpp/hf_ggml-org_embeddinggemma-300m-qat-Q8_0.gguf \
  --metrics --no-ui
```
然后立即 `curl -I http://127.0.0.1:19433/health`，如果返回 `HTTP/1.1 200 OK` 证明配置没问题。

## 关键路径备忘

- 插件预设/安装路径：由 `resolveStateDir()` 决定，是 `~/.openclaw/tools/llama.cpp/`，不是早期的 `~/.openclaw/llama-cpp/`（后者仅放二进制，不影响）
- 插件 `prepareManagedLlamaServer` 返回的 args 只在插件首次配置时生成，**后续手动改配置后必须手动补全 args**
- 主程序 `provider-local-service` 总是使用配置中 `localService.args` 启动 llama-server，不自动生成参数

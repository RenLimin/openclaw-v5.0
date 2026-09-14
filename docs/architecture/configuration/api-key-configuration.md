# API Key 配置规范

> **安全等级**：敏感 · 本文件只说明配置方式与位置，**绝不存储任何密钥值**
> **最后更新**：2026-09-14

---

## 1. 存储机制

OpenClaw 采用 **双层密钥存储**：

| 层级 | 存储位置 | 用途 | 权限 |
|---|---|---|---|
| **Secret 文件** | `~/.openclaw/secrets/<name>` | 密钥原始值 | `600` (rw-------) |
| **配置引用** | `~/.openclaw/openclaw.json` | `secretRef` 指向 secret 文件名 | `600` |

**原则**：配置文件中只存引用，不存值。密钥值只存在 `secrets/` 目录下的独立文件中。

---

## 2. 配置方式

### 2.1 通过 `openclaw config` 命令（推荐）

```bash
# 交互式设置（会自动创建 secret 文件 + 配置引用）
openclaw config set models.providers.<provider>.apiKey
```

命令会提示输入密钥值，然后：
1. 创建 `~/.openclaw/secrets/<provider>.apiKey` 文件
2. 在 `openclaw.json` 中写入 `{"secretRef": "<provider>.apiKey"}`

### 2.2 手动配置

```bash
# 1. 创建 secret 文件
echo -n "your-api-key" > ~/.openclaw/secrets/myprovider.apiKey
chmod 600 ~/.openclaw/secrets/myprovider.apiKey

# 2. 在 openclaw.json 中添加引用
# "models": {
#   "providers": {
#     "myprovider": {
#       "apiKey": { "secretRef": "myprovider.apiKey" }
#     }
#   }
# }
```

---

## 3. 已配置 Provider 清单

| Provider | 配置路径 | Secret 文件 | 状态 | 备注 |
|---|---|---|---|---|
| **ark** | `models.providers.ark.apiKey` | `ark.apiKey` | ✅ 正常 | 火山引擎 ARK |
| **doubao** | `models.providers.doubao.apiKey` | `doubao.apiKey` | ✅ 正常 | 豆包（走 ARK 代理） |
| **longCat** | `models.providers.longCat.apiKey` | `longcat.apiKey` | ❌ 401 | key 在平台端失效，待更新 |
| **deepseek** | `models.providers.deepseek.apiKey` | `deepseek.apiKey` | ❌ 401 | key 无效，待更新 |

> **验证方法**：`curl -H "Authorization: Bearer $(cat ~/.openclaw/secrets/<file>)" <endpoint>/models`

---

## 4. 安全规则

- ❌ **绝不**将密钥值写入任何 Markdown 文件（包括本文件、记忆文件、工作日志）
- ❌ **绝不**在命令行参数中明文传递密钥（用环境变量或文件传递）
- ❌ **绝不**将 `secrets/` 目录纳入版本控制
- ✅ Secret 文件权限必须是 `600`
- ✅ 密钥轮换后，删除旧 secret 文件并更新引用
- ✅ 新增 provider 时，优先使用 `openclaw config set` 交互式配置

---

## 5. 故障排查

### 5.1 401 / "incorrect api key"

1. 确认 secret 文件存在且可读：`cat ~/.openclaw/secrets/<name>`
2. 确认文件末尾没有换行：`wc -c ~/.openclaw/secrets/<name>` 对比 key 长度
3. 直接 curl 验证：
   ```bash
   curl -s -H "Authorization: Bearer $(cat ~/.openclaw/secrets/longcat.apiKey)" \
     https://api.longcat.chat/openai/v1/models
   ```
4. 如仍 401，登录 provider 后台确认 key 状态（可能过期/被回收）

### 5.2 "request failed" / 网络超时

1. 检查 Gateway 是否有代理配置
2. 检查 provider endpoint 可达性
3. 查看 Gateway 日志：`tail -f /tmp/openclaw/openclaw-$(date +%Y-%m-%d).log`

### 5.3 配置未生效

1. 重启 Gateway：`openclaw gateway restart`
2. 检查配置：`openclaw config get models.providers.<name>`
3. 确认 secretRef 指向的文件名与 `secrets/` 目录下一致（大小写敏感）

---

## 6. 相关文档

- [系统资产清单](../01-asset-inventory.md) — L2 插件/Provider 总览
- [模型调度](../../components/model-scheduling/README.md) — 模型路由与健康探测

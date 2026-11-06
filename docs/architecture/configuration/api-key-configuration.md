# API Key 配置规范

> **安全等级**：敏感 · 本文件只说明配置方式与位置，**绝不存储任何密钥值**
> **最后更新**：2026-11-06

---

## 1. 存储机制：统一 SecretRef

OpenClaw 采用 **SecretRef 引用对象**，密钥值与配置分离。SecretRef 统一形态：

```json
{ "source": "env" | "file" | "exec" | "store", "provider": "<别名>", "id": "<标识>" }
```

- 引用写在消费侧（如 `models.providers.<provider>.apiKey`）；
- 当 `source: "file"` 时，`provider` 是**别名**，真实文件路径在定义层
  `secrets.providers.<别名>` 中声明（双层结构）；
- 密钥值只存在于 Secret provider 后端（文件 / 环境 / exec 解析器 / team store），
  **配置文件里永远只有引用，没有值**。

### 1.1 两种本地实际用法

**A. file —— 经定义层别名解析（双层）**

引用层（消费侧）：
```json
"models": {
  "providers": {
    "llama-cpp": {
      "apiKey": { "source": "file", "provider": "llamacpp", "id": "value" }
    }
  }
}
```

定义层（`secrets.providers.<别名>`）：
```json
"secrets": {
  "providers": {
    "llamacpp": {
      "source": "file",
      "path": "/Users/bangcle/.openclaw/secrets/llama.cpp.apiKey",
      "mode": "singleValue"
    }
  }
}
```

> `mode: "singleValue"` 时引用层 `id` 必须是 `"value"`；文件存单一密钥，权限 `600`。
> `mode: "json"` 时 `id` 为指向 JSON 文件的绝对 JSON pointer（如 `"/providers/openai/apiKey"`）。

**B. store / env —— provider 为 `default`**

```json
"apiKey": { "source": "store", "provider": "default", "id": "DEEPSEEK_API_KEY" }
"apiKey": { "source": "env",   "provider": "default", "id": "OPENAI_API_KEY" }
```

- `store`：从 Gateway-wide team scope 解析（id 须匹配 `^[A-Z][A-Z0-9_]{0,127}$`）；
- `env`：从进程环境变量解析（id 为变量名，同名大写规则）。

---

## 2. 配置方式

### 2.1 通过 `openclaw` CLI（推荐）

```bash
# 交互式设置（自动创建 secret 后端 + 写入 SecretRef，密钥不落 shell 历史）
openclaw config set models.providers.<provider>.apiKey
```

`secrets apply` 可直接针对 `openclaw.json` 支持的凭证路径写入（走 masked entry，不回显）。

### 2.2 手动配置 file（双层）

```bash
# 1) 创建 secret 文件（值只落在这里）
echo -n "your-api-key" > ~/.openclaw/secrets/myprovider.apiKey
chmod 600 ~/.openclaw/secrets/myprovider.apiKey

# 2) openclaw.json：引用层
#    "models": { "providers": { "myprovider": {
#        "apiKey": { "source": "file", "provider": "myprovider", "id": "value" }
#    } } }

# 3) openclaw.json：定义层
#    "secrets": { "providers": { "myprovider": {
#        "source": "file",
#        "path": "/Users/<you>/.openclaw/secrets/myprovider.apiKey",
#        "mode": "singleValue"
#    } } }
```

> ⚠️ file 引用层**不带 `path`**；路径只在 `secrets.providers.<别名>` 定义层声明。
> 早期误把引用层写成 `{"secretRef": "<file>"}` 单层形态，已不是运行时格式。

---

## 3. 已配置 Provider 清单（当前实际）

| Provider | 引用层（source/provider/id） | 后端 | 状态 |
|---|---|---|---|
| **llama-cpp** | `file` / `llamacpp` / `value` | 文件 `secrets/llama.cpp.apiKey` | ✅ 正常 |
| **deepseek** | `store` / `default` / `DEEPSEEK_API_KEY` | team store | 以实际连通为准 |
| **coding-plan** | `store` / `default` / `CODING_PLAN_API_KEY` | team store | 以实际连通为准 |
| **model-scheduling** | apiKey 未设置（路由引擎，自身不持凭证） | — | — |
| **longCat** | apiKey 未设置 | — | — |

定义层 `secrets.providers`：`llamacpp`（file/singleValue）、`gatewayauthtoken`、`memorysearchkey`。

> **验证方法**：`curl -H "Authorization: Bearer *** ~/.openclaw/secrets/<file>)" <endpoint>/models`

---

## 4. 校验规则（id 语法）

| source | provider 规则 | id 规则 |
|---|---|---|
| `env` | `^[a-z][a-z0-9_-]{0,63}$` | `^[A-Z][A-Z0-9_]{0,127}$` |
| `file` | 同上（别名） | singleValue 固定 `value`；json 为绝对 JSON pointer |
| `store` | 通常 `default` | `^[A-Z][A-Z0-9_]{0,127}$`（仅 team scope） |
| `exec` | 同上 | `^[A-Za-z0-9][A-Za-z0-9._:/#-]{0,255}$`（支持 `secret#json_key`） |

- SecretRef 在**激活期**解析为内存快照，请求路径只读快照；
- 已启用表面上解析不了的引用会导致启动/热加载失败（fail-closed），未启用表面带诊断跳过。

---

## 5. 安全规则

- ❌ **绝不**将密钥值写入任何 Markdown 文件（本文件、记忆、日志）
- ❌ **绝不**在命令行参数明文传递密钥（用 masked entry / 文件 / 环境变量）
- ❌ **绝不**将 `secrets/` 目录纳入版本控制
- ✅ secret 文件权限必须 `600`
- ✅ 轮换后更新后端值；文件/exec 路径须通过 ACL 校验（fail-closed，无绕过）
- ✅ 新增 provider 优先用 `openclaw config set` / `secrets apply`

---

## 6. 故障排查

### 6.1 401 / "incorrect api key"

1. 确认后端存在且可读：`cat ~/.openclaw/secrets/<name>`（file）
2. 确认文件末尾无多余换行：`wc -c ~/.openclaw/secrets/<name>` 对比长度
3. 直接 curl 验证（见 §3）
4. 仍 401 → 登录 provider 后台确认 key 状态（过期/回收）

### 6.2 引用解析失败 / 启动报 unresolved ref

1. 引用层 `provider` 别名是否在 `secrets.providers` 有定义层（file 双层）
2. 定义层 `path` 文件是否存在、权限是否 `600`
3. id 语法是否符合 §4（singleValue 必须 `value`）
4. store/env 的 id 是否在 team scope / 环境中真实存在

### 6.3 配置未生效

- SecretRef 在激活期解析；改后需重新激活（热加载）或重启。
- 重启走安全脚本：`L2-infra/components/gateway-safety/scripts/safe_restart.sh`
  （禁止裸调 `openclaw gateway restart`，compaction in-flight 硬阻断）。

---

## 7. 相关文档

- OpenClaw 官方：`docs/gateway/config-secrets-env.md`（SecretRef / secret providers）
- OpenClaw 官方：`reference/secretref-credential-surface.md`（凭证面矩阵）
- OpenClaw 官方：`gateway/secrets/secretref-contract.md`（契约与 id 文法）
- [系统资产清单](../../01-asset-inventory.md) — 组件/Provider 总览
- [模型调度](../../../L2-infra/components/model-scheduling/README.md) — 路由与健康探测

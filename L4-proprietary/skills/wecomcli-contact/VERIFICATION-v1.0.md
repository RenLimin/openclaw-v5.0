# VERIFICATION — 企业微信通讯录查询能力 v1.0

## 0. 结论

| 项 | 结果 |
|---|---|
| 能力可用（二进制/凭据/授权） | ✅ bin 定位成功、`auth show`=authorized |
| **通讯录接口权限** | ❌ `errcode 850002`（机器人未开通「通讯录」权限）→ **显式降级** |
| 降级行为 | ✅ 输出「权限未开通」+ 企微授权链接，**未编造任何部门** |
| 复用 | ✅ 复用 `bdms.core.wecom.wecom_cli_call`，未重写客户端 |

## 1. 验证证据（2026-11-20 实测）

### 1.1 `--check`（能力探测）

```json
{
  "bin": "/Users/bangcle/.openclaw/npm/projects/wecom-…/@wecom/cli-darwin-arm64/bin/wecom-cli",
  "credentials": true,
  "auth": "authorized",
  "contact": "no_permission",
  "status": "unavailable"
}
```

### 1.2 `--name 任立民`（真实查询）

返回 `errcode=850002`，脚本输出：

```
⚠️ 通讯录权限未开通（errcode 850002）
当前机器人未被授权「通讯录」使用权限…
→ 能力降级：需机器人在企微后台开通「通讯录」权限后重试；不编造部门。
```

### 1.3 降级红线遵守

- AGENTS.md「数据源不可用即缺陷」：本能力把 850002 视为**未开通**而非正常输出 ✅
- 未编造部门 ✅（无 `users` 数据时不产出任何部门字段）

## 2. 待开通后复验项

- `--names 徐亚东 潘天功 张燕兰` → 应返回 `departments`（主部门靠前）
- C5 分流（PM 部门 → 任立民/冯刚）接入后真实 E2E

## 3. 变更清单

| 文件 | 说明 |
|---|---|
| `SKILL.md` | 触发条件/前置门禁/用法/边界/调研来源 |
| `scripts/wecom_contact.py` | 查询 + `--check` 探测 + 850002 降级 |
| `registry.yaml` | 能力条目 `skill-wecomcli-contact` |

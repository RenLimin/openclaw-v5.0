---
name: wecomcli-contact
description: "企业微信通讯录查询：按姓名/关键词检索成员及其所属部门（QueryUserOpenUserInfo.departments），用于判定人员部门归属（如项目经理指派分流任立民/冯刚）。底层复用 wecom-cli contact users search（机器人需开通「通讯录」权限）。当需要查企微通讯录、人员部门归属、组织架构判定、按部门分流指派时使用。"
user-invocable: true
metadata:
  openclaw:
    emoji: "🏢"
    os: ["darwin", "linux"]
---
# 企业微信通讯录查询（wecomcli-contact）

## 触发条件
- 需要查企微通讯录成员 / 所属部门
- 需要按部门判定人员归属（如 PM 指派分流：任立民 vs 冯刚）
- 需要组织架构口径（部门序列）

## 前置条件（硬门禁）
| 项 | 要求 |
|---|---|
| 二进制 | `wecom-cli`（插件依赖内 `@wecom/cli-darwin-arm64/bin/wecom-cli`） |
| 授权 | `wecom-cli auth show` = authorized |
| **通讯录权限** | 机器人须开通「通讯录」使用权限；未开通返回 `850002`（**能力不可用，须显式留证，不伪造**） |

## 用法
```bash
python3 L4-proprietary/skills/wecomcli-contact/scripts/wecom_contact.py --name 任立民
python3 L4-proprietary/skills/wecomcli-contact/scripts/wecom_contact.py --names 徐亚东 潘天功 张燕兰
python3 L4-proprietary/skills/wecomcli-contact/scripts/wecom_contact.py --json   # 原始 JSON
python3 L4-proprietary/skills/wecomcli-contact/scripts/wecom_contact.py --check # 能力可用性探测
```

## 输出字段（权威 schema：`QueryUserOpenUserInfo`）
`name` / `userid` / `alias` / `position` / `departments`（数组，主部门靠前）

## 边界（Always / Never）
- Always `850002` → 输出 `权限未开通` 显式降级，附企微授权链接，**不编造部门**
- Always 复用 `bdms.core.wecom.wecom_cli_call`（既有能力，禁止重写客户端）
- Never 把机器人凭据写入任何文件 / markdown
- Never 用「部门名猜测」替代真实查询

## 调研来源与业界最佳实践
- 企微开放平台：通讯录接口须开通机器人「通讯录」权限（`qyapi.weixin.qq.com`）；错误码 `850002` = 未授权该接口
- 既有资产复用：`bdms/src/bdms/core/wecom.py`（wecom-cli 调用封装，含 auth init / 配置目录 / 二进制解析）
- 官方 CLI 文档：`wecom-cli contact users search --doc`（schema `QueryUserOpenReq`/`QueryUserOpenRsp`）

## 变更历史
- 2026-11-20: v1.0 创建（Rex 批准重建；PM 指派分流 C5 依赖）

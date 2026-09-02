# L2 MCP Server 模式 — 设计文档

> 版本：v1.0
> 创建日期：2026-09-02
> 状态：✅ 已上线
> 层级：L2 基础设施层

---

## 一、概述

### 1.1 定位

将 BDMS 能力（数据采集、报告生成、关联查询）通过 MCP 协议暴露给其他 AI Agent 使用，实现跨系统互操作。

### 1.2 核心目标

1. **能力暴露**：将 BDMS 数据采集和报告生成能力暴露为 MCP 工具
2. **跨 Agent 互操作**：支持其他 Agent（Claude Code、Cursor 等）调用 BDMS 能力
3. **标准化接口**：通过 MCP 协议提供统一的能力访问接口

---

## 二、架构设计

### 2.1 核心能力

| 能力 | MCP 工具名 | 说明 |
|---|---|---|
| OA 合同查询 | `oa_contract_query` | 按合同编号查询合同详情 |
| 确收凭证查询 | `revenue_voucher_query` | 按月份查询确收凭证 |
| 验收凭证查询 | `acceptance_voucher_query` | 按月份查询验收凭证 |
| 交付月报生成 | `delivery_report_generate` | 生成交付月报 Excel |
| 确收月报生成 | `revenue_report_generate` | 生成确收月报 Excel |
| 关联查询 | `join_query` | 跨系统关联查询 |

### 2.2 实现方式

利用 OpenClaw 官方内置的 `openclaw mcp serve` 能力：

```bash
# 启动 MCP Server（stdio 模式）
openclaw mcp serve --url ws://127.0.0.1:18789

# 其他 Agent 通过 MCP 协议连接
# 配置到 Claude Code / Cursor / Copilot 等工具中
```

### 2.3 配置示例

```json
{
  "mcp.servers": {
    "bdms": {
      "transport": "stdio",
      "command": "openclaw",
      "args": ["mcp", "serve", "--url", "ws://127.0.0.1:18789"]
    }
  }
}
```

---

## 三、实施状态

- [x] 架构设计文档
- [x] OpenClaw 官方 `mcp serve` 能力验证
- [ ] 实际配置和测试（需要时启用）
- [ ] 工具定义文件

---

## 四、变更历史

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-09-02 | v1.0 | 初始化：利用 OpenClaw 官方 MCP serve 能力 |

---
type: adr
id: ADR-202609-028
date: 2026-09-08
title: L0 系统安装层设计
status: proposed
deciders: [Rex, Jerry]
layers: [L0]
tags: [l0, installation, setup, architecture, environment]
supersedes: null
superseded_by: null
---

# [ADR-202609-028] L0 系统安装层设计

| 字段 | 值 |
|---|---|
| **状态** | proposed |
| **日期** | 2026-09-08 |
| **作者** | Jerry |
| **评审者** | Rex |
| **分类** | 架构 / L0 |

## 上下文/背景

综合开放平台需要从零到一的一键安装流程，需要：
1. 环境探测，提前发现依赖/权限/OS不兼容
2. 运行时选型隔离，新增运行时不影响上层
3. 安装完成后验证 L1 契约满足度，早失败早止损
4. 安装结果快照，可审计可回滚

## 决策

我们决定建设 **L0-install 系统安装层**，实现六步流水线：

1. **env_probe** → 环境探测（OS/依赖/网络/权限）
2. **select** → 运行时选型，确认注册表存在性
3. **install** → 按注册表执行安装
4. **init_adapter** → 初始化 L1 适配层
5. **verify** → 验证 L1 十项能力契约
6. **snapshot** → 保存安装结果快照到 manifest

### 架构设计要点：

1. **目录结构**：
   - `registry/`：每个运行时一个 yaml，包含名称/版本/要求/安装命令/契约检查
   - `installer/`：六步流水线每个步骤一个脚本
   - `contract/`：L1 契约验证，每个能力一个测试脚本
   - `manifest/`：每个运行时一个安装结果清单，可回滚

2. **注册表格式**：yaml，包含：
   - name: 运行时名称
   - description: 描述
   - version: 支持最低版本
   - requirements: 依赖列表（node/python/os）
   - install_command: 安装命令 shell
   - contract_checks: 标记需要检查哪些 L1 能力

3. **验证方式**：每个能力单独测试脚本，主验证脚本统一收集结果，输出完整报告

## 替代方案

### 替代方案 1：不单独做 L0 安装层，把安装逻辑放到 setup.sh 主脚本

**拒绝理由**：
- 需求演进后会越来越臃肿，不清晰
- 不满足运行时选型隔离设计，后续不好扩展

### 替代方案 2：把注册表放到 L1 适配层里

**拒绝理由**：
- 注册表是安装选型时需要的，安装完成才会生成适配层，所以必须前置放 L0
- 注册表和适配层分离，更容易维护

## 后果

### 正面：
- 从零到一安装流程清晰，自动化程度高
- 运行时选型隔离，新增运行时只需添加 yaml，不影响核心代码
- 环境/契约提前验证，减少中途失败概率
- 可审计可回滚，安全

### 负面：
- 需要维护多脚本，增加了一点代码量
- 新增运行时需要新增 yaml，不能省略

## 验收标准

- [x] DESIGN.md 完成 ✅
- [ ] 注册表默认条目（OpenClaw）完成
- [ ] 六步流水线脚本全部完成
- [ ] OpenClaw 全流程 dry-run 通过
- [ ] 契约测试 10/10 pass
- [ ] ADR accepted

## 相关链接

- [系统架构](../../../architecture/00-system-architecture.md) §3.1
- [L0 DESIGN.md](../../../architecture/components/l0-install/DESIGN.md)
- [开发规范](../../../../docs/conventions/dev-standards.md)

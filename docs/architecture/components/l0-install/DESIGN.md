# L0 系统安装层 (L0-install)

> 六步流水线一键部署 + 运行时注册表 + 契约验证
> 版本: v1.0 · 日期: 2026-09-08 · 作者: Jerry

## 目的

解决什么问题：
- **零到一初始化**：从零开始将综合开放平台部署到目标机器，完成环境探测、运行时选择、安装、适配、验证全流程，一步到位。
- **运行时选型隔离**：将运行时选择和后续上层代码完全分离，新增运行时只需添加注册表条目和适配层，不影响上层。
- **环境验证**：部署前探测依赖/网络/权限/OS，提前发现不兼容，避免部署一半失败。
- **一致性验证**：部署后验证 L1 契约满足度，确保运行时可用，早失败早止损。

不解决什么问题：
- 不修改操作系统配置（如 sudo 权限、环境变量），只探测，由用户自行处理不兼容问题。
- 不解决运行时安装过程中的非预期错误，只探测并报告。

## 分层定位

- **所属层级**: L0-install (系统安装层)
- **依据**: 符合架构文档 §2.1/§3.1，是从零到一的系统安装，运行时选型和初始化，属于最底层。上层只依赖环境信息，不反向依赖。

## 职责边界

| 角色 | 管什么 | 不管什么 |
|---|---|---|
| **L0-install** | 环境探测 → 运行时选择 → 运行时安装 → 适配层初始化 → 系统验证 → 快照入库 | 上层代码开发、后续运行时维护、业务功能 |
| **L1 运行时抽象** | L1 最小契约定义、运行时适配层 | L0 安装流程、注册表管理 |
| **上层(L2-L4)** | 只依赖 L1 抽象契约，不涉及安装选型 | 安装流程选型逻辑 |

## 三查记录

| 查 | 结果 | 结论 |
|---|---|---|
| 运行时原生能力 | OpenClaw 没有提供开箱即用的全流程一键安装，只有单独命令 | 需要自建 |
| 现有 L2 资产 | 无，L0 是独立底层，无现有资产 | 新建 |
| 现有 L3/L4 资产 | 不适用 | 不适用 |

## 六问自答

1. **分层位置**: L0-install，符合架构设计，最底层安装层，没有越级。
2. **职责边界**: 只负责零到一安装流程、运行时注册表、契约验证，职责清晰，不越界。
3. **原生优先**: OpenClaw 没有全流程一键安装能力，所以自建。
4. **可移植性**: 核心逻辑不绑定具体运行时，每个运行一个注册表 yaml，适配层放 L1，不绑定。
5. **可继承性**: L0 不被上层继承，只给上层提供基础环境，不涉及业务复用。
6. **冲突规避**: 只在零到一阶段运行，后续不干预运行时，不会冲突。

## 架构设计

### 目录结构

```
L0-install/
├── install.sh                  # 主入口脚本
├── registry/                   # 运行时注册表
│   └── <runtime>.yaml          # 每个运行时一个 yaml（name/version/requirements/install-command/contract-check)
├── installer/                  # 安装流水线模块
│   ├── env_probe.sh            # 环境探测（OS/deps/network/perm)
│   ├── select.sh              # 运行时选择、验证注册表条目
│   ├── install.sh             # 运行时安装执行
│   ├── init_adapter.sh        # 适配层初始化
│   ├── verify.sh             # 契约验证（调用 L0-install/contract/verify.sh）
│   └── snapshot.sh            # 安装结果快照入库
├── contract/                  # L1 契约验证
│   ├── verify.sh             # 主验证脚本，调用每个能力的 test
│   └── test_<cap>.py/sh       # 每个能力单独测试脚本
└── manifest/                  # 部署清单（系统资产 + 运行时部署映射）
    └── <runtime>.txt          # 每个运行时一个清单
```

### 安装流水线六步

| 步骤 | 脚本 | 产出 |
|---|---|---|
| 1 | env_probe | 环境报告（OS/依赖版本/网络连通/权限），不满足提示用户处理。 |
| 2 | select | 选择运行时（默认 openclaw），检查注册表存在性，提示确认。 |
| 3 | install | 按注册表中 install-command 执行安装，检查安装成功。 |
| 4 | init_adapter | 初始化适配层，写入配置。 |
| 5 | verify | 验证 L1 十项能力契约，输出报告，不满足提示缺失能力。 |
| 6 | snapshot | 保存安装配置快照到 manifest，可回滚、可审计。 |

### 注册表格式

每个运行时一个 yaml：

```yaml
name: openclaw
description: OpenClaw 全功能 Agent 平台
version: 2026.9.1
requirements:
  - node: ^26.0.0
  - python: ^3.10.0
  - os: [macOS, Linux]
install_command: |
  # 安装命令，shell 脚本
  curl -fsSL https://raw.githubusercontent.com/openclaw-ai/openclaw/main/install.sh | bash
contract_checks:
  - agent_loop: yes
  - tool_execution: yes
  - memory: yes
  - scheduling: yes
  - channels: yes
  - config: yes
  - credentials: yes
  - sandbox: yes
  - context: yes
  - health: yes
```

## 依赖声明

| 依赖 | 最低版本 | 校验点 |
|---|---|---|
| bash | 3.2 | 脚本执行 |
| python3 | 3.10 | 契约测试 |
| curl | 7.0 | 下载安装脚本 |
| git | 2.0 | 代码操作 |

## 可移植性

- 核心脚本用 bash/python，兼容 macOS/Linux。
- 新增运行时只需新增 yaml 到 registry，无需修改核心代码。
- 适配层在 L1，L0 不绑定具体运行时实现。

## 测试策略

- 每个能力测试单独写测试脚本，主脚本统一调用。
- 全流程 dry-run 模式，只探测不修改，方便预检查。
- OpenClaw 默认运行时全流程必须 10/10 测试通过。
- 契约测试每个能力必须有明确的 pass/fail 结果。

## 验收标准

- [ ] 编写完成所有脚本，OpenClaw 全流程 dry-run 通过
- [ ] 编写完成所有脚本，OpenClaw 全流程 install 通过
- [ ] 契约测试 10/10 pass（OpenClaw 默认）
- [ ] ADR 文档完成，accepted
- [ ] DESIGN.md 完整，符合规范

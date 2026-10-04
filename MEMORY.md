# MEMORY.md - 系统级长期记忆

> 主会话专用。不加载到共享场景（群聊/其他会话）。

## 元数据

- 系统：综合开放平台 · 4 层（L1~L4） · 基座 OpenClaw
- AI：Jerry 🦞 · 详见 `IDENTITY.md`/`SOUL.md`
- 知识库：Markdown+元数据（自建系统为目标，0/7 触发暂缓）
- 用户：Rex · 中英混合 · 全栈+管理 · 拍板点：仅不可逆操作

## 关键决策

| 日期 | 决策 | 文档 |
|---|---|---|
| 08-21 | 4 层架构(ADR-001) · 三维知识库(ADR-002) · 双轨沉淀 · 知识库演进3阶段(ADR-003) | `docs/architecture/00-system-architecture.md` |
| 08-21 | 凭据管理通用化(ADR-005) · 持久化 SQLite+Repository(ADR-006) | |
| 08-22 | 配置管理(ADR-007) · 工具策略三态(ADR-008) · 记忆嵌入本地 GGUF(ADR-009) | |
| 08-23 | 知识库工具链(ADR-010) · 全盘 review 13 项偏差 · 选择性引用教训 | |
| 08-24 | 上下文管理(压缩同 provider + sticky 隔离 + 供应链加固) | |
| 09-02 | 运行时抽象(ADR-012) · 会话生命周期(ADR-013) · 错误自动处理(ADR-014) | |
| 09-15 | BDMS 全量交付 · 对比 18/18 零误差 · 验收 7 步法制度化 | |

## 活跃项目

- **综合开放平台**：L2 19 组件齐备 · L3 7 组件 · L4 7 组件 · 66 份文档已补齐
- 已完成：BDMS · Bangcle PPT · 合同审批 SCA-001 · FIN-L4 M1-M4 · DMS · OCR · Office 生成 · 模型调度
- 阻塞：WeCom 每日观测摘要（缺 Agent mode 凭据）

## 核心经验

| 类别 | 教训 |
|---|---|
| 运维 | 僵尸 subagent 须停 Gateway 删 DB · cron 必须 isolated · subagent_runs 有内存缓存 |
| 数据 | 凭据存 SQLite 需独立备份 · DB 重制全丢 |
| 引用 | 读完章节全文再引 · 交叉 concepts/+reference/ |
| 证据 | 不用启发式代替证据 · 不把讨论当执行 · 不把目录当权限 |
| 建设 | 迭代>平行 · 同一功能单路径 · 参数收了必须用 |

## 变更历史

- 2026-10-04：全量资产文档补齐(66份) · AGENTS.md 瘦身 24k→11k · USER.md 瘦身 8k→2.6k · 系统升级 2026.9.1→2026.9.8
- 2026-09-16：model-scheduling 注册为 OpenClaw provider
- 2026-09-15：BDMS v2.1 全量交付 · 验收 7 步法
- 2026-08-23：全盘 review + 14 项修复 · 二轮 review + 9 项修复
- 2026-08-24：压缩失效根因 · sticky 隔离 · 火山 embedding 结案

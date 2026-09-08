# 多会话并行建设规范

> 版本：v1.1 · 2026-09-07
> 归属层级：L1 操作规范（约定层）— 与 `commit-and-config.md` 同级
> 依据：ADR-202609-024（会话隔离与共享）· 00-system-architecture.md
> 适用场景：Rex 发起多个子会话/进程并行推进多个功能建设

## 目的

在多个子会话并行建设时，保证：
1. **架构一致** — 每个会话严格遵循 `00-system-architecture.md` 的分层契约
2. **资产共享** — 已建成的组件、设计、决策、技能跨会话可见可复用
3. **互不冲突** — 同组件并发时通过任务卡分工，避免覆盖

## 核心原则

| 原则 | 说明 |
|---|---|
| **自主建设** | 子会话按建议自行建设，主会话不逐步骤干预，只做监控/仲裁/验收 |
| **架构先行** | 每个子会话开工前必须先读架构文档，遵守分层契约 |
| **官方合规** | 遵循 OpenClaw 官方文档，明确依赖关系，供后续 AI Agent 升级前校验/升级后更新 |
| **业界最佳实践** | 建设时参考业界最佳实践，优化并预留扩展空间 |
| **资产入库** | 建设成果（DESIGN/ADR/代码/技能）必须写入共享位置 |
| **任务卡驱动** | 每个任务先建 TASK.yml，状态可跨会话追踪 |
| **验收合入** | 测试通过 + 架构对齐才提交合入 |

## 一、任务卡协议（强制）

每个子会话开工前，**必须**创建任务卡：

```bash
# 方式 A：使用 CLI（推荐）
python3 L2-infra/components/session-isolation/scripts/task_init.py \
  --task-id task-YYYYMMDD-NNN \
  --name "<任务名称>" \
  --owner "subagent-xxx" \
  --scope-project "<项目名>" \
  --scope-component "<组件名>" \
  --scope-version "v1"

# 方式 B：手动复制模板
cp tasks/_templates/TASK.yml tasks/in-progress/task-YYYYMMDD-NNN/TASK.yml
```

任务卡字段规范（详见 `tasks/_templates/TASK.yml`）：

| 字段 | 必填 | 说明 |
|---|---|---|
| `id` | ✅ | `task-YYYYMMDD-NNN` |
| `name` | ✅ | 任务名称 |
| `status` | ✅ | pending / in-progress / blocked / done / cancelled |
| `owner` | ✅ | main-agent / subagent-xxx / rex |
| `scope` | ✅ | project / component / version 三级定位 |
| `goals` | ✅ | 结构化目标（每个 g1/g2 带 status） |
| `blockers` | ✅ | 当前阻塞点，空数组=无阻塞 |
| `context` | ✅ | AI 启动时应读取的上下文文件（相对 workspace 根） |
| `artifacts` | ✅ | 产出物清单（name/path/status） |

**状态流转**：`pending → in-progress → done`（或 `blocked`）。任务结束时更新为 `done` 并填实 `artifacts`。

## 二、会话启动清单（每个子会话必做）

子会话收到任务后，按顺序执行：

0. **读全局开发规范**：`docs/conventions/dev-standards.md`（三查 + 六问，所有开发设计强制）
1. **读架构**：`docs/architecture/00-system-architecture.md`
   - 确认任务所属层级（L2/L3/L4）和分层依赖方向
   - 确认任务对应组件是否有 DESIGN.md / ADR，有则先读
2. **读任务卡**：`tasks/in-progress/<task_id>/TASK.yml`
   - 明确 goals、scope、blockers、context
3. **建/更新任务卡**：将 `status` 置为 `in-progress`
4. **查重资产**：`docs/architecture/components/` 找现有 DESIGN，避免重复建设
5. **开始建设**：遵循架构约束（见下）

## 三、架构约束（分层契约）

来自 `00-system-architecture.md`，所有子会话必须遵守：

| 约束 | 内容 |
|---|---|
| **依赖方向** | L4 → L3 → L2 → L1 → L0（允许）；L4 → L2/L1/L0（禁止）；L3 → L4（禁止） |
| **抽象契约** | L2-L4 只能通过 L1 抽象接口调用，不直接引用具体运行时 API |
| **组件文档** | 新组件必须有 `docs/architecture/components/<name>/DESIGN.md` |
| **决策记录** | 重大决策必须有 ADR（`docs/architecture/ADR-*.md`） |
| **技能共享** | 可复用流程沉淀为技能，放入对应层级 `skills/` |
| **测试先行** | 新代码必须带测试，通过后才提交 |
| **官方合规** | 调用 OpenClaw/L1 能力时查官方文档（docs 目录或 docs.openclaw.ai），不臆造 API |
| **依赖声明** | 组件必须声明依赖关系（`DESIGN.md` 中 dependencies 字段），明确升级前校验点/升级后更新点 |
| **业界实践** | 建设前先调研业界最佳实践（参考已存在的 REPLACE-REPORT/调研文档），优化并预留扩展接口 |
| **可升级性** | 不硬编码 L1 版本特性；升级兼容点写入 ADR，标注「升级前校验/升级后更新」

## 四、资产共享机制

建设成果必须写入共享位置，所有会话可见：

| 资产类型 | 位置 | 共享方式 |
|---|---|---|
| 组件设计 | `docs/architecture/components/<name>/DESIGN.md` | 写文件，全会话可读 |
| 决策记录 | `docs/architecture/ADR-*.md` | 新建 ADR，全局引用 |
| 任务状态 | `tasks/<task_id>/TASK.yml` | 子会话更新，主会话监控 |
| 共享数据 | `state/project/<project>/` | 子会话读写 |
| 事件日志 | `tasks/<task_id>/events.jsonl` | 审计追踪 |
| 技能 | `<层级>/skills/<name>/SKILL.md` | 新增即共享 |

## 五、主会话职责（Jerry）

| 职责 | 动作 |
|---|---|
| **分发任务** | 每个子会话明确任务卡 + 架构约束 + 成果验收标准 |
| **监控进度** | 通过 `tasks/` + `state/` 看全局，不轮询子会话 |
| **冲突仲裁** | 同组件并发时按任务卡分工，避免文件覆盖 |
| **成果验收** | 测试通过 + 架构对齐才允许合入 |
| **合入汇总** | 各子会话完成 → 汇总合并 → commit + push |

## 六、多会话并行防冲突规则

| 规则 | 说明 |
|---|---|
| **文件所有权** | 每个子会话只写自己任务卡的 `artifacts` 列出的文件 |
| **共享文件只读** | 架构文档、ADR 对所有会话只读，改动走主会话 |
| **先读后写** | 写共享位置前先确认当前内容，避免覆盖他人成果 |
| **冲突上报** | 发现覆盖风险 → 立即上报主会话，不擅自处理 |
| **命名空间隔离** | `state/` 按 scope 隔离：session/task/project/user/global |
| **禁止嵌套子会话** | 所有开发任务基于一级子会话进行，不再从子会话发起二级/孙会话；主会话拆分所有一级子任务，一级子会话直接干活，不拆分二级任务（避免 provider tool schema 不兼容导致失败） |

## 七、验收标准（子会话完成条件）

子会话报告完成时，必须满足：

- [ ] 所有 `goals` 状态为 `done`
- [ ] 所有 `artifacts` 已产出且路径存在
- [ ] 测试通过（`pytest` 全绿）
- [ ] 符合架构约束（依赖方向 / 组件文档 / ADR）
- [ ] 任务卡 `status` 更新为 `done`
- [ ] 无未解决的 `blockers`

## 相关文档

- 系统架构：`docs/architecture/00-system-architecture.md`
- 全局开发规范：`docs/conventions/dev-standards.md`（三查 + 六问，所有开发强制）
- 会话隔离组件：`L2-infra/components/session-isolation/DESIGN.md`（含 ADR-202609-024）
- 任务模板：`tasks/_templates/TASK.yml`
- 提交流程：`docs/conventions/commit-and-config.md`

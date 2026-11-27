# DESIGN-OUTLINE — 能力路由与编排层（Capability Routing & Orchestration Layer）v1.0

| 项 | 值 |
|---|---|
| 对象 | 能力路由 + 编排层（`capability-router` 组件 + `dag-orchestrator` 上游接线） |
| 版本 | v1.0（设计大纲，不含实现细节） |
| 日期 | 2026-11-27 |
| 作者 | Lane D |
| 状态 | **待 Rex 评审**（同批 PRD / ADR 一并评审） |
| 前置 | `PRD-capability-routing-orchestration-layer-v1.0.md`、`00-system-architecture.md` §1/§3.2/§3.3/§4 |
| 关联 | `ADR-202611-0NN-capability-routing-orchestration-layer.md` |

> 命名遵循 `00-system-architecture.md` §7.4 统一命名规则；文档形态对齐既有 `DESIGN-OUTLINE-*` 系列（outline 级，不含类级实现）。

---

## 1. 层归属建议：并入 L2 vs 独立横切层

### 1.1 判定依据（来自架构文档的硬约束）

| 依据 | 内容 | 出处 |
|---|---|---|
| J-1 | L2 定义 = 基础设施层，提供「跨 L3/L4 可复用的通用能力」，且**允许依赖 L1 + 其他 L2** | `00-system-architecture.md` §3.3 |
| J-2 | L2 只做**原生之上的编排逻辑**（任务依赖排序/错峰发起/状态跟踪），不做底层并发控制 | `00-system-architecture.md` §1 原生优先原则 |
| J-3 | 「治理横切」是横切关注点，贯穿所有层，**不是独立层** | `00-system-architecture.md` §1 设计原则 / §4 |
| J-4 | `dag-orchestrator` 已登记为 **L2 基础设施层** skill（SKILL.md 头部明写「层级：L2 基础设施层」）；`customer-delivery-intelligence` PRD 亦按 L2 引用 | `L2-infra/skills/dag-orchestrator/SKILL.md` |
| J-5 | L1 自建组件「仅依赖 L1 抽象契约」，而本层必须消费 L1 能力并驱动 L2 执行器——**职责跨 L1-L2，但不构成新层** | `00-system-architecture.md` §3.2.5 |

### 1.2 方案对比

| 维度 | A：并入 L2（推荐） | B：独立横切层（L2.5） | C：下沉 L1 组件 |
|---|---|---|---|
| 分层一致性（J-1/J-3） | ✅ 符合四层结构 | ❌ 制造第五层，破坏 §2 全景图 | ⚠️ 勉强可行但失真 |
| 与 dag-orchestrator 关系（J-4） | ✅ 同层，调用即复用 | ⚠️ 跨层，需新增契约 | ❌ 反向依赖 L2，违反 J-1 |
| 复用范围（面向 L3/L4） | ✅ L3/L4 经契约调用 | ✅ 同左 | ❌ L3/L4 不宜直连 L1 组件 |
| 门禁/测试/文档负担 | ✅ 沿用 L2 既有 | ❌ 新建一套 | ⚠️ 改 L1 规范 |
| 运行时无关性（G-5） | ✅ 由 L1 契约保证 | ✅ 同左 | ✅ 同左 |
| 变更可逆性 | ✅ 只增不改 | ❌ 结构性改动，回滚贵 | ❌ 动 L1 影响面最大 |

### 1.3 结论

> **采纳 A：作为 L2 基础设施组件 `L2-infra/components/capability-router/`**，与 `dag-orchestrator`（L2 skill）同为 L2；对 L3/L4 暴露**契约**（而不是直接调 L1）。

**理由（三条，均可证伪）**：

1. **同层复用零成本**：被编排对象 `dag-orchestrator` 已在 L2（J-4）。若路由层放 L1 或独立层，都要么反向依赖要么新增跨层契约，纯属增加摩擦。
2. **横切不等于新层**：架构文档明确「治理横切」贯穿各层而非独立成层（J-3）。路由/编排是**编排型横切**，属 L2「原生之上的编排逻辑」（J-2）。
3. **最小变更**：不修改既有分层（演进可逆原则，§1「演进可逆」），只在 L2 内新增一个组件目录 + 在 §3.3 组件表补一行。

**明确否掉的边界**：不建「L2.5」这类中间层；不在 L1 内塞编排决策（L1 只做能力抽象与注册发现，不做「选哪个」的判断）。

---

## 2. 模块划分

```
L2-infra/components/capability-router/
├── README.md                      ← 组件说明 + 操作入口
├── DESIGN-v1.0.md                 ← 详细设计（本期后续，非本 outline）
├── scripts/
│   ├── index_builder.py           ← F-1 能力索引构建器
│   ├── intent.py                  ← F-2 意图解析器
│   ├── retriever.py               ← F-3 top-k 检索器（召回 + 精排）
│   ├── injector.py                ← F-4 上下文增量注入器
│   ├── planner.py                 ← F-5 编排决策器（直连 / DAG 判定）
│   ├── dag_bridge.py              ← F-6 DAG 适配桥（调 runner.py）
│   └── registry_client.py         ← F-7 agent-registry 契约客户端
├── tests/
│   ├── fixtures/intent-benchmark-20.yaml   ← D-4 验收基准集（前置）
│   ├── test_index_builder.py      ← 索引无漂移断言（对 registry.yaml）
│   ├── test_retriever.py          ← M-1/M-2 命中率
│   ├── test_injector.py           ← M-3 token 降幅
│   ├── test_planner.py            ← F-5 判定准确率
│   ├── test_dag_bridge.py         ← M-4 端到端（真实跑 runner.py）
│   ├── test_registry_client.py    ← M-7 契约接线
│   └── test_runtime_isolation.py   ← M-8 禁 import openclaw 门禁
└── config/router-policy.yaml      ← k 值 / 降级开关 / 每会话上限(64)参数
```

| 模块 | 职责 | 契约边界 | 明确不做 |
|---|---|---|---|
| `index_builder` | 扫描 28 自建 skill（读 SKILL.md front-matter）+ registry.yaml → 归一化索引 | **只读** registry.yaml；不写 | 不改 registry.yaml（Lane A/B） |
| `intent` | 自然语言 → 能力需求列表 + 槽位；规则优先，词法打分 | 输出纯数据结构，不触运行时 | 不做语义向量（S-1，v1.1） |
| `retriever` | 召回（结构+词法）→ 精排（能力标签匹配度 + 触发条件命中）→ top-k | 不触模型 | 不生成 prompt 文本 |
| `injector` | 把 top-k 增量（描述/触发条件/入口）渲染进上下文 | 只产出字符串，不持久化 | **不做 truncate**；压缩归运行时（B-5） |
| `planner` | 判定 mode ∈ {skill, agent, dag}；选图；绑定 inputs | 只输出 plan 结构 | 不执行 |
| `dag_bridge` | plan → YAML + inputs → 调 `dag-orchestrator/scripts/runner.py` | 经 L1 RuntimeAdapter 派发（不裸 subprocess `openclaw`） | 不自建执行引擎（W-1/W-3） |
| `registry_client` | 读写 `agent-registry.AgentSpec`，调 `find_by_capability()`/`instantiate()` | 依赖 L1 契约接口，不依赖实现类 | 不改 registry 数据模型 |

**设计原则落点**：每个模块单一职责 + 可单测；任何模块失败都可被上层降级吞掉（F-8）。

---

## 3. 边界契约

### 3.1 与 `agent-registry`（L1 组件）

| 方向 | 契约 | 形式 |
|---|---|---|
| router → registry | **消费**：以 `capability` / `tag` 查询，取 `AgentSpec`（含 `entrypoint` / `input_schema`）；实例化走 `instantiate()` | 依赖 L1 ABC（`AgentRegistry`），不依赖 `InMemoryAgentRegistry` 具体类 |
| registry → router | **供给**：router 首次启动时把自建 skill/agent 声明式注册进 registry（只注册一次，幂等） | 新增注册清单文件（`config/agent-specs.yaml`），不手写代码 |
| 禁止 | router **不得**修改 `AgentSpec` 字段定义或 registry 内部存储 | 由 M-8 门禁覆盖 |

> **价值**：把 P-7「registry 无消费者」转为 M-7 有生产调用点。

### 3.2 与 `dag-orchestrator`（L2 skill）

| 方向 | 契约 | 形式 |
|---|---|---|
| router → dag | **调用**：`python dag-orchestrator/scripts/runner.py <workflow.yaml> --max-workers N`（现有 CLI，不改） | 子进程契约：stdin/stdout JSON + exit code |
| dag → router | **被调**：不提供反向 API | — |
| 禁止 | router **不得**重写 DAG 执行逻辑；**不得**修改 `dispatch.py` 默认后端 | W-1/W-3 |

> **缺口修复**：P-5「dag-orchestrator 无生产调用方」→ F-6 给出唯一且明确的上游。

### 3.3 与横切关注点（`00-system-architecture.md` §4）

| 横切项 | 本层如何接入 | 出处 |
|---|---|---|
| 安全 / 凭据 | 索引构建读文件用只读权限；不引入新的凭据读取 | §4 |
| 可观测 | 路由耗时/命中率/降级次数打点，交给 L1 `telemetry`（✅ 已实现） | §4 |
| 成本 | top-k 本身就是成本控制手段；记录 token 前后差值上报 | §4 |
| 工具策略治理 | 遵守 §5.4：路由结果仍受运行时 ToolPolicy 约束，不绕过 | §5.4 |
| 统一错误契约 | 路由失败一律走 §5.5 错误契约 + F-8 降级 | §5.5 |

### 3.4 与 `L0-gateway`（详见 §4）

**结论先行**：本层与 L0-gateway **无运行期调用关系**。

- 路由发生在 **agent 会话内部**（prompt 组装阶段），不在入站管道。
- L0-gateway 若落地，属「入站认证/限流/路由」域（`auth-gateway` / `channel-router` / `session-manager`），与本层「出站能力选择」域正交。
- 二者唯一可能的交集是 **session-manager 持有会话上下文**，本层读会话元数据决定 k / 注入量——这属于 v1.1 自适应（Q-3），**本期不做**，因此 v1.0 明确零耦合。

---

## 4. L0-gateway 处置建议

> 完整决策论证见同批 ADR 专节，此处只给设计侧结论与依赖关系。

| 选项 | 内容 | 设计侧评估 |
|---|---|---|
| **取 A（建议）** | **正式移交运行时原生通道**：OpenClaw 已有 auth/channels/session 完整实现（`00-system-architecture.md` §3.2.3 映射表逐条列明：通道接入 / 凭据管理 / 沙箱隔离 / 会话生命周期均为 ✅）。L0-gateway 三组件**归档为「参考设计」**，状态改 📋（架构预留），并 ADR 留痕 | 消除「零落地悬空」；不重复造运行时已有能力（W-1 原生优先铁律的直接适用） |
| 取 B | 落地三组件（1,488 行骨架 → 生产化） | 需要实现认证签发、通道适配器、会话持久化——**全部与 OpenClaw 原生能力重叠**，属两层控制打架；成本高、收益负 |
| 取 C | 维持现状（README+DESIGN+骨架） | 持续产生「设计了但没做」的审计噪音（`DEFECT-LEDGER` 已多次出现同类项） |

**建议 A**，理由与 ADR 一致（原生优先 + 不重复建设 + 消除悬空态）。本层设计**不依赖**该决策落地，可并行推进。

> **决策落地（2026-11-27）**：Rex 拍板取 A。`L0-gateway/README.md` / `DESIGN.md` 已改 📋 架构预留（参考设计），`00-system-architecture.md` §3.1.1 / §3.1.2 状态行同步、§8 ADR-037、§12 v6.1 登记。本层 v1.0 与 L0-gateway 零耦合，不受影响。

---

## 5. 运行时无关性保障（G-5）

| 风险 | 保障措施 | 门禁 |
|---|---|---|
| 直接 `import openclaw` | 编码规范硬约束（`00-system-architecture.md` §3.2.3） | `tests/test_runtime_isolation.py` 静态扫描（M-8 = 0） |
| 直接 `subprocess` 裸调 `openclaw` CLI | 一律经 L1 RuntimeAdapter 的 `execute()` 契约；CLI 路径解析用绝对路径兜底（AGENTS.md 事故教训 2026-11-19） | 代码审查 + 绝对路径断言 |
| 绑定 OpenClaw 特有概念（Skill front-matter 格式等） | 索引层做**格式适配器**，把 skill front-matter / registry.yaml 归一化为运行时中立的 `CapabilityRecord`；其它运行时只需新增 adapter | `CapabilityRecord` schema 不出现运行时专有字段 |
| 绑定文件系统路径 | 根路径从配置读，禁硬编码（AGENTS.md 资产一致性探针要求） | `gen_asset_inventory` 硬编码根路径检查复用 |

**核心抽象**：

```
CapabilityRecord（运行时中立）
  id / name / description
  capability_tags[]
  trigger_hints[]        ← 由 SKILL.md「触发条件」/ registry entry 归一化而来
  entry_ref              ← skill 路径 或 AgentSpec.entrypoint
  runtime_requirement    ← 当前恒为 "openclaw"（S-3 再扩展）
  source                 ← "self-built-skill" | "capability-registry"
```

---

## 6. 可逆性与回滚（G-6）

| 机制 | 内容 |
|---|---|
| **功能开关** | `config/router-policy.yaml` 的 `enabled`（总开关）、`mode ∈ {inject-only, full-route}`、`fallback_policy` |
| **降级路径（F-8）** | 索引不可用 / 检索异常 / 命中为空 → 回退到「全量目录注入」= **现状行为**，主链路不中断（M-6 要求 100%） |
| **灰度** | 先只对 `dashboard`/`webchat` 之一的会话生效（配置维度），对比 M-3 后再放开 |
| **数据面零写入** | 本层**只读** registry.yaml、**不改** `openclaw.json`、**不改** SKILL.md；仅在 registry 里**幂等注册**自建能力声明（可随时 unregister） |
| **回滚动作** | 关总开关即可完全退回 v0 行为；组件目录删除无残留（不产生持久状态，除 telemetry 指标） |
| **不动他人资产** | 禁改 `registry.yaml` / `system_full_audit.py` / `openclaw.json`（Lane A/B 持有，见 PRD W-4） |
| **契约稳定** | 对 L3/L4 只暴露「查询接口」，契约变更须走 ADR（§1 契约稳定原则） |

---

## 7. 与既有资产的复用矩阵

| 需求 | 复用资产 | 状态 | 备注 |
|---|---|---|---|
| 能力索引上游 | `capability-registry/registry.yaml`（84 条目） | ✅ 存在 | **只读**消费 |
| 技能列表数据源 | `openclaw skills list --json` | ✅ 可用 | B-7，避免重造 |
| Agent 注册发现 | `L1_runtime/components/agent-registry` | 🚧 骨架未接线 | 本期接线（M-7） |
| 编排执行 | `L2-infra/skills/dag-orchestrator/scripts/runner.py` | ✅ 34 用例 + VERIFICATION v1.1 | 本期做上游 |
| 遥测打点 | `L1_runtime/components/telemetry` | ✅ 已实现 | S-4 部分可用 |
| 资产文档判定 | `capability_registry._asset_docs()` | ✅ 存在 | AGENTS.md 单一事实源红线：必须复用，禁自造匹配规则 |
| 一致性探针/漂移检测 | `gen_asset_inventory.py` + `system_full_audit.py` | ✅ 存在 | 复用其硬编码根路径检查 |

> 遵循「复用优先」+「Never 未盘点就先写自实现」（AGENTS.md）。

---

## 8. 本期明确的「不做」边界

1. 不做语义向量检索（S-1）。
2. 不做多运行时路由（S-3）——`runtime_requirement` 字段预留但只填 `openclaw`。
3. 不做自适应 k（Q-3）。
4. 不改 `openclaw.json`（Q-4）。
5. 不给 `agent-registry` 加持久化（Q-5），只要求内存态下接线成功。
6. 不碰 L0-gateway 代码（仅出 ADR 处置结论）。
7. 不 commit / 不 add / 不碰共享 git index（并行会话纪律）。

---

## 9. 开放问题（Q-1/Q-2 已决）

| # | 问题 | 状态 |
|---|---|---|
| Q-1 | L0-gateway 处置 | ✅ 已决（Rex 2026-11-27）：取 A 移交 + 归档参考设计，ADR-037 已 accepted |
| Q-2 | 基准集 20 条定标人 | ✅ 已决：Rex 本人定标；文档 `docs/architecture/intent-benchmark-20-calibration.md` 待填备注 |
| Q-3 ~ Q-5 | k 动态 / extraDirs 摘除 / agent-registry 持久化 | 本期按建议（固定 k=5 / 不动 openclaw.json / 内存态接受），v1.1 再评 |

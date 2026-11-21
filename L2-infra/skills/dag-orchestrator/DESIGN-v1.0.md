# dag-orchestrator 执行引擎设计草案 (v0.1 DRAFT — 待评审)

> 状态: **DRAFT / 待 Rex 评审** · 日期: 2026-11-21
> 设计对象: `L2-infra/skills/dag-orchestrator/`（SKILL.md v1.0，2026-09-02）
> 设计范围: SKILL.md 第 90-91 行未实现项 — 「DAG 执行引擎（Python 实现）」、「可视化」
> 设计原则: **只设计，不实现**。评审通过后再走开发闭环（代码 / 测试 / VERIFICATION / registry）。

---

## 0. TL;DR

| 决策 | 结论 | 依据 |
|---|---|---|
| **总体方案** | 自研轻量 Python 执行器 | 节点是 agent 动作（子代理会话），非数据算子；重框架常驻组件是负资产 |
| **拓扑排序** | `graphlib.TopologicalSorter`（标准库） | Python 3.9+，本机 3.14.7 可用；零依赖；DAG 规模小 |
| **并发机制** | `concurrent.futures.ThreadPoolExecutor` + 显式并发上限 | 与 `sessions_spawn` IO 密集特性匹配；可控、可测 |
| **失败策略** | 失败即停下游（沿用 SKILL 规则 3） | 已在 SKILL.md 定义；实现时加失败传播标记 |
| **超时** | 单任务 5min / 整体 30min（沿用 SKILL 规则 4） | 同上 |
| **契约衔接** | 终态调用 `check_answer_contract.py` 做 fail-closed 门禁 | 引擎只保证工件存在性，语义由契约校验器判定 |
| **可视化** | 第一阶段输出 Mermaid 文本，不做 Web UI | 轻量、可嵌入 Markdown/文档；后续再升阶 |
| **重框架引入** | 不引入 Airflow / Prefect / Dagster | 详见 §2.5 方案对比 |
| **OpenClaw / ClawHub 复用** | 无可复用 DAG 执行引擎 skill | ClawHub 检索仅蓝图生成类与 n8n 平台类，无 Python 执行器 |

---

## 1. 现状与约束

### 1.1 SKILL.md 已定义的契约（权威输入）

- **YAML 定义**：`name` / `description` / `tasks[]`
- **task 字段**：`id, name, agent, action, outputs[], inputs[], depends_on[]`
- **示例 DAG**（交付月报）：`collect_oa ∥ collect_revenue ∥ collect_acceptance → join_data → analyze → generate_report`（并行度 3）
- **执行规则 4 条**（SKILL.md §执行规则，必须严格遵循）：
  1. 无依赖任务经 `sessions_spawn` 并行执行
  2. 上游 `outputs` → 下游 `inputs` 变量传递
  3. 任一任务失败 → 停止下游 → 报错
  4. 单任务超时 5 分钟、整体超时 30 分钟
- **内置模板 4 个**：交付月报(6/3)、确收月报(5/2)、系统健康检查(4/4)、数据质量审计(3/1)

### 1.2 当前缺口

`VERIFICATION-v1.0.md` 仅静态结构校验（YAML 合法、id 唯一、依赖无悬空、模板齐全）。
**运行时行为零覆盖**：并行真假、变量传递是否落地、失败是否停下游、超时是否生效。

### 1.3 约束（来自仓内规则）

1. **hermetic 测试**：不依赖外部服务、登录态、网络、PATH 里的 openclaw。
2. **生命周期闭环**：先设计评审 → 再写代码 → 测试 → VERIFICATION → registry 登记；禁止跳过设计直接开发。
3. **fail-closed 契约门禁**：末端产物必须过 `L2-infra/prompts/tools/check_answer_contract.py`。
4. **可审计**：所有 entry 路径真实存在，`--validate` 全通过。
5. **不碰 SKILL.md 既有语义**：4 条执行规则与 YAML 格式是权威契约，引擎是它的实现而非修改它。

---

## 2. 业界方案与取舍

### 2.1 候选方案概览

| 方案 | 形态 | 匹配度 | 引入成本 |
|---|---|---|---|
| Apache Airflow | Scheduler + Executor + 元数据库 | 低 | 极高（常驻服务 + DB） |
| Prefect 2/3 | `@flow`/`@task` + 可选 server | 中 | 中（server 才用完整能力） |
| Dagster | 资产中心 + op + IOManager | 低 | 高（概念负担最重） |
| Dagu | 单二进制 + YAML DAG + Web UI | 中 | 中（外部二进制依赖） |
| taskflow（社区库） | 纯 Python 库 + 拓扑 + 重试 | 中高 | 低 |
| **graphlib + concurrent.futures（自研）** | 标准库 + 轻量封装 | **高** | **零** |

### 2.2 为什么不引入重框架

1. **节点语义不匹配**：本仓 DAG 节点是 **agent 动作**（`sessions_spawn` 子代理，分钟级、有 LLM 不确定性），不是数据处理算子。Airflow/Prefect/Dagster 的调度/分区/重试/资产版本模型在此无收益。
2. **违反 hermetic 原则**：重框架需要元数据库 / scheduler 常驻 / worker 进程，无法像 pytest 一样本地跑通。
3. **状态存储冗余**：本仓已有 OpenClaw 会话层的 runId/sessionKey 状态，引擎只需要一次性进程内执行 + 工件落盘，不需要独立状态机。
4. **学习与维护成本**：三人以下团队维护三个重框架是灾难，何况我们只要 4 条规则。

### 2.3 可借鉴的机制（非框架本身）

- **Dagster** `allow_retries=False` 快速失败思想 → 对应规则 3
- **Prefect** `cache_key_fn` 幂等键 → 可作为跨 run 复用的可选增强
- **taskflow** 的 `trigger_rules` 命名（`all_success`/`all_done`/`none_failed`）→ 失败传播的语义参考
- **Dagu** 的声明式 YAML + 无数据库 → 与本仓方向一致，但外部二进制依赖违反 hermetic

### 2.4 OpenClaw 原生能力的互补关系

| 能力 | 层级 | 与本引擎关系 |
|---|---|---|
| `sessions_spawn` | 运行时 | 引擎的 `agent` 执行后端（真正派生子代理） |
| Task Flow | 运行时（durable） | 引擎可作为其中一个「复合步骤」的执行体 |
| Lobster 插件 | 进程内 DSL | 与本引擎是平行路线，不冲突 |

**定位**：本引擎是 **YAML 定义 → 结构化派发** 的翻译层，不替代 OpenClaw 原生的会话/任务编排能力。

---

## 3. 架构设计

### 3.1 模块划分（建议目录 `scripts/` + `tests/`）

```
L2-infra/skills/dag-orchestrator/
├── SKILL.md                       # 已存在（YAML 契约 + 规则）
├── DESIGN-v1.0.md                 # 本文档
├── VERIFICATION-v1.0.md           # 已存在（静态部分；v2.0 补运行时）
├── scripts/
│   ├── __init__.py
│   ├── loader.py                  # YAML 解析 + 结构校验
│   ├── graph.py                   # 拓扑排序 + 环检测
│   ├── executor.py                # 调度 + 并发 + 失败/超时
│   ├── artifact_store.py          # outputs → inputs 工件传递
│   ├── state.py                   # run 状态落盘
│   ├── runner.py                  # 组合 + 契约门禁
│   └── viz.py                     # Mermaid 文本生成
└── tests/
    ├── conftest.py
    ├── test_loader.py             # YAML 加载/校验
    ├── test_graph.py              # 拓扑/环检测
    ├── test_executor.py           # 并行/失败/超时（注入假执行器）
    ├── test_artifact_store.py     # 变量传递
    ├── test_runner.py             # 端到端 + 契约门禁
    └── test_viz.py                # Mermaid 生成
```

### 3.2 数据流

```
YAML 文件
    │
    ▼
loader.py → DagSpec（校验 id 唯一 / depends_on 无悬空 / inputs ⊆ 上游 outputs）
    │
    ▼
graph.py → TopologicalSorter（就绪层推进）
    │
    ▼
executor.py → ThreadPoolExecutor + 并发上限
    │            │
    │            ├─ 任务完成 → artifact_store.py 写工件
    │            ├─ 任务失败 → 标记下游 skipped，不再派发
    │            └─ 超时 → 标 failed(timeout)，触发停下游
    │
    ▼
state.py → run_state.json（每任务状态 + 工件路径 + 错误）
    │
    ▼
runner.py → 末端节点成功后，调用 check_answer_contract.py
    │
    ▼
exit 0 / 1（契约校验结果决定终态）
```

### 3.3 关键数据结构

```python
# DagSpec（loader 输出）
@dataclass
class DagSpec:
    name: str
    description: str
    tasks: list[TaskSpec]

@dataclass
class TaskSpec:
    id: str                    # 唯一
    name: str
    agent: str                 # 执行体标识，如 "data-collector"
    action: str                # 引擎据此派发 sessions_spawn
    inputs: list[str]          # 必须 ⊆ 上游 outputs 并集
    outputs: list[str]         # 声明式产物名
    depends_on: list[str]      # 边
    timeout_s: int = 300       # 默认 5 分钟（规则 4）

# TaskRun（state 落盘）
@dataclass
class TaskRun:
    task_id: str
    status: Literal["pending", "running", "success", "failed", "skipped"]
    attempts: int = 0
    started_at: str | None = None      # iso8601
    finished_at: str | None = None
    error: str | None = None
    artifact_paths: dict[str, str] = field(default_factory=dict)
                                       # output_name → 绝对路径
```

### 3.4 执行语义要点

| 规则 | 实现方式 | 可测点 |
|---|---|---|
| **并行**（规则 1） | 拓扑层推进；同层任务提交线程池；`max_workers` 显式配置 | 3 任务各 sleep 0.5s，总耗时 < 1.0s |
| **变量传递**（规则 2） | 上游完成后把 outputs 指向的工件路径写入 artifact store；下游从 store 解析 | 上游写值，下游读到相同值 |
| **失败停下游**（规则 3） | 任务 failed → 所有可达下游标 skipped（不提交）；已提交并行任务允许跑完 | 中间任务抛错，下游 skipped，run 终态 failed |
| **单任务超时**（规则 4） | future `result(timeout=task.timeout_s)` | 任务 sleep > timeout，标 failed(timeout) |
| **整体超时**（规则 4） | `wait(futures, timeout=overall_timeout)` | 配置小值（如 2s），总耗时超限标 failed |
| **契约门禁** | runner 在末端节点成功后调用 `check_answer_contract.py` | 夹具报告满足 F1-F5 时 pass，缺溯源链时 fail |

---

## 4. 与契约体系的衔接

### 4.1 check_answer_contract 作为终态 fail-closed 门禁

1. **触发点**：`runner.py` 在末端任务成功后，对末端产物（如 `report_file`）调用校验器。
2. **校验内容**：
   - 内容契约（`answer-spec-base.md`）：时间戳、降级标注、溯源链、推断标记
   - 格式契约（`format-spec-base.md`）F1-F5：H1、元信息块、数据基准、溯源链、质量信号
3. **结果语义**：
   - 退出码 0 → run 终态 `success`
   - 退出码 1 → run 终态 `failed`，错误信息透传
4. **边界**：引擎**不**判定语义对错——与该校验器「不判定语义对错」的定位一致。

### 4.2 hermetic 测试的夹具策略

- **不触真实 OA/BDMS**：用 `tests/fixtures/` 下的预置报告（满足/不满足契约各一份）。
- **不依赖 PATH 里的 openclaw**：用假执行器（注入纯 Python 函数）替代真实 `sessions_spawn`。
- **时间断言**：注入 `sleep` 长度可控，验证并行/超时边界。

---

## 5. 验收测试集（hermetic，共 13 条）

| # | 用例 | 输入 | 断言 |
|---|---|---|---|
| T01 | YAML 加载与校验 | 合法 SKILL.md 示例 | `DagSpec` 6 任务；id 唯一 |
| T02 | 悬空依赖检测 | `depends_on: [nope]` | 抛错且信息含 `nope` |
| T03 | 环检测 | A→B→A | 抛 `CycleError` 类错误，不静默 |
| T04 | 拓扑序正确 | 示例 DAG | `collect_*` 均在 `join_data` 前 |
| T05 | **并行真实发生** | 3 个无依赖任务，各 `sleep 0.5` | 总耗时 < 1.0s（串行需 ≥1.5s）；并发度=1 时 ≈1.5s 对照 |
| T06 | **变量传递** | 上游写工件，下游读 | 下游收到上游 `outputs` 值 |
| T07 | **失败停下游** | 中间任务抛错 | 下游 `skipped`；run 终态 `failed`；无下游工件 |
| T08 | **单任务超时** | 任务 sleep > timeout | 标 `failed(timeout)`，触发停下游 |
| T09 | **整体超时** | 多任务总耗时 > 配置小值 | run 标 `failed`，未完成任务不残留 |
| T10 | **契约门禁通过** | 夹具报告满足 F1-F5 + 内容契约 | run 终态 `success`，退出码 0 |
| T11 | **契约门禁拦截** | 夹具报告缺 `## 0. 溯源链` | run 终态 `failed`，错误含契约校验输出 |
| T12 | 状态落盘可解析 | 任意 run | JSON 状态文件可被独立解析 |
| T13 | 可视化生成 | 示例 DAG | 输出合法 Mermaid 文本，含 6 节点 + 5 条边 |

---

## 6. 可视化方案（两阶段）

### 阶段一：Mermaid 文本（第一期交付）
- `viz.py` 输入 DagSpec，输出 Mermaid `graph TD` 文本。
- 可直接嵌入 Markdown 报告、SKILL.md、文档。
- 零依赖、零服务、hermetic。

### 阶段二：交互式可视化（第二期，按需）
- 独立 HTML 页面 + D3/cytoscape.js（或复用现有 bangcle-ppt 前端栈）。
- 展示运行时状态（pending/running/success/failed/skipped 着色）。
- **不在第一期范围内**，待评审后决定是否立项。

---

## 7. 风险与未决事项（待评审拍板）

| # | 事项 | 选项 | 建议 |
|---|---|---|---|
| 1 | 跨 run 幂等复用（断点续跑）是否纳入第一期 | 纳入 / 第二期 / 不做 | **第二期**：SKILL.md 未要求，避免过度设计 |
| 2 | 重试机制 | 支持 / 不支持 | **不支持**：agent 动作重试成本高（token + 时间），失败即停更安全 |
| 3 | `agent` 字段的派发后端 | 直接 `sessions_spawn` / 可插拔策略模式 | **可插拔接口 + 默认 sessions_spawn**：便于 hermetic 测试注假执行器 |
| 4 | 整体超时的语义 | 硬杀未完成任务 / 标记后允许跑完 | **标记后允许已提交的跑完，不再派发新层**：与「失败停下游」一致，且子代理会话杀不净 |
| 5 | 工件存储格式 | JSON 工件 / 纯文件路径 | **JSON 工件（结构化）**：便于下游解析与契约校验 |
| 6 | 状态落盘位置 | run 目录 / 全局状态目录 | **run 目录（tmpdir 或指定路径）**：hermetic 测试友好，隔离 run |
| 7 | 是否作为 L2 component 而非 skill | 保留 skill / 升 component | **先 skill，使用率提升后再考虑升组件** |
| 8 | registry 条目命名 | `dag-orchestrator.v1.runner.run(dag_path)` / 其它 | 待评审，沿用 `--query` 命名惯例 |

---

## 8. 调研来源

### 本仓
- `L2-infra/skills/dag-orchestrator/SKILL.md`
- `L2-infra/skills/dag-orchestrator/VERIFICATION-v1.0.md`
- `L2-infra/prompts/tools/check_answer_contract.py`
- `L2-infra/prompts/answer-spec-base.md`
- `L2-infra/prompts/format-spec-base.md`

### 官方文档
- Airflow: https://airflow.apache.org/docs/apache-airflow/stable/core-concepts/overview.html
- Prefect: https://www.prefect.io/docs/v3/concepts/flows
- Dagster: https://dagster.io/docs/getting-started/concepts
- graphlib: https://docs.python.org/3/library/graphlib.html
- concurrent.futures: https://docs.python.org/3/library/concurrent.futures.html
- OpenClaw sub-agents: https://docs.openclaw.ai/tools/subagents

### 开源项目
- Dagu: https://github.com/dagucloud/dagu
- taskflow: https://github.com/hajirufai/taskflow
- Lobster: https://github.com/openclaw/lobster
- ClawHub: https://clawhub.ai/（检索关键词：workflow / dag / orchestration）

---

## 9. 下一步

1. **Rex 评审本文档**，拍板 §7 未决事项，确定是否进入实现阶段。
2. 评审通过 → 开实施批次：
   - 建 `scripts/` + `tests/` 目录结构
   - 按 §5 测试集逐条实现（TDD）
   - 更新 SKILL.md 第 90-91 行为 `[x]`
   - 产出 VERIFICATION-v2.0.md（补运行时用例）
   - registry 补 entry
   - 走 pre-commit 全门禁 + 推送
3. 评审未通过 → 记录意见，修订后再审。

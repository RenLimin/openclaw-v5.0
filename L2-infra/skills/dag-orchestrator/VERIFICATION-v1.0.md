# dag-orchestrator — 验收文档 (VERIFICATION)

> 版本: v1.1 · 更新: 2026-11-22
> 验收对象: `L2-infra/skills/dag-orchestrator/`（SKILL.md + scripts/ 执行引擎 + tests/）

## 验收标准（Definition of Done）

1. DAG 定义格式有明确规范：任务 `id` 唯一、`depends_on` 无悬空引用、`inputs`/`outputs` 变量传递规则可判定。
2. 内嵌 YAML 工作流定义块为**合法 YAML** 且结构完整（name/description/tasks）。
3. 执行规则可执行语义清晰：并行（无依赖并行）、变量传递（上游 outputs → 下游 inputs）、失败停下游、超时（单任务 5min / 整体 30min）。
4. 内置工作流模板齐全：交付月报 / 确收月报 / 系统健康检查 / 数据质量审计。
5. 实施状态清单与实际文件一致（未实现项不得标成已实现）。
6. **运行时行为真实可执行**（v1.1 新增）：`scripts/runner.py` 可加载真实 YAML 并执行，拓扑/并行/失败/超时/契约门禁均有自动化覆盖。

## 测试范围

- SKILL.md 内嵌 YAML 工作流定义块的结构与引用完整性（TC01–TC05）。
- 执行引擎 hermetic 自动化测试（T01–T13，DESIGN §5）：
  loader 校验 / 拓扑环检测 / 并行真实发生 / 变量传递 / 失败停下游 / 单任务与整体超时 / 契约门禁 fail-closed / 状态落盘 / Mermaid 生成。
- 实施状态清单（`[x]`/`[ ]`）与目录实际内容的一致性。

> 说明：v1.0 验收时引擎未实现（仅静态结构校验）。v1.1 已落地执行引擎
> `scripts/`（loader/graph/executor/artifact_store/state/runner/viz）+ `tests/`（17 用例），
> 运行时行为已纳入自动化验收。

## 测试用例（静态，v1.0 保留）

| # | 场景 | 输入 | 预期结果 | 实测 |
|---|---|---|---|---|
| TC01 | YAML 合法性 | SKILL.md 内嵌 ```yaml 块 | 可 `yaml.safe_load`，无异常 | ✅ 通过 |
| TC02 | 任务 id 唯一 | 工作流 tasks[].id | 无重复 | ✅ 6 个 id 全唯一 |
| TC03 | 依赖无悬空 | tasks[].depends_on | 每个 dep 都在 ids 中 | ✅ 无悬空 |
| TC04 | 并行/变量传递规则 | 执行规则章节 | 4 条规则齐备 | ✅ 齐备 |
| TC05 | 内置工作流模板 | SKILL.md 表格 | 4 个模板声明 | ✅ 4 个（步骤数/并行度标注） |
| TC06 | 实施状态一致性 | 文件清单 vs 清单 | 声明与实际相符 | ✅ 引擎+可视化已 [x]，与 scripts/ 实际存在一致 |

## 运行时测试（v1.1 新增，hermetic 自动化）

| # | 用例 | 输入 | 断言 | 实测 |
|---|---|---|---|---|
| T01 | YAML 加载与校验 | SKILL.md 示例 | 6 任务、id 唯一 | ✅ |
| T02 | 悬空依赖检测 | `depends_on: [nope]` | 抛错含 `nope` | ✅ |
| T02b | 输入未产出检测 | `inputs: [ghost]` | 抛错含 `ghost` | ✅ |
| T02c | 重复 id 检测 | 两个同 id | 抛错含「重复」 | ✅ |
| T03 | 环检测 | A→B→A | 抛 DagCycleError | ✅ |
| T04 | 拓扑序正确 | 示例 DAG | collect_* 均在 join_data 前 | ✅ |
| T05 | 并行真实发生 | 3 无依赖任务各 sleep 0.5 | 总耗时 < 1.0s（串行对照 ≥1.2s） | ✅ |
| T06 | 变量传递 | 上游写工件下游读 | join_data 收到 3 上游输出 | ✅ |
| T07 | 失败停下游 | 中间任务抛错 | 下游 skipped、run failed、无下游工件 | ✅ |
| T08 | 单任务超时 | sleep 3 > timeout 1 | failed(timeout)、下游 skipped | ✅ |
| T09 | 整体超时 | 多任务总耗时 > 配置 | run failed、超时任务标 failed | ✅ |
| T10 | 契约门禁通过 | 合规报告 | run success、契约 PASS | ✅ |
| T11 | 契约门禁拦截 | 缺信封报告 | fail-closed 拦截 | ✅ |
| T11b | 报告缺失 | 不存在路径 | fail-closed | ✅ |
| T12 | 状态落盘可解析 | 任意 run | JSON 可独立解析 | ✅ |
| T13 | 可视化生成 | 示例 DAG | Mermaid 6 节点 + 5 边 | ✅ |
| T14 | 派发消息契约 | 任务节点 | 含 id/agent/action/outputs + JSON 回报契约 | ✅ |
| T15 | 回复解析（纯 JSON） | `{"outputs":{...}}` | 解析出 outputs | ✅ |
| T16 | 回复解析（嵌套+前后文字） | 嵌套 JSON 带解释文字 | 括号平衡提取正确 | ✅ |
| T17 | 错误信封 → 失败 | `{"error":...}` | 抛错，不静默 | ✅ |
| T18 | CLI 非零/失败信封 | rc≠0 / ok=false | 抛 RuntimeError | ✅ |
| T19 | CLI 定位 | PATH / 候选绝对路径 | 绝对路径兜底 | ✅ |
| T20 | 派发接入执行器 | dispatcher + run_dag | 端到端 success | ✅ |

## 实测结果

- 命令（自动化）:
  ```bash
  /opt/homebrew/opt/python@3.14/bin/python3.14 -m pytest L2-infra/skills/dag-orchestrator/tests/ -q
  ```
- 输出: **34 passed in 8.88s**（含契约门禁 T10/T11/T11b 真实调用 check_answer_contract；
  派发 T14–T20 用 fake CLI 注入，hermetic 不触真实 Gateway）。
- 真实运行（非仅测试）：从 SKILL.md 提取真实 YAML 块 →
  ```bash
  python3 L2-infra/skills/dag-orchestrator/scripts/runner.py /tmp/dag_skill_sample.yaml --max-workers 3
  ```
  输出 6 任务按序执行（3 并行采集 → join → analyze → report），`run 状态: success`，exit=0；
  `--mermaid` 输出合法 Mermaid（6 节点 + 5 边）。
- 结论: **通过**。定义层 + 运行时行为全部验收；实施状态与实际文件一致。

## 遗留问题（如实记录）

1. **内置模板仅「交付月报」有 YAML 定义块**：「确收月报 5」「系统健康检查 4」「数据质量审计 3」三个模板仅有表格声明（SKILL.md 未内嵌对应 YAML）。引擎已就绪，可后续补 YAML 定义块。
2. **默认执行器为框架实现**：runner 默认执行器打印任务信息并透传 inputs；真实 agent 派发（sessions_spawn）待接入（接口已留 `runner(task, inputs)` 注入点）。
3. **两套 visual 测试并存**（L2 聚合 + L4 组件内）待拍板去重（E-06 遗留）。

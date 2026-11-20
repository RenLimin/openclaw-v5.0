# dag-orchestrator — 验收文档 (VERIFICATION)

> 版本: v1.0 · 日期: 2026-11-20
> 验收对象: `L2-infra/skills/dag-orchestrator/`（仅 `SKILL.md`，无 scripts/、无 tests/）

## 验收标准（Definition of Done）

1. DAG 定义格式有明确规范：任务 `id` 唯一、`depends_on` 无悬空引用、`inputs`/`outputs` 变量传递规则可判定。
2. 内嵌 YAML 工作流定义块为**合法 YAML** 且结构完整（name/description/tasks）。
3. 执行规则可执行语义清晰：并行（无依赖并行）、变量传递（上游 outputs → 下游 inputs）、失败停下游、超时（单任务 5min / 整体 30min）。
4. 内置工作流模板齐全：交付月报 / 确收月报 / 系统健康检查 / 数据质量审计。
5. 实施状态清单与实际文件一致（未实现项不得标成已实现）。

## 测试范围

- SKILL.md 内嵌 YAML 工作流定义块的结构与引用完整性。
- 内置工作流模板覆盖度（对照 SKILL.md 声明表）。
- 实施状态清单（`[x]`/`[ ]`）与目录实际内容的一致性。

> 说明：本 skill 无执行引擎、无脚本、无 pytest 用例（SKILL.md 自己将「DAG 执行引擎（Python 实现）」标为 `[ ]` 未实现）。
> 因此验收方式为**静态结构校验 + 人工走查**，不含运行时行为验证。

## 测试用例

| # | 场景 | 输入 | 预期结果 | 实测 |
|---|---|---|---|---|
| TC01 | YAML 合法性 | SKILL.md 内嵌 ```yaml 块 | 可 `yaml.safe_load`，无异常 | ✅ 通过 |
| TC02 | 任务 id 唯一 | 工作流 tasks[].id | 无重复 | ✅ 6 个 id 全唯一 |
| TC03 | 依赖无悬空 | tasks[].depends_on | 每个 dep 都在 ids 中 | ✅ 无悬空 |
| TC04 | 并行/变量传递规则 | 执行规则章节 | 4 条规则齐备 | ✅ 齐备 |
| TC05 | 内置工作流模板 | SKILL.md 表格 | 4 个模板声明 | ✅ 4 个（步骤数/并行度标注） |
| TC06 | 实施状态一致性 | 文件清单 vs 清单 | 声明与实际相符 | ⚠️ 见遗留问题 |

## 实测结果

- 命令:
  ```bash
  cd /Users/bangcle/.openclaw/workspace && python3 - <<'EOF'
  import yaml, pathlib, re
  txt = pathlib.Path('L2-infra/skills/dag-orchestrator/SKILL.md').read_text(encoding='utf-8')
  blocks = re.findall(r"```yaml\n(.*?)```", txt, re.S)
  for b in blocks:
      d = yaml.safe_load(b); tasks = d.get('tasks', []); ids = [t['id'] for t in tasks]
      assert len(ids) == len(set(ids))
      for t in tasks:
          for dep in t.get('depends_on', []): assert dep in ids
      print(d.get('name'), len(tasks), ids)
  EOF
  ```
- 输出摘要:
  ```
  dag-orchestrator yaml blocks: 1
    block0: name=交付月报生成 tasks=6 ids=['collect_oa','collect_revenue','collect_acceptance','join_data','analyze','generate_report'] deps-ok
  dag YAML structure valid: OK
  ```
- 结论: **部分通过**。定义层（格式规范 + YAML 结构 + 执行规则 + 4 个模板）达标；**执行引擎未实现**，故运行时行为（并行、变量传递、失败停下游、超时）不在本次验收覆盖内，不得视为已验收能力。

## 遗留问题（如实记录）

1. **执行引擎缺失**：SKILL.md「实施状态」中 `DAG 执行引擎（Python 实现）` 与 `可视化` 均为 `[ ]`，当前只有规范文本，没有可执行引擎。运行时验收待引擎落地后补做。
2. **声明与实现存在口径差**：SKILL.md 声明交付月报「步骤数 6 / 并行度 3」，实测 YAML 确为 6 任务；但「确收月报 5」「系统健康检查 4」「数据质量审计 3」三个模板**没有对应 YAML 定义块**（仅表格声明），无法逐条结构校验。
3. **无自动化回归**：建议后续为 YAML 定义块补一个结构校验脚本（本次 TC01–TC03 的校验逻辑可直接固化）。

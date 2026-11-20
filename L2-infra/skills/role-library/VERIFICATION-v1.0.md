# role-library — 验收文档 (VERIFICATION)

> 版本: v1.0 · 日期: 2026-11-20
> 验收对象: `L2-infra/skills/role-library/`（SKILL.md + references/roles/data-analyst.yaml + references/roles/ui-designer.md）

## 验收标准（Definition of Done）

1. 角色定义格式规范明确：YAML frontmatter 含 `role_id / name / category / description / tools / permissions`，正文含职责/工作规范/输出格式。
2. 内置角色清单与实际文件对应（SKILL.md 声明的角色可在 `references/roles/` 找到，或明确标注为「待补」）。
3. 角色文件可被 YAML 解析（frontmatter 部分），字段类型正确。
4. 三种使用方式（直接指定 / 自动匹配 / 多角色协作）在文档中可操作。
5. 应答契约适用范围（ADR-035）在文档中明确。

## 测试范围

- SKILL.md 声明的角色清单 vs `references/roles/` 实际文件。
- YAML 文件 frontmatter 解析与字段校验。
- Markdown 形态角色定义的可解析性（结构约定核查）。

> 本 skill 目录内**无 scripts/、无 tests/**，验收方式为静态解析 + 声明一致性核查。

## 测试用例

| # | 场景 | 输入 | 预期结果 | 实测 |
|---|---|---|---|---|
| TC01 | YAML 解析 | references/roles/data-analyst.yaml | frontmatter 解析为 dict，字段齐全 | ✅ 6 字段齐全 |
| TC02 | 字段值 | data-analyst.yaml | role_id/name/category 正确 | ✅ data-analyst / 数据分析师 / analysis |
| TC03 | MD 角色文件 | references/roles/ui-designer.md | 含 role_id/category/description 结构 | ✅ 含（Markdown 形态，非 YAML） |
| TC04 | 声明 vs 文件 | SKILL.md 7 个内置角色 vs 实际 2 个文件 | 一致 | ⚠️ 声明 7 / 实到 2 |
| TC05 | 实施状态 | SKILL.md 清单 | 未实现项不得标已实现 | ✅ 内置角色定义标 `[ ]` |

## 实测结果

- 命令与输出摘要:
  ```bash
  # TC01–TC03
  python3 -c "import yaml,pathlib; raw=pathlib.Path('L2-infra/skills/role-library/references/roles/data-analyst.yaml').read_text(encoding='utf-8'); \
    doc=yaml.safe_load(raw.split('---',2)[1]); print(list(doc.keys()), doc['role_id'], doc['name'], doc['category'])"
  # → ['role_id','name','category','description','tools','permissions'] data-analyst 数据分析师 analysis

  # TC03：ui-designer.md 为 Markdown 结构（**role_id**: `ui-designer` / **category**: `design`），
  #      不含 YAML frontmatter —— 与 SKILL.md「新增角色请在 references/roles/ 下创建 YAML 文件」的格式要求不一致
  ```
- 结论: **部分通过**。格式规范与字段定义清晰，唯一 YAML 角色文件解析与字段校验通过；但**声明与实现存在明显缺口**（声明 7 个内置角色，实际仅 2 个角色文件，其中 1 个还不是规定格式的 YAML）。

## 遗留问题（如实记录）

1. **声明 7 / 实到 2（新发现）**：SKILL.md 内置角色表列出 `data-analyst / report-generator / quality-auditor / sys-admin / db-admin / pm-assistant / data-collector` 共 7 个，`references/roles/` 实际只有 `data-analyst.yaml` 与 `ui-designer.md`。缺 5 个声明角色（report-generator / quality-auditor / sys-admin / db-admin / pm-assistant / data-collector），且多出 1 个未在清单中的 `ui-designer`。
2. **格式不统一**：SKILL.md 要求新增角色建 YAML（含 frontmatter），但 `ui-designer.md` 是 Markdown 结构，`yaml.safe_load` 直接抛 `ScannerError`。→ 需统一为 YAML 或在 SKILL.md 显式声明支持两种格式。
3. **角色自动匹配 / 多角色协作未实现**：SKILL.md 实施状态已将「角色自动匹配逻辑」「多角色协作编排」标为 `[ ]`，本次不纳入验收覆盖。
4. **无自动化校验**：建议补一个 `verify_roles.py`，校验「SKILL.md 声明集合 == references/roles 文件集合」与「YAML frontmatter 字段完整」，把 TC04 变成机器门禁。

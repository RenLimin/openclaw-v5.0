# web-ui-design — 验收文档 (VERIFICATION)

> 版本: v1.0 · 日期: 2026-11-20
> 验收对象: `L2-infra/skills/web-ui-design/`（SKILL.md + DESIGN-OUTLINE.md + DESIGN-DETAIL.md）
> 关联: `L4-proprietary/skills/bdms-web-ui-design/`（仅 SKILL.md）

## 验收标准（Definition of Done）

1. 三层文档齐备：SKILL.md（能力入口/原则）+ DESIGN-OUTLINE.md（框架大纲）+ DESIGN-DETAIL.md（详细设计）。
2. 原则体系统一：核心设计原则 4 项 + UX/UI 通用原则 5 项，三份文档口径一致。
3. 关键量化口径一致：动效时长、动画曲线、分层架构、测试验证要求。
4. 工程实践可执行：分层架构 / 前后分离 / 单一来源 / 代码规范 / 测试验证（浏览器模拟人工 + 零 JS 错误）。
5. 文档结构完整：标题层级清晰、无破损代码块。

## 测试范围

- 三份文档存在性与结构（行数、标题数、代码块配对）。
- 关键词跨文档覆盖度（原则口径一致性）。
- 动效时长等量化口径一致性。
- 与 L4 bdms-web-ui-design 的关联关系。

> 本 skill 是**规范/知识型**资产（无脚本、无 tests/），验收方式为**文档一致性与结构核查**，不含运行时验证。

## 测试用例

| # | 场景 | 输入 | 预期结果 | 实测 |
|---|---|---|---|---|
| TC01 | 文档齐备 | 目录文件清单 | 3 份文档存在 | ✅ SKILL/OUTLINE/DETAIL 均在 |
| TC02 | 结构完整 | 行数/标题/代码块 | 结构可解析、无破损 | ✅ 84/41/200 行；fence 均为偶数 |
| TC03 | 原则一致性 | 9 个原则关键词 | 三份文档均出现 | ✅ 9/9 × 3/3 |
| TC04 | 量化口径 | 动效时长 | 口径一致（150–400ms） | ✅ SKILL 与 DETAIL 一致 |
| TC05 | L4 关联 | L4 bdms-web-ui-design | 关联对象存在 | ✅ 存在（仅 SKILL.md） |

## 实测结果

- 命令与输出摘要:
  ```bash
  python3 - <<'EOF'
  import pathlib, re
  base = pathlib.Path('L2-infra/skills/web-ui-design')
  files = ['SKILL.md','DESIGN-OUTLINE.md','DESIGN-DETAIL.md']
  # 结构
  #   SKILL.md 1683 chars / 84 lines / 8 headings
  #   DESIGN-OUTLINE.md 615 chars / 41 lines / 11 headings
  #   DESIGN-DETAIL.md 4218 chars / 200 lines / 25 headings
  #   fence 计数 0/0/0（偶数，无破损代码块）
  # 原则关键词（内容分层/视觉层次/一致性/简化任务/以人为本/设计系统/动效/微交互/简约）
  #   → 每个关键词命中 3/3 份文档
  # 动效时长
  #   SKILL.md: '150ms - 400ms'   DESIGN-DETAIL.md: '150-400ms'   （口径一致）
  EOF
  # L4 关联：L4-proprietary/skills/bdms-web-ui-design/SKILL.md 存在
  ```
- 结论: **通过**。三份文档齐备、结构完整，9 项原则关键词在三层文档 100% 一致，动效量化口径一致。作为规范型资产，验收点（口径一致性 + 结构完整性）达标。

## 遗留问题（如实记录）

1. **无落地实现/测试**：本 skill 仅沉淀规范文本，没有组件实现或自动化测试；SKILL.md「工程实践 · 测试验证」要求「浏览器自动化模拟人工测试 + 零 JS 错误」，但该要求只能约束**使用本规范的项目**，无法在本 skill 内自测。→ 建议在具体承接项目（如 L4 bdms-web-ui-design）的验收文档中回链本规范并记录走查结果。
2. **L4 关联对象单薄**：`L4-proprietary/skills/bdms-web-ui-design/` 只有 SKILL.md，无 DESIGN/VERIFICATION，无法核对其是否真正遵循 L2 规范。建议补齐或在本文档记录映射关系。
3. **组件规范层未见配套实现**：DESIGN-DETAIL 第 2 节列了按钮/输入框/表格等组件规范，但 `L2-infra/components/web-common` 等既有实现是否与之对齐未做逐项核对（超出本次 10 个 skill 的验收范围，建议单独立项）。

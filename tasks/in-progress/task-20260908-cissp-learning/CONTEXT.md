# CISSP 学习系统建设 — 上下文

## 业务目标
为 Rex 的 CISSP 备考建设结构化学习系统：完整学习规划 + 每日学习内容 + 复习题/参考题 + 速记背诵内容。

## 关键参数（Rex 已确认）
- 学习周期：16 周（支持动态调整：某域正确率低则自动延长）
- 每日时长：工作日 1h/天，周末/节假日 3h/天
- 输出载体：Markdown 知识库 + CLI，附操作指南

## 分层落地
1. **L3**：`security-engineering` 维度（已在 kb_index.py 白名单但未建设）
   - 知识：CISSP CBK 8 域（按主项/子项组织）
   - 角色：备考教练 / 题库出题官 / 知识讲解员
   - 模板：学习计划 / 错题本 / 速记卡
2. **L4**：`cissp-learning` 组件
   - 学习规划引擎（动态调整）
   - 每日内容生成器
   - 题库管理器
   - 速记卡生成器
   - CLI 封装

## 参考资料根目录
`/Users/bangcle/Bangcle Workspace/02. Learning/CISSP/`

## 已解析中间产物（/tmp）
- `cissp_domains.json`：8 域 → 62 主项 → 274 子项（来自「各域考点分布汇总.xlsx」）
- `cissp_chapter_map.json`：275 条考点→OSG 章节映射

## 建设规范
- 维度设计：`docs/knowledge-base/by-category/business/methodology/dimension-design.md`
- 角色定义：`docs/knowledge-base/by-category/business/methodology/role-definition.md`
- 知识文档：`docs/knowledge-base/by-category/business/methodology/knowledge-authoring.md`
- 质量标准：`docs/knowledge-base/by-category/business/methodology/quality-standard.md`
- 参考范例：`docs/knowledge-base/by-category/business/project-management/`
- kb_index 白名单：`L2-infra/components/memory-embedding/kb_index.py` 的 VALID_DIMENSIONS 已有 "security-engineering"
- 提交规范：Conventional Commits，建设完成且验证通过后自动 commit + push

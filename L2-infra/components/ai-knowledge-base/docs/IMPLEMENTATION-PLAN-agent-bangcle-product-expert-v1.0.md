# 产品专家Agent实施计划 — Bangcle产品专家 v1.0

> 基于AI知识库构建的产品专家Agent资产建设计划
> 版本：v1.0 · 状态：Draft
> 最后更新：2026-10-18

---

## 1. 总体计划

### 1.1 目标

交付可部署的 Bangcle 产品专家 Agent 资产包：
- Agent 系统提示词（继承 AI 知识库全部能力）
- MCP 工具对接配置
- 产品知识库实例（product-kb 模板）
- 产品知识样例文档 + 导入脚本
- E2E 验证脚本

### 1.2 阶段划分

| 阶段 | 名称 | 目标 | 交付物 |
|---|---|---|---|
| P-A | 资产准备 | Agent 提示词 + 配置 + 文档资产 | SYSTEM_PROMPT / tools.json / 产品样例 |
| P-B | 知识库实例化 | 创建 bangcle-products 实例 + 导入产品知识 | 可用实例 + 导入脚本 |
| P-C | E2E 验证 | 全链路验证（查询/引用/反馈/MCP） | 验证报告 |

### 1.3 资产目录结构

```
agents/bangcle-product-expert/
├── SYSTEM_PROMPT.md              # Agent 系统提示词（最终版）
├── TOOLS.md                      # MCP 工具对接说明
├── config.json                   # Agent 配置（实例/MCP端点/参数）
├── knowledge/                    # 产品知识源文档
│   ├── 产品-APP加固.md
│   ├── 产品-渠道监测.md
│   └── ...
├── scripts/
│   ├── init_instance.sh          # 创建实例脚本
│   └── import_knowledge.sh       # 导入知识脚本
└── tests/
    └── e2e_verify.py             # E2E 验证脚本
```

---

## 2. P-A 资产准备

### 2.1 工作项

| # | 任务 | 说明 |
|---|---|---|
| A1 | 编制 SYSTEM_PROMPT.md | 最终优化版提示词（继承检索增强/质量/审计能力） |
| A2 | 编制 TOOLS.md | MCP 工具对接说明 |
| A3 | 编制 config.json | Agent 运行配置 |
| A4 | 编制产品知识样例 | 梆梆安全核心产品知识文档（不少于 3 篇） |

### 2.2 验收标准

- [ ] SYSTEM_PROMPT.md 完整可用，包含：角色/工作流程/约束规则/来源引用格式
- [ ] TOOLS.md 列出全部 MCP 工具及参数
- [ ] config.json 包含实例 code、MCP 端点、top_k 等参数
- [ ] 产品知识样例 ≥ 3 篇，格式为 markdown，含结构化章节

---

## 3. P-B 知识库实例化

### 3.1 工作项

| # | 任务 | 说明 |
|---|---|---|
| B1 | 创建实例脚本 | init_instance.sh：使用 product-kb 模板创建 bangcle-products |
| B2 | 导入知识脚本 | import_knowledge.sh：批量导入 knowledge/ 目录 |
| B3 | 实例化执行 | 实际创建实例 + 导入文档 |

### 3.2 验收标准

- [ ] 实例创建成功，domain_id 返回
- [ ] 文档导入成功，实体/文档/切片入库
- [ ] 查询可返回带来源引用的结果

---

## 4. P-C E2E 验证

### 4.1 工作项

| # | 任务 | 说明 |
|---|---|---|
| C1 | E2E 验证脚本 | e2e_verify.py：创建实例→导入→查询→引用→反馈全链路 |
| C2 | MCP 工具验证 | kb_query / kb_add_feedback / kb_stats 可用 |
| C3 | 验证报告 | 输出验证结果 |

### 4.2 验收标准

- [ ] E2E 脚本全部通过
- [ ] 查询结果包含来源引用
- [ ] 反馈提交成功
- [ ] 无未处理异常

---

## 5. 风险与应对

| 风险 | 概率 | 应对 |
|---|---|---|
| 产品知识文档不足 | 中 | 样例先建 3-5 篇核心产品，后续补充 |
| Embedding 模型不可用 | 高 | 系统已处理 None 向量降级，查询仍可用 FTS+实体召回 |
| MCP 端点不通 | 低 | E2E 直接调用服务层验证，不依赖网络 |

---

## 6. 提交

资产建设完成后：
1. 运行全量测试确认无回归
2. 提交 git
3. 推送 github

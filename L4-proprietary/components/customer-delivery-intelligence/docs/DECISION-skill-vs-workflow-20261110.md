# 决策记录：CDI 定位为「工作流」，SKILL 仅作路由入口

- 日期：2026-11-10
- 决策者：Rex
- 状态：已定（applied）

## 背景
CDI 建成后需明确资产定位：SKILL 还是工作流？这决定复用方式与治理边界。

## 判断依据
SKILL = agent 按需读的程序性知识，具体执行由模型临场决定（可跳步/换序/倒推）。
CDI 的核心价值恰是「不能由模型临场决定」的强制约束：

| 约束 | 强制载体 |
|---|---|
| 固定拓扑 N1→N7 | runner 状态机 |
| 两道 HITL 闸 | gate + 决策事件 |
| 数字一致性 / sourceUri 100% | fail-closed 校验 |
| 多实例幂等 / 断点恢复 | SQLite 检查点 |

故流程本体必须是工作流；SKILL 只承担意图识别与参数归一。

## 结论（分层）
```
全局薄 skill（路由） → runner 工作流（本体） → 既有 collector/引擎
```
- 全局 skill：`L4-proprietary/skills/customer-delivery-intelligence/SKILL.md`（薄入口）
- 流程唯一权威：本组件 `runner/` 代码
- 组件 SKILL.md：标注 `kind: workflow`，只描述契约与产物，不复述可漂移的流程细节

## 影响
- 任何会话可经自然语言稳定触发，但进入工作流后顺序/闸不受模型自由度影响。
- 拓扑/闸/校验只在代码维护一处，避免 skill 与实现两处漂移。

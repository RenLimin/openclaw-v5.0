# tool-policy — 测试方案 (VERIFICATION)

> 版本: v1.0 · 日期: 2026-09-28

## 测试范围

- 三态治理
- 六项审计
- 策略合规

## 测试用例

| # | 场景 | 输入 | 预期结果 |
|---|---|---|---|
| TC01 | 三态检查 | 工具列表 | denied/allowed-broken/allowed-working |
| TC02 | 六项审计 | workspace | 审计报告 |
| TC03 | 策略合规 | 当前配置 | 合规通过 |

## 实测结果

- 三态: ✅
- 审计: ✅
- 合规: ✅

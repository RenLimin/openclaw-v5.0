# credentials — 测试方案 (VERIFICATION)

> 版本: v1.0 · 日期: 2026-09-28

## 测试范围

- 凭据扫描
- SecretRef 解析
- 凭据完整性

## 测试用例

| # | 场景 | 输入 | 预期结果 |
|---|---|---|---|
| TC01 | 凭据扫描 | workspace | 无泄露 |
| TC02 | SecretRef 解析 | 引用列表 | 全部可解析 |
| TC03 | 凭据完整性 | store | 全部有效 |

## 实测结果

- cred_scan: ✅
- SecretRef: ✅
- audit: ✅

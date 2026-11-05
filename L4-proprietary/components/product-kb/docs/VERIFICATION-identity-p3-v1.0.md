# VERIFICATION — product-kb 权威身份层 P3

| 项 | 值 |
|---|---|
| Phase | P3（导入幂等 + 身份管理 CLI） |
| 日期 | 2026-11-02 |
| 依据 | IMPLEMENTATION-PLAN-identity-v1.0 §4 |
| 结论 | ✅ 通过（真实命令） |

## 交付物
- `io.py`：PriceImporter 改为 **canonical_key 定位产品**（新建才 create_product），新建产品自动 register 身份 + `price_excel` 别名 + internal 编码别名；历史产品补登 price_excel 别名；
- `identity.py`：新增 `get_by_canonical()`；
- `cli.py`：7 个身份子命令 identity-backfill / alias-add / alias-list / merge / unmerge / resolve / identity-conflicts。

## 测试结果（真实执行）
```
python3 -m pytest tests/test_import_idempotent.py -v   → 2 passed
python3 -m pytest tests/ -q                            → 12 passed
```
- 同一价格表（含 2 产品/2 SKU）**连导 3 次**：首次 products=2，后两次 products=0，产品/SKU 数量恒定（幂等）；
- 新名称价格表：products=1，产品总数 2→3（不误伤新品）；
- price_excel / internal 别名均可 resolve。

## CLI 冒烟（真实 product_kb.db）
```
resolve internal AS-AIOTP-6.0-EA-SAP-021 → 1
resolve contract_text 鬼东西xyz          → None
identity-backfill                        → Backfilled 0 (193 已齐)
alias-list --product 1                   → 2 aliases
```

## 碰撞与回滚
- 全程未改 contract.py（合同验证会话入口），仅改 io/identity/cli；
- 导入逻辑幂等，重复执行无副作用；身份表可独立 drop 回滚。

## 遗留
- P2 ContractMatcher 接入 resolve + needs_human_review（等合同案例验证收口）；
- P4 审计表 + 批量业务别名回填 + unmerge 工具收尾（unmerge 已在 P1 实现，P4 补审计）。

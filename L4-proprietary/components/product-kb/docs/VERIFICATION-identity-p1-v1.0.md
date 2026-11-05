# VERIFICATION — product-kb 权威身份层 P1

| 项 | 值 |
|---|---|
| Phase | P1（身份表 + canonical_key 回填 + IdentityService API） |
| 日期 | 2026-11-02 |
| 依据 | IMPLEMENTATION-PLAN-identity-v1.0 §2 |
| 结论 | ✅ 通过（真实命令，非自述） |

## 交付物
- `product_kb/db.py`：新增 `init_identity_tables()`（migration v12，增量幂等），未改任何既有方法；
- `product_kb/identity.py`：`canonical_key()` + `ProductIdentityService`（register/add_alias/resolve/merge/unmerge/list/get_by_product_id/list_aliases），算法对齐 L2 v8；
- `tests/test_identity.py`：10 用例；
- `product_kb.db`：新增 product_identity/product_alias/kb_migration 三表，回填 193 身份 + 386 internal 别名，**product/sku 等既有表零改动**。

## 测试结果（真实执行）
```
python3 -m pytest tests/test_identity.py -v
10 passed in 0.06s
python3 -m pytest tests/ -q
10 passed
```
覆盖：规范化（NFKC/标点/大小写）、版本号区分 V4/V5、register 冲突、resolve CWA 命中/未命中、alias UNIQUE、merge alias 转移+去重+防重复归并、unmerge 回滚、DDL 幂等。

## 数据断言（真实 backfill）
- 身份数 = 193（等于产品数）；
- canonical_key 0 空值、0 重复（保留版本号规则，实测）；
- 别名 386 = 193 code + 193 旧 id；
- 冒烟：`resolve('internal','AS-AIOTP-6.0-EA-SAP-021')→1`、`id:193→193`、未命中→`None`。

## 安全与回滚
- 建表前已备份 `data/product_kb.db.bak-p1-*`（已 gitignore）；
- 只 CREATE 新表 + INSERT 新表，未 UPDATE/DELETE 既有任何行；
- 完全回滚：drop 三张新表（product/sku 无涉）。

## 遗留（后续 Phase）
- P2 ContractMatcher 接入 resolve + needs_human_review（等合同案例验证会话收口）；
- P3 io.py 导入幂等 + CLI；P4 审计表/批量业务别名回填（当前仅 internal 别名）。

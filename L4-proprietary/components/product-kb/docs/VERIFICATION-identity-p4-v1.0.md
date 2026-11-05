# VERIFICATION — product-kb 权威身份层 P4

| 项 | 值 |
|---|---|
| Phase | P4（审计留痕 + 批量业务别名回填） |
| 日期 | 2026-11-02 |
| 依据 | IMPLEMENTATION-PLAN-identity-v1.0 §5 |
| 结论 | ✅ 通过（真实命令） |

## 交付物
- `db.py`：新增 `identity_audit` 表（migration v13），merge/unmerge 全留痕；
- `identity.py`：merge/unmerge 写 `identity_audit`（identity_id/op/actor/details/ts），unmerge 增加 actor；新增 `_audit()`；
- `cli.py`：新增 `alias-backfill [--from-doc]`（legacy_alias + doc_asset 批量回填）；unmerge 加 --actor；**跨产品同名歧义显式报告，不自动裁决**。

## 审计留痕验证（真实临时 db）
```
ident=1 merge   by rex: {"into_id":2,"dropped_duplicate_aliases":[]}
ident=1 unmerge by rex: {"restored_from":2}
migrations: v12 product_identity, v13 identity_audit
```
live db identity_audit 当前 0 行（回填不产生审计，尚无真实 merge），机制已证。

## 批量回填结果（真实 product_kb.db）
| source_system | 数量 |
|---|---|
| doc_asset | 918 |
| internal | 386 |
| legacy_alias | 3 |
| **total** | **1307** |

## 关键：跨产品歧义不静默吞（CWA）
回填脚本最初把"同名已映射到另一产品"当幂等跳过、误报 0 conflict。**已修正**：现在显式列出 ambiguous：
```
legacy_alias: Dart加固工具/Flutter混淆工具/Dart源码加固  want_pid=73  already->pid=49
doc_asset: 销售一指禅-应用安全测评平台20220819         want_pid=14  already->pid=5
```
- pid 49(Android加固V7.0) 与 pid 73(iOS加固V4.0) 共用 3 个别名 → 先到者 pid49 持有，pid73 标记待人工裁定；
- 系统不自动决定别名归谁，留 Rex 拍板。

## 测试
```
python3 -m pytest tests/ -q → 12 passed
```

## 遗留 / 待人工
- 上述 4 项 ambiguous 别名归属需人工确认；
- P2 ContractMatcher 接入 resolve + needs_human_review（等合同案例验证收口，唯一未完成 Phase）。

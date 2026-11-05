# VERIFICATION P1 权威身份层（Identity）v1.0

> 组件：L2-infra/components/ai-knowledge-base
> 依据：DESIGN-DETAIL-operational-ontology-v1.0 §2.1 / §3.1、IMPLEMENTATION-PLAN P1 任务清单
> 日期：2026-10-31 · 执行人：P1 subagent

## 1. 改动文件清单

| 文件 | 类型 | 说明 |
|---|---|---|
| `ai_kb/db.py` | 增量修改 | 新增 `init_ontology_identity_tables()`：建 ont_identity / ont_identity_alias 两表 + idx_ont_identity_sor 索引，并幂等登记 migration **v8**（`operational_ontology_identity`）。未改动任何既有表与只读路径。 |
| `ai_kb/ontology/__init__.py` | 新增 | 包入口，导出 IdentityService 与 is_operational_object_type。 |
| `ai_kb/ontology/identity.py` | 新增 | IdentityService + object_type 白名单判定。 |
| `tests/test_ontology_identity.py` | 新增 | 12 个单元测试，临时 SQLite 真实跑通。 |
| `docs/VERIFICATION-P1-identity-v1.0.md` | 新增 | 本文档。 |

未触碰：`ai_kb/api.py`、`mcp/`、L3/L4 任何文件；无新第三方依赖；无凭据。

## 2. 新增表 / 方法

### 表（DDL 严格按详设 §2.1，`CREATE TABLE IF NOT EXISTS`）
- **ont_identity**：id / domain_id(FK domain) / object_type / canonical_key /
  system_of_record / display_name / status(default 'active') /
  merged_into(FK self) / metadata(JSON) / created_at / updated_at；
  `UNIQUE(domain_id, object_type, canonical_key)`；
  索引 `idx_ont_identity_sor(system_of_record)`。
- **ont_identity_alias**：id / identity_id(FK ont_identity) / source_system /
  source_key / confidence / created_at；`UNIQUE(source_system, source_key)`。

### IdentityService 方法（§3.1，依赖注入 db，类型注解、snake_case）
- `register_identity(domain, object_type, canonical_key, sor, display_name=None) → int`：
  domain 接受 id 或 code；canonical_key 唯一冲突抛 sqlite3.IntegrityError。
- `add_alias(identity_id, source_system, source_key, confidence=None) → int`：
  源键冲突抛 IntegrityError；身份不存在抛 ValueError。
- `resolve(source_system, source_key) → Optional[int]`：**CWA 边界**——命中即存在，
  未命中返回 None（不存在）；对 merged_into 做防御性链跟随。
- `merge(from_id, into_id, actor) → dict`：软归并（from 方 status='merged' +
  merged_into 指针，不物理删除、可逆）；alias 整体转移；与吸收方重复的源键
  作为同一身份冗余别名删除（保证 UNIQUE）；拒绝自归并/重复归并/向非 active 归并。
- `list_identities(domain, object_type, status=None) → List[dict]`。

### CWA / 白名单
- 模块级 `is_operational_object_type(domain_code, object_type, whitelist)`：
  白名单由 domain 配置（Mapping[domain_code, Collection[object_type]]）驱动，
  支持 "*" 通配；未配置/未声明 domain 默认放行；显式声明后语料类型
  （document/chunk/qa 等）不在封闭世界内。IdentityService 构造期注入，
  register 时强制校验。

## 3. 测试命令与实际结果

```
cd L2-infra/components/ai-knowledge-base
python3 -m pytest tests/test_db.py tests/test_ontology_identity.py -q
```

实际输出：`15 passed in 0.10s`

- tests/test_db.py（既有，无回归）：**3 passed**
- tests/test_ontology_identity.py（新增）：**12 passed**

覆盖项：migration v8 登记、建表幂等、注册身份、重复 canonical_key 冲突、
add_alias、resolve 命中 / 未命中（CWA 返回 None）、merge 软归并 + alias 转移 +
merged 状态、自归并拒绝、重复归并拒绝、重复 (source_system, source_key) 冲突、
白名单判定（含/不含/通配/未配置）、白名单外类型注册拒绝。

## 4. 遗留 TODO

1. **merge 决策记录占位**：P1 无 ont_decision_record 表（P3 才建），merge 现返回
   占位 dict（含 from/into/actor/去重 alias/ts）。`identity.py` 内已留
   `TODO(P3)`：P3 经 DecisionService.record 实写 ont_decision_record
   （result='allowed'，change_set/evidence 完整），并在 kb_audit_log details
   关联 proposal_id。
2. T1.5 product-kb 只读联调（核对自然键唯一性）不在本次代码改动范围，需单独安排，
   不写业务数据。
3. canonical_key 自然键生成规则由 L3/L4 装配期经 domain metadata 注入，
   L2 不内置业务规则（符合详设决策）。

---
name: product-kb
description: "Bangcle 产品知识库 — 产品信息查询、合同标的匹配、文档知识检索；OA 产品中心文档自动增量同步（水位过滤/一键编排）"
homepage:
metadata:
  openclaw:
    emoji: "📦"
    os: ["darwin", "linux"]
    requires:
      components: []
    layer: L4
    component_id: PKB-001
---

# Bangcle 产品知识库 (Product KB)

覆盖 8 产品线 / 37 分类 / 193 产品 / 385 SKU / 1046 文档，支持产品查询、合同标的匹配、文档知识检索。

## ⚠️ 关键路径

所有命令必须使用**绝对路径**，否则找不到模块：
- 项目根: `../../components/product-kb`
- 数据库: `./data/product_kb.db`（相对项目根）
- 入口: `python3 -m product_kb.cli`

## 使用方式

### 1. 查询产品信息（最常用）

```bash
cd /Users/bangcle/.openclaw/workspace/L4-proprietary/components/product-kb && python3 -m product_kb.cli query "关键词"
```

示例：
- `python3 -m product_kb.cli query "鸿蒙NEXT安全键盘"`
- `python3 -m product_kb.cli query "APP双平台安全测试"`
- `python3 -m product_kb.cli query "合规评估服务"`

### 2. 合同标的匹配

```bash
cd /Users/bangcle/.openclaw/workspace/L4-proprietary/components/product-kb && python3 -m product_kb.cli match "产品名"
```

### 3. 列出产品

```bash
cd /Users/bangcle/.openclaw/workspace/L4-proprietary/components/product-kb && python3 -m product_kb.cli list
python3 -m product_kb.cli list --line "安全保护线"
python3 -m product_kb.cli list --search "鸿蒙"
```

### 4. 数据维护

```bash
cd /Users/bangcle/.openclaw/workspace/L4-proprietary/components/product-kb
./scripts/init_db.sh
./scripts/import_price.sh "/Users/bangcle/Bangcle Workspace/07. Bangcle Prod/梆梆_产品价格查询-2026-09-08.xlsx"
./scripts/scan_docs.sh "/Users/bangcle/Bangcle Workspace/07. Bangcle Prod/"
./scripts/build_index.sh
```

### 5. OA 产品中心文档增量同步（自动）

> 链路：OA（泛微）→ 流程 → 知识 → 知识类文档 → 产品中心（114 个叶子目录）。
> 基线 2026-09-20，之后每次只拉取 `doclastmoddate > 水位` 的更新；每轮自动标记截止日期。

```bash
cd /Users/bangcle/.openclaw/workspace/L4-proprietary/components/product-kb
./scripts/oa_sync_pipeline.sh             # 增量抓取 + scan 入库 + build-index（推荐一键）
./scripts/oa_sync_pipeline.sh --dry-run   # 只统计不落盘
./scripts/oa_sync_pipeline.sh --since 2026-10-01   # 临时指定水位
python3 scripts/oa_incremental_sync.py    # 只跑抓取（不入库）
```

落盘与基线同构 `07. Bangcle Prod/<产品线>/<目录>/<文件名>`；覆盖更新的旧版备份到 `~/.openclaw/data/product-kb-oa-sync/trash/`，不直接删。

| 状态/审计位置 | 内容 |
|---|---|
| `~/.openclaw/data/product-kb-oa-sync/state.json` | 基线/水位/最近同步日期/历史 run |
| `~/.openclaw/data/product-kb-oa-sync/manifests/run-<ts>.json` | 每轮 added/updated/unchanged/无附件/错误清单 |
| `~/.openclaw/data/product-kb-oa-sync/trash/<run-ts>/` | 覆盖更新的旧版备份（scan root 之外，不误入库） |

依赖 `~/.openclaw/data/clm-oa-recon/state.json` 的 OA 登录态；失效（API 返回「登录信息超时」）时先重建会话：
`cd L4-proprietary/components/bangcle-contract && python3 -c "from services.oa.browser_fallback import refresh_oa_session; print(refresh_oa_session())"`

## 依赖

- Python 3.10+
- openpyxl / python-docx / python-pptx / PyPDF2
- 语义 embedding：运行环境注入 `get_embedding`

## FAQ

### Q: 查询结果为空？
A: 检查关键词。产品 FTS 索引使用 SQLite FTS5，中文分词需要完整词组匹配（如 "鸿蒙NEXT" 而非 "鸿蒙"）。

### Q: 如何添加新产品？
A: 修改价格表 Excel，重新运行 `import_price.sh`。

### Q: 文档匹配率低？
A: 产品目录名和价格表族名差异大时会降低匹配率。可在 `product` 表 `aliases` 字段（JSON 数组）添加别名。

## 应答规范（ADR-035 强制引用）

> 本技能输出口径必须遵循以下应答契约（ADR-035 P1/P2 纵切层）：
>
> 1. **P1 通用应答契约**（数据源优先级与时效、证据三档【已验证】/【推断】/【缺失】、降级显式声明、落盘与副作用、客户实体归一、风险定级通用规则）：
>    `../../../L2-infra/prompts/answer-spec-base.md`
> 2. **P2 域应答契约**（固定输出维度 + 域风险定级矩阵）：
>    `../../prompts/product-answer-spec.md`
>
> 契约优先于本 SKILL 内任何自定义口径；两者冲突时以契约为准，并提请维护对应 spec。
>
> 3. **交付闸门（强制，1.1 新增）**：生成最终结果前，逐项对照 P2 §1.5「维度合格判据」自检，任一 NO 即重做；
>    复杂任务（>5 步/多数据源）走 P1 §7 plan→validate→execute→verify。
>    每条关键结论带 `【已验证 日期|来源】/【推断】/【缺失】`，文档出处定位到章节，落盘含溯源链。
>    **fail-closed 机器校验（强制）**：报告落盘后运行
>    `python3 ../../../L2-infra/prompts/tools/check_answer_contract.py <报告路径>`
>    exit≠0（BLOCK）→ 修正后重跑，禁止交付；PASS 才算完成。

# Bangcle 产品知识库 OA 文档增量同步 详细设计

| 项 | 值 |
|---|---|
| 文档 | DESIGN-DETAIL-oa-sync |
| 版本 | v1.1（增量，基于 v1.0） |
| 层级 | L4 Bangcle 专有业务模块 |
| 模块编码 | product-kb |
| 能力 | OA（泛微）产品中心文档自动增量同步 |
| 状态 | 建设后补录（能力已于 2026-11-03 交付，本文档固化实际落地契约） |

> **性质说明**：本能力在 v1.0 交付（价格库 + 目录扫描 + 混合检索）之后按增量需求建设。
> 为不破坏 v1.0 历史审计链，不回改 v1.0 正文，以本 v1.1 文档固化实际落地契约；
> v1.0 的 `PRD` / `IMPLEMENTATION-PLAN` 以"v1.1 变更指针"方式引用本文档。

---

## 1. 目标与边界

### 1.1 目标

- 让本地知识库源文件与 OA（泛微）**流程 → 知识 → 知识类文档 → 产品中心**保持同步。
- 基线 `2026-09-20`（本地知识库文档截止日）：首次只拉取该日期**之后**更新的文档。
- 之后每次只做增量，并**标记本次同步截止日期（水位）**。

### 1.2 边界

| 范围内 | 范围外 |
|---|---|
| 产品中心目录树遍历、文档列表分页、增量过滤、附件下载、落盘、旧版备份 | OA 登录（复用既有登录态/刷新，不在本能力重做） |
| 落盘后复用 v1.0 的 scan 入库 + build-index | 知识库检索/问答（v1.0 已提供，本能力只更新源数据） |
| 水位与同步清单的状态管理 | 全量重抓（保留 `fetch_oa_kb.py` 作为独立工具，非本能力主路径） |

---

## 2. 数据来源与接口契约

OA 地址基址 `https://oa.bangcle.com`，全程携带 `~/.openclaw/data/clm-oa-recon/state.json` 中的 cookie。

| 步骤 | 方法 | 路径 | 说明 |
|---|---|---|---|
| 目录树 | GET | `/api/doc/searchlist/treeNode` | 参数 `menuIds=2,760` 等；返回 `treedata` |
| 文档列表 | POST | `/api/doc/searchlist/list?seccategory=<叶子key>` | 先取列表拿 `sessionkey` |
| 列表数据 | POST | `/api/ec/dev/table/datas` | body `dataKey=<sessionkey>&current=<page>`；每行含 `doclastmoddate`、`id`、附件字段 |
| 文档详情 | GET | `/api/doc/detail/basicInfo` | 取附件 `imagefileid` |
| 附件下载 | GET | `/weaver/weaver.file.FileDownload?fileid=<id>` | 直出原件，无需加密 token |

**关键判据：**
- 列表分页不可只看 `total`：实测出现 `total=0` 但 `datas_count=5`，以 `datas` 实际行数 + 是否取满一页共同判定结束。
- 增量过滤字段为 `doclastmoddate`（`YYYY-MM-DD`，**天粒度**）。

---

## 3. 水位与增量模型

### 3.1 状态文件

位置：`~/.openclaw/data/product-kb-oa-sync/state.json`

```json
{
  "baseline_date": "2026-09-20",
  "watermark": "2026-10-08",
  "last_sync_date": "2026-11-03",
  "runs": [ { "date": "...", "run_ts": "...", "watermark_after": "...",
              "added": 4, "updated": 0, "unchanged": 0,
              "no_attachment": 0, "errors": 0, "manifest": "<路径>" } ]
}
```

### 3.2 过滤规则（天粒度防漏）

- 候选条件：`doclastmoddate > watermark`（**严格大于**）。
- 选严格大于而非 ≥：同一天可能多次更新，水位停在该日时重跑仍能覆盖同日后续更新，避免天粒度漏更新。
- 一轮结束后，`watermark` 推进为本轮命中文档的**最大 `doclastmoddate`**；无候选则不推进。
- `--no-advance`：执行但不推进水位（演练/回滚验证用）。

### 3.3 去重

按 `doclastmoddate` + OA 文档 ID + 附件 ID + 文件 MD5 四重判据；落盘内容以 MD5 判定是否真正变化。

---

## 4. 目录遍历与落盘

### 4.1 叶子目录收集（114 个）

产品中心 key=`174`，实际叶子 **114 个**。除 6 条预设产品线（62 叶）外，必须纳入：
- `784` 其他产品（已下架）、`730` 其他资料 等非产品线分支；
- `1747` 退市通知（产品中心直属叶）。

非产品线分支用分支名作落盘桶，直属叶归入"产品中心"桶。仅收集预设产品线会漏掉 52 个叶子。

### 4.2 落盘结构（与 v1.0 基线同构）

```
<root>/<产品线桶>/<产品目录>/<OA原始文件名>
# 默认 root = ~/Bangcle Workspace/07. Bangcle Prod
```

- 文件名使用 OA 原始名单点后缀（**修复**全量脚本 `f"{base}.{ext}"` 造成的 `..docx` 双点 bug）。
- 与基线同构保证 scan 时与既有 944 文档同路径，不会因路径不同重复入库。

### 4.3 写入与备份（安全替换）

1. 附件先下载到同目录 `.part` 临时文件。
2. 目标不存在 → `.part` 直接落位（新增）。
3. 目标已存在 → 比对 MD5：
   - 内容相同 → 记 `unchanged`，丢弃 `.part`；
   - 内容变更 → 旧文件移入 `~/.openclaw/data/product-kb-oa-sync/trash/<run-ts>/`，再原子替换（更新）。
4. 备份目录位于 scan root 之外，不会被误扫入库。

---

## 5. 入库与索引衔接（复用 v1.0）

落盘后依次执行 v1.0 既有链路（见 `oa_sync_pipeline.sh`）：

1. **scan**：path-first upsert（v1.1 对 `io.py` / `db.py` 的增强）
   - 同路径 + MD5 变 → `replaced`：更新 `doc_asset` 行并删除其旧 chunks（触发重建）；
   - 新路径 → `added`；新路径但 MD5 已存在 → `duplicate` 跳过；同路径同 MD5 → `unchanged`。
   - 新增方法：`db.get_doc_by_path()` / `db.update_doc_asset()`。
2. **build-index**：增量，仅为无 chunk 的文档重建 chunks/FTS/embedding。

> 说明：`zip` 等非文档解析格式只落盘、不进 `doc_asset`，符合 v1.0 scanner 支持范围。
> `index.py` 在 `get_embedding` 未注入时 embedding 置空（纯 FTS 可用），属既有行为，非本能力引入。

---

## 6. 组件与脚本

| 脚本 | 角色 |
|---|---|
| `scripts/oa_incremental_sync.py` | 增量同步核心（水位/遍历/下载/备份/manifest），纯 `requests` + cookie |
| `scripts/oa_sync_pipeline.sh` | 一键编排：同步 → scan → build-index |
| `scripts/fetch_oa_kb.py` | 全量抓取（保留，含已知双点后缀 bug，非主路径） |

`oa_incremental_sync.py` 参数：`--root`、`--since YYYY-MM-DD`、`--no-advance`、`--dry-run`。

每轮产出清单：`~/.openclaw/data/product-kb-oa-sync/manifests/run-<ts>.json`，
字段含 `watermark_before/after`、`added/updated/unchanged/no_attachment/errors`、`stats`。

---

## 7. 故障与降级

| 现象 | 处理 |
|---|---|
| API 返回 `登录信息超时 / errorCode 002` | 重建 OA 会话后重跑 |
| 列表 `total=0` 但有数据 | 以 `datas` 实际行判定，不提前结束分页 |
| 下载中断 | `.part` 残留，重跑自动覆盖续下，不污染正式文件 |
| 落盘内容与旧版相同 | 记 unchanged，不触发备份/入库/索引 |

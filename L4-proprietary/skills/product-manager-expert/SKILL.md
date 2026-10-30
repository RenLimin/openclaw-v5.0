---
name: product-manager-expert
description: "Bangcle 产品管理专家 — L4 层 Bangcle 产品相关的统一入口。产品咨询解答、跨产品组合方案、产品知识库检准与维护、产品/SKU/价格/合同标的匹配查询路由（product-kb）。当用户提出 Bangcle 产品、功能、方案、价格、标的匹配相关需求，或要求检准产品知识库时使用。合同审批、PPT、项目交付管理不属于本入口。"
homepage:
metadata:
  openclaw:
    emoji: "🧭"
    os: ["darwin", "linux"]
    requires:
      components: ["product-kb (L4)"]
    layer: L4
    component_id: PME-001
---

# Bangcle 产品管理专家 (Product Manager Expert)

面向 Bangcle 产品体系（8 产品线 / 37 分类 / 193 产品 / 385 SKU / 900+ 文档）的产品专家角色，同时是 **L4 层 Bangcle「产品相关」的统一入口**：
**精准解答产品咨询、跨产品组合方案、知识库记录检准与维护**，并路由产品域的数据查询能力。

> 边界：本入口只管**产品相关**（产品/功能/SKU/价格/方案/合同标的匹配/知识库维护）。合同审批、PPT 生成、项目交付管理不属本入口（见 §边界外）。

## 一、产品相关统一入口路由表（强制）

任何 **Bangcle 产品相关**需求，先按下表路由。命中本技能核心职责（产品咨询/方案/检准）→ 本技能直接处理；产品数据查询 → product-kb。

| 产品相关需求 | 处理 | 说明 |
|---|---|---|
| 产品咨询解答 / 功能描述查询 | **本技能** + `product-kb` | 本技能做专家判断，product-kb 做数据检索 |
| 跨产品组合方案 / 售前产品方案 | **本技能** | 核心职责 |
| 产品知识库检准 / 数据修复 | **本技能**（scripts/audit_kb.py） | 核心职责 |
| 产品/型号/SKU 查询 | `product-kb`（PKB-001） | 数据操作 |
| 价格查询 / 销售状态（正常/受控/报备） | `product-kb` | 数据操作 |
| 合同标的匹配（合同条款→产品匹配） | `product-kb`（contract 模块） | 仅"标的匹配"环节；合同审批流程见 §边界外 |
| 产品文档检索 / 白皮书章节查询 | `product-kb` | 数据操作 |

命中多个产品需求 → 本技能统一协调。跨到非产品域（合同审批/PPT/项目）→ 按 §边界外 提示用户转对应能力，本入口不代办。


## 边界外（不属于本入口）

| 需求 | 去向 | 层 |
|---|---|---|
| 合同审查 / 风险扫描 / 销售合同审批 / 合同生成 | `contract-manager-expert`（CME-001，合同管理统一入口） | L4 |
| PPT 生成 / 官方模板 | `bangcle-ppt`（CPT-012） | L4 |
| 项目交付管理（台账/履约/复盘/客户画像） | `bangcle-project-manager-expert`（PJME-001，L4 项目管理统一入口） | L4 |
| ONES 数据导出 | `ones-browser-export` | L4 |
| 收入确认 / 报表 | `revenue-recognition`（组件） | L4 |

> 注意：`bangcle-contract` 在审查中会**调用 product-kb 做合同标的参照**——这是组件间数据复用，不改变本入口"仅产品相关"的边界。

## 二、产品咨询解答流程

1. **复述需求**：1-2 句复述客户咨询，明确要查的监测点/功能/产品形态。
2. **检索知识库**：
   ```bash
   cd /Users/bangcle/.openclaw/workspace/L4-proprietary/components/product-kb && python3 -m product_kb.cli query "关键词"
   ```
   - 中文 FTS 需完整词组匹配（如"鸿蒙NEXT安全键盘"），单字/短词会查不到，此时换长关键词或拆词。
   - 文档命中后，**必须打开原始 docx/pptx 读取对应章节全文**再回答，禁止只凭检索摘要下结论（白皮书正文才有功能细节）。
3. **核对平台/版本/形态**：功能是否双平台（Android/iOS）、是否受控/报备销售、检测点归属模块。
4. **给出可追溯结论**：每个结论附来源文档名与章节；无依据的推断明确标注"需产品线确认"。

## 三、跨产品组合方案流程

1. 按客户行业/场景（金融/政企/运营商/IoT/互联网）梳理需求点。
2. 用 `query` 检索每个需求点对应产品，注意区分：
   - **软件/硬件/服务** 形态；**正常/受控/报备** 销售状态
   - 客户端 SDK 型 vs 平台服务端型（如"运行环境可信检测SDK"回调APP vs "移动应用安全监测平台"服务端处置——交互模式不同，务必查清）
3. 组合输出：产品清单 + 各自核心能力 + 组合逻辑 + 引用文档。

## 四、知识库检准与维护（核心）

知识库记录可能偏离源文件/事实，周期或按需执行检准。

### 1. 运行检准脚本
```bash
python3 /Users/bangcle/.openclaw/workspace/L4-proprietary/skills/product-manager-expert/scripts/audit_kb.py \
  --db /Users/bangcle/.openclaw/workspace/L4-proprietary/components/product-kb/data/product_kb.db \
  --json <输出>.json --report <输出>.md
```
退出码：0=无异常 / 1=有警告 / 2=有错误。报告含：FK 完整性、唯一性、枚举合法性、源文件存在性、覆盖度、价格健康、embedding 状态。

### 2. 检准结论分级处置

| 级别 | 处置 |
|---|---|
| 🔴 error | 必须修：源文件缺失→核实路径/补录；孤儿引用→清理或重建 |
| 🟡 warn | 按业务判断：doc_type 归类→按文件名强规则重分类；无文档产品→服务类维保/定制/第三方占位桶无独立文档属正常（第三方桶自动剔除），在报告标注；embedding 为空→建议重建索引 |
| 🔵 info | 记录说明：kb_relation 空、version 缺失等 |

### 3. embedding 重建（语义检索恢复）

检准报 `EMBED: doc_chunk.embedding 全为空` 时执行（本地 GGUF 模型，无需外部 API）：

```bash
# 1. 启动本地 embedding 服务（llama.cpp b10534, embeddinggemma-300m, 注意 ubatch 必须≥2048）
/Users/bangcle/.openclaw/tools/llama.cpp/b10534/darwin-arm64/llama-server \
  -m ~/.node-llama-cpp/models/hf_ggml-org_embeddinggemma-300m-qat-Q8_0.gguf \
  --embedding --port 8123 --ctx-size 2048 --host 127.0.0.1 --batch-size 2048 --ubatch-size 2048

# 2. 全量重建（float64 bytes 写入，对齐 search.py 的 np.frombuffer dtype）
python3 scripts/rebuild_embeddings.py --db <product-kb>/data/product_kb.db --batch 2
```

要点：
- **ubatch 必须 ≥ 2048**：默认 512 时单条 chunk（>512 token）会 500 失败。
- 实测吞吐 ~37 chunk/s（M 系芯片），6195 chunks 约 3 分钟。
- 重建前先备份 DB；脚本幂等（只处理 embedding IS NULL 的行）。

### 3. 已建立的校准规则（2026-10-29）

- **doc_type 合法枚举**：`white_paper / sales_note / func_list / ppt / tech_white_paper / manual / faq / version_note / other`（`version_note` 为实际使用补充，`pdf` 不是角色类型，`user_manual` 并入 `manual`）。
- **pdf 文件重分类**（按文件名）：含"使用手册/操作手册/部署/安装/接入"→`manual`；含"FAQ/常见问题"→`faq`；含"产品介绍/主打胶片/宣传页/彩页/简介/培训"→`sales_note`；软著/专利/检测报告/销售许可证/兼容认证证书→`other`。
- **第三方占位桶识别**（2026-10-29 新增）：产品名含"非梆梆"的 3 个记账桶（id 191-193：其他（非梆梆产品/定制化开发/服务））用于合同标的归类第三方硬件/外购软件/转包服务，`status` 统一为 **`第三方产品/服务`**（非"未知"）。该状态为合法枚举，检准自动豁免其 summary/文档/目录价检查；导入器 `io.py` 对名称含"非梆梆"者自动写入此状态。
- 数据库修改前**先备份**：`cp data/product_kb.db data/product_kb.db.bak-<日期>`。

## 五、常见坑

- **检索摘要≠答案**：白皮书目录页/章节标题会先命中，必须读正文章节。
- **产品线目录名与价格表族名差异大**时文档匹配率低：在 `product.aliases` 加别名后重扫。
- **doc_type='pdf' 是扫描器兜底**（按扩展名归类），不是文档角色，检准时按上表重分类。
- **embedding 为空**：`build-index` 时 `get_embedding` 不可用则纯 FTS 检索，语义检索需在 OpenClaw 运行环境执行。
- 修改 `openclaw.json` 的 skills 配置需走配置流程，新增技能落 L4 分层目录即可被 `extraDirs` 加载。

## 验收

- 产品咨询：结论有文档出处、区分平台/版本/销售状态、无依据处明确标注。
- 检准：脚本可复跑、报告含分级问题清单、修复项可追溯（备份+变更记录）。
- 统一入口：任何 Bangcle **产品相关**需求能按 §一 路由表定位；非产品需求按 §边界外 正确分流、不越界代办。

## 应答规范（ADR-035 强制引用）

> 本技能输出口径必须遵循以下应答契约（ADR-035 P1/P2 纵切层）：
>
> 1. **P1 通用应答契约**（数据源优先级与时效、证据三档【已验证】/【推断】/【缺失】、降级显式声明、落盘与副作用、客户实体归一、风险定级通用规则）：
>    `/Users/bangcle/.openclaw/workspace/L2-infra/prompts/answer-spec-base.md`
> 2. **P2 域应答契约**（固定输出维度 + 域风险定级矩阵）：
>    `/Users/bangcle/.openclaw/workspace/L4-proprietary/prompts/product-answer-spec.md`
>
> 契约优先于本 SKILL 内任何自定义口径；两者冲突时以契约为准，并提请维护对应 spec。

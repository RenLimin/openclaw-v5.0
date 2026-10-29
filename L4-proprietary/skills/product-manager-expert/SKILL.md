---
name: product-manager-expert
description: "Bangcle 产品管理专家 — 产品咨询解答、跨产品组合方案、产品知识库检准与维护。查询产品/方案时用 product-kb；检准知识库记录、校准产品文档归类、发现数据异常时用本技能。"
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

面向 Bangcle 产品体系（8 产品线 / 37 分类 / 193 产品 / 385 SKU / 900+ 文档）的产品专家角色：
**精准解答产品咨询、跨产品组合方案、知识库记录检准与维护**。

## 定位分工

| 技能 | 职责 |
|---|---|
| `product-kb` | 查询/导入/索引等**数据操作**（查产品、查文档、合同匹配、导入价格表） |
| `product-manager-expert`（本技能） | **专家决策**：产品咨询解答、组合方案、知识库记录检准与修复 |

## 一、产品咨询解答流程

1. **复述需求**：1-2 句复述客户咨询，明确要查的监测点/功能/产品形态。
2. **检索知识库**：
   ```bash
   cd /Users/bangcle/.openclaw/workspace/L4-proprietary/components/product-kb && python3 -m product_kb.cli query "关键词"
   ```
   - 中文 FTS 需完整词组匹配（如"鸿蒙NEXT安全键盘"），单字/短词会查不到，此时换长关键词或拆词。
   - 文档命中后，**必须打开原始 docx/pptx 读取对应章节全文**再回答，禁止只凭检索摘要下结论（白皮书正文才有功能细节）。
3. **核对平台/版本/形态**：功能是否双平台（Android/iOS）、是否受控/报备销售、检测点归属模块。
4. **给出可追溯结论**：每个结论附来源文档名与章节；无依据的推断明确标注"需产品线确认"。

## 二、跨产品组合方案流程

1. 按客户行业/场景（金融/政企/运营商/IoT/互联网）梳理需求点。
2. 用 `query` 检索每个需求点对应产品，注意区分：
   - **软件/硬件/服务** 形态；**正常/受控/报备** 销售状态
   - 客户端 SDK 型 vs 平台服务端型（如"运行环境可信检测SDK"回调APP vs "移动应用安全监测平台"服务端处置——交互模式不同，务必查清）
3. 组合输出：产品清单 + 各自核心能力 + 组合逻辑 + 引用文档。

## 三、知识库检准与维护（核心）

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
| 🟡 warn | 按业务判断：doc_type 归类→按文件名强规则重分类；无文档产品→服务类维保/定制无独立文档属正常，在报告标注；embedding 为空→建议重建索引 |
| 🔵 info | 记录说明：kb_relation 空、version 缺失等 |

### 3. 已建立的校准规则（2026-10-29）

- **doc_type 合法枚举**：`white_paper / sales_note / func_list / ppt / tech_white_paper / manual / faq / version_note / other`（`version_note` 为实际使用补充，`pdf` 不是角色类型，`user_manual` 并入 `manual`）。
- **pdf 文件重分类**（按文件名）：含"使用手册/操作手册/部署/安装/接入"→`manual`；含"FAQ/常见问题"→`faq`；含"产品介绍/主打胶片/宣传页/彩页/简介/培训"→`sales_note`；软著/专利/检测报告/销售许可证/兼容认证证书→`other`。
- 数据库修改前**先备份**：`cp data/product_kb.db data/product_kb.db.bak-<日期>`。

## 四、常见坑

- **检索摘要≠答案**：白皮书目录页/章节标题会先命中，必须读正文章节。
- **产品线目录名与价格表族名差异大**时文档匹配率低：在 `product.aliases` 加别名后重扫。
- **doc_type='pdf' 是扫描器兜底**（按扩展名归类），不是文档角色，检准时按上表重分类。
- **embedding 为空**：`build-index` 时 `get_embedding` 不可用则纯 FTS 检索，语义检索需在 OpenClaw 运行环境执行。
- 修改 `openclaw.json` 的 skills 配置需走配置流程，新增技能落 L4 分层目录即可被 `extraDirs` 加载。

## 验收

- 产品咨询：结论有文档出处、区分平台/版本/销售状态、无依据处明确标注。
- 检准：脚本可复跑、报告含分级问题清单、修复项可追溯（备份+变更记录）。

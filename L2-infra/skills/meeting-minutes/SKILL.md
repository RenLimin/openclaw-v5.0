---
name: meeting-minutes
description: 把会议录音转写/速记提炼为结构化、可溯源、术语统一的正式纪要，支持会后材料合并与多格式交付。触发：整理会议纪要、会议记录、校订智能纪要、纪要修订。
metadata:
  version: "2.0"
  updated: "2026-11-06"
  layer: "L2-infra"
  input:
    kinds: [transcript, speed_notes, post_meeting_text]
    max_chars: 200000
  boundaries:
    - "不做实时转写（仅处理已有文本）"
    - "不臆造未讨论的结论/职务/数据"
    - "对外发送前必须经用户确认"
---

# Meeting Minutes — 会议纪要整理

> v2.0 | 2026-11-06 | L2 通用基础能力

## 触发条件

收到以下输入并要求整理/校订/修订时触发：
- 录音转写、智能纪要（飞书/腾讯/讯飞）、速记稿
- 会后追加的结论性文字，要求合并进既有纪要
- 调整篇幅（更精简）、统一术语、导出格式

## 核心原则

1. **保真**：只提炼已说出的信息，不臆测；有分歧写分歧，不强行统一。
2. **可溯源**：每条决策/待办/结论挂原文逐字引用 + 时间戳（`quote` + `timestamp`）。
3. **术语一致**：全文同一概念只用一个名称（用户指定优先）。
4. **结论可执行**：每条待办含唯一 Owner + 具体日期 + 状态。
5. **交付即可用**：用户能直接打开、看懂、转发。

## 标准工作流

### 1. 接收与通读

- 完整读原文，标记：决策、问题、根因、数据、承诺、争议、待办。
- 识别参会人及身份/职务（职务不明不杜撰，用"（职务待确认）"或不列）。
- 用户同时给了会后确认文字时，**以会后确认为准**（版本号、交付时间、排期常在此处才明确）。
- **完成判据**：原文无未读段落，参会人列表已列全。

### 2. 说话人归因核查

- 检测转写是否为单说话人、标签是否异常（如 `SPEAKER_01` 未映射真名）。
- 异常时先让用户确认映射，再继续抽取——避免待办挂错人。
- **完成判据**：每个说话人有明确身份，或用户已确认。

### 3. 抽取先于行文（结构化 JSON）

先产出结构化抽取结果（不直接写正文），字段契约见 `{baseDir}/references/field-contract.md`：

```json
{
  "chapters": [{"title": "...", "description": "...", "timestamp_start": 0.0, "timestamp_end": 120.5}],
  "decisions": [{"content": "...", "reason": "...", "status": "已定|待议|分歧|搁置", "approver": "...", "quote": "原文逐字", "timestamp": 45.2}],
  "action_items": [{"task": "动词开头的任务", "owner": "唯一人名", "due": "YYYY-MM-DD", "status": "待启动|进行中|阻塞|已完成", "quote": "原文逐字", "timestamp": 78.3}],
  "open_questions": [{"content": "...", "owner": "...", "expected_answer_date": "YYYY-MM-DD", "quote": "...", "timestamp": 90.0}],
  "risks": [{"content": "...", "impact": "...", "quote": "...", "timestamp": 100.0}]
}
```

- **quote 必须是转写原文的逐字子串**，用于后续脚本校验。
- **timestamp** 为秒级时间点（转写格式 `HH:MM:SS` 时转为秒）。
- 长转写（>2 万字）按说话人轮次或话题分块抽取，再按 owner+任务语义去重合并。
- **完成判据**：JSON 可解析，每条含 quote+timestamp。

### 4. 澄清口语歧义

转写常见陷阱，必须主动消解：
- **指代不清**："这个/那个/他们" → 还原成具体对象。
- **同名异义 / 异名同义**：如"主动调用接口" vs "主动发数据"、"保护模式" vs "安全模式" → 区分概念，统一命名。
- **ASR 识别错误**：人名、专有名词、数字（如"5.1.3""2%""十余万"）→ 结合上下文校订，无法确定的标注。
- **因果倒置/碎片化**：把散落在多段对话里的同一机制，重组成完整叙述或链路。
- **完成判据**：全文无未消解的关键指代。

### 5. 选篇幅档位并渲染

| 档位 | 适用 | 模板 |
|---|---|---|
| **精简版**（默认） | 内部快速对齐 | `{baseDir}/assets/template-concise.md` |
| 标准版 | 正式归档、多方同步 | `{baseDir}/assets/template-standard.md` |

用户说"更精简"→ 直接降档，删展开、合并同类表、只留结论性信息。

渲染规则：
- 摘要放最前（TL;DR ≤3 条）。
- 正文按议程议题分组，禁止按发言时间流水账。
- 三类信息强制分区：事实 / 决策 / 行动；另设"开放问题与风险"区，悬而未决不得写成决策。
- 平台/方案对比、排期一律表格化。
- 每条待办挂 `[mm:ss]` 锚点（从转写时间戳换算）。
- **完成判据**：模板所有必填模块已填，无空占位。

### 6. 术语统一（用户显式要求时强制）

- 用户指定用词（如统一"安全模式"）→ 全文替换。
- 运行校验脚本，必须零残留：
  ```bash
  python3 "{baseDir}/scripts/verify_minutes.py" --file minutes.md --transcript transcript.txt --deprecated "保护模式"
  ```
- **完成判据**：脚本退出码 0，无 deprecated 残留。

### 7. 校验与交付

运行完整校验：
```bash
python3 "{baseDir}/scripts/verify_minutes.py" \
  --file minutes.md \
  --transcript transcript.txt \
  --deprecated "旧词1,旧词2"
```

校验内容：引用可在转写中逐字匹配、待办四要素齐全、废弃词残留=0、UTF-8 合法。

交付：
```bash
bash "{baseDir}/scripts/deliver.sh" minutes.md --html --copy-to ~/Downloads
```

自动完成：UTF-8 BOM、复制到可达目录、生成 HTML 兜底。

- **完成判据**：脚本退出码 0；`~/Downloads` 有副本；HTML 可打开。

### 8. 自检清单

交付前逐条过 `{baseDir}/references/checklist.md`。

## 输出位置

- 工作目录：`meeting-minutes/YYYY-MM-DD-<主题>.md`
- 对用户可达副本：`~/Downloads/`（必要时 `~/Desktop/`）
- 多格式：同名 `.md` / `.html` / `.pdf`

## 禁止事项

- ❌ 杜撰未发生的结论、职务、数据
- ❌ 把有争议的方案写成已定论
- ❌ 只留沙箱路径、不给可打开副本
- ❌ 未确认就对外发送纪要
- ❌ 跳过说话人归因核查直接抽待办

# 字段契约（结构化抽取 JSON）

先抽取为 JSON，再渲染 Markdown。每个抽取物必须携带 `quote`（原文逐字子串）+ `timestamp`（秒），否则视为不可溯源，禁止写入正文。

## 顶层结构

```json
{
  "meta": {
    "title": "会议主题",
    "date": "YYYY-MM-DD",
    "start_time": "HH:MM",
    "end_time": "HH:MM",
    "duration_min": 33,
    "host": "主持人",
    "recorder": "记录人",
    "attendees": [
      {"name": "姓名", "org": "公司/部门", "role": "职务（可选，不明不填）", "status": "attended|absent"}
    ]
  },
  "summary": ["≤3 条 TL;DR"],
  "chapters": [
    {"title": "3–8 词议题", "description": "一句话", "timestamp_start": 0.0, "timestamp_end": 120.5}
  ],
  "decisions": [
    {
      "content": "决策陈述（一句话）",
      "reason": "理由/依据（含数据）",
      "alternatives": ["备选方案1", "备选方案2（含 do nothing）"],
      "status": "已定|待议|分歧|搁置",
      "approver": "唯一拍板人（DACI 的 Approver）",
      "driver": "推动人（DACI 的 Driver，可选）",
      "contributors": ["有建议权的人"],
      "informed": ["决后告知的人"],
      "expected_outcome": "预期可衡量结果（可选）",
      "review_date": "YYYY-MM-DD（可选）",
      "quote": "原文逐字",
      "timestamp": 45.2
    }
  ],
  "action_items": [
    {
      "task": "动词开头、可验证的任务描述",
      "owner": "唯一人名（禁用'团队/大家'）",
      "due": "YYYY-MM-DD（禁用'尽快/下周'）",
      "priority": "high|medium|low",
      "status": "待启动|进行中|阻塞|已完成",
      "quote": "原文逐字",
      "timestamp": 78.3
    }
  ],
  "open_questions": [
    {
      "content": "悬而未决的问题",
      "owner": "跟进人",
      "expected_answer_date": "YYYY-MM-DD",
      "quote": "原文逐字",
      "timestamp": 90.0
    }
  ],
  "risks": [
    {
      "content": "风险描述",
      "impact": "影响",
      "mitigation": "缓解措施（可选）",
      "quote": "原文逐字",
      "timestamp": 100.0
    }
  ],
  "key_terms": [
    {"standard": "标准术语", "deprecated": ["废弃写法1", "废弃写法2"]}
  ]
}
```

## 规则

1. **quote 逐字**：必须是转写原文的连续子串（允许省略号截断），不得改写。
2. **timestamp 秒级**：转写为 `HH:MM:SS` 时换算为秒（如 `17:08:36` → `61716`）；正文中显示为 `[mm:ss]` 锚点。
3. **owner 唯一**：一个条目出现多个 owner 时拆成多条。
4. **status 枚举**：决策用 `已定|待议|分歧|搁置`；待办用 `待启动|进行中|阻塞|已完成`。
5. **允许"未讨论"**：某类信息确实没有时输出空数组，不编造。
6. **术语表**：`key_terms` 记录全文统一术语与废弃写法，渲染前用 `scripts/verify_minutes.py --deprecated` 校验。

## 时间戳换算

```
HH:MM:SS → 秒 = HH*3600 + MM*60 + SS
秒 → [mm:ss] = f"{int(s)//60:02d}:{int(s)%60:02d}"
```

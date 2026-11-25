# VERIFICATION — customer-rectification-report v1.0

- 验收日期：2026-11-24
- 依据：DESIGN.md §6/§7、references/authoring-standard.md V0.1（Limin 2026-11-24 审批）
- 结论：**PASS**（机器门禁全绿；真实成品回归通过；突变测试全部正确拦截）

## 1. 资产清单
- `SKILL.md` 入口契约（When/Hard Rules/Workflow/门禁/验证）
- `DESIGN.md` 设计文档（问题、目标/非目标、业界框架 ISO9001/8D/CAPA、SMART/RACI、ITIL、release management、取舍、数据模型）
- `references/authoring-standard.md` 编制要求 V0.1（11 节）
- `assets/report-skeleton.md` report.yaml 骨架；`assets/style-spec.json` 字体/字号/禁词/正则枚举
- `scripts/build_docx.py` 结构化渲染（内部/对外双版）
- `scripts/validate_report.py` fail-closed 门禁 G1–G9（G10 人眼）
- `tests/test_validate_report.py` + `tests/fixtures/report.sample.yaml`（脱敏自包含）

## 2. 真实成品回归（基准：城商行联盟 V1.7）
命令：`validate_report.py V1.7.docx --n 20 --pdf v17.pdf`
- 问题条数=20，文本 run=477，**违例=0 警告=0，RESULT: PASS（exit 0）**
- PDF：10 页、越界块 0；V1.7 关键页（两张宽表/附件2/附件3/附件4/落款）已经人眼逐页复核（2026-11-23）。

## 3. pytest 回归（脱敏 fixture，无真实人名/合同号/ONES）
`python3 -m pytest tests/test_validate_report.py -q` → **8 passed**
- test_internal_golden_passes：渲染内部版 → PASS
- test_external_passes_and_strips_ones：对外版 ONES URL/任务号/ONES 列清零 → PASS
- test_external_blocks_internal_docx：内部版加 --external 被 BLOCK
- 5 类突变全 BLOCK：缺验收标准 / 行动日期 11-26 与明细不一致 / 附件2 含合同号条款 / 时限"尽快"非法 / "待指定"禁词

## 4. 突变测试补充（对真实 V1.7 手工注入）
M1 缺验收标准 / M2 行动日期 11-26 / M3 附件2 XSZS+第5.5条 / M4 时限"尽快" / M5 待指定 / M6 内部冒充对外（命中 14 处 ONES）——**6/6 全部 BLOCK**。

## 5. 门禁覆盖对照
| 门禁 | 实现 | 验证 |
|---|---|---|
| G1 越界/落款 | PDF blocks + 人眼 | V1.7 越界=0 |
| G2 N条+四必填+时限白名单+禁词 | validate | M1/M4/M5 拦截 |
| G3 行动-明细日期一致 | 边界推导 | M2 拦截（抓住 11-26 事故） |
| G4 附件2 三类+去合同来源 | validate | M3 拦截 |
| G5 字体字号显式 | run 级 | V1.7 477 run 全合规 |
| G6 称谓/全称 | validate | V1.7 PASS |
| G7 修订残留 | w:ins/del/pPrChange | V1.7 接受修订后为 0 |
| G8 对外脱敏 | --external | M6 拦截 |
| G9 页眉/页脚/页码 | header/footer 部件 | PASS |
| G10 关键页人眼 | 流程要求 | V1.7 已执行存档 |

## 6. 已知边界
- build_docx.py 内置渲染不带官方模板品牌页眉（页脚标语+页码已含）；生产正式件以官方 Word 模板为底，页眉 logo 在套用模板时具备，validate G9 对 logo 仅 WARN 不阻断。
- G1 PDF 越界依赖 Word/pymupdf 导出；docx 静态门禁可离线全跑。
- G3 采用"行动日期必须是明细窗口边界"强规则；若未来行动表含与整改明细无关的独立行动，需在 yaml 用 issue_refs 标注范围（后续增强）。

## 7. 生命周期
已登 capability-registry（skill-customer-rectification-report），coverage=100%，资产清单已重生成。

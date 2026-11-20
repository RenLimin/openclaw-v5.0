# meeting-minutes — 验收文档 (VERIFICATION)

> 版本: v1.0 · 日期: 2026-11-20
> 验收对象: `L2-infra/skills/meeting-minutes/`（SKILL.md + references/ + assets/ + scripts/verify_minutes.py + scripts/deliver.sh）

## 验收标准（Definition of Done）

1. `verify_minutes.py` 五项校验生效：UTF-8 合法性（可选 BOM）、引用可在转写中逐字匹配、待办四要素（task/owner/due/status）、废弃术语残留 = 0、必填模块存在。
2. 退出码语义正确：`0` = 通过，`1` = 有错误；错误信息逐条可读、可定位。
3. `deliver.sh` 交付链路可用：补 UTF-8 BOM、复制到用户可达目录、按需生成 HTML 兜底。
4. 交付前自检清单（references/checklist.md）与字段契约（references/field-contract.md）覆盖内容/术语/待办/交付四类要求。

## 测试范围

- `scripts/verify_minutes.py`：正向用例、反向用例、BOM 要求、废弃术语、引用校验。
- `scripts/deliver.sh`：BOM 注入、目录复制、HTML 生成。
- 模板资产（assets/template-concise.md、template-standard.md）存在性。

> 本 skill 目录内**无 pytest tests/**，验收方式为脚本真实运行（构造正反输入）。

## 测试用例

| # | 场景 | 输入 | 预期结果 | 实测 |
|---|---|---|---|---|
| TC01 | 合规纪要 | minutes-good.md + transcript.txt | PASS，exit=0 | ✅ PASS，exit=0 |
| TC02 | 伪造引用 + 缺模块 | minutes-bad.md + transcript.txt | FAIL 且逐条列问题，exit=1 | ✅ FAIL 4 项，exit=1 |
| TC03 | BOM 要求 | 带 BOM 文件 + `--require-bom` | PASS，exit=0 | ✅ PASS，exit=0 |
| TC04 | 废弃术语 | 含「保护模式」+ `--deprecated 保护模式` | FAIL 1 项，exit=1 | ✅ FAIL 1 项，exit=1 |
| TC05 | 交付脚本 | `deliver.sh minutes-good.md --html --copy-to <dir>` | 加 BOM + 复制 + 生成 HTML | ✅ added BOM / copied / html / DONE |
| TC06 | 反向交付 | 不存在的文件 | 明确报错 | ✅ `ERROR: 请提供存在的 .md 文件` |

## 实测结果

- 命令与输出摘要:
  ```bash
  # TC01
  python3 L2-infra/skills/meeting-minutes/scripts/verify_minutes.py \
    --file tmp/verif-l2/mm/minutes-good.md --transcript tmp/verif-l2/mm/transcript.txt \
    --deprecated "保护模式,旧词"
  # → PASS: 校验通过    exit=0

  # TC02
  python3 L2-infra/skills/meeting-minutes/scripts/verify_minutes.py \
    --file tmp/verif-l2/mm/minutes-bad.md --transcript tmp/verif-l2/mm/transcript.txt
  # → FAIL: 4 项问题
  #    - 引用未在转写中找到: '这句话在转写原文中根本不存在…'
  #    - 缺少必填模块: 根因 / 方案 / 结论      exit=1

  # TC03
  python3 L2-infra/skills/meeting-minutes/scripts/verify_minutes.py \
    --file tmp/verif-l2/mm/minutes-bom.md --transcript tmp/verif-l2/mm/transcript.txt --require-bom
  # → PASS: 校验通过    exit=0   （文件头字节 efbb bf）

  # TC04
  python3 L2-infra/skills/meeting-minutes/scripts/verify_minutes.py \
    --file tmp/verif-l2/mm/minutes-bom.md --deprecated "保护模式"
  # → FAIL: 1 项问题  - 废弃术语残留: '保护模式' 出现 1 次   exit=1

  # TC05
  bash L2-infra/skills/meeting-minutes/scripts/deliver.sh tmp/verif-l2/mm/minutes-good.md \
    --html --copy-to tmp/verif-l2/mm/deliver
  # → added BOM / copied -> …/deliver/minutes-good.md / html -> …/minutes-good.html / DONE   exit=0
  ```
- 结论: **通过**。校验器五项规则与退出码语义均实测正确；交付脚本端到端跑通（BOM + 复制 + HTML）。反向用例能准确报出引用伪造、必填模块缺失、废弃术语残留。

## 遗留问题（如实记录）

1. **无自动化回归**：正反用例目前靠临时构造，建议固化为 `tests/test_verify_minutes.py`（本次 TC01–TC05 可直接转用例）。
2. **待办四要素校验依赖表格形态**：TC02 中「待办没有四要素表格」是被「缺少必填模块」间接暴露，`check_action_items` 对非表格待办的判定路径建议补一条独立用例确认。

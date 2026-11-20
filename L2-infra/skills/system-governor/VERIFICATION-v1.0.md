# system-governor — 验收文档 (VERIFICATION)

> 版本: v1.0 · 日期: 2026-11-20
> 验收对象: `L2-infra/skills/system-governor/`（SKILL.md，薄编排入口）
> 实际实现: `L2-infra/components/system-governor/`（scripts/governor.py + src/）

## 验收标准（Definition of Done）

1. 统一入口可用：`run`（默认 dry-run 零写）/ `run --json` / `run --only <lane>` / `report` / `audit`（含 `--only/--apply/--json`）。
2. Lane 路由正确：A 问题自愈 / B 资产健康 / C 文件治理 / D 任务盘点，各自委托既有组件，不重复实现。
3. 分级闸门生效：L0/L1 在 `--apply` 下可执行，L2/L3 即使 `--apply` 也只记 `needs-human`，不执行。
4. 账本落盘：`memory/governor-latest.json` / `governor-audit-latest.json`。
5. 组件回归套件全绿。
6. 默认 dry-run 零写操作（安全铁律）。

## 测试范围

- 组件 pytest 全量（`L2-infra/components/system-governor/tests`）。
- `governor.py run --json` 真实运行（dry-run）。
- `governor.py report` / `report --ledger <path>`。
- `governor.py audit --json`（默认零写）。

## 测试用例

| # | 场景 | 输入 | 预期结果 | 实测 |
|---|---|---|---|---|
| TC01 | 组件回归 | `pytest tests -q`（组件目录） | 全绿 | ✅ 50 passed in 12.05s |
| TC02 | dry-run 盘点 | `governor.py run --json` | apply=false，有 summary/lanes | ✅ apply=false；open 192 / ok 15 / planned 0 |
| TC03 | 账本读取（无参） | `governor.py report` | 读默认账本 | ❌ TypeError 崩溃 |
| TC04 | 账本读取（显式） | `governor.py report --ledger memory/governor-latest.json` | 输出 JSON | ✅ 输出正常 |
| TC05 | 资产审计 | `governor.py audit --json` | 默认零写，含 tier/suggestion | ✅ total 1 / needs-human 1 / L2 |

## 实测结果

- 命令与输出摘要:
  ```bash
  # TC01
  cd L2-infra/components/system-governor && python3 -m pytest tests -q -p no:cacheprovider
  # → 50 passed in 12.05s

  # TC02（dry-run，零写）
  python3 L2-infra/components/system-governor/scripts/governor.py run --json
  # → {"apply": false, "summary": {"auto_fixed":0,"needs_human":0,"planned":0,
  #     "open":192,"ok":15,"total_unique":207,"total_raw":207}, "lanes": {A/B/C…}}
  #   lane B elapsed 25.53s / scanned 15 / warnings 1；账本 memory/governor-latest.json（81KB）

  # TC03
  python3 L2-infra/components/system-governor/scripts/governor.py report
  # → TypeError: argument should be a str or an os.PathLike object … not 'NoneType'
  #   （cmd_report: `path = Path(args.ledger)`，而 report 子命令 --ledger 默认 None 且未回退默认账本路径）

  # TC04
  python3 L2-infra/components/system-governor/scripts/governor.py report --ledger memory/governor-latest.json
  # → 正常打印账本 JSON

  # TC05（默认零写）
  python3 L2-infra/components/system-governor/scripts/governor.py audit --json
  # → summary {total 1, pending 0, done 0, needs-human 1, skipped 0, approved 0}
  #   regression.remaining_count = 1（P4 未跟踪/未提交超阈值）
  #   tiers Counter({'L2':1}) / status Counter({'needs-human':1})
  ```
- 结论: **部分通过**。组件回归 50/50 全绿；dry-run 盘点与资产审计（零写、L2 项正确落入 needs-human）达标。但 **`governor.py report`（SKILL.md「核心命令」第 5 条）无参调用直接崩溃**，属真实缺陷。

## 遗留问题（如实记录）

1. **`report` 子命令无参崩溃（新发现，真实缺陷）**：`report` 的 `--ledger` 默认 `None`，`cmd_report` 直接 `Path(args.ledger)` → `TypeError`。SKILL.md 明确写 `governor.py report` 为「查看最近一次账本」，当前不可用。修复方向：`--ledger` 缺省时回退到 `memory/governor-latest.json`。**本次未修改任何代码**，仅记录。
2. **dry-run 结果含大量 open 项**：`run --json` 报 `open 192`，其中 lane B 15 项 warnings、lane A/C 各 1 项。属真实环境状态，非本 skill 缺陷；但说明巡检口径需与「系统当前健康度」联动解读。
3. **审计回归项与并行会话在途相关**：`audit` 的 `P4 未跟踪/未提交` 命中 6 未跟踪 / 15 未提交，与本次验收同时段其他会话的在途改动重叠（`git status` 中 L4-proprietary 多项 MM）。该结论只在无并行写入时才有证明力，需在稳定窗口复跑确认。
4. **账本时间戳口径**：`run --json` 输出 `timestamp` 为 UTC（`2026-11-20T05:30:18+00:00`），与本地 +08:00 混用，建议统一口径。

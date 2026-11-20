# ones-browser-export — 验收文档 (VERIFICATION)
> 版本: v1.0 · 日期: 2026-11-20

> 范围说明：本 skill 提供 ONES 数据获取（浏览器导出 + GraphQL + OA 待办桥）。
> 真实环境依赖 Chrome 已登录 ONES、OA 会话、CDP 端口，**自动化测试缺失**，
> 本次以「脚本可加载 + CLI 参数可解析 + 依赖探测符合 fail-closed 预期」为实测。

## 验收标准（Definition of Done）

| # | 标准 | 判据 |
|---|---|---|
| 1 | 脚本可加载 | `oa_workflow_ones.py` / `oa_todo_dist.py` import 无异常 |
| 2 | CLI 契约稳定 | `--help` 退出码 0，参数与 SKILL.md 用法一致 |
| 3 | 无依赖时 fail-closed | ONES 不可用 → `ones_available()=False`，不伪造数据 |
| 4 | 会话过期显式报错 | OA 过期 → exit 2，不静默 |
| 5 | 字段映射文档齐备 | `references/oa-workflow-fields.md` 覆盖 8 个 workflowid |
| 6 | 不重复造轮子 | 权威能力名 `ones-export`/`ones-auth`/`oa-workflow-ones` 唯一 |

## 测试范围

- skill 自身：`scripts/oa_workflow_ones.py`（394 行，v2）、`scripts/oa_todo_dist.py`（163 行）、`references/oa-workflow-fields.md`。
- **无 `tests/` 目录**。

## 测试用例

| # | 场景 | 输入 | 预期结果 | 实测 |
|---|---|---|---|---|
| 1 | CLI 契约 A | `oa_workflow_ones.py --help` | usage 列出 `--capture/--code/--raw-dir/--pm/--final-customer` | ✅ exit 0 |
| 2 | CLI 契约 B | `oa_todo_dist.py --help` | usage 列出 `--save/--max-pages/--out` | ✅ exit 0 |
| 3 | 脚本加载 | import 两个模块 | 无异常 | ✅ 无异常 |
| 4 | 依赖探测 | `ones_available()` | 无 Chrome/ONES 上下文时 False（fail-closed） | ✅ `ones_available=False` |
| 5 | 状态文件 | `OA_STATE.exists()` | 返回布尔 | ✅ True（存在性探测） |
| 6 | 自动化测试 | `pytest tests` | — | ⛔ **无自动化测试** |
| 7 | 真实导出 | 浏览器导出三视图 | 行数 16600/5030/362 量级 | ⛔ 需 Chrome 已登录 ONES，本次未执行（环境性） |

## 实测结果

- 命令: `PYTHONDONTWRITEBYTECODE=1 python3 scripts/oa_workflow_ones.py --help`
- 输出摘要: usage 正常，含 `--capture/--code/--raw-dir/--pm/--final-customer` 与位置参数 `rids`；exit 0。
- 命令: `python3 -c "...exec_module...; print(m.ones_available(), m.OA_STATE.exists(), m.RAW_DEFAULT)"`
- 输出摘要: `ones_available= False`、`OA_STATE exists= True`、`RAW_DEFAULT=/Users/bangcle/.openclaw/workspace/tmp/oa-pif/raw`（锚点用 AGENTS.md 向上定位，符合「权威源/sandbox 层级不同」设计）。
- 结论: **部分通过（离线契约验证）**。脚本加载、CLI 契约、fail-closed 探测符合预期；真实浏览器/OA 链路未验。

## 可复现手动验证步骤（无自动化测试）

1. 确认 Chrome 已登录 ONES 且打开含 `ones.bangcle.com` 的标签页；
2. `python3 scripts/oa_workflow_ones.py --code SSXM-2026-0611-1491 --pm <姓名> --final-customer <客户>`，核对输出块字段与顺序（全角冒号、4 空格缩进）；
3. OA 桥：`python3 scripts/oa_workflow_ones.py --capture 886291`，再 `python3 scripts/oa_workflow_ones.py 886291`；
4. 待办双口径：`python3 scripts/oa_todo_dist.py --save`，核对树口径与列表口径差异并注明；
5. 负例：无 ONES 上下文时确认脚本报错而非输出伪造数据。

## 遗留与后续

- **该 skill 无自动化测试**，是本次验收最主要缺口；建议对纯函数（`_to_iso`/`norm_date`/`code_of`/`_spans`/`license_period`）补 pytest 单测，这些函数不依赖网络，可稳定回归。
- 真实链路依赖登录态，建议以「有会话时跑 + 无会话 skip 留证」方式纳入定期跑批。

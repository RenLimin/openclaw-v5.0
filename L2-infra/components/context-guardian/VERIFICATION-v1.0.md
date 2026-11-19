# context-guardian 修复版 — 验证报告 (VERIFICATION)

## 1. 单元测试（自动化）

```bash
cd /Users/bangcle/.openclaw/workspace/L2-infra/components/context-guardian
node --test tests/test_core.js
```

**结果（2026-11-18）：17/17 pass，0 fail。**

| 用例 | 覆盖 |
|---|---|
| G1 | QUERY + warn → 压缩 |
| G2 | EDIT + critical → 不压缩 |
| G3 | PRESERVE + critical → 不压缩 |
| G4 | low → 永不压缩 |
| G5 | 未知 + warn → 不压缩 |
| G6 | 未知 + critical → 压缩 |
| G7 | 开关关闭 → 全不压缩 |
| G8 | 阈值 warn=×2.5 / critical=base |
| G9 | 阈值 < host 持久化 cap（ctx=196608→32000，回归锁定） |
| G10 | middleTruncate 头尾保留 + 总长 ≤ 预算 |
| G11 | 短文本原样 |
| G12 | 数组压缩首尾 + 提示 |
| G13 | 对象结构保持 |
| G14 | 字符/token 提取与估算 |
| G15 | 消息 token 含 baseOverhead |
| G16 | 压力分级边界 |
| G17 | 三分类互斥 |

## 2. 运行时验证清单（2026-11-18 重启后新代际实测）

> 新代际起点：`2026-11-18T17:44:40`（gateway pid 变化，v6 loaded 重新打印）。
> 日志：`~/Library/Logs/openclaw/gateway.log`

| # | 检查 | 实测结果（2026-11-18） | 判定 |
|---|---|---|---|
| V1 | 版本/钩子 | `17:44:43 [ContextGuardian] v6 loaded: ... rewrite=tool_result_persist debug=false`（重启后打印 2 次） | ✅ |
| V2 | 无门禁 block | `grep "context-guardian.*blocked"` 重启后无匹配 | ✅ |
| V3 | 压力基线 | `session=... turn=1 totalTokens=26362 ratio=13.4% level=low`、`turn=2 ... ratio=16.6%`（重启前代际，钩子未被 block） | ✅ |
| V4 | 压缩生效 | `Persist-compressed` 5 次：`read 50,823→4,536(-91%)`、`read 19,069→4,536(-76%)`、`exec 3,366→1,835(-45%)`、`exec 25,828→1,836(-93%)`、`exec 6,207→1,835(-70%)` | ✅ |
| V5 | transcript 落库 | agent sqlite `transcript_events` seq=23163 正文 **1836** 字符，与 `exec 25,828→1,836(-93%)` 吻合；截断标记起始 offset=1165（head 0.4 / tail 0.2）；模型可见上下文出现截断标记 | ✅ 强验收 |
| V6 | EDIT 不被压缩 | 重启前后 `edit`/`write` 在 `pressure=critical` 下 20+ 次全未压缩；`web_search` 4,007 字符 critical 下未压缩 | ✅ |
| V7 | 更新免疫 | `openclaw plugins update context-guardian --dry-run` → `Skipping "context-guardian" (source: path).` | ✅ |

**补充证据（运行态审计）**：
- 活体 `debug=false`（重启后），重启前 `debug=true`（审计行 `tool=... pressure=...` 每工具一条）。
- `plugins list`：`version=6.0.0, enabled=true, origin=config, status=loaded`。
- `plugins doctor`：仅剩 1 条 hook-only **info**，无 error/warn/duplicate。
- 权威 registry 索引 `config_machine_state`：`packageName=openclaw-context-guardian-fix`、`packageVersion=6.0.0`、`installOwner=context-guardian`、`enabled=true`、`origin=config`。

## 3. 与 v5 的对照基线（修复前实测）

| 指标 | 修复前 | 说明 |
|---|---|---|
| `Micro-compacted` | 16 条 | 仅插件本地日志 |
| transcript 截断标记 | 0 | 改写从未生效 |
| `Large result after compaction` | 1900+ | 全部停在 ~8014（插件自身 8000 告警值） |
| `session=` 日志 | 0 | 授权缺失，钩子被 block |
| 阈值 warn | 12500 | 可触发（host cap=32000）；真正缺陷是钩子误用 |

## 4. 结论

修复前：压缩为 no-op（Observe 钩子 + 返回值不回读）。
修复后：压缩在 `tool_result_persist` 同步改写，host 将 `{ message }` 写入 transcript。

> V1–V7 实测输出已填入（见 §2）。
> 注：`debug` 开关经重启生效为 `false`（`plugins reload` 的 drain 会被发起者自身活跃 turn 阻塞，故走 `safe_restart.sh`）。

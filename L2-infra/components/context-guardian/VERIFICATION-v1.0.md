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

## 2. 运行时验证清单（需新代际）

| # | 检查 | 命令 | 期望 |
|---|---|---|---|
| V1 | 版本 | `grep "v6 loaded" ~/Library/Logs/openclaw/gateway.log \| tail -1` | 出现 `v6 loaded ... rewrite=tool_result_persist` |
| V2 | 无门禁 block | `grep "context-guardian.*blocked" ...` | 新代际无匹配 |
| V3 | 压力基线 | `grep "\[ContextGuardian\] session=" ...` | 出现 `session=...turn=... totalTokens=...` |
| V4 | 压缩生效 | `grep "Persist-compressed" ...` | 出现 `N → M chars` |
| V5 | transcript 落库 | `sessions_history` 读对应 toolResult | 文本含 `ContextGuardian` 标记且长度显著缩短 |
| V6 | EDIT 不被压缩 | 对 edit 结果检查 | 无截断标记 |
| V7 | 更新免疫 | `openclaw plugins update` 后 `plugins list` | 仍为 v6（workspace 路径） |

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

> 待补：V1–V7 的实测输出（reload 后填入）。

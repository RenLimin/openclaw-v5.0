# workspace-temp-cleanup — 测试方案 (VERIFICATION)

> INFRA-CLN-001 · v1.0 · 2026-10-29

## 1. 验收标准（映射 PRD §3）

| # | 标准 | 测试用例 |
|---|---|---|
| AC1 | 未标记路径不删 | T1 伪装文件 |
| AC2 | 只 trash 禁 rm | T2 代码扫描 + 删除可恢复 |
| AC3 | TTL 边界正确 | T3 当天/次日判定 |
| AC4 | registry 容错 | T4 缺字段/非法 JSON |
| AC5 | 子命令契约 | T5 dry-run/clean/list/verify 退出码 |
| AC6 | 幂等 | T6 连跑 3 次 |

## 2. 测试用例

| ID | 场景 | 构造 | 预期 |
|---|---|---|---|
| T1 | 未标记不删 | tmp 沙箱内放 `secret/important.txt`（非约定名、未登记） | 候选集不含它；clean 后仍存在 |
| T2 | 删除走 trash | 过期 `scratch/x.tmp` clean --yes | 文件移入废纸篓、原路径消失；代码 grep 无 `rmtree`/`os.remove`/` rm ` |
| T3 | TTL 边界 | created=今天-7天，ttl=7 | age=7 不删（7>7 false）；created=今天-8天则删 |
| T4a | 缺 kind | entry 无 kind/ttl | 用 intermediate 默认 7 天，不报错 |
| T4b | 非法 JSON | registry 写坏 | verify exit 3；clean abort exit 1 |
| T5a | dry-run | 有过期项 | exit 2，无文件被删 |
| T5b | clean 无 --yes | — | 拒绝执行 exit 1 |
| T5c | verify | 正常环境 | exit 0；删 trash 后 exit 3 |
| T6 | 幂等 | 同一过期集 clean 3 次 | 第 1 次删 N，第 2/3 次删 0，无报错 |
| T7 | 越界防护 | registry 写 `../../etc` | 拒绝（路径必须在 root 内） |
| T8 | 目录 mtime | 目录旧、内含今日新文件 | 以最新文件为准，不删 |

## 3. 黄金基准

固定沙箱（tmp 临时 root）：3 登记项 + 4 约定项 + 2 伪装项，造不同 mtime。
期望：候选 7（不含伪装），过期 3，clean 后 trash 3、保留 4+2。

## 4. 运行

```bash
cd L2-infra/components/workspace-temp-cleanup
python3 -m pytest tests/ -v
```

全部用真实文件系统 + 真实 `/usr/bin/trash`（运维安全组件，不用 mock 删除）。

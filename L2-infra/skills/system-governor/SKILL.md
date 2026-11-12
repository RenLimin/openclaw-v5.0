# system-governor — 系统治理工作流技能入口

> L2 基础设施层技能。**本体是工作流**（薄编排层），本 SKILL 只是它的调用入口与路由说明，
> 不包含检测/处置实现——检测与自愈全部委托既有组件（见下方路由表）。
>
> **触发场景**：定期巡检、故障排查、变更后验证、「跑一次系统全量检测」。

## 定位边界（重要）

- ✅ **它编排**：把既有的 scan_errors / full_audit / tempclean / archive / guardian 能力统一成
  一个入口 + L0–L3 分级闸门 + 统一账本。
- ❌ **它不检测**：检测逻辑在既有组件里，governor 只聚合回执、按 policy 分级。
- ❌ **它不重复建设**：凡已有能力（问题自愈、服务拉起、临时清理）一律委托，不新写。

## 核心命令

```bash
GOV="python3 L2-infra/components/system-governor/scripts/governor.py"

# 1) 只读盘点（默认，零写操作）——日常巡检用这个
$GOV run

# 2) 只跑某一 lane（如只看未完成任务）
$GOV run --only D

# 3) 程序消费（JSON 摘要）
$GOV run --json

# 4) 真实处置（L0/L1 写动作：归档移动 + trash 过期临时资产）
#    ⚠️ 默认 dry-run；只有确认清单后才加 --apply
$GOV run --apply

# 5) 查看最近一次账本
$GOV report

# 6) 资产审计六环节（v1.1）——默认零写
$GOV audit
# 只跑指定探针（P1-P6）
$GOV audit --only P2,P6
# L1 项（git mv 归位）执行；L2+ 仍 needs-human
$GOV audit --apply
```

## Lane 路由表（谁负责什么）

| Lane | 职责 | 检测/处置委托自 | 写动作 |
|---|---|---|---|
| A 问题自愈 | 系统异常（compaction 失败、zombie 等） | `scan_errors.py` + reliability 常驻 | 委托既有 auto_fix，不重复执行 |
| B 资产健康 | 组件/配置/DB/端点/模型调度 | `system_full_audit.py` + `service_guardian_state.json` | guardian 常驻自动拉起 |
| C 文件治理 | 过期临时资产 + 历史归档 | `tempcleanctl` + `archive.py` | `--apply` 下 trash + 归档移动（sha256 manifest，可回滚） |
| D 任务盘点 | 未完成建设任务 + 文档缺口 | current-task / task-history / docs/architecture | 纯只读，永不写 |

## 分级闸门（policy L0–L3）

| 级别 | 处置 | 是否自动 |
|---|---|---|
| L0 可逆自愈 | 重试 / guarded 重启 / 配额恢复 | `--apply` 下自动 |
| L1 可回滚 | 文件移动（trash / 归档） | 默认 dry-run，确认后 apply |
| L2 需确认 | 改配置 / 切 Provider / 删数据 | **停手问 Rex，永不自动** |
| L3 禁止 | 对外副作用 / 凭据变更 / 强推 | **永不执行**，只记 needs-human |

## 安全铁律

- 默认 **dry-run**，不加 `--apply` 零写操作。
- `--apply` 前先 `run` 看 planned 清单；L2/L3 项即使 apply 也只会记 needs-human，不会执行。
- 归档产物进 `.archive/`（dot 目录 + gitignore），每笔移动登记 `manifest.json`（sha256），可回滚。

## 资产审计工作流（v1.1）

当需要全盘资产审计（残留/重复/空壳/口径漂移/断链）时：

1. 取证：`governor.py audit`（默认零写，跑 full_audit §12 六探针）
2. 看报告：`governor.py audit --json`（含 category/suggestion/tier）
3. L2+ 项：按 suggestion 列出的命令人工拍板
4. L1 项：确认 dry-run 清单后 `governor.py audit --apply`（仅 git mv 归位/合并）
5. 回归：重跑 `governor.py audit` 确认命中项清零

安全：audit 默认零写；L2+ 即使 --apply 也不执行；账本落 memory/governor-audit-latest.json。

## 产物与账本

| 文件 | 说明 |
|---|---|
| `memory/governor-latest.json` | 最近一次 run 账本（gitignore） |
| `memory/governor-audit-latest.json` | 最近一次资产审计账本（v1.1，gitignore） |
| `.archive/manifest.json` | 归档移动登记（源→目标、规则、sha256） |

## 与既有技能的关系

- **system-health-check**（同层技能）：健康检测 + 服务自愈，侧重**检测执行**；
- **system-governor**（本技能）：把多源检测结果**统一编排 + 分级处置**，侧重**工作流治理**。
  两者互补：巡检可先 health-check 细查，再 governor 统一盘点/处置。

## 参考

- 设计文档：`docs/architecture/PRD/DESIGN-OUTLINE/DESIGN-DETAIL-system-governor-v1.0.md`、`DESIGN-DETAIL-system-governor-v1.1.md`（资产审计）
- 操作手册：`L2-infra/components/system-governor/OPERATIONS-system-governor-v1.0.md`
- 验收：`L2-infra/components/system-governor/VERIFICATION-system-governor-v1.0.md`

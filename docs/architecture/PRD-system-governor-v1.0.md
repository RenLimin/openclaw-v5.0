# PRD — 系统治理工作流（system-governor）v1.0

| 项 | 值 |
|---|---|
| 所属层级 | L2 基础设施（横切编排） |
| 版本 | v1.0 |
| 日期 | 2026-11-10 |
| 作者 | Jerry 🦞 |
| 状态 | **待 Rex 评审** |
| 关联 | `reliability-auto-recovery-v1.0`（故障自愈，已落地）、`00-system-architecture.md`、`dag-orchestrator`（仅设计模板） |

---

## 1. 背景与问题

系统已建设了**大量检测能力**，但实测确认它们是「散装脚本 + 独立 launchd/automation job」，存在三个结构性缺口：

1. **无统一编排**：`scan_errors.py`（15min，12 项）与 `system_full_audit.py`（9 大域，全只读）两个全量扫描器各自为战，检测与处置之间没有「扫描→分级→处置→复核→报告」闭环。
2. **处置覆盖不均**：故障自愈（重启补偿/会话卡住/对症探测/重试/配额/上下文溢出）已落地；但**历史文件归档**能力不存在（`tempcleanctl` 只有 clean 无 archive），**未完成建设任务盘点**没有扫描器。
3. **缺单一入口与统一账本**：Rex 无法用一条命令拿到「问题 + 资产 + 文件 + 在建任务」四份对账结果和处置回执。

### 1.1 已确认的既有资产（复用，不重造）

| 能力 | 实现 | 状态 |
|---|---|---|
| 错误/超时/压缩/Provider/插件/上下文 扫描 | `L2-infra/scripts/error_handler/scan_errors.py` | ✅ 已落地 |
| 9 大域只读审计 | `L2-infra/scripts/system_full_audit.py` | ✅ 已落地 |
| 挂起补偿重启 P1-a | `recovery_pending.py` + `guarded_restart` | ✅ commit b3a6f63 |
| FailoverError 对症探测 P1-c | `endpoint_probe.py` | ✅ commit 457f379 |
| 分项超时隔离 P1-d | `run_scan_items` | ✅ commit 31b8273 |
| 会话卡住识别 P1-b | `stall_detect.py` | ✅ commit d1afbde |
| 服务常驻守护 | `service_guardian`（launchd 常驻） | ✅ 在跑 |
| 配额检测恢复 | `check_quota_and_restore.py` | ✅ 在跑 |
| 临时文件删除（trash） | `workspace-temp-cleanup/tempcleanctl.py` clean | ✅ 工具具备 |
| 仓库健康 | `maintenance/repo_health.sh` | ✅ 只读 |

### 1.2 真正的缺口（本项目新建）

| 缺口 | 说明 |
|---|---|
| **编排层** | 统一调度四条 lane、聚合结果、分级处置、出统一报告 |
| **Lane C 归档** | 在 tempcleanctl 增 `archive` 子能力（区别于 trash 删除），按架构规则把历史文件移到归档区 |
| **Lane D 任务盘点扫描器** | 聚合 task_tracker / IMPLEMENTATION-PLAN / 未勾验收项 / 活跃会话，枚举全部未完成建设任务 |

---

## 2. 目标 / 非目标

### 目标

1. 提供**单一入口**，一键跑完四条 lane 并产出统一治理报告与处置回执。
2. 全量扫描**已知未解决问题**，可安全自愈的自动处置，不可逆的停下问 Rex。
3. 全量扫描**运行依赖资产健康度**，服务挂自动拉起，配置/凭据类只报不自动改。
4. 全盘扫描**系统文件**，按架构文档执行临时文件清理与**历史文件归档**（默认 dry-run）。
5. 全量扫描并**罗列未完成建设任务**，逐条给出位置、状态、下一步。
6. 所有自动动作**幂等、有界、可审计、可人工接管**，杜绝风暴与自杀式操作。

### 非目标（v1.0 不做）

- 不重写任何既有扫描/自愈逻辑，仅调用与编排。
- 不自动改配置、凭据、Provider 路由核心；不做对外副作用（邮件/公开发送）。
- 不做跨主机编排；不做 DAG 可视化图形界面。
- 不做"自动重放用户原始消息代跑"（沿用 reliability v1.0：默认只通知）。

---

## 3. 功能清单

### 3.1 统一入口

```bash
python3 -m bdms...  # 非业务模块；用独立 CLI
python3 L2-infra/components/system-governor/scripts/governor.py run [--only A,B,C,D] [--apply] [--json]
python3 L2-infra/components/system-governor/scripts/governor.py report
```

- 默认 **dry-run（计划模式）**：只列出"将做什么"，不执行写操作；`--apply` 才真处置。
- `--only` 选择 lane；默认四条全跑。

### 3.2 四条 Lane

| Lane | 名称 | 复用 | 新建 | 自动处置边界 |
|---|---|---|---|---|
| **A** | 已知问题自愈 | scan_errors.py + reliability P1-a/b/c/d | 结果聚合、去重、分级 | 重试/补偿重启/配额恢复 自动；卡住代跑 只通知 |
| **B** | 资产健康修复 | system_full_audit 第3/4域 + endpoint_probe + service_guardian | 统一健康评分、修复编排 | 服务挂自动拉起；配置/key 失效 只报 `doctor --fix` |
| **C** | 文件治理 | tempcleanctl clean + audit_garbage | **tempcleanctl archive 子能力 + 归档规则** | dry-run 默认；clean(trash)/archive 需 --apply |
| **D** | 建设任务盘点 | task_tracker + 会话状态 | **任务盘点扫描器（新）** | 只读罗列，不自动改任务 |

### 3.3 统一治理报告

一次 run 产出 `memory/governor-latest.json`，含：

- 四 lane 分区结果；
- 每条发现：`severity`（critical/warning/info）、`status`（open/auto-fixed/needs-human）、`evidence`、`action`；
- 处置回执汇总（自动修复 N、待人工 M、归档/清理清单）；
- Lane D 的未完成任务表。

---

## 4. 自动处置分级（安全红线）

| 级别 | 动作类型 | 默认行为 |
|---|---|---|
| **L0 可逆自愈** | 重试、guarded 重启、配额恢复、服务拉起 | `--apply` 下自动 |
| **L1 可回滚文件操作** | trash 删除、归档到指定目录 | 默认 dry-run，`--apply` 执行 |
| **L2 需确认** | 改配置、切 Provider 路由、删数据 | 一律停下，列命令请 Rex 拍板 |
| **L3 禁止自动** | 对外副作用、凭据变更、强制推送 | 不自动执行 |

护栏：同一动作有界（次数/TTL，沿用 recovery_pending 常量）、evidence 去抖、全量审计日志。

---

## 5. 验收标准

1. **单一入口**：`governor.py run` 一次跑通四 lane，产出结构合法的 `governor-latest.json`。
2. **Lane A**：注入可自愈故障 → `--apply` 自动修复且幂等；不可逆项 → needs-human 不自动做。
3. **Lane B**：服务停掉 → guardian 路径自动拉起；key/配置失效 → 只报 `doctor --fix`，不自动改。
4. **Lane C**：`archive` 把符合规则的历史文件移到归档区并登记；默认 dry-run 不移动；clean 走 trash。
5. **Lane D**：准确枚举出当前所有未完成建设任务（含已知 current-task 之外的在建/搁置项），每条带位置与下一步；无未完成时明确返回空。
6. **安全**：无 `--apply` 时零写操作；连跑 3 轮，自动动作次数稳定不增长。
7. **回归**：不破坏既有 error_handler / gateway-safety / session-recovery / model-scheduling / temp-cleanup 测试。
8. 所有结果真实执行，不虚构。

---

## 6. 待 Rex 拍板

1. CLI 形态：独立 `governor.py`（推荐）还是封装为 OpenClaw skill / 接入现有命令？
2. 调度：v1.0 仅手动触发（推荐先验证），还是接一个低频定时（如每日 08:30 dry-run 投递摘要）？
3. Lane C 归档区位置与规则口径：归档到 workspace 内 `archive/` 还是 workspace 外指定目录？
4. 是否同意自动处置分级（L0 自动 / L1 dry-run+apply / L2+ 停手）？

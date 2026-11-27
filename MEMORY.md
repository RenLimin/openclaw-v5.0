# MEMORY.md - 系统级长期记忆

> 主会话专用。不加载到共享场景（群聊/其他会话）。

## 元数据

- 系统：综合开放平台 · 4 层（L1~L4） · 基座 OpenClaw
- AI：Jerry 🦞 · 详见 `IDENTITY.md`/`SOUL.md`
- 知识库：Markdown+元数据（自建系统为目标，0/7 触发暂缓）
- 用户：Rex · 中英混合 · 全栈+管理 · 拍板点：仅不可逆操作

## 关键决策

| 日期 | 决策 | 文档 |
|---|---|---|
| 08-21 | 4 层架构(ADR-001) · 三维知识库(ADR-002) · 双轨沉淀 · 知识库演进3阶段(ADR-003) | `docs/architecture/00-system-architecture.md` |
| 08-21 | 凭据管理通用化(ADR-005) · 持久化 SQLite+Repository(ADR-006) | |
| 08-22 | 配置管理(ADR-007) · 工具策略三态(ADR-008) · 记忆嵌入本地 GGUF(ADR-009) | |
| 08-23 | 知识库工具链(ADR-010) · 全盘 review 13 项偏差 · 选择性引用教训 | |
| 08-24 | 上下文管理(压缩同 provider + sticky 隔离 + 供应链加固) | |
| 09-02 | 运行时抽象(ADR-012) · 会话生命周期(ADR-013) · 错误自动处理(ADR-014) | |
| 09-15 | BDMS 全量交付 · 对比 18/18 零误差 · 验收 7 步法制度化 | |

## 活跃项目

- **综合开放平台**：L2 19 组件齐备 · L3 7 组件 · L4 7 组件 · 66 份文档已补齐
- 已完成：BDMS · Bangcle PPT · 合同审批 SCA-001 · FIN-L4 M1-M4 · DMS · OCR · Office 生成 · 模型调度
- 阻塞：WeCom 每日观测摘要（缺 Agent mode 凭据）

## 待外部输入（阻塞项）

- **Palantir P4.2 OA 真实写回**：冻结中。2026-11-08 Rex 拍板合并至人工验收测试环境执行。解锁条件（全在 Rex）：① 指定**测试流程单据**（非真实在审合同）② 写接口抓包契约（端点/CSRF/body，详设 §4.3 留空待补）③ 单据级二次授权。增量文档 `…-p4-write-v1.1`。 <!-- project: github.com/RenLimin/openclaw-v5.0 -->

## 核心经验

| 类别 | 教训 |
|---|---|
| 运维 | 僵尸 subagent 须停 Gateway 删 DB · cron 必须 isolated · subagent_runs 有内存缓存 |
| 数据 | 凭据存 SQLite 需独立备份 · DB 重制全丢 |
| 引用 | 读完章节全文再引 · 交叉 concepts/+reference/ |
| 证据 | 不用启发式代替证据 · 不把讨论当执行 · 不把目录当权限 |
| 建设 | 迭代>平行 · 同一功能单路径 · 参数收了必须用 |
| 技术选型 | 涉及技术选型的工作必须先产出选型方案文档，确认后再更新至详细设计文档 |

## 环境约束（实测）

- **Gateway cron 环境 `python3` 解析到系统 Python 3.9（CommandLineTools，x86_64 numpy 不兼容 arm64）**；command payload 必须用绝对路径 `/opt/homebrew/opt/python@3.14/bin/python3.14`，否则 ImportError 退出码 2。 <!-- project: github.com/RenLimin/openclaw-v5.0 -->
- **OA 项目实施管理三流程（2026-11-12 侦察固化）**：POC→「PoC需求申请流程」(编号 PoC-YYYYMMDD-NNNN)；提前实施→「提前实施需求申请流程」(TqSS-…)；签约项目→「销售合同下单流程（数据审核触发）」(XD…)。SPA static4form 页 + storage_state 只读；端点 `loadForm`/`detailData`/`getRequestLogList`（JSON 藏 text/plain）。固化见 `docs/knowledge-base/oa-project-implementation-workflows.md`。 <!-- project: github.com/RenLimin/openclaw-v5.0 -->
- **OA 对账数据链（P4.4，实测打通）**：`contracts.oa_billid` → CubeClient 卡片主字段「合同审批流程→」= requestid（billid 15134 → requestid 882663）→ ApprovalLogReader 审批链。cron job `oa-reconcile-daily (P4.4)` 每日 09:30 Asia/Shanghai 只读对账，落盘 `memory/oa-reconcile-latest.json`（gitignored）。 <!-- project: github.com/RenLimin/openclaw-v5.0 -->
- **泛微 OA（oa.bangcle.com，e-cology 9）：当前仅具备普通账号登录权限，无开放平台应用凭证、无 WorkflowService/管理权限。** <!-- project: github.com/RenLimin/openclaw-v5.0 -->
- 含义：合同桥只能走「登录会话 cookie + 浏览器/SPA 内部接口」路线（cube.py 已是此模式，非 app token）；无法走 REST apply token / WebService。
- ~~已证鸿沟~~ **2026-11-04 已解**：销售合同卡片主字段 `合同审批流程→` 即审批 **requestid**（billid 15134 → 882663），另有 `流程编号`/`概算申请流程`/`存档流程`。普通账号带会话即可读完整审批链。
- ~~只读端点纯 HTTP 重放已验证（2026-11-04）~~ **2026-11-06 实测否决**：`getRequestLogList` 需表单页签发的 4 个签名令牌（`loadForm`→signatureSecretKey/signatureAttributesStr，`detailData`→authStr/authSignatureStr，后者返 500），裸 POST 被 `LoadRequestLogDataCmd` 拦截或返空。**读路径定为真实浏览器驱动**（`ApprovalLogReader`，点「流转意见」懒加载后拦 XHR）。 <!-- project: github.com/RenLimin/openclaw-v5.0 -->
- ecology 会话可无人值守重建：`contractctl oa-login`（IAM headless + BDMS IMAP 取码）→ SSO 换票 → state 落盘 → 探针 billid 15134 校验；失败返 `{ok:false, stage, error}` 信封，不抛裸异常。 <!-- project: github.com/RenLimin/openclaw-v5.0 -->

## 变更历史

- 2026-11-17：Palantir 主任务收口（P1–P7 全 completed，P4.2 冻结待外部输入挂账）；纠正 OA 只读端点记录（纯 HTTP 已否决 → 浏览器驱动）
- 2026-10-04：全量资产文档补齐(66份) · AGENTS.md 瘦身 24k→11k · USER.md 瘦身 8k→2.6k · 系统升级 2026.9.1→2026.9.8
- 2026-09-16：model-scheduling 注册为 OpenClaw provider
- 2026-09-15：BDMS v2.1 全量交付 · 验收 7 步法
- 2026-08-23：全盘 review + 14 项修复 · 二轮 review + 9 项修复
- 2026-08-24：压缩失效根因 · sticky 隔离 · 火山 embedding 结案

## Dreaming 晋升（自动 · memory-promotion-gate）

<!-- dream-promoted: 155fdfb996d5 -->
- reference_data 表设计: `variance_reason`（8 条）：确收差异原因枚举  (evidence: memory/2026-09-14.md:42-42; recalls=0; score=0.3269)
<!-- dream-promoted: 105e40412ee2 -->
- 关键决策: **图例数据**：项目经理/偏差状态/验收原因/预算进度/团队/产线 → 全部存入 reference_data 表  (evidence: memory/2026-09-14.md:32-32; recalls=0; score=0.3269)
<!-- dream-promoted: 0182aef68e82 -->
- 已修复项确认（本次会话）: ✅ 架构文档同步：00/01/02/03 全部更新到最新状态  (evidence: memory/2026-09-17.md:23-23; recalls=0; score=0.3269)
<!-- dream-promoted: 0e729f8bebd3 -->
- 13:00-13:05 model-scoding health_check 修复 ★★: **修复 2**：lite 模型优先探测（chat completions 兼容性最好）  (evidence: memory/2026-09-17.md:6-6; recalls=0; score=0.3269)
<!-- dream-promoted: ef8b68c30a8e -->
- 已修复项确认（本次会话）: ✅ ~/.openclaw/ 根目录清理：备份归档 + 3.7GB tmp 清空  (evidence: memory/2026-09-17.md:24-24; recalls=0; score=0.3269)
<!-- dream-promoted: 069ff1336ba4 -->
- 关键上下文: 现有 Base 层代码：`modules/base.py`（已实现 BaseEngine/BaseService/BaseExporter，缺 BaseImporter）  (evidence: memory/2026-09-19.md:22-22; recalls=0; score=0.3269)
<!-- dream-promoted: 0009340a0e0c -->
- 待完成: Step 5：确收 Excel 导出器（与手工报表格式一致，最耗时）  (evidence: memory/2026-09-18.md:33-33; recalls=0; score=0.3269)
<!-- dream-promoted: 0b0015d7f163 -->
- 变更文件: `src/bdms/modules/revenue/service.py` — 更新 `has_data`/`list_months` 从宽表查询  (evidence: memory/2026-09-18.md:27-27; recalls=0; score=0.3269)
<!-- dream-promoted: 60d11890e231 -->
- Step 1 + Step 2 已完成（统一持久化 + 确收导入器）: 单位：我方元 / 手工万元（÷10000）  (evidence: memory/2026-09-18.md:20-20; recalls=0; score=0.3269)
<!-- dream-promoted: 5f815500fb99 -->
- 02:15 - BDMS v2.1 详细设计文档编制开始: Rex 要求今晚完成所有 BDMS v2.1 详细设计文档的编制，从 Base 层开始。  (evidence: memory/2026-09-19.md:5-5; recalls=0; score=0.3269)
<!-- dream-promoted: 7e9efd28c60a -->
- 模板对齐工作: Rex 16:41 要求"补模板对齐"。6 份旧模板文档（AFTER-SALES / BASE / CONTRACT-MANAGEMENT / DELIVERY-REPORT / KNOWLEDGE-BASE / PROJECT-MANAGEMENT）缺少统一章节结构，已全部补齐：  (evidence: memory/2026-09-19.md:54-54; recalls=0; score=0.3269)
<!-- dream-promoted: 936487f444ce -->
- 关键决策: 企微文档 → 本机路径 + API 预留  (evidence: memory/2026-09-20.md:22-22; recalls=0; score=0.3269)
<!-- dream-promoted: 1ca159660b49 -->
- 审核进度: ✅ PROJECT-MANAGEMENT — 通过（4 点确认：+ChangeManagementEngine / +ProjectFinancialService / 合同关联不囊括 / 业界对比）  (evidence: memory/2026-09-20.md:11-11; recalls=0; score=0.3269)
<!-- dream-promoted: af21d4b57073 -->
- 关键决策: ONES/OA/工时 → 全部浏览器自动化  (evidence: memory/2026-09-20.md:21-21; recalls=0; score=0.3269)
<!-- dream-promoted: fac915579bb1 -->
- 审核进度: ✅ DATA-MODEL — 通过（4 点建议已补：表类型分类 / 分片策略 / 报表配置表 / 业界对比）  (evidence: memory/2026-09-20.md:9-9; recalls=0; score=0.3269)
<!-- dream-promoted: 769a5729a55d -->
- L3 健康管理与理财引擎 五件套文档补齐 ★★: 6 大领域：profile / checkup / metrics / medication / risk_assessment / health_plan  (evidence: memory/2026-09-30.md:15-15; recalls=0; score=0.3269)
<!-- dream-promoted: 98498f93ca13 -->
- L3 健康管理与理财引擎 五件套文档补齐 ★★: 风险等级 5 级，风险类型 13 种  (evidence: memory/2026-09-30.md:19-19; recalls=0; score=0.3269)
<!-- dream-promoted: 8ca6a868295f -->
- L3 健康管理与理财引擎 五件套文档补齐 ★★: 模型：Pydantic v2，TenantModel 基类（id/tenant_id/created_at/updated_at/is_deleted）  (evidence: memory/2026-09-30.md:17-17; recalls=0; score=0.3269)
<!-- dream-promoted: a0d7674d47e4 -->
- L3 健康管理与理财引擎 五件套文档补齐 ★★: 用药频次 12 种（qd/bid/tid/qid 等医学缩写）  (evidence: memory/2026-09-30.md:20-20; recalls=0; score=0.3269)
<!-- dream-promoted: 20eb6a990719 -->
- 修复（已执行）: fallback 链优化：去掉 `model-scheduling/auto`（减少一层代理），改用 `deepseek-v4-flash` + `doubao-seed-2.0-lite`  (evidence: memory/2026-10-03.md:20-20; recalls=0; score=0.3269)
<!-- dream-promoted: dbf1a042a966 -->
- Session: 2026-10-02 21:14:56 Asia/Shanghai: **Session Key**: agent:main:main  (evidence: memory/2026-10-02-2114.md:3-3; recalls=0; score=0.3269)
<!-- dream-promoted: 6b002dc02960 -->
- Session: 2026-10-02 21:14:56 Asia/Shanghai: **Session ID**: 1fbbfe45-de4b-43bd-b949-cf73e48f6c52  (evidence: memory/2026-10-02-2114.md:4-4; recalls=0; score=0.3269)
<!-- dream-promoted: 0d587ac67e50 -->
- BDMS 清空历史测试数据（人工验收前置）✅: **清空**： > 顺带修复：kb_fts FTS5 表此前已损坏（reading blob 10 corruption），DROP 后按原 schema 重建  (evidence: memory/2026-10-27.md:11-11; recalls=0; score=0.3269)
<!-- dream-promoted: 2620ec7fd0af -->
- BDMS 清空历史测试数据（人工验收前置）✅: **清空**：  (evidence: memory/2026-10-27.md:7-7; recalls=0; score=0.3269)
<!-- dream-promoted: 0b74be48213c -->
- 任务 3：202606 交付月报浏览器自动化测试 ✅: 企微缓存：revenue_202606.csv + acceptance_202606.csv 已存在  (evidence: memory/2026-10-26.md:18-18; recalls=0; score=0.3269)
<!-- dream-promoted: a15f433623ff -->
- BDMS 清空历史测试数据（人工验收前置）✅: **验证**：服务由 tmux 守护脚本自动重启（PID 54516，uvicorn bdms.web.main 127.0.0.1:8000），HTTP 200；`/api/report/months`=[]、`/api/master-data/types`=[]、revenue summary 数值全 0  (evidence: memory/2026-10-27.md:13-13; recalls=0; score=0.3269)
<!-- dream-promoted: 5c6d3e10f3ba -->
- BDMS 修复月报生成完成后界面不刷新 + Tab 改名 ✅: **现象**：进度条 100% + toast 生成完成，但状态文字/圆点停在初始未生成态、KPI 全 0  (evidence: memory/2026-10-27.md:18-18; recalls=0; score=0.3269)
<!-- dream-promoted: 656f5bac60d1 -->
- 任务 3：202606 交付月报浏览器自动化测试 ✅: **E2E 测试修复**（真异步改造后的新发现）：  (evidence: memory/2026-10-26.md:23-23; recalls=0; score=0.3269)
<!-- dream-promoted: 1ae7436cce67 -->
- 任务 1：pytest collect error 排查 ✅: **修复**：`git mv tests/visual/test_dashboard.py tests/visual/test_visual_dashboard.py`，331 tests collected 0 error  (evidence: memory/2026-10-26.md:7-7; recalls=0; score=0.3269)
<!-- dream-promoted: 1f48079d7e8d -->
- 任务 1：pytest collect error 排查 ✅: **根因**：`tests/visual/test_dashboard.py` 与 `tests/test_dashboard.py` 同名模块冲突（pytest import file mismatch），visual 测试子目录 basename 撞名  (evidence: memory/2026-10-26.md:6-6; recalls=0; score=0.3269)
<!-- dream-promoted: 26c46cea4899 -->
- 任务 3：202606 交付月报浏览器自动化测试 ✅: **数据链路重建**（清空后）：  (evidence: memory/2026-10-26.md:16-16; recalls=0; score=0.3269)
<!-- dream-promoted: dc24d1e73abe -->
- Session: 2026-10-26 15:34:38 Asia/Shanghai: **Source**: webchat  (evidence: memory/2026-10-26-1534.md:5-5; recalls=0; score=0.3269)
<!-- dream-promoted: 35c6490df89c -->
- Session: 2026-10-27 20:50:13 Asia/Shanghai: **Session Key**: agent:main:dashboard:b669ddb2-3b01-4583-b4bd-3f8932dc59e9  (evidence: memory/2026-10-27-2050.md:3-3; recalls=0; score=0.3269)

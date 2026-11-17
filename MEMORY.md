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

# DESIGN — customer-rectification-report（客户整改报告技能）

- 状态：approved（Limin 2026-11-24 审批 V0.1 编制要求后开建）
- 层级：L3（通用业务 / 项目管理域）
- 关联技能：`bangcle-project-report`（周期汇报 md）、`bangcle-project-retrospective`（内部复盘 md）、`bangcle-project-summary`（台账）、`bangcle-obligation-summary`（履约义务）
- 回归基准：山东省城商行联盟《项目复盘与整改报告》V1.7（2026-11-23，10 页）

## 1. 业务问题（Why）

对客户现场反馈的 N 条问题，需要正式提交一份**承诺型**《项目复盘与整改报告》Word 件。
实战（V1.0→V1.7，七轮人工修订）暴露的可固化点：
1. 章节/附件结构每次重搭；
2. 整改表 8 列、四必填（措施/责任方/时限/验收）易缺项；
3. **近期行动日期与明细表不一致**（同一事项两个日期、混合到期日不拆行）；
4. 交付物清单按"合同条款/产品"两版反复，最终定为"大版本/小版本/周期专项"且要去合同条款；
5. 表格 5 种字号 + 中文字体靠继承，跨平台（银行 Windows）风险；
6. 内部版含 ONES 号，外发需脱敏，靠人工易漏；
7. 修订接受、版本另存、PDF 越界等全靠人肉。

## 2. 目标 / 非目标

**目标**
- 一套编制规范 + 可套 Word 骨架 + 机器门禁，使同类报告 1 天内出合规初稿且零返工级错误。
- 日期一致性、对外脱敏、字体版式、修订残留等可机器判定项 100% 自动校验。
- 内部版/对外版双轨，对外版 fail-closed。

**非目标**
- 不替代 ONES/合同取数（复用 project-summary / obligation-summary）。
- 不做内部产品差异×PMBOK 复盘（属 retrospective）。
- 不自动外发客户（对外副作用必须人工确认）。

## 3. 业界最佳实践调研（Why this shape）

- ** corrective action 范式（ISO 9001 / IATF 8D / CAPA）**：问题→根因→措施→责任方→时限→验证（verification of effectiveness）。
  本技能整改表 8 列对应：问题（贵司问题）+ 措施 + 责任方 + 完成时限 + **验收标准（= 有效性验证）** + 参考/证据。
- **SMART 行动项 + RACI**：整改与行动必须 Specific/Time-bound、有唯一责任方；A/B 角名单即 RACI 的 R/备援。
- **ITSLA/ITIL 事件管理**：SLA（响应/解决时限）、定级、主动通报、升级通道——落到「总体整改机制」与附件4。
- **发布管理（release management，major/minor release）**：大版本全量回归全套文档、小版本变更清单+影响分析+回滚——附件2 的三类切分依据。
- **AI Agent 官方/社区实践**（OpenClaw 文档与 Clawhub 技能惯例）：技能 = SKILL.md（When/Hard Rules/Workflow/Verification）+ scripts（fail-closed 校验）+ assets（模板/ golden）+ tests；外部副作用不自动执行；可机器门禁前置（本仓 pre-commit 与既有 answer-spec 闸门同款思路）。
- **GitHub/开源同类**：8D/CAPA 报告模板、SLA/OLA 模板普遍采用"问题登记表 + 纠正措施表 + 验证关闭"结构；脱敏（redaction）作为外发前独立 stage，与既有 `bangcle-project-report/assets/*-external.md` 双受众做法一致。

**取舍**：不引入完整 8D 八步（对客户过重，D0/D3/D6 内部化）；保留客户最关心的"逐条问题—措施—责任—时限—验收—附件证据"主线。
不把 PMBOK 全知识域放进对外件（客户不关心内部管理域），仅在内部取材时由 retrospective 提供。

## 4. 方案（What）

目录：
- `SKILL.md`：入口契约（定位/双版本/章节/铁律/Workflow/Verification）。
- `references/authoring-standard.md`：编制要求全文（V0.1，Limin 审批稿）。
- `assets/report-skeleton.md`：六章四附件内容骨架（占位与填写指引）。
- `assets/style-spec.json`：字体/字号/列宽/页面枚举（机器可读）。
- `scripts/build_docx.py`：由结构化数据（YAML/JSON）+ 官方 Word 模板渲染内部版 docx。
- `scripts/validate_report.py`：fail-closed 机器门禁（见 §6）。
- `tests/`：以 V1.7 脱敏 fixture 为 golden，校验应 PASS；故意制造违例应 FAIL。
- `VERIFICATION-v1.0.md`：验收结论与证据。

## 5. 数据模型（结构化输入）

report.yaml：meta（客户全称/我方全称/部门/日期/版本/密级）、contracts[]、
issues[]{id,cat,question,action,owner,due,acceptance,ref,ones}（ones 仅内部）、
mechanism[]、phases[]、actions[]{no,action,owner,due}、
deliverables[]{type,name,requirement}、ab_roles[]{domain,a,b,lead}、
notify[]{stage,trigger,action,sla,owner}、annex1_fields[]。

## 6. 机器门禁（validate_report.py，exit≠0 即 BLOCK）

内部版跑 G1–G7、G9–G10；对外版额外强制 G8。
- G1 PDF/docx 无越界块；纵/横节正常；落款承诺段同页。
- G2 问题条数 = 声明 N；每条 action/owner/due/acceptance 非空；due 命中白名单（已完成/日期/区间/X起跟进）；禁词（待定/尽快/技术复盘确定/待指定）=0。
- G3 日期一致性：actions[].due 可由相关 issues 窗口推导（最晚完成日/最早起算）；混合到期必须拆行；旧日期/旧里程碑残留=0。
- G4 附件2：三类齐全；交付物非空；合同号/§条款/"数据来源/依据"字样=0。
- G5 字体：全部含文本 run 显式 eastAsia∈{宋体,黑体}；字号∈style-spec 枚举。
- G6 称谓：甲方/附录/格式化表格=0；客户/我方全称出现。
- G7 修订残留 w:ins/w:del/pPrChange=0。
- G8（对外）ONES 号（6 位任务号/#号）、ONES URL、内部列（列名含 ONES）、工号/内部经营项=0。
- G9 页眉 logo/页脚标语/页码首末页存在。
- G10 关键页人眼复核截图归档（脚本检查证据文件存在；人工判定内容）。

## 7. 生命周期与回归
- 验收基准：V1.7 脱敏成 internal golden（去真实 ONES 号/人名敏感项），validate 须 PASS。
- 突变测试：注入（缺验收标准 / 行动日期不符 / 附件2 含合同号 / 对外版含 ONES / 字号越界）各须 FAIL。
- 完成后：登 capability-registry、--coverage 100%、重生成资产清单。

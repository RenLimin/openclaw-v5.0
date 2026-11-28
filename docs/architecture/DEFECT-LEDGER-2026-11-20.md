# 资产验收缺陷登记册（DEFECT-LEDGER）

> 来源：2026-11-20「全部补齐」验收中 29 份 VERIFICATION + 4 组件实测发现
> 规则：验收只记录不改代码；本登记册是后续专项修复的权威待办。修一项→改状态→回填证据。

状态图例：🔴 待修 · 🟡 修复中 · ✅ 已修(含证据) · ⚪ 验收为环境/外部(非缺陷) · 🔵 路线图(本就未实现)

## P0 — 真实代码缺陷（影响核心命令/门禁）

| ID | 资产 | 缺陷 | 修复方向 | 状态 |
|---|---|---|---|---|
| D-01 | system-governor | `governor.py report` 无参 `Path(None)` → TypeError 崩溃（SKILL 核心命令第 5 条不可用） | `--ledger` 缺省回退 `ledger.DEFAULT_LEDGER` | ✅ 已修 2026-11-20：无参 exit=0 读到默认账本；回归 50 passed |
| D-02 | bangcle-project-report | `render_report.py` 缺 `fetchedAt` 时产物无【已验证 时间戳】→ check_answer_contract BLOCK（真实 20261106 报告带 47 时间戳则 PASS） | render 缺真实取数时间时 **fail-closed exit=2**（不再产出空日期假章）；normalize/aggregate 透传 `completeness.fetchedAt` | ✅ 已修 2026-11-20：缺 fetchedAt exit=2 零输出；带真实时间戳 exit=0 日期正确；回归测试 4 passed（D-09） |
| D-03 | bangcle-project-summary | 台账 md 缺 `## 0. 溯源链` / `质量信号` 章节 → 契约信封 F4/F5 BLOCK | 台账模板补信封骨架（元信息/溯源链/质量信号/降级标注） | ✅ 已修 2026-11-20：模板补全后真实样例过 check_answer_contract **PASS exit=0** |

## P1 — 回归红项 / 文档与实现不符

| ID | 资产 | 缺陷 | 修复方向 | 状态 |
|---|---|---|---|---|
| D-04 | ocr-digitalization | `test_03_preprocess.py::test_adaptive_binarize` 失败（渐变图二值化 `arr.min()==255`） | 纯渐变图无高频结构，自适应二值化全白是数学必然（OpenCV 同款公式亦然）——**测试夹具不真实**，改用带黑白结构的 text_image | ✅ 已修 2026-11-20：test_03 21 passed，组件全量 113 passed |
| D-05 | ocr-digitalization | SKILL.md 把 `correct_ocr_errors` 列为 `ocr_engine` API，实际在 `ocr_backends.py`（引擎内叫 `correct_contract_text`） | ocr_engine 加 lazy re-export，文档即契约 | ✅ 已修 2026-11-20：`from ocr_engine import correct_ocr_errors` 实测纠错生效 |
| D-06 | model-scheduling / scheduler-guard | `session_cleanup.py` plist 未 loaded → audit inconsistent=1；SKILL.md 仍写「不一致 0」（口径过期） | `launchctl load` 该 plist | ✅ 已修 2026-11-20：load 成功，audit **inconsistent=0**（total=17 scheduled=16 unscheduled=0）；SKILL.md 口径已与实际一致 |
| D-07 | ontology-identity-gate | 聚合 `-k` 跨文件运行时 `test_tampered_signature_rejected` 受同进程 secret/缓存影响变红（单文件 18/18 绿） | 测试隔离 | ⚪ 2026-11-20 复验：聚合选择器 3 连跑 38 passed + 组件全量 175 passed **未复现**；VERIFICATION 记录为 flaky，暂缓处理 |
| D-08 | role-library | 声明 7 内置角色，实际仅 2 个角色文件，其中 1 个还非规定 YAML 格式 | 补 5 个角色 YAML + ui-designer.md 转 YAML | ✅ 已修 2026-11-20：8 个角色文件全 YAML 合规（7 声明 + ui-designer 扩展），frontmatter 六字段齐备 |

## P2 — 方法论型 skill 无自动化测试（非红项，工程债）

| ID | 资产 | 现状 | 状态 |
|---|---|---|---|
| D-09 | 5 个 L3 skill（project-report/summary/retrospective/obligation-summary/customer-profile） | 均无 `tests/` 目录，验收靠真实运行+手动步骤 | ✅ 已修 2026-11-20：5 个 skill 全补关键路径 pytest（模板实例化过契约闸门 / 报告骨架 + 6 指标铁律），18 passed |
| D-10 | dag-orchestrator | DAG 执行引擎未实现（SKILL 自身已标 `[ ]`）；定义层/模板达标，运行时未验收 | ✅ 已实现 2026-11-22：DESIGN-v1.0.md 评审通过后落地 `scripts/` 执行引擎（loader/graph/executor/artifact_store/state/runner/viz，graphlib+concurrent.futures 零依赖）；同日晚补齐 **4 个内置模板 YAML 定义块** + **agent 派发后端**（dispatch.py，可插拔，默认 openclaw CLI 真实派发）；`tests/` **34 用例全绿**（并行真实/变量传递/失败停下游/超时/契约门禁 fail-closed/Mermaid/派发 T14-T20）；真实运行 SKILL.md 示例 YAML success exit=0；SKILL.md 打钩、registry 补 runner.py+dispatch.py 入口、VERIFICATION 升级 v1.1 |
| D-12 | bangcle-project-report | 新增 `tests/test_render_fail_closed.py`（4 用例）：缺 fetchedAt fail-closed exit=2 + normalize/aggregate 透传 + 带时间戳渲染，防 D-02 复发 | ✅ 已修 2026-11-20：4 passed |
| D-11 | ones-browser-export | 仅离线契约验证，真实浏览器/OA 链路未验 | ⚪ 待有登录态/专用 CDP 时补 E2E |

## 环境性 / 外部（非代码缺陷，仅留证）

| ID | 现象 | 判定 |
|---|---|---|
| E-01 | bangcle-ppt visual 3 failed、fin-l4 visual 14 failed（127.0.0.1:18806 ERR_CONNECTION_REFUSED） | ✅ 已治理（2026-11-21）：共享基类加「服务缺失即 skip」前置守卫，服务未启动不再误报 fail（见修复记录）；功能测试 249/189 全绿 |
| E-06 | visual 套件跨组件**端口撞号**：L4 组件内 `tests/visual/test_pages.py` 四处 BASE 错乱（ppt→18806 无服务、fin→18801 撞 PPT、dc→18804 撞 FIN、oc→18803 撞 DC），L2 web-common 套件端口正确；服务起到权威端口时错乱套件打 404 | ✅ 已治理（2026-11-22）：4 个 L4 套件 BASE 对齐权威映射（PPT:18801/CISSP:18802/DC:18803/FIN:18804/OC:18805）；真实服务身份经 lsof+health+title 三方钉死；对齐后四套件 18 passed（此前 18 failed 全 404），6 个 skip 为 golden 首建非缺陷。**同日晚已去重（Rex 拍板）**：删除 6 组件 7 个 L4 重复套件（bdms test_pages/test_visual_dashboard、dc/ppt/oc/fin/cissp test_pages），保留 L2 聚合套件为唯一权威（唯一运行器 run-visual-tests.sh + 唯一 golden 库 + web-common DESIGN-DETAIL §6 声称）；合并 L4 独有覆盖到 L2（bdms error 404 页、ppt 真实模板路由 cover-light）；清理 10 张 L4 独有命名孤儿 golden（index/dashboard_view/master_data/revenue_compare/report_detail/coverage_gap/contract_list/contract_new/risk_rules/detail）；同步 CI glob、ui-designer.yaml、bdms README。去重后 42 tests collected、golden 0 孤儿。 |
| E-02 | system-health-check：bdms-web、llama-cpp-embedding Connection refused | ⚪ 真实服务未启动，三态判定正确 |
| E-03 | model-scheduling：deepseek 两模型 HTTP 402 | ⚪ 外部账户额度，脚本判定正确 |
| E-04 | product-manager-expert 检准 1 error：源文件缺失 | ⚪ 真实数据问题，按 SKILL 由维护者补录 |
| E-05 | product-kb/CDI 等 openpyxl/pydantic/PyPDF2 弃用告警 | ⚪ 依赖告警非失败 |
| D-13 | bdms/scripts 历史重复脚本归并 | 34 个 git 跟踪脚本，经只读分析聚类：A 组 ONES 导出 11、B 组认证诊断 9、C 组页面诊断 3、D 组 OA 导出 5、E 组企微/异常 3、F 组报告 2、G 组通用 1 | ✅ 已治理（2026-11-22）：**删除 30 个重复/一次性脚本**（A11+B7+C3+BC2+EF5+D2，git 历史可恢复，supersedes 谱系保留）；**保留 4 个待 Rex 拍板**（oa_export_playwright / oa_export_full / export_abnormal_osascript / start_wecom_chrome，被跨组件文档引用）；registry 幽灵路径已修（D-13 关联）。前置：detect_duplicates 只按文件名不查存在性→测试固定输入仍通过；pre-commit ACMR 排除 D；无代码 import 引用 |

## 修复纪律

- 每项修复必须真实运行验证（禁止读代码自认修好），回填命令+结果到本文件。
- 验收文档与登记册口径同步：修复后更新对应 VERIFICATION 的「遗留问题」。
- P0/P1 代码修复走 pre-commit 全门禁 + 显式 pathspec 提交（共享 index 有并行会话文件）。
- D-10 引擎类大改须先 DESIGN 评审，不在本批次顺手做。

## E-01 修复记录（2026-11-21）：visual 服务缺失 skip 守卫

**根因**：`web-common/tests/visual/base.py` 直接 `page.goto()`，预览服务未启动时浏览器抛 `ERR_CONNECTION_REFUSED`，被记成视觉回归 failed——但这是「环境未就绪」而非「页面回归」。

**改动**（共享基类，一处覆盖全部 visual 套件：ppt:18806 / fin:18801 / cissp:18802 / dc:18803 / oc:18805 / bdms:8000）：
- 新增 `ensure_http_service_available()`：导航前用 `socket.create_connection` 探测目标主机端口，**仅** `ECONNREFUSED` → `pytest.skip`；服务在监听（哪怕返回 4xx/5xx）、超时、非 http URL 一律不 skip，交后续真实浏览器/像素校验暴露，不用 skip 掩盖产品缺陷。
- `assert_visual_match()` 在 `goto` 前调用该守卫。

**验证（真实运行）**：
- hermetic 单测 `tests/visual/test_service_guard.py`（3 用例：关端口必 skip / 在监听不 skip / file:// 绕过）：**3 passed**。
- 真实 ppt visual 套件（18806 无服务）：改动前 3 failed（ERR_CONNECTION_REFUSED）→ 改动后 **3 skipped**。
- 全 visual 聚合跑（`--import-mode=importlib`，绕过既有同名 test_pages.py 收集冲突）：服务在的套件真实执行像素对比；无服务的 skip。聚合中 18 failed 经逐一定位**全部是 404（E-06 端口撞号），无一例 ERR_CONNECTION_REFUSED 误报**，反证守卫语义正确。
- 非 visual 功能测试不受影响（守卫只在 VisualTestBase 内）。

**文件**：`L2-infra/components/web-common/tests/visual/base.py`、`L2-infra/components/web-common/tests/visual/test_service_guard.py`（新增）。

## 修复记录（2026-11-20 批次）

| ID | 验证证据 |
|---|---|
| D-01 | `governor.py report` 无参 exit=0 输出默认账本；system-governor 回归 50 passed in 12.60s |
| D-02 | 缺 fetchedAt：exit=2、stdout 0 字节、stderr 报 missing fetchedAt；带 fetchedAt：exit=0、报告含【已验证 2026-11-20|…】 |
| D-03 | 模板样例过 `check_answer_contract.py`：2 处时间戳、全部硬性项通过、PASS exit=0 |
| D-04 | `test_03_preprocess.py` 21 passed；ocr 组件全量 113 passed in 0.22s |
| D-05 | `from ocr_engine import correct_ocr_errors` 实测 `合同产晶数量→合同产品数量` |
| D-06 | `launchctl load` exit=0；`audit.py --json`：total=17 scheduled=16 unscheduled=0 **inconsistent=0** |
| D-07 | 聚合 `-k` 3 连跑 38 passed；组件全量 175 passed in 4.13s（未复现，标记 flaky） |
| D-08 | 8 个 YAML 角色文件 frontmatter 六字段全齐，无非 YAML 残留 |
| D-09 | 5 skill 关键路径测试 18 passed in 0.30s（project-report 4 + summary 3 + obligation 3 + customer-profile 3 + retrospective 3 + 交叉） |

---

# 长期项总清单（2026-11-27 盘点）

> 来源：2026-11-27 全仓只读取证（task-20261127-arch-audit-fix）。本表是「之前提过的所有长期项」的**单一事实源**，与上方 D-/E- 缺陷账本互补（此处多为决策项 / 工程债 / 口径核验，非单点代码缺陷）。
> 状态图例同上。Owner 列「待定」= 需 Rex 拍板归属；证据均为实测，未核实项归入 D 类并标明待核实点。

## A 类 · 待拍板才能动（决策项）

| ID | 事项 | 现状（实测证据） | 需 Rex 拍板 |
|---|---|---|---|
| L-A-01 | Q-2 意图基准集 20 条定标 | `docs/architecture/intent-benchmark-20-calibration.md` 已备 20 条 + 理由，最终 YAML fixture **未生成** | **B-1**（customer-rectification-report 是否算 retrospective 竞品）、**B-4**（system-governor vs dag-orchestrator）、**B-7**（统一入口是否应优先于底层组件）、**A-4**（wecomcli-contact 走自建还是同名 plugin） |
| L-A-02 | 会话中断根因修复 | 压缩截断为主因：日志 13 次 `compaction-safeguard`（多为 `loss=summary-tail`）；`postCompactionMaxChars=40000` 偏小。另有「发消息挤掉维护压缩」（`Session maintenance yielded to a foreground turn`）、子代理超时（`b87fcbb9…` / `af5af78e…` TimeoutError）、transcript 抢写（`SessionTranscriptWriterClaimReboundError`） | 本期 Q-4 冻结 `~/.openclaw/openclaw.json`，故**未改**。是否解冻调大 40000→96000 / `keepRecentTokens` 上调？transcript 按 task_id 分文件是否单独立项？ |
| L-A-03 | 5 份 proposed ADR 定性 | KB：`ADR-202609-024` / `-028` / `-029` / `ADR-202611-036-session-boundary-guard`；arch：`ADR-033-web-ui-design-system` | 各自 accepted 还是 withdrawn？其中 036 尤其卡着——护栏已落地但状态未升 |

## B 类 · 条件具备，可直接开工

| ID | 事项 | 证据 | 建议 |
|---|---|---|---|
| L-B-01 | capability-router 建设 | `ADR-202611-037` 已 accepted，但代码未建；`dag-orchestrator` 有完整执行引擎却**零生产调用方**（引用仅落在自身目录 / registry / 描述性提及） | 走完整生命周期（调研→DESIGN→验收标准→建设→测试→登记），单独立项 |
| L-B-02 | 自建 SKILL.md 依赖门禁未声明 | **口径已修正（2026-11-28）**：顶层 `bins:`/`env:` 并非 SKILL.md 字段，真身是 `metadata.openclaw.requires.{bins,env}`（官方 docs/tools/skills.md §Optional frontmatter keys）。实测 28 份中 16 份有 `metadata.openclaw`、其中仅 8 份声明 `requires`；另 12 份完全无 metadata 块 | **不在本轮盲改**：`requires.bins` 会使缺失二进制的 skill 直接失格（加载期硬门禁），误加会把现有可用 skill 弄成不可见，须逐份核实真实外部依赖后再加。降为 D 类核验项（见 L-D-06） |
| L-B-03 | ones-browser-export 真实 E2E | 同 D-11：仍受登录态 / CDP 阻塞，离线契约已过 | 待专用 CDP 环境，可与其他 E2E 合并排期 |

## C 类 · 外部 / 环境阻塞（留证即可）

| ID | 事项 | 判定 |
|---|---|---|
| L-C-01 | deepseek 两模型 HTTP 402 | 同 E-03：账户额度问题，脚本判定正确，非代码缺陷 |
| L-C-02 | visual 端口撞号 / 服务缺失误报 | E-01、E-06 均已治理，可销账 |
| L-C-03 | openpyxl / pydantic / PyPDF2 弃用告警 | E-05，依赖告警非失败 |

## D 类 · 口径待核实（未下结论，禁止当既成事实引用）

| ID | 事项 | 待核实点 |
|---|---|---|
| L-D-01 | **dreaming 管线「只进不出」**（2026-11-28 定性，真实缺陷） | 实测（md5 逐篇去重）：`light` 83 篇均有内容，含 **7599 条 `- Candidate:` 且全部 `status: staged`**；`deep` 83 篇仅 **3 种内容**（80 篇同一 md5 的固定句「Ranked 0 candidate(s)…Promoted 0…」）；`rem` 83 篇仅 **68 种内容**（16 篇同 md5 的「No strong patterns surfaced.」）。旧记「7499 staged」与实测 7599 为同批数字（口径漂移非矛盾），但「staged 从不 promote」属实 | 待决策：dreaming 的 deep/rem 两层产出高度模板化、且候选无晋级通道——需先定机制（谁来 rank/promote、阈值、去重）再动；属新组件建设，须走完整生命周期 |
| L-D-02 | ~~delivery-quality 闭环是否在跑~~ | **2026-11-28 澄清：按设计已接线，销账**。`record.py` 每次记录后默认 subprocess 调 `review.py`（内置触发，非 cron），AGENTS.md §交付质量反馈闭环明文要求「收到纠正即记录」；实测 `feedback.jsonl` 38 行、`reviews/` 9 份，链路与约定一致 |
| L-D-03 | ~~P6 sha256 语义重复~~ | **2026-11-28 证伪，销账**：`archive.py` 中 `sha256_file()` 仅定义一次，两处调用分别作用于不同文件（`move.dst` 冲突检测 / `mv.src` 入 manifest），非重复实现；所谓「10 处」是把字段名与注释一并计入所致 |
| L-D-04 | ~~kb collectors 重叠~~ | **2026-11-28 查实为伪缺口，销账**：三者职责不同且不重复——`kb_index` 做 frontmatter schema 校验+索引派生（扫 `docs/knowledge-base`）、`lane_d_tasks` 只扫 L2/L3/L4 的 `- [ ]` 未勾选项（不解析 frontmatter）、`system_full_audit` 做全系统计数体检且已复用 `kb_index --stats`；后者 ADR/EXP 计数路径（`KB_DIR/adr`、`KB_DIR/correct`）经核实指向真实目录。无需划边界 |
| L-D-05 | P4 JSON Schema 校验器 | `VERIFICATION-P4` 自留 TODO：`$ref` / `oneOf` 等复杂关键字仍为最小实现 |
| L-D-06 | 12 份自建 SKILL.md 无 `metadata.openclaw` 块 | dag-orchestrator / meeting-minutes / model-scheduling / ocr-digitalization / role-library / system-governor / system-health-check / web-ui-design / contract-approval / bdms-web-ui-design / fin-l4 / ones-browser-export；正文实测用到 openclaw/python3/bash/git/curl/playwright 等外部命令。需逐份判定哪些该升为 `requires`（风险：误加即致失格，见 L-B-02） |

## E 类 · 已闭环可销账

| ID | 事项 | 证据 |
|---|---|---|
| L-E-01 | Q-1 L0-gateway 正式移交运行时原生通道 | `ADR-202611-037-capability-routing-orchestration-layer` accepted（2026-11-27 Rex 拍板）；auth-gateway / channel-router / session-manager 归档为「架构预留 / 参考设计」，骨架保留 |
| L-E-02 | 跨目录 ADR 同号治理 | 提交 `2918ac2`：026 改号 `ADR-202609-030`、035/023 声明权威镜像、`adr_id→id` 归一、`--adr-audit` 接入 pre-commit step 3b、回归 12 例；`--adr-audit` exit=0、阻断错误 0 |
| L-E-03 | 知识库 validate 口径与断链修复 | 提交 `7166df1`：`缺 stage` 检查移入非业务库分支（业务库误报 177→28，剩余 28 份逐份核对确无 dimension）；清零 8 处失效相对链接 + 2 条悬空 ID 引用（EXP-20260903-003/004 号段不存在，改指真实 006~009）；新增回归 4 例（`test_kb_validate_fixes.py`）。全量回归 68 passed |


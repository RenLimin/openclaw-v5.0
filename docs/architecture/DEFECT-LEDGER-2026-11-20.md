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
| D-10 | dag-orchestrator | DAG 执行引擎未实现（SKILL 自身已标 `[ ]`）；定义层/模板达标，运行时未验收 | 🔵 路线图，非缺陷；**2026-11-21 已提交 DESIGN-v1.0.md 草案待 Rex 评审**（自研轻量执行器方案，13 条 hermetic 验收用例；未写代码、未打钩 SKILL.md）；**评审通过前不得当已建成能力调用** |
| D-12 | bangcle-project-report | 新增 `tests/test_render_fail_closed.py`（4 用例）：缺 fetchedAt fail-closed exit=2 + normalize/aggregate 透传 + 带时间戳渲染，防 D-02 复发 | ✅ 已修 2026-11-20：4 passed |
| D-11 | ones-browser-export | 仅离线契约验证，真实浏览器/OA 链路未验 | ⚪ 待有登录态/专用 CDP 时补 E2E |

## 环境性 / 外部（非代码缺陷，仅留证）

| ID | 现象 | 判定 |
|---|---|---|
| E-01 | bangcle-ppt visual 3 failed、fin-l4 visual 14 failed（127.0.0.1:18806 ERR_CONNECTION_REFUSED） | ✅ 已治理（2026-11-21）：共享基类加「服务缺失即 skip」前置守卫，服务未启动不再误报 fail（见修复记录）；功能测试 249/189 全绿 |
| E-06 | visual 套件跨组件**端口撞号**：18801 同时被 bangcle-ppt 与 fin-l4 套件引用、18803/18804 被 delivery-center/office-contract 交叉引用；服务起到 A 端口时 B 套件打 404 | ⚪ 配置/环境类，非本批代码缺陷；重排端口需同步各组件预览脚本+文档，待 Rex 拍板。守卫已确保「服务在但 404」仍真实 fail 不被掩盖（聚合跑 18 failed 即此类，均为 404） |
| E-02 | system-health-check：bdms-web、llama-cpp-embedding Connection refused | ⚪ 真实服务未启动，三态判定正确 |
| E-03 | model-scheduling：deepseek 两模型 HTTP 402 | ⚪ 外部账户额度，脚本判定正确 |
| E-04 | product-manager-expert 检准 1 error：源文件缺失 | ⚪ 真实数据问题，按 SKILL 由维护者补录 |
| E-05 | product-kb/CDI 等 openpyxl/pydantic/PyPDF2 弃用告警 | ⚪ 依赖告警非失败 |
| D-13 | bdms/scripts 历史重复脚本归并 | 34 个 git 跟踪脚本，经只读分析聚类：A 组 ONES 导出 11、B 组认证诊断 9、C 组页面诊断 3、D 组 OA 导出 5、E 组企微/异常 3、F 组报告 2、G 组通用 1 | ⚪ 方案已出（2026-11-21 只读分析报告）：24 个可立即安全归档（前置：同步改 registry supersedes + test_capability_registry 固定输入）；4 个需 Rex 拍板（oa_export_playwright / oa_export_full / export_abnormal_osascript / start_wecom_chrome，被跨组件文档引用）；另发现 registry allow 白名单 2 条幽灵路径。**未执行任何删除/移动** |

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

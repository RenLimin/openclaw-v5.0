# IMPLEMENTATION-PLAN — customer-delivery-intelligence v1.0

- 对应：PRD v1.0 / DESIGN-OUTLINE v1.0 / DESIGN-DETAIL v1.0 / VERIFICATION v1.0 / OPERATIONS v1.0
- 首个实例：中国建设银行（黄金基准）
- 状态：**待 Rex 评审** · 2026-11-10

---

## 1. 总体策略

**先窄后宽、先内后外、先跑通后打磨。**

- Phase 0：骨架 + 基础设施（状态机、检查点、schema 骨架）
- Phase 1：取数 + 解析（从 OA/ONES 直接拿原始文件到 ContractRegister IR）
- Phase 2：汇总 + 成文（六类产物全量生成 + 自校验）
- Phase 3：渲染 + HITL（两道人工闸 + md/docx/PPT 输出）
- Phase 4：E2E + 黄金基准 + 换客户验证

每个 Phase 结束都有明确验收点，不进入下一 Phase 直到当前 Phase 全绿。

## 2. Phase 拆分与工时

### Phase 0：骨架与基础设施（1 天）

| 任务 | 工时 | 产出 | 验收点 |
|---|---|---|---|
| 0.1 目录结构搭建 | 0.5h | 按 DESIGN-DETAIL 的目录结构 | 目录全 + 空文件占位 |
| 0.2 状态机核心实现 | 4h | runner/main.py + state.py，9 状态跃迁 | U2-01/02/06/07 单元测试通过 |
| 0.3 检查点持久化 | 2h | SQLite schema + CRUD | U2-02/07 集成测试通过 |
| 0.4 产物 schema 骨架 | 2h | 六类产物 Pydantic 模型（字段先占位） | schema 校验可运行 |
| 0.5 配置与日志 | 1.5h | config.yaml.example + logging | health 命令可用 |
| **小计** | **10h ≈ 1.25 人日** | | |

### Phase 1：取数 + 解析（2.5 天）

| 任务 | 工时 | 产出 | 验收点 |
|---|---|---|---|
| 1.1 ONES 取数集成 | 4h | 复用 ones-browser-export，封装 step_N2_ones | 取数完整性证据可生成 |
| 1.2 OA 取数集成 | 4h | 复用 clm-oa-recon，封装 step_N2_oa | 合同附件可下载+校验 |
| 1.3 并行取数编排 | 2h | N2 节点：两分支并行 + 结果合并 | 并行执行日志正确 |
| 1.4 Docling/MarkItDown 集成 | 3h | 解析模块：PDF/DOCX → 结构化文本 | 样例合同可解析 |
| 1.5 ContractRegister 抽取 | 5h | 9 大条款维度抽取 + schema 校验 + 重试机制 | U1-11~15 通过 |
| 1.6 血缘标注（Level 2） | 2h | 每条抽取结果带 sourceUri + clauseNo | 字段级 trace 可查 |
| **小计** | **20h ≈ 2.5 人日** | | |

### Phase 2：汇总与成文（2.25 天）

| 任务 | 工时 | 产出 | 验收点 |
|---|---|---|---|
| 2.1 ProjectRegister 派生 | 2h | 从 ContractRegister + ONES raw 生成项目汇总 | 数字自洽 |
| 2.2 PerformanceObligation 识别 | 3h | IFRS15 五步法映射，生成履约义务汇总 | 分摊合计=合同额 |
| 2.3 AcceptanceChecklist 生成 | 3h | 验收条款→三列制核查清单（证据-标准-结论） | 三级结论正确 |
| 2.4 AcceptanceReport 草稿 | 2h | 验收单草稿（签字栏空） | 可导出 md |
| 2.5 PaymentTracker 生成 | 3h | 回款计划 + 账龄 + 逾期 | 账龄合计=未收 |
| 2.6 评估器自校验 | 3h | 数字一致性 + 血缘完整性 + fail-closed | U1-21~24 通过 |
| 2.7 无源项检测（铁律） | 2h | audit.missing_sources 统计 + BLOCK 逻辑 | 无来源字段被拦 |
| **小计** | **18h ≈ 2.25 人日** | | |

### Phase 3：渲染 + 人在环（1.5 天）

| 任务 | 工时 | 产出 | 验收点 |
|---|---|---|---|
| 3.1 md 渲染 | 2h | 六类产物各一份 md，带血缘链接 | 打开可读 |
| 3.2 docx 渲染 | 3h | python-docx + 模板，对内版 + 对外脱敏版 | 排版正确 |
| 3.3 PPT 集成 | 2h | 调用 bangcle-ppt 技能生成汇报 PPT | 10 页内可用 |
| 3.4 HITL gate1 齐套闸 | 2h | 自动校验 + 企微通知 + 决策回执 | U2-04 通过 |
| 3.5 HITL gate2 签发闸 | 2h | 对外稿签发 + 企微通知 + revise 回退 | U2-05 通过 |
| 3.6 受众适配与脱敏 | 1.5h | external 版本脱敏（系统名/商务比例白名单） | 对外版无敏感 |
| **小计** | **12.5h ≈ 1.5 人日** | | |

### Phase 4：E2E + 黄金基准 + 文档（1.5 天）

| 任务 | 工时 | 产出 | 验收点 |
|---|---|---|---|
| 4.1 E2E-01 建行跑通 | 3h | 全链路一次跑通 | E2E-01 全绿 |
| 4.2 黄金基准冻结 | 2h | golden/ccb-2026/v1.0/ | 人工复核签字 |
| 4.3 E2E-02 换客户验证 | 2h | 山东城商行联盟跑通 | 结构一致 |
| 4.4 E2E-03 数据来源验证 | 1.5h | sourceUri 覆盖率 + 抽检 | 100% 有来源 |
| 4.5 SKILL.md 编写 | 2h | L4 SKILL 入口文档 | 可被 PM 专家调用 |
| 4.6 测试报告 + 文档清理 | 2h | 测试报告 + final 文档 | 归档完成 |
| **小计** | **12.5h ≈ 1.5 人日** | | |

## 3. 总工时汇总

| Phase | 工时 | 人日 |
|---|---|---|
| Phase 0 骨架 | 10h | 1.25 |
| Phase 1 取数+解析 | 20h | 2.5 |
| Phase 2 汇总+成文 | 18h | 2.25 |
| Phase 3 渲染+HITL | 12.5h | 1.5 |
| Phase 4 E2E+基准 | 12.5h | 1.5 |
| **总计** | **73h** | **≈ 9 人日** |

> 注：不含前期调研（3 份子代理调研）和文档设计（PRD/OUTLINE/DETAIL/VERIFY/OPS/PLAN）工时。实际开发工作从 Phase 0 开始。

## 4. 里程碑与交付物

| 里程碑 | 时间（从开工算） | 交付物 | 决策点 |
|---|---|---|---|
| M0 设计通过 | Day 0 | 6 份文档全通过 Rex 评审 | 开工 Go/No-Go |
| M1 骨架完成 | Day 1 | 状态机可运行 + schema 骨架 | Phase 0 验收 |
| M2 取数+解析完成 | Day 3.5 | ContractRegister IR + 血缘 | Phase 1 验收 |
| M3 六类产物完成 | Day 5.75 | 六类 md 产物 + 自校验通过 | Phase 2 验收 |
| M4 渲染+HITL 完成 | Day 7.25 | docx/PPT + 两道闸可用 | Phase 3 验收 |
| M5 上线可用 | Day 8.75 | E2E 全绿 + 黄金基准 + SKILL | 正式交付 |

## 5. 风险与对策

| 风险 | 概率 | 影响 | 对策 |
|---|---|---|---|
| OA/ONES UI 变化，选择器失效 | 中 | 中 | 启动 browser-use 兜底；同步更新 Playwright 脚本 |
| 合同解析准确率不够（<90%） | 中 | 高 | 先跑建行黄金基准，校准 prompt；低置信度字段标 needs_human |
| Docling 依赖重 / 安装失败 | 低 | 中 | 备选 MarkItDown + 纯文本解析降级路径 |
| 人在环体验差（通知看不到） | 低 | 中 | 同时支持企微通知 + CLI 决策 + web 状态页 |
| 数据量超预期，性能问题 | 低 | 低 | 当前量级分钟级；若未来增长，迁 Temporal 适配面 |
| 安全合规问题（数据出境） | 低 | 高 | Docling/MarkItDown 全部本地运行；OCR 不用云服务 |

## 6. 依赖与前置

- **硬依赖**：ones-browser-export、clm-oa-recon、contract-manager-expert、bangcle-contract、bangcle-project-report、bangcle-ppt、bdms-revenue-forecast（均已存在）
- **新依赖**：docling、markitdown、pydantic（Python 包）
- **环境依赖**：Playwright + Chromium、企微机器人 webhook
- **外部系统**：OA（合同/验收/附件）、ONES（项目/工作项/附件）

## 7. 验收清单（交付时逐项勾）

- [ ] Phase 0 骨架：U2 集成测试全通过
- [x] Phase 1 取数+解析：建行合同可解析到 ContractRegister，100% 字段有 sourceUri
- [x] Phase 2 汇总成文：六类产物 schema 全通过，数字自洽，无源项=0
- [ ] Phase 3 渲染+HITL：docx/PPT 排版正确，两道闸可正常交互
- [ ] E2E-01 建行全链路通过
- [ ] E2E-02 换客户结构一致
- [ ] E2E-03 数据来源铁律验证通过
- [ ] 黄金基准冻结 v1.0
- [ ] SKILL.md 可被 L4 专家入口调用
- [x] 文档齐全（PRD/OUTLINE/DETAIL/VERIFY/OPS/PLAN）

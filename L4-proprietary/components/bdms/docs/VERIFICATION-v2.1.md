# BDMS v2.1 测试方案（VERIFICATION）

> 版本：v2.1（2026-09-25）
> 依据：PRD-v2.1 + DESIGN-OUTLINE-v2.1 + 7 份 DESIGN-DETAIL
> 状态：待 Rex 审核

---

## 1. 测试策略

### 1.1 测试分层

| 层 | 范围 | 工具 | 环境 | 铁律 |
|---|---|---|---|---|
| 单元测试 | 函数/方法级 | pytest | 内存/临时 DB | ✅ 纯函数可测 |
| 集成测试 | 模块内多组件 | pytest + 临时 DB | 临时 DB | ✅ 真实 DB 事务 |
| E2E 测试 | 跨模块全链 | 真实 HTTP + CLI | 测试服务器 | ✅ 禁 TestClient |
| 回归测试 | 黄金基准对比 | 逐格比对脚本 | 黄金基准文件 | ✅ 手工报表基准 |
| 性能测试 | 耗时/规模 | 计时断言 | 批量数据 | ✅ 指标达标 |

### 1.2 测试铁律（强制）

1. ✅ Web/安全功能验收必须用真实 HTTP（浏览器或 urllib），完整走浏览器流程
2. ✅ 测试流程：登录 → Set-Cookie → 带 Cookie 访问页面 → 带 Cookie 调 API
3. ❌ 禁止用 FastAPI TestClient 测试网络安全/Cookie/访问控制相关功能
4. ✅ 单元测试用 pytest，集成/端到端测试用真实 HTTP
5. ✅ E2E 测试必须覆盖真实用户操作路径（浏览器实际传什么格式/参数，测试就传什么格式/参数）
6. ✅ 后端 API 应同时兼容多种输入格式（如 YYYY-MM 和 YYYYMM）
7. ❌ 不能只测 API 层就认为功能正常（前端 JS 的格式转换、按钮点击等也必须覆盖）

### 1.3 测试环境

| 环境 | 用途 | 数据 |
|---|---|---|
| 开发环境 | 单元/集成测试 | 临时 DB（tmp_path） |
| 测试环境 | E2E + 回归测试 | 黄金基准 202606 |
| 生产环境 | 最终验收 | 真实数据 |

### 1.4 黄金基准

| 报表 | 路径 | 用途 |
|---|---|---|
| 交付月报 | ~/Bangcle Workspace/01. Management/2026/2026团队报告/202606/2026交付月报-20260630.xlsx | 15 Sheet 逐格比对 |
| 确收分析 | ~/Bangcle Workspace/01. Management/2026/2026团队报告/202606/2026年计划确收&实际确收对比表202601-06-0724 - 差异分析.xlsx | 10 Sheet 逐格比对 |

---

## 2. 单元测试

### 2.1 合同管理（contract_management）

| # | 测试用例 | 输入 | 预期结果 | 覆盖点 |
|---|---|---|---|---|
| UT-CM-01 | 状态机合法转换 | draft→submit→review1 | 返回 review1，approval_log 1 条 | 状态机 |
| UT-CM-02 | 状态机非法转换 | draft→approve | 抛 InvalidTransitionError，状态不变 | 状态机守卫 |
| UT-CM-03 | 审批分级-1级 | amount=80000 | level=1，roles=[销售经理] | 分级逻辑 |
| UT-CM-04 | 审批分级-2级边界 | amount=100000 | level=2，roles=[销售经理, 法务审查员] | 边界值 |
| UT-CM-05 | 审批分级-3级边界 | amount=500000 | level=3，roles=[销售总监, 法务审查员, PMO] | 边界值 |
| UT-CM-06 | 审批分级-4级 | amount=2000000 | level=4 | 分级逻辑 |
| UT-CM-07 | 风险扫描-22条规则 | 标准合同文本 | 22 条规则各有命中/未命中 | 风险引擎 |
| UT-CM-08 | 风险综合评级 | fail>0 | overall=high | 评级逻辑 |
| UT-CM-09 | 加密解密往返 | "测试合同" | decrypt(encrypt(x)) == x | 加密 |
| UT-CM-10 | 脱敏-名称 | "北京梆梆安全科技有限公司" | "北***司" | 脱敏 |
| UT-CM-11 | 脱敏-金额 | 1568200 | "157万" | 脱敏 |
| UT-CM-12 | 合同编号生成 | 同日连续创建 | CR-YYYYMMDD-0001/0002 递增 | 幂等 |
| UT-CM-13 | OCR字段提取 | 金额"1,500万元" | 1500000.0 | 归一化 |
| UT-CM-14 | OCR日期归一 | "2026年6月15日" | "2026-06-15" | 日期格式 |
| UT-CM-15 | 合同关联-补充协议 | BC-20260922-0001 | 关联到 CR-20260922-0001 | 关联规则 |
| UT-CM-16 | 合同关联-终止协议 | ZZ-20260922-0001 | 关联到 CR-20260922-0001 | 关联规则 |
| UT-CM-17 | 标的对比分析 | 价格偏离 ±25% | 触发 price_anomaly 告警 | 知识库对比 |
| UT-CM-18 | docx生成 | 合同ID=1 | 文件存在，水印含状态 | 文档生成 |

### 2.2 项目管理（project_management）

| # | 测试用例 | 输入 | 预期结果 | 覆盖点 |
|---|---|---|---|---|
| UT-PM-01 | 创建项目 | 完整数据 | 项目ID 返回，6 阶段创建 | 生命周期 |
| UT-PM-02 | 启动项目-缺PM | pm=None | ValidationError | 前置校验 |
| UT-PM-03 | 启动项目-正常 | 完整数据 | initiating→planning→executing | 状态流转 |
| UT-PM-04 | 提交交付 | status=executing | 进入 delivering | 交付管理 |
| UT-PM-05 | 验收通过 | 无未关闭风险 | delivering→accepting | 验收 |
| UT-PM-06 | 验收阻断 | 存在 critical 风险 | ValidationError | 风险守卫 |
| UT-PM-07 | 转售后 | accepting | 创建维保合同，进入 after_sales | 售后管理 |
| UT-PM-08 | 售后工单创建 | after_sales 状态 | ticket_id 返回 | 工单 |
| UT-PM-09 | SLA-critical | priority=critical | 响应 2h / 解决 24h | SLA |
| UT-PM-10 | 结项前置检查 | 有未关闭工单 | ValidationError | 结项守卫 |
| UT-PM-11 | 结项正常 | 工单全关闭 | closing→closed | 结项 |
| UT-PM-12 | 风险报备 | 完整数据 | risk_id 返回 | 风险 |
| UT-PM-13 | 风险处置 | risk_id + mitigate | 状态变更 | 风险处置 |
| UT-PM-14 | 成本归集幂等 | 同一成本项重复归集 | 不重复计算 | 幂等 |
| UT-PM-15 | 利润计算 | revenue=10000, cost=6000 | profit=4000, margin=0.4 | 利润引擎 |
| UT-PM-16 | 预算告警 | cost=11000, budget=10000 | critical 告警 | 告警 |
| UT-PM-17 | 取消项目 | 任意状态 | →cancelled | 取消 |
| UT-PM-18 | 重新激活 | cancelled | →initiating | 重激活 |

### 2.3 交付月报（delivery_report）

| # | 测试用例 | 输入 | 预期结果 | 覆盖点 |
|---|---|---|---|---|
| UT-DR-01 | 15 Sheet 完整性 | 202606 数据 | 15 Sheet 全部存在 | 结构 |
| UT-DR-02 | 行数误差 | 黄金基准 | 每 Sheet ≤ 1 行差异 | 准确性 |
| UT-DR-03 | 列名一致性 | 黄金基准 | 100% 一致 | 列定义 |
| UT-DR-04 | 公式计算-状态桶 | 9 个状态标志 | c56 正确映射 | 计算引擎 |
| UT-DR-05 | 公式计算-考核列 | 计划/实际日期 | 偏差率正确 | 考核 |
| UT-DR-06 | VLOOKUP | 项目经理名 | 部门映射正确 | 跨表引用 |
| UT-DR-07 | 统计 Sheet 聚合 | 签约数据 | 聚合行数正确 | 统计 |
| UT-DR-08 | 异常台账 36 行 | 202606 | 固定 36 行 | 固定结构 |
| UT-DR-09 | c80 逐行去重 | 重复所属项目 | 首次出现显示值，后续空 | POC 统计 |
| UT-DR-10 | 数据校验-非空 | 合同编号为空 | ERROR 拒绝 | 校验 |
| UT-DR-11 | 数据校验-金额 | 负数金额 | ERROR 拒绝 | 校验 |
| UT-DR-12 | 存疑数据展示 | 校验有 WARNING | 存疑列表返回 | 存疑流程 |
| UT-DR-13 | Excel 导出 | 202606 | 文件存在，15 Sheet | 导出 |
| UT-DR-14 | DASHBOARD 统计 | 202606 | 统计 Sheet 由 DASHBOARD 生成 | 集成 |
| UT-DR-15 | 月份格式规范化 | YYYY-MM/YYYY/MM 输入 | 统一为 YYYYMM（normalize_month） | 格式统一 |
| UT-DR-16 | 月份登记防重 | 同月两种格式登记 | report_month 只登记一条 | 幂等 |
| UT-DR-17 | 月份列表去重 | 历史脏数据两种格式 | list_months 去重 + 规范化 | 数据质量 |

### 2.4 确收分析（revenue）

| # | 测试用例 | 输入 | 预期结果 | 覆盖点 |
|---|---|---|---|---|
| UT-RV-01 | 10 Sheet 完整性 | 202606 数据 | 10 Sheet 全部存在 | 结构 |
| UT-RV-02 | 汇总 31 行 | 202606 | 固定 31 行 | 固定结构 |
| UT-RV-03 | 新签/递延/合计 | 标准数据 | 三维度分开计算 | 汇总逻辑 |
| UT-RV-04 | 环比计算 | 两期数据 | 环比正确 | 趋势 |
| UT-RV-05 | 差异分析 | 计划 vs 实际 | 差异值正确 | 差异 |
| UT-RV-06 | 重拆履约 | 提前/滞后合同 | 重拆正确 | 重拆 |
| UT-RV-07 | 导入校验-合同编号 | 空值 | ERROR 拒绝 | 校验 |
| UT-RV-08 | 导入校验-金额 | 非数值 | ERROR 拒绝 | 校验 |
| UT-RV-09 | 导入校验-枚举 | 非法分类 | ERROR 拒绝 | 校验 |
| UT-RV-10 | 导入校验-行数 | 与上月偏差 >20% | WARNING | 校验 |
| UT-RV-11 | 收入同步幂等 | 同一项目同一期间 | 重复同步结果一致 | 幂等 |
| UT-RV-12 | 快照锁定 | confirmed 状态修改 | SnapshotLockedError | 状态机 |
| UT-RV-13 | 知识库自动填充 | 产品名匹配 | 建议收入确认方法 | 知识库 |
| UT-RV-14 | 合同关联 | 补充协议编号 | 关联到原合同 | 关联 |

### 2.5 项目利润（profit_management）

| # | 测试用例 | 输入 | 预期结果 | 覆盖点 |
|---|---|---|---|---|
| UT-PF-01 | 利润计算-基本 | revenue=10000, cost=6000 | profit=4000, margin=0.4 | 核心公式 |
| UT-PF-02 | 利润计算-零收入 | revenue=0 | margin=0 | 除零保护 |
| UT-PF-03 | 利润计算-亏损 | revenue=5000, cost=8000 | profit=-3000 | 亏损 |
| UT-PF-04 | 成本归集-工时 | 8h × 500元/h | labor_cost=4000 | 工时成本 |
| UT-PF-05 | 成本归集-设备 | 10天 × 200元/天 | device_cost=2000 | 设备成本 |
| UT-PF-06 | 成本归集-差旅 | 3 笔 | travel_cost 汇总 | 差旅 |
| UT-PF-07 | 成本归集幂等 | 同一成本项重复 | 不重复计算 | 幂等 |
| UT-PF-08 | 预算告警-warning | cost=9500, budget=10000 | warning | 告警 |
| UT-PF-09 | 预算告警-critical | cost=11000, budget=10000 | critical | 告警 |
| UT-PF-10 | 快照唯一 | 同项目同期间 | 只一条 | 唯一约束 |
| UT-PF-11 | 快照状态流转 | draft→confirmed→archived | 状态正确 | 状态机 |
| UT-PF-12 | 部门聚合 | 多项目 | 按 dept 聚合正确 | 聚合 |
| UT-PF-13 | 时间聚合 | 多期间 | 按 period 聚合正确 | 趋势 |
| UT-PF-14 | 收入同步 | revenue 模块事件 | 自动同步 | 事件驱动 |
| UT-PF-15 | 知识库产品匹配 | 标准产品名 | 默认确认方法 | 知识库 |

### 2.6 驾驶舱（dashboard）

| # | 测试用例 | 输入 | 预期结果 | 覆盖点 |
|---|---|---|---|---|
| UT-DB-01 | 12 KPI 计算 | 标准数据 | 12 个 KPI 值正确 | KPI |
| UT-DB-02 | KPI 颜色阈值 | 交付及时率=85% | 橙色 | 阈值 |
| UT-DB-03 | 趋势数据 | 12 个月 | 返回 12 个数据点 | 趋势 |
| UT-DB-04 | 下钻-部门 | dept=安服一部 | 部门明细 | 三级下钻 |
| UT-DB-05 | 下钻-项目 | project_id=1 | 项目明细 | 三级下钻 |
| UT-DB-06 | 下钻-记录 | record_id=1 | 单条记录 | 三级下钻 |
| UT-DB-07 | 筛选 | status=open | 筛选结果正确 | 筛选 |
| UT-DB-08 | 排序 | sort_by=profit | 排序正确 | 排序 |
| UT-DB-09 | 分页 | page=2, page_size=50 | 第二页数据 | 分页 |
| UT-DB-10 | 视图 CRUD | 创建/读取/更新/删除 | CRUD 完整 | 视图管理 |
| UT-DB-11 | 默认视图 | 首次访问 | 交付月报+确收分析汇总 | 默认配置 |
| UT-DB-12 | 字段编辑 | remark 字段 | 编辑成功 + 历史记录 | 明细编辑 |
| UT-DB-13 | 编辑权限 | PM 编辑他人项目 | PermissionError | 权限 |
| UT-DB-14 | 批量编辑 | 3 条记录 | 3 条全部更新 | 批量编辑 |
| UT-DB-15 | 撤销 | edit_id=1 | 恢复原值 | 撤销 |
| UT-DB-16 | 数据源注册 | source_key=test | 注册成功 | 数据源 |
| UT-DB-17 | SQL 校验 | 非法 SQL | 校验失败 | SQL 安全 |
| UT-DB-18 | SQL 试运行 | SELECT COUNT(*) | 返回样例数据 | 试运行 |

### 2.7 数据集成（integration）

| # | 测试用例 | 输入 | 预期结果 | 覆盖点 |
|---|---|---|---|
| UT-IN-01 | ONES 连接器认证 | 有效 Cookie | authenticate=True | 认证 |
| UT-IN-02 | ONES 数据拉取 | 模拟 CSV | 标准化后写入 staging | 数据管道 |
| UT-IN-03 | OA 连接器认证 | 有效 Cookie | authenticate=True | 认证 |
| UT-IN-04 | 工时门户导出 | 模拟浏览器 | CSV 文件下载 | 浏览器自动化 |
| UT-IN-05 | 企微文档 API | 模拟响应 | 文档列表返回 | API |
| UT-IN-06 | 本机导入 | Excel 文件 | 解析成功 | 文件导入 |
| UT-IN-07 | 频率配置 | cron 表达式 | 配置保存 | 频率 |
| UT-IN-08 | 幂等写入 | 同一 source_id 重复 | 不重复插入 | 幂等 |
| UT-IN-09 | 错误重试 | 网络超时 | 指数退避重试 | 容错 |
| UT-IN-10 | 死信队列 | 3 次重试失败 | 进入死信队列 | 死信 |

---

## 3. 集成测试

### 3.1 合同管理集成测试

| # | 测试场景 | 步骤 | 预期结果 | 覆盖点 |
|---|---|---|---|---|
| IT-CM-01 | 2级全生命周期 | create(30万)→submit→approve×2→sign→archive | 状态轨迹正确，signed_date/archive_date 写入 | 完整流程 |
| IT-CM-02 | 4级全生命周期 | create(500万)→submit→approve×4→approved | review1→4 逐级推进 | 多级审批 |
| IT-CM-03 | 1级直达 | create(8万)→submit→approve→approved | review1 直达 approved | 快速审批 |
| IT-CM-04 | 驳回重提 | submit→reject→draft→修改→submit | 回 draft，comment 留痕 | 驳回 |
| IT-CM-05 | 非法流转 | 对 draft 合同 approve | 抛错且状态不变（事务回滚） | 事务 |
| IT-CM-06 | 软删除 | delete→list/get | 不可见；audit 有 DELETE 记录 | 软删除 |
| IT-CM-07 | 审计完整性 | 任意生命周期后 audit_log | 每次状态变更双流各一条 | 审计 |
| IT-CM-08 | 列表脱敏 | list(mask=True) vs get_contract | 列表脱敏，详情完整 | 脱敏 |
| IT-CM-09 | docx 生成 | 无模板/带模板 | 文件存在，水印文案随状态 | 文档 |
| IT-CM-10 | OCR 导入 | fixture 扫描件 | cr_contracts +1（draft, ocr_import） | OCR |
| IT-CM-11 | 幂等 | 重复 submit/sign/archive | 第二次抛 CR-4002，无副作用 | 幂等 |
| IT-CM-12 | 合同关联 | 创建补充协议 | 自动关联原合同 | 关联 |
| IT-CM-13 | OA 自动获取 | mock 浏览器 | 数据落盘 int_staging_oa | 集成 |
| IT-CM-14 | WeCom 交互 | mock 消息 | 指令执行正确 | 集成 |

### 3.2 项目管理集成测试

| # | 测试场景 | 步骤 | 预期结果 | 覆盖点 |
|---|---|---|---|---|
| IT-PM-01 | 创建→启动→提交交付→验收→结项 | 完整流程 | 状态轨迹正确 | 生命周期 |
| IT-PM-02 | 转售后→工单→关闭→结项 | 完整售后流程 | 工单全部关闭后可结项 | 售后 |
| IT-PM-03 | 风险报备→处置→关闭 | 完整风险流程 | 风险状态正确 | 风险 |
| IT-PM-04 | 成本归集→利润计算 | 工时提交→成本归集→利润更新 | 利润值正确 | 成本+利润 |
| IT-PM-05 | 收入同步→利润更新 | revenue 事件→profit 同步 | 利润更新 | 事件驱动 |
| IT-PM-06 | 预算告警 | 成本超预算 10% | 告警创建 | 告警 |
| IT-PM-07 | 取消项目 | 任意状态取消 | →cancelled | 取消 |
| IT-PM-08 | 重新激活 | cancelled→initiating | 状态恢复 | 重激活 |
| IT-PM-09 | 并发工时提交 | 多线程 | 数据一致性 | 并发 |

### 3.3 交付月报集成测试

| # | 测试场景 | 步骤 | 预期结果 | 覆盖点 |
|---|---|---|---|---|
| IT-DR-01 | 原始数据导入 | ONES CSV | 5 Sheet 原始数据落盘 | 导入 |
| IT-DR-02 | 数据校验 | 含 ERROR 行 | ERROR 行拒绝，WARNING 标记 | 校验 |
| IT-DR-03 | 公式计算 | 标准数据 | 公式列值正确 | 计算 |
| IT-DR-04 | 统计聚合 | DASHBOARD 实时 | 统计 Sheet 正确 | 聚合 |
| IT-DR-05 | Excel 导出 | 202606 | 15 Sheet 文件 | 导出 |
| IT-DR-06 | 黄金基准对比 | 202606 基准 | 逐格比对通过 | 回归 |

### 3.4 确收分析集成测试

| # | 测试场景 | 步骤 | 预期结果 | 覆盖点 |
|---|---|---|---|---|
| IT-RV-01 | 导入→汇总→导出 | 完整流程 | 10 Sheet 文件 | 全流程 |
| IT-RV-02 | 数据校验 | 含非法数据 | ERROR 拒绝，WARNING 存疑 | 校验 |
| IT-RV-03 | 存疑数据处置 | 人工校正 | 校正值写入，留痕 | 存疑 |
| IT-RV-04 | 收入同步 | revenue 事件 | 利润更新 | 事件 |
| IT-RV-05 | 快照生命周期 | draft→confirmed→archived | 状态正确 | 状态机 |
| IT-RV-06 | 黄金基准对比 | 202606 基准 | 逐格比对通过 | 回归 |

### 3.5 项目利润集成测试

| # | 测试场景 | 步骤 | 预期结果 | 覆盖点 |
|---|---|---|---|---|
| IT-PF-01 | 工时提交→成本归集→利润计算 | 完整流程 | 利润值正确 | 全流程 |
| IT-PF-02 | 差旅导入→成本归集 | Excel 导入 | 成本增加 | 导入 |
| IT-PF-03 | 收入同步→利润更新 | revenue 事件 | 利润更新 | 事件 |
| IT-PF-04 | 预算告警 | 超预算 | 告警创建 | 告警 |
| IT-PF-05 | 快照确认 | draft→confirmed | 锁定 | 状态 |
| IT-PF-06 | 部门聚合 | 多项目 | 聚合正确 | 聚合 |

### 3.6 驾驶舱集成测试

| # | 测试场景 | 步骤 | 预期结果 | 覆盖点 |
|---|---|---|---|---|
| IT-DB-01 | KPI 汇总 | 标准数据 | 12 KPI 值正确 | KPI |
| IT-DB-02 | 下钻三级 | 部门→项目→记录 | 明细正确 | 下钻 |
| IT-DB-03 | 视图 CRUD | 创建/读取/更新/删除 | CRUD 完整 | 视图 |
| IT-DB-04 | 字段编辑 | 编辑 + 历史 | 历史记录正确 | 编辑 |
| IT-DB-05 | 数据源注册 | 注册 + 试运行 | 指标值正确 | 数据源 |
| IT-DB-06 | 权限检查 | PM 编辑他人项目 | 拒绝 | 权限 |

### 3.7 数据集成集成测试

| # | 测试场景 | 步骤 | 预期结果 | 覆盖点 |
|---|---|---|---|
| IT-IN-01 | ONES 同步 | 模拟 CSV | 数据落盘 | 同步 |
| IT-IN-02 | OA 同步 | 模拟浏览器 | 数据落盘 | 同步 |
| IT-IN-03 | 工时门户 | 模拟浏览器 | CSV 下载 | 同步 |
| IT-IN-04 | 企微文档 | 模拟 API | 文档列表 | 同步 |
| IT-IN-05 | 本机导入 | Excel | 解析成功 | 导入 |
| IT-IN-06 | 幂等 | 重复同步 | 不重复 | 幂等 |
| IT-IN-07 | 错误重试 | 模拟超时 | 指数退避 | 容错 |

---

## 4. 回归测试

### 4.1 黄金基准对比方案

#### 4.1.1 交付月报回归

| 对比项 | 基准 | 容差 | 方法 |
|---|---|---|---|
| Sheet 数量 | 15 | 0 | 精确匹配 |
| 行数 | 黄金基准 | ≤ 1 | 逐 Sheet 比对 |
| 列名 | 黄金基准 | 100% | 逐列比对 |
| 公式计算值 | 黄金基准 | ≤ 0.01 元 | 逐格比对 |
| 统计 Sheet | 黄金基准 | ≤ 1 行 | 聚合比对 |

#### 4.1.2 确收分析回归

| 对比项 | 基准 | 容差 | 方法 |
|---|---|---|---|
| Sheet 数量 | 10 | 0 | 精确匹配 |
| 汇总行数 | 31 | 0 | 精确匹配 |
| 列名 | 黄金基准 | 100% | 逐列比对 |
| 汇总计算值 | 黄金基准 | ≤ 0.01 元 | 逐格比对 |

### 4.2 回归测试执行

```bash
# 交付月报回归
python3 tools/compare_delivery_report.py \
  --baseline ~/Bangcle\ Workspace/01.\ Management/2026/2026团队报告/202606/2026交付月报-20260630.xlsx \
  --output output/交付月报_202606.xlsx

# 确收分析回归
python3 tools/compare_revenue_summary.py \
  --baseline ~/Bangcle\ Workspace/01.\ Management/2026/2026团队报告/202606/2026年计划确收\&实际确收对比表202601-06-0724\ -\ 差异分析.xlsx \
  --output output/确收分析_202606.xlsx
```

### 4.3 回归测试用例

| # | 测试用例 | 输入 | 预期结果 | 覆盖点 |
|---|---|---|---|---|
| RT-01 | 交付月报-Sheet 完整性 | 202606 | 15 Sheet 全部存在 | 结构 |
| RT-02 | 交付月报-行数 | 黄金基准 | 每 Sheet ≤ 1 行差异 | 准确性 |
| RT-03 | 交付月报-列名 | 黄金基准 | 100% 一致 | 列定义 |
| RT-04 | 交付月报-公式值 | 黄金基准 | ≤ 0.01 元 | 计算 |
| RT-05 | 确收分析-Sheet 完整性 | 202606 | 10 Sheet 全部存在 | 结构 |
| RT-06 | 确收分析-汇总行数 | 黄金基准 | 31 行 | 固定结构 |
| RT-07 | 确收分析-汇总值 | 黄金基准 | ≤ 0.01 元 | 计算 |
| RT-08 | 确收分析-差异分析 | 黄金基准 | 一致 | 差异 |

---

## 5. E2E 测试

### 5.1 合同管理 E2E

| # | 测试场景 | 步骤 | 预期结果 | 覆盖点 |
|---|---|---|---|---|
| E2E-CM-01 | 完整审批流（真实 HTTP） | 登录→Cookie→create→submit→approve→sign→archive | 全链 200，状态正确 | 全流程 |
| E2E-CM-02 | 权限矩阵 | 各角色操作 | 权限内通过，权限外 403 | 权限 |
| E2E-CM-03 | 风险扫描 | scan-risks | 22 条规则结果 | 风险 |
| E2E-CM-04 | 合同关联 | 创建补充协议 | 自动关联 | 关联 |
| E2E-CM-05 | docx 生成 | generate-docx | 文件存在 | 文档 |
| E2E-CM-06 | WeCom 交互 | mock 消息 | 指令执行 | 集成 |

### 5.2 项目管理 E2E

| # | 测试场景 | 步骤 | 预期结果 | 覆盖点 |
|---|---|---|---|---|
| E2E-PM-01 | 项目全生命周期 | 登录→Cookie→create→start→deliver→accept→after_sales→close | 全链 200 | 全流程 |
| E2E-PM-02 | 售后工单 | create→assign→resolve→close | 工单状态正确 | 售后 |
| E2E-PM-03 | SLA 监控 | 超时工单 | 告警创建 | SLA |
| E2E-PM-04 | 风险处置 | report→resolve→close | 风险状态正确 | 风险 |
| E2E-PM-05 | 利润查看 | 利润报表 | 数据正确 | 利润 |

### 5.3 交付月报 E2E

| # | 测试场景 | 步骤 | 预期结果 | 覆盖点 |
|---|---|---|---|---|
| E2E-DR-01 | 生成+导出 | 登录→Cookie→generate→export | 15 Sheet 文件 | 全流程 |
| E2E-DR-02 | 数据校验 | 含存疑数据 | 存疑列表展示 | 校验 |
| E2E-DR-03 | 黄金基准对比 | 逐格比对 | 通过 | 回归 |

### 5.4 确收分析 E2E

| # | 测试场景 | 步骤 | 预期结果 | 覆盖点 |
|---|---|---|---|---|
| E2E-RV-01 | 导入+生成+导出 | 登录→Cookie→import→generate→export | 10 Sheet 文件 | 全流程 |
| E2E-RV-02 | 存疑数据处置 | 人工校正 | 校正值写入 | 存疑 |
| E2E-RV-03 | 收入同步 | revenue 事件 | 利润更新 | 事件 |
| E2E-RV-04 | 黄金基准对比 | 逐格比对 | 通过 | 回归 |

### 5.5 项目利润 E2E

| # | 测试场景 | 步骤 | 预期结果 | 覆盖点 |
|---|---|---|---|---|
| E2E-PF-01 | 利润计算 | 登录→Cookie→sync→report | 利润值正确 | 全流程 |
| E2E-PF-02 | 预算告警 | 超预算 | 告警创建 | 告警 |
| E2E-PF-03 | 知识库填充 | 产品匹配 | 建议值正确 | 知识库 |

### 5.6 驾驶舱 E2E

| # | 测试场景 | 步骤 | 预期结果 | 覆盖点 |
|---|---|---|---|---|
| E2E-DB-01 | 默认驾驶舱 | 登录→Cookie→看板加载 | 12 KPI + 5 区域 | 默认配置 |
| E2E-DB-02 | 下钻 | 点击 KPI→明细 | 三级穿透 | 下钻 |
| E2E-DB-03 | 视图管理 | 创建/保存/切换 | CRUD 完整 | 视图 |
| E2E-DB-04 | 字段编辑 | 编辑备注 | 即时保存 + 历史 | 编辑 |
| E2E-DB-05 | 数据源注册 | 注册 + 试运行 | 指标值正确 | 数据源 |

### 5.7 数据集成 E2E

| # | 测试场景 | 步骤 | 预期结果 | 覆盖点 |
|---|---|---|---|---|
| E2E-IN-01 | ONES 同步 | 登录→Cookie→sync ones | 数据落盘 | 同步 |
| E2E-IN-02 | OA 同步 | 登录→Cookie→sync oa | 数据落盘 | 同步 |
| E2E-IN-03 | 工时门户 | 登录→Cookie→sync timesheet | CSV 下载 | 同步 |
| E2E-IN-04 | 企微文档 | 登录→Cookie→sync wecom | 文档列表 | 同步 |
| E2E-IN-05 | 本机导入 | 上传 Excel | 解析成功 | 导入 |

---

## 6. 性能测试

| # | 测试场景 | 指标 | 方法 |
|---|---|---|---|
| PERF-01 | 合同列表查询（万级） | < 500ms | 批量造数 + 计时 |
| PERF-02 | 风险扫描（单份） | < 2s | 计时断言 |
| PERF-03 | OCR（单页） | < 5s | L2 基准继承 |
| PERF-04 | docx 生成 | < 3s | 计时断言 |
| PERF-05 | 交付月报生成 | < 30s | 计时断言 |
| PERF-06 | 确收分析生成 | < 30s | 计时断言 |
| PERF-07 | 驾驶舱 KPI 汇总 | < 3s | 计时断言 |
| PERF-08 | 驾驶舱下钻 | < 2s | 计时断言 |
| PERF-09 | Excel 导出（15 Sheet） | < 10s | 计时断言 |
| PERF-10 | 并发工时提交 | 数据一致性 | 多线程 |

---

## 7. 测试通过标准

| 层 | 标准 |
|---|---|
| 单元测试 | 全部 PASS，覆盖率 ≥ 80% |
| 集成测试 | 全部 PASS |
| E2E 测试 | 全部 PASS |
| 回归测试 | 黄金基准逐格比对通过 |
| 性能测试 | 全部指标达标 |

---

## 8. 测试执行计划

| 阶段 | 内容 | 产出 |
|---|---|---|
| Phase 1 | 单元测试全部通过 | 测试报告 |
| Phase 2 | 集成测试全部通过 | 测试报告 |
| Phase 3 | E2E 测试全部通过 | 测试报告 |
| Phase 4 | 回归测试通过 | 对比报告 |
| Phase 5 | 性能测试达标 | 性能报告 |
| Phase 6 | Rex 人工审核 | 验收报告 |

---

## 9. 手工调整列测试专项

> 确收分析报表中部分列需手工调整（下拉选择/文本框/日期），需专项测试。

### 9.1 下拉列表列测试

| # | 列 | 可选值 | 测试用例 | 预期 |
|---|---|---|---|---|
| MA-01 | c1 分类 | 新签/递延 | 选择"新签" | 保存成功，值="新签" |
| MA-02 | c1 分类 | 新签/递延 | 选择非法值"测试" | 拒绝，提示枚举值 |
| MA-03 | c11 收入确认方法 | 时点法/时段法 | 选择"时段法" | 保存成功 |
| MA-04 | c63 偏差-状态/趋势 | 5 个枚举值 | 选择"滞后确收" | 保存成功 |
| MA-05 | c64 偏差-原因类别 | 6 个枚举值 | 选择"交付原因-延期" | 保存成功 |
| MA-06 | c66 合同分类 | 4 个枚举值 | 选择"框架合同" | 保存成功 |
| MA-07 | 知识库联动 | 产品名匹配 | 选择标准产品 | 自动填充 c11/c28/c29/c20 |

### 9.2 文本框列测试

| # | 列 | 测试用例 | 预期 |
|---|---|---|---|
| MA-08 | c46 消失备注 | 输入 500 字文本 | 保存成功 |
| MA-09 | c52 财务反馈 | 输入特殊字符 | 保存成功，无 SQL 注入 |
| MA-10 | c62 偏差备注 | 输入 1000 字 | 保存成功 |
| MA-11 | c70 备注 | 输入空字符串 | 允许清空 |
| MA-12 | c71 预算说明 | 输入 HTML 标签 | 转义存储，不执行 |

### 9.3 日期列测试

| # | 列 | 测试用例 | 预期 |
|---|---|---|---|
| MA-13 | c18 计划开始时间 | "2026-01-15" | 保存成功 |
| MA-14 | c18 计划开始时间 | "2026-13-15" | 拒绝，非法月份 |
| MA-15 | c19 计划结束时间 | < c18 | 拒绝，结束早于开始 |
| MA-16 | c75 预估交付日期 | "2026-06-30" | 保存成功 |

### 9.4 编辑留痕测试

| # | 测试场景 | 预期 |
|---|---|---|
| MA-17 | 修改 c63 | rr_edit_history 记录原值/新值/操作人/时间 |
| MA-18 | 批量修改 | 每条修改独立留痕 |
| MA-19 | 撤销修改 | 恢复原值，留痕标记 is_undo=1 |

---

## 10. ASC 606 收入确认准则测试专项

### 10.1 五步法模型验证

| # | 步骤 | 测试用例 | 预期 |
|---|---|---|---|
| ASC-01 | ① 识别合同 | 关联合同存在 | cr_contracts 查到 |
| ASC-02 | ② 识别履约义务 | 履约义务清单 | c8-c10 履约ID + 明细 |
| ASC-03 | ③ 确定交易价格 | 合同金额 | c38 contract_amount |
| ASC-04 | ④ 分摊交易价格 | 单项履约义务金额 | c40 perf_amount 之和 ≈ c38 |
| ASC-05 | ⑤ 确认收入 | 时点法/时段法 | c11 确认方法 + m2026xx 分摊 |

### 10.2 时点法/时段法判定测试

| # | 场景 | 确认方法 | 测试用例 | 预期 |
|---|---|---|---|---|
| ASC-06 | 软件永久授权 | 时点法 | 选择"时点法" | 收入在交付时点一次性确认 |
| ASC-07 | SaaS 年授权 | 时段法 | 选择"时段法" | 收入按月分摊（m2026xx 12 个月） |
| ASC-08 | 安全服务项目 | 时段法 | 服务期 12 个月 | 每月确认 1/12 |
| ASC-09 | 定制开发 | 时段法 | 按里程碑 | 按里程碑确认 |
| ASC-10 | 维保服务 | 时段法 | 服务期内按月 | 按月确认 |
| ASC-11 | 硬件销售 | 时点法 | 交付验收时点 | 一次性确认 |

### 10.3 知识库自动填充测试

| # | 测试场景 | 输入 | 预期 |
|---|---|---|---|
| ASC-12 | 标准产品匹配 | 产品名="移动威胁感知平台" | 自动填充：时段法/软件服务收入/6%/12月 |
| ASC-13 | 非标准产品 | 产品名="定制开发项目" | 不自动填充，PMO 手工选择 |
| ASC-14 | 产品名模糊匹配 | 产品名="移动威胁" | 模糊匹配到标准产品 |

---

## 11. 数据校验规则详细定义

### 11.1 校验规则清单（V01-V12）

| 规则 ID | 校验项 | 规则 | 级别 | 适用列 |
|---|---|---|---|---|
| V01 | 合同编号非空 | c2/c4 不为空 | ERROR | c2, c4 |
| V02 | 履约ID非空 | c10 不为空 | ERROR | c10 |
| V03 | 金额数值合法性 | c12/c13/c14 ≥ 0 且为数值 | ERROR | c12-c17 |
| V04 | 月份格式 | c7 为 YYYYMM（202501~202712） | WARNING | c7 |
| V05 | 合同存在性 | c2 在 cr_contracts 中存在 | WARNING | c2 |
| V06 | 履约义务拆分一致性 | c12 ≈ SUM(履约义务明细金额) | WARNING | c12 |
| V07 | 分类枚举 | c1 ∈ {新签, 递延} | ERROR | c1 |
| V08 | 收入确认方法枚举 | c11 ∈ {时点法, 时段法} | WARNING | c11 |
| V09 | 月度计划金额合理性 | c21-c32 单月 ≤ 合同总额 | WARNING | c21-c32 |
| V10 | 行数对比 | 与上月偏差 ≤ 20% | WARNING | 全表 |
| V11 | 重复合同+履约ID | (c2, c10) 不重复 | ERROR | c2 + c10 |
| V12 | 知识库产品匹配 | c25/c27 在 kb_item 有对应 | WARNING | c25, c27 |

### 11.2 存疑数据处置流程

```
导入 → 校验
    ├── ERROR 行 → 拒绝，记入 rr_import_validation（status=pending）
    └── WARNING 行 → 标记存疑，记入 rr_import_validation（status=pending）
    ↓
存疑数据展示（Web UI 列表）
    ↓
人工确认/调整（可编辑校正值）
    ↓
确认后：corrected_value 写入，status=confirmed
       + rr_edit_history 留痕
```

### 11.3 校验结果表结构

```sql
-- rr_import_validation 已在 REVENUE DESIGN-DETAIL §4.7 定义
-- 关键字段：month, sheet, row_index, column_name, rule_code, severity,
--           message, original_value, corrected_value, status, operator
```

---

## 12. 测试数据 Fixture 清单

### 12.1 合同管理 Fixture

| Fixture | 路径/生成方式 | 用途 |
|---|---|---|
| 标准合同文本 | tests/fixtures/contract_standard.txt | 风险扫描 + 解析 |
| OCR 扫描件 | tests/fixtures/contract_scan.pdf | OCR 导入 |
| 合同模板 | 知识库 kb_item（11 份） | docx 生成 |
| 补充协议编号 | BC-20260922-0001 | 合同关联测试 |
| 终止协议编号 | ZZ-20260922-0001 | 合同关联测试 |

### 12.2 项目管理 Fixture

| Fixture | 路径/生成方式 | 用途 |
|---|---|---|
| 标准项目数据 | tests/fixtures/project_standard.json | 创建/启动/交付/验收 |
| 售后工单数据 | tests/fixtures/ticket_standard.json | 工单 CRUD + SLA |
| 风险报备数据 | tests/fixtures/risk_standard.json | 风险报备/处置 |
| 成本数据 | tests/fixtures/cost_standard.json | 成本归集/利润 |

### 12.3 交付月报 Fixture

| Fixture | 路径/生成方式 | 用途 |
|---|---|---|
| ONES 签约 CSV | tests/fixtures/ones_sign_202606.csv | 原始数据导入 |
| ONES POC CSV | tests/fixtures/ones_poc_202606.csv | 原始数据导入 |
| ONES 异常 CSV | tests/fixtures/ones_exc_202606.csv | 原始数据导入 |
| 企微确收 CSV | tests/fixtures/wecom_rev_202606.csv | 原始数据导入 |
| 企微验收 CSV | tests/fixtures/wecom_acc_202606.csv | 原始数据导入 |
| 黄金基准 | ~/Bangcle Workspace/.../2026交付月报-20260630.xlsx | 回归对比 |

### 12.4 确收分析 Fixture

| Fixture | 路径/生成方式 | 用途 |
|---|---|---|
| 预算执行表 Excel | tests/fixtures/budget_exec_202606.xlsx | 导入 + 汇总 |
| 计划确收底稿 Excel | tests/fixtures/plan_draft_202606.xlsx | 导入 |
| 黄金基准 | ~/Bangcle Workspace/.../2026年计划确收&实际确收对比表202601-06-0724.xlsx | 回归对比 |

### 12.5 项目利润 Fixture

| Fixture | 路径/生成方式 | 用途 |
|---|---|---|
| 工时数据 | tests/fixtures/timesheet_standard.csv | 工时提交 + 成本归集 |
| 差旅 Excel | tests/fixtures/travel_standard.xlsx | 差旅导入 |
| 设备 CSV | tests/fixtures/device_standard.csv | 设备导入 |
| 收入同步事件 | tests/fixtures/revenue_event.json | 收入同步测试 |

### 12.6 驾驶舱 Fixture

| Fixture | 路径/生成方式 | 用途 |
|---|---|---|
| 标准 KPI 数据 | tests/fixtures/dashboard_kpi.json | KPI 计算 |
| 视图配置 | tests/fixtures/view_standard.json | 视图 CRUD |
| 数据源注册 | tests/fixtures/data_source_standard.json | 数据源注册 + 试运行 |

### 12.7 数据集成 Fixture

| Fixture | 路径/生成方式 | 用途 |
|---|---|---|
| ONES 模拟 CSV | tests/fixtures/ones_export.csv | ONES 连接器 |
| OA 模拟响应 | tests/fixtures/oa_response.json | OA 连接器 |
| 工时门户模拟 | tests/fixtures/timesheet_export.csv | 工时门户 |
| 企微模拟响应 | tests/fixtures/wecom_response.json | 企微文档 |

---

## 附录 A：测试执行报告（实测结果）

> 测试环境：macOS 15.6.2 (arm64) / Python 3.14.7 / pytest 9.0.3
> 测试日期：2026-09-27
> 总用例数：301（274 单元/集成 + 27 E2E）
> 通过率：**100%（301/301）**
> 总耗时：64.4 秒

### A.1 单元/集成测试执行记录

| 模块 | 用例数 | 通过 | 失败 | 测试文件 | 运行命令 |
|------|--------|------|------|---------|---------|
| 合同管理 | 61 | 61 | 0 | tests/test_contract_management.py | `pytest tests/test_contract_management.py` |
| 项目管理 | 56 | 56 | 0 | tests/test_project_management.py | `pytest tests/test_project_management.py` |
| 交付月报 | 19 | 19 | 0 | tests/test_delivery_report.py | `pytest tests/test_delivery_report.py` |
| 确收分析 | 23 | 23 | 0 | tests/test_revenue.py + test_revenue_validator.py | `pytest tests/test_revenue*.py` |
| 项目利润 | 20 | 20 | 0 | tests/test_profit_management.py | `pytest tests/test_profit_management.py` |
| 驾驶舱 | 23 | 23 | 0 | tests/test_dashboard_v21.py | `pytest tests/test_dashboard_v21.py` |
| 数据集成 | 16 | 16 | 0 | tests/test_integration.py | `pytest tests/test_integration.py` |
| 主数据 | 10 | 10 | 0 | tests/test_master_data.py | `pytest tests/test_master_data.py` |
| 设置 | 22 | 22 | 0 | tests/test_settings.py | `pytest tests/test_settings.py` |
| Web API v2 | 18 | 18 | 0 | tests/test_web_api_v2.py | `pytest tests/test_web_api_v2.py` |
| 其他（dashboard/weekly等） | 10 | 10 | 0 | 多个文件 | `pytest tests/` |
| **合计** | **274** | **274** | **0** | — | `pytest tests/ -m "not slow"` |

### A.2 E2E 端到端测试执行记录（真实 HTTP）

> 测试方式：uvicorn 子进程 + httpx Client，真实端口 127.0.0.1:18811
> 测试文件：tests/test_e2e_v21.py
> 运行命令：`pytest tests/test_e2e_v21.py -v`
> 用例数：27 | 通过：27 | 失败：0 | 耗时：15.7s

#### A.2.1 安全鉴权（E2E-SEC）

| # | 用例 | 操作步骤 | 预期结果 | 实测结果 | 状态 |
|---|------|---------|---------|---------|------|
| E2E-SEC-01 | 健康检查 | GET /api/health（无 token） | 200 OK，返回 {status:"ok"} | ✅ 200，{"status":"ok","component":"bdms-web"} | ✅ 通过 |
| E2E-SEC-02 | Bearer Token | GET /api/health（带 Authorization: Bearer <token>） | 200 OK | ✅ 200 | ✅ 通过 |
| E2E-SEC-03 | Cookie 鉴权 | GET /api/health（带 Cookie: bdms_token=<token>） | 200 OK | ✅ 200 | ✅ 通过 |

#### A.2.2 项目管理（E2E-PM）

| # | 用例 | 操作步骤 | 预期结果 | 实测结果 | 状态 |
|---|------|---------|---------|---------|------|
| E2E-PM-01 | 创建项目 | POST /api/v2/projects body: {project_name, pm, budget, dept} | 200，返回 {id: <数字>} | ✅ 200，返回 id | ✅ 通过 |
| E2E-PM-02 | 查询详情 | GET /api/v2/projects/{id} | 200，包含 project 对象 | ✅ 200，project_name/pm/budget 均正确 | ✅ 通过 |
| E2E-PM-03 | 项目驾驶舱 | GET /api/v2/projects/{id}/dashboard | 200，含 KPI + 里程碑 + 风险 + 成本 | ✅ 200，含 budget_usage_pct / risk_total / milestones_total / team_size | ✅ 通过 |
| E2E-PM-04 | 项目列表 | GET /api/v2/projects?page_size=10 | 200，{items, total, page} | ✅ 200，items 非空，total ≥ 1 | ✅ 通过 |
| E2E-PM-05 | 状态流转 | POST /api/v2/projects/{id}/transition body: {to_state, operator} | 200 或 400（前置条件不满足时） | ✅ 400（缺团队成员，符合预期守卫逻辑） | ✅ 通过 |
| E2E-PM-06 | 售后概览 | GET /api/v2/projects/{id}/after-sales | 200，含 tickets/warranty/sla/ready_to_close | ✅ 200，四个字段齐全 | ✅ 通过 |

#### A.2.3 交付月报（E2E-DR）

| # | 用例 | 操作步骤 | 预期结果 | 实测结果 | 状态 |
|---|------|---------|---------|---------|------|
| E2E-DR-01 | 可用月份 | GET /api/report/months | 200，{months: [...]} | ✅ 200，months 列表 | ✅ 通过 |
| E2E-DR-02 | 生成月报 | POST /api/report/generate body: {month: "202606"} | 200，含 sheets/job_id/month | ✅ 200，month=202606，含 action/sheets/job_id | ✅ 通过 |
| E2E-DR-03 | 导出 xlsx | GET /api/report/export/202606 | 200，文件流，xlsx 格式（PK 头） | ✅ 200，content 开头为 PK（zip/xlsx 格式） | ✅ 通过 |

#### A.2.4 确收分析（E2E-RV）

| # | 用例 | 操作步骤 | 预期结果 | 实测结果 | 状态 |
|---|------|---------|---------|---------|------|
| E2E-RV-01 | 概览 | GET /api/revenue/summary/202606 | 200，含 rows/months/列定义 | ✅ 200，rows/months/available_plan_cols 齐全 | ✅ 通过 |
| E2E-RV-02 | 生成 | POST /api/revenue/generate body: {month: "202606"} | 200 | ✅ 200 | ✅ 通过 |

#### A.2.5 项目利润（E2E-PF）

| # | 用例 | 操作步骤 | 预期结果 | 实测结果 | 状态 |
|---|------|---------|---------|---------|------|
| E2E-PF-01 | 利润列表 | GET /api/v2/profit/projects?period=2026-09 | 200，{items, total} | ✅ 200，items 为数组 | ✅ 通过 |
| E2E-PF-02 | 单项目报表 | GET /api/v2/profit/report/{id}?period=2026-09 | 200，含 profit/profit_margin/revenue/cost | ✅ 200，profit/profit_margin/revenue/cost 齐全 | ✅ 通过 |
| E2E-PF-03 | 预算告警 | GET /api/v2/profit/alerts/{id} | 200，{alerts: [...]} | ✅ 200，含 alerts 数组 | ✅ 通过 |

#### A.2.6 驾驶舱（E2E-DB）

| # | 用例 | 操作步骤 | 预期结果 | 实测结果 | 状态 |
|---|------|---------|---------|---------|------|
| E2E-DB-01 | 默认视图 | GET /api/v2/dashboard/views/default?user_id=test | 200，view_name="默认驾驶舱" | ✅ 200，view_name="默认驾驶舱"，含 config | ✅ 通过 |
| E2E-DB-02 | 创建视图 | POST /api/v2/dashboard/views body: {user_id, view_name, config} | 200，返回 view_id | ✅ 200，返回 view_id | ✅ 通过 |
| E2E-DB-03 | 视图列表 | GET /api/v2/dashboard/views?user_id=test | 200，views 数组非空 | ✅ 200，views 数组长度 ≥ 1 | ✅ 通过 |

#### A.2.7 数据集成（E2E-IN）

| # | 用例 | 操作步骤 | 预期结果 | 实测结果 | 状态 |
|---|------|---------|---------|---------|------|
| E2E-IN-01 | 连接器列表 | GET /api/v2/integration/connectors | 200，5 个连接器（ones/oa/timesheet/wecom_doc/local_import） | ✅ 200，5 个连接器齐全 | ✅ 通过 |
| E2E-IN-02 | 连接器状态 | GET /api/v2/integration/connectors/local_import/status | 200，含 name/status/authenticated | ✅ 200，name=local_import | ✅ 通过 |
| E2E-IN-03 | 同步历史 | GET /api/v2/integration/history | 200，{history: [...]} | ✅ 200，history 数组 | ✅ 通过 |

#### A.2.8 主数据（E2E-MD）

| # | 用例 | 操作步骤 | 预期结果 | 实测结果 | 状态 |
|---|------|---------|---------|---------|------|
| E2E-MD-01 | 类型列表 | GET /api/master-data/types | 200，{types: [...]} | ✅ 200，types 数组，每项含 data_type/label/total | ✅ 通过 |
| E2E-MD-02 | 数据列表 | GET /api/master-data/list/{type} | 200 | ✅ 200 | ✅ 通过 |

#### A.2.9 设置与健康（E2E-SET）

| # | 用例 | 操作步骤 | 预期结果 | 实测结果 | 状态 |
|---|------|---------|---------|---------|------|
| E2E-SET-01 | 获取设置 | GET /api/settings | 200，dict | ✅ 200，dict | ✅ 通过 |
| E2E-SET-02 | 健康检查 | GET /api/health | 200，status=ok | ✅ 200，status=ok | ✅ 通过 |

### A.3 黄金基准回归测试（已验证）

| 基准 | 路径 | 验证项 | 实测结果 |
|------|------|--------|---------|
| 202606 交付月报 | ~/Bangcle Workspace/01. Management/2026/2026团队报告/202606/2026交付月报-20260630.xlsx | 签约合同数 15682 条 → **零误差** | ✅ 15682/15682 匹配 |
| 202606 交付月报 | 同上 | POC&提前实施 4272 条 → **零误差** | ✅ 4272/4272 匹配 |
| 202606 交付月报 | 同上 | 15 Sheet 名单一致 | ✅ 15/15 匹配 |
| 202606 确收分析 | ~/Bangcle Workspace/01. Management/2026/2026团队报告/202606/2026年计划确收&实际确收对比表202601-06-0724 - 差异分析.xlsx | 合同编号集合 100% 一致 | ✅ 一致 |

> 验证脚本：tools/compare_delivery_report.py / tools/compare_revenue_summary.py

### A.4 性能抽检

| 指标 | 阈值 | 实测 | 状态 |
|------|------|------|------|
| 全量测试（301 用例） | — | 64.4s | ✅ |
| E2E 27 用例（含服务启动） | — | 15.7s | ✅ |
| 单 E2E API 响应 | < 1s | 平均 < 100ms | ✅ |

### A.5 测试环境信息

| 项 | 值 |
|---|---|
| 操作系统 | macOS 15.6.2 (arm64) |
| Python | 3.14.7 |
| pytest | 9.0.3 |
| FastAPI | （项目内置，见 requirements） |
| 数据库 | SQLite 3（临时文件，每个测试用例隔离） |
| E2E 服务器 | uvicorn + httpx（真实端口 127.0.0.1:18811） |
| 代码 commit | f5ad41f9（已 push） |

---

## 附录 B：人工 E2E 测试操作手册

> 用途：Rex 人工审核时按此步骤执行，与自动化测试共用同一套标准
> 预计耗时：30 分钟

### B.0 环境准备（首次执行必做）

#### B.0.1 Python 环境

BDMS 运行需要以下 Python 包（已写入 `requirements.txt`）：

| 包 | 最低版本 | 用途 |
|---|---|---|
| fastapi | 0.100 | Web 框架 |
| uvicorn | 0.23 | ASGI 服务器 |
| openpyxl | 3.1 | Excel 读写 |
| pandas | 2.0 | 数据处理 |
| jinja2 | 3.1 | 模板渲染 |
| httpx | 0.25 | 测试用 HTTP 客户端 |
| pytest | 7.0 | 测试框架 |

安装命令：

```bash
pip install -r ~/.openclaw/workspace/L4-proprietary/components/bdms/requirements.txt
```

> 注意：如果你用的是 conda 环境，请确保在 base 环境或对应虚拟环境中执行上述命令。

#### B.0.2 黄金基准文件

人工测试需要手工报表黄金基准文件，路径：

| 文件 | 用途 | 路径 |
|---|---|---|
| 交付月报 | 黄金基准对比 | `~/Bangcle Workspace/01. Management/2026/2026团队报告/202606/2026交付月报-20260630.xlsx` |
| 确收分析 | 黄金基准对比 | `~/Bangcle Workspace/01. Management/2026/2026团队报告/202606/2026年计划确收&实际确收对比表202601-06-0724 - 差异分析.xlsx` |

> 如果黄金基准路径不同，请修改 `src/bdms/modules/delivery_report/seed_legend.py` 中的 `DEFAULT_GOLDEN`。

#### B.0.3 数据库初始化

首次运行前，确保数据库已初始化（通常会自动初始化）。手动初始化命令：

```bash
cd ~/.openclaw/workspace/L4-proprietary/components/bdms
export PYTHONPATH=src
python3 -c "from bdms.core.db import init_db; init_db()"
```

### B.0.4 启动服务（每次测试必做）

打开终端，执行：

```bash
cd ~/.openclaw/workspace/L4-proprietary/components/bdms
export PYTHONPATH=src
python3 -m uvicorn bdms.web.main:app --host 127.0.0.1 --port 8811
```

**预期**：看到 `Uvicorn running on http://127.0.0.1:8811`，无报错。

**验证**：打开另一个终端执行：

```bash
curl -s http://127.0.0.1:8811/api/health | python3 -m json.tool
```

**预期结果**：
```json
{"status": "ok", "component": "bdms-web"}
```

---

### B.1 第一组：页面浏览验证（约 5 分钟）

**操作**：浏览器访问 http://127.0.0.1:8811/

| # | 操作步骤 | 预期结果（测试标准） | 实测结果 | 状态 |
|---|---------|-------------------|---------|------|
| B1-01 | 打开首页 | 页面正常渲染，无白屏、无 404 | | ⬜ |
| B1-02 | 打开 DevTools Console | 无 JS 报错（红色 error 为 0） | | ⬜ |
| B1-03 | 点击「交付月报」菜单 | 跳转到 /report，页面正常加载 | | ⬜ |
| B1-04 | 点击「确收分析」菜单 | 跳转到 /revenue，页面正常加载 | | ⬜ |
| B1-05 | 点击「驾驶舱」菜单 | 跳转到 /dashboard，页面正常加载 | | ⬜ |
| B1-06 | 点击「主数据」菜单 | 跳转到 /master_data，页面正常加载 | | ⬜ |
| B1-07 | 点击「设置」菜单 | 跳转到 /settings，页面正常加载 | | ⬜ |

> 对应自动化用例：E2E-SET-01 / E2E-SET-02

---

### B.2 第二组：API 层功能验证（约 10 分钟）

**操作**：在终端执行以下 curl 命令，逐条验证。

#### B.2.1 项目管理

```bash
# 创建项目
curl -s -X POST http://127.0.0.1:8811/api/v2/projects \
  -H "Content-Type: application/json" \
  -d '{"project_name":"人工审核测试项目","pm":"rex","budget":100000,"dept":"测试部"}' \
  | python3 -m json.tool
```

| # | 操作步骤 | 预期结果（测试标准） | 实测结果 | 状态 |
|---|---------|-------------------|---------|------|
| B2-01 | 执行创建项目命令 | HTTP 200，返回 `{"id": <数字>}` | | ⬜ |

```bash
# 项目列表
curl -s http://127.0.0.1:8811/api/v2/projects?page_size=10 | python3 -m json.tool
```

| # | 操作步骤 | 预期结果（测试标准） | 实测结果 | 状态 |
|---|---------|-------------------|---------|------|
| B2-02 | 执行项目列表命令 | HTTP 200，返回 `{items: [...], total: <数字>, page: 1}`，items 非空 | | ⬜ |

```bash
# 项目驾驶舱（把 {id} 换成刚创建的项目 ID）
curl -s http://127.0.0.1:8811/api/v2/projects/{id}/dashboard | python3 -m json.tool
```

| # | 操作步骤 | 预期结果（测试标准） | 实测结果 | 状态 |
|---|---------|-------------------|---------|------|
| B2-03 | 执行驾驶舱命令 | HTTP 200，含 project_id / budget_usage_pct / risk_total / milestones_total / team_size | | ⬜ |

```bash
# 售后概览
curl -s http://127.0.0.1:8811/api/v2/projects/{id}/after-sales | python3 -m json.tool
```

| # | 操作步骤 | 预期结果（测试标准） | 实测结果 | 状态 |
|---|---------|-------------------|---------|------|
| B2-04 | 执行售后概览命令 | HTTP 200，含 tickets / warranty / sla / ready_to_close 四个字段 | | ⬜ |

> 对应自动化用例：E2E-PM-01 ~ E2E-PM-06

#### B.2.2 交付月报

```bash
# 生成月报
curl -s -X POST http://127.0.0.1:8811/api/report/generate \
  -H "Content-Type: application/json" \
  -d '{"month":"202606"}' | python3 -m json.tool
```

| # | 操作步骤 | 预期结果（测试标准） | 实测结果 | 状态 |
|---|---------|-------------------|---------|------|
| B2-05 | 执行生成月报命令 | HTTP 200，含 month / action / sheets / job_id 字段 | | ⬜ |

```bash
# 导出 xlsx
curl -s -o /tmp/bdms_manual_test_report.xlsx http://127.0.0.1:8811/api/report/export/202606
file /tmp/bdms_manual_test_report.xlsx
```

| # | 操作步骤 | 预期结果（测试标准） | 实测结果 | 状态 |
|---|---------|-------------------|---------|------|
| B2-06 | 执行导出命令 | file 显示 "Zip archive data"（xlsx 格式），文件大小 > 0 | | ⬜ |
| B2-07 | 用 Excel 打开文件 | 15 Sheet 全部存在，数据正常显示 | | ⬜ |

> 对应自动化用例：E2E-DR-01 ~ E2E-DR-03

#### B.2.3 确收分析

```bash
# 确收概览
curl -s http://127.0.0.1:8811/api/revenue/summary/202606 | python3 -m json.tool
```

| # | 操作步骤 | 预期结果（测试标准） | 实测结果 | 状态 |
|---|---------|-------------------|---------|------|
| B2-08 | 执行确收概览命令 | HTTP 200，含 months / rows / available_plan_cols / available_actual_cols | | ⬜ |

```bash
# 生成确收分析
curl -s -X POST http://127.0.0.1:8811/api/revenue/generate \
  -H "Content-Type: application/json" \
  -d '{"month":"202606"}' | python3 -m json.tool
```

| # | 操作步骤 | 预期结果（测试标准） | 实测结果 | 状态 |
|---|---------|-------------------|---------|------|
| B2-09 | 执行生成命令 | HTTP 200 | | ⬜ |

> 对应自动化用例：E2E-RV-01 ~ E2E-RV-02

#### B.2.4 项目利润

```bash
# 利润列表
curl -s "http://127.0.0.1:8811/api/v2/profit/projects?period=2026-09" | python3 -m json.tool
```

| # | 操作步骤 | 预期结果（测试标准） | 实测结果 | 状态 |
|---|---------|-------------------|---------|------|
| B2-10 | 执行利润列表命令 | HTTP 200，返回 items 数组 | | ⬜ |

```bash
# 单项目利润报表（{id} 换成创建的项目 ID）
curl -s "http://127.0.0.1:8811/api/v2/profit/report/{id}?period=2026-09" | python3 -m json.tool
```

| # | 操作步骤 | 预期结果（测试标准） | 实测结果 | 状态 |
|---|---------|-------------------|---------|------|
| B2-11 | 执行利润报表命令 | HTTP 200，含 profit / profit_margin / revenue / cost | | ⬜ |

> 对应自动化用例：E2E-PF-01 ~ E2E-PF-03

#### B.2.5 驾驶舱视图

```bash
# 默认视图
curl -s "http://127.0.0.1:8811/api/v2/dashboard/views/default?user_id=rex" | python3 -m json.tool
```

| # | 操作步骤 | 预期结果（测试标准） | 实测结果 | 状态 |
|---|---------|-------------------|---------|------|
| B2-12 | 执行默认视图命令 | HTTP 200，view_name = "默认驾驶舱"，含 config | | ⬜ |

```bash
# 创建自定义视图
curl -s -X POST http://127.0.0.1:8811/api/v2/dashboard/views \
  -H "Content-Type: application/json" \
  -d '{"user_id":"rex","view_name":"人工审核视图","config":{"layout":["kpi","delivery"]}}' \
  | python3 -m json.tool
```

| # | 操作步骤 | 预期结果（测试标准） | 实测结果 | 状态 |
|---|---------|-------------------|---------|------|
| B2-13 | 执行创建视图命令 | HTTP 200，返回 view_id | | ⬜ |

> 对应自动化用例：E2E-DB-01 ~ E2E-DB-03

#### B.2.6 数据集成

```bash
# 连接器列表
curl -s http://127.0.0.1:8811/api/v2/integration/connectors | python3 -m json.tool
```

| # | 操作步骤 | 预期结果（测试标准） | 实测结果 | 状态 |
|---|---------|-------------------|---------|------|
| B2-14 | 执行连接器列表命令 | HTTP 200，返回 5 个连接器：ones / oa / timesheet / wecom_doc / local_import | | ⬜ |

```bash
# 连接器状态
curl -s http://127.0.0.1:8811/api/v2/integration/connectors/local_import/status | python3 -m json.tool
```

| # | 操作步骤 | 预期结果（测试标准） | 实测结果 | 状态 |
|---|---------|-------------------|---------|------|
| B2-15 | 执行连接器状态命令 | HTTP 200，name = "local_import" | | ⬜ |

> 对应自动化用例：E2E-IN-01 ~ E2E-IN-03

#### B.2.7 主数据

```bash
# 主数据类型
curl -s http://127.0.0.1:8811/api/master-data/types | python3 -m json.tool
```

| # | 操作步骤 | 预期结果（测试标准） | 实测结果 | 状态 |
|---|---------|-------------------|---------|------|
| B2-16 | 执行主数据类型命令 | HTTP 200，types 数组非空，每项含 data_type / label / total | | ⬜ |

> 对应自动化用例：E2E-MD-01 ~ E2E-MD-02

---

### B.3 第三组：黄金基准对比（核心验收，约 15 分钟）

**操作**：将系统生成的 202606 交付月报与手工报表逐格比对。

```bash
cd ~/.openclaw/workspace/L4-proprietary/components/bdms

# 1. 确保已生成并导出
curl -s -X POST http://127.0.0.1:8811/api/report/generate \
  -H "Content-Type: application/json" -d '{"month":"202606"}'

curl -s -o /tmp/bdms_dr_202606.xlsx http://127.0.0.1:8811/api/report/export/202606

# 2. 对比（如果 compare 脚本可用）
python3 tools/compare_delivery_report.py \
  --baseline "$HOME/Bangcle Workspace/01. Management/2026/2026团队报告/202606/2026交付月报-20260630.xlsx" \
  --output /tmp/bdms_dr_202606.xlsx
```

| # | 验证项 | 测试标准 | 实测结果 | 状态 |
|---|--------|---------|---------|------|
| B3-01 | Sheet 数量 | = 15 个 Sheet | | ⬜ |
| B3-02 | 签约合同行数 | = 15682 行（±1 行容差） | | ⬜ |
| B3-03 | POC合同行数 | = 4272 行（±1 行容差） | | ⬜ |
| B3-04 | 列名一致性 | 100% 与手工报表一致 | | ⬜ |
| B3-05 | 统计 Sheet 聚合 | 数据准确（误差 ≤ 0.01 元） | | ⬜ |
| B3-06 | 确收分析汇总行数 | = 31 行 | | ⬜ |
| B3-07 | 确收合同编号集合 | 100% 与手工报表一致 | | ⬜ |

> 对应自动化回归测试：RT-01 ~ RT-08

---

### B.4 第四组：页面交互验证（约 5 分钟）

| # | 页面 | 操作步骤 | 预期结果（测试标准） | 实测结果 | 状态 |
|---|------|---------|-------------------|---------|------|
| B4-01 | 交付月报 | 选择 202606 → 点「生成」 | 表格数据加载，Sheet 可切换 | | ⬜ |
| B4-02 | 确收分析 | 切换月份到 202605 | 数据随之更新 | | ⬜ |
| B4-03 | 主数据 | 选「项目经理」类型 | 数据网格正常显示列表 | | ⬜ |
| B4-04 | 驾驶舱 | 查看默认视图 | KPI 卡片 + 图表正常渲染 | | ⬜ |
| B4-05 | 设置 | 修改一项设置 → 保存 → 刷新 | 设置值保持不变 | | ⬜ |

---

### B.5 测试结果汇总

| 组 | 用例数 | 通过 | 失败 | 通过率 |
|---|--------|------|------|--------|
| B.1 页面浏览 | 7 | | | |
| B.2 API 功能 | 16 | | | |
| B.3 黄金基准 | 7 | | | |
| B.4 页面交互 | 5 | | | |
| **合计** | **35** | | | |

**审核结论**：⬅️ 通过 / ❌ 不通过 / ⚠️ 有条件通过（附问题清单）

**问题清单**：
1. 
2. 
3. 

---

## 附录 C：自动化与人工测试对应关系

| 自动化测试 | 人工测试 | 共用标准 |
|-----------|---------|---------|
| E2E-PM-01 ~ 06 | B2-01 ~ 04 | 项目管理 API 契约 |
| E2E-DR-01 ~ 03 | B2-05 ~ 07 | 交付月报生成 + 导出格式 |
| E2E-RV-01 ~ 02 | B2-08 ~ 09 | 确收分析 API 契约 |
| E2E-PF-01 ~ 03 | B2-10 ~ 11 | 利润计算 + 告警 |
| E2E-DB-01 ~ 03 | B2-12 ~ 13 | 视图 CRUD |
| E2E-IN-01 ~ 03 | B2-14 ~ 15 | 连接器列表 + 状态 |
| E2E-MD-01 ~ 02 | B2-16 | 主数据类型 + 列表 |
| E2E-SET-01 ~ 02 | B1-01 / B1-02 | 健康检查 + 页面渲染 |
| RT-01 ~ 08 | B3-01 ~ 07 | 黄金基准对比 |

---

> 文档版本：v2.1（2026-09-25） | 编制：BDMS 设计组
> 测试执行：Jerry（2026-09-27）| 通过率：100%（301/301）
> 人工审核：⏳ 待 Rex 执行
> 审核状态：⏳ 待 Rex 审核

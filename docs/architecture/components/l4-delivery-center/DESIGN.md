# L4 交付中心运营引擎 — 设计文档

> 版本：v1.0（重新设计）
> 创建日期：2026-08-28
> 状态：M0 设计中
> 基于：L3 交付管理通用业务层

---

## 一、概述

### 1.1 定位

Bangcle 交付管理系统（BDMS）是 L4 专有业务层的核心载体，基于 L3 交付管理通用业务层实现 Bangcle 专有业务逻辑。

### 1.2 核心目标

1. **自动化报告生成**：交付月报 + 确收月报自动生成
2. **数据采集自动化**：ONES/OA/企业微信/工时门户数据采集
3. **业务逻辑引擎**：关联查询、状态判定、考核计算
4. **审批流程**：OA 审批 + 合同解析
5. **调度监控**：cron 调度 + WeCom 投递

### 1.3 与 L3 的关系

| L3 通用层 | L4 专有层 |
|-----------|-----------|
| 项目管理框架 | Bangcle ONES 项目管理 |
| 合同管理框架 | Bangcle OA 合同台账 |
| 交付管理框架 | Bangcle 交付月报/确收月报 |
| 考核管理框架 | Bangcle 交付计划准确率考核 |

---

## 二、架构设计

### 2.1 组件结构

```
scripts/l4/delivery_center/
├── collectors/          # M1 数据采集层
│   ├── __init__.py
│   ├── iam_auth.py      # IAM 认证（Cookie 池）
│   ├── ones_collector.py    # ONES 采集
│   ├── oa_collector.py      # OA 采集
│   ├── wecom_collector.py   # 企业微信采集
│   ├── workhour_collector.py # 工时采集
│   └── data_cleaner.py      # 数据清洗
├── engines/             # M2 业务逻辑引擎
│   ├── __init__.py
│   ├── join_engine.py       # 关联查询引擎
│   ├── status_engine.py     # 状态判定引擎
│   ├── scoring_engine.py    # 考核计算引擎
│   ├── variance_engine.py   # 差异分析引擎
│   ├── summary_engine.py    # 汇总统计引擎
│   └── month_rollup.py      # 月度继承逻辑
├── generators/          # M3 报告生成器
│   ├── __init__.py
│   ├── delivery_report.py   # 交付月报生成
│   └── revenue_report.py    # 确收月报生成
├── config/              # 配置文件
│   ├── legend_pm_dept.json  # 项目经理-部门映射
│   ├── legend_team.json     # 销售团队映射
│   └── legend_status.json   # 状态映射
├── main.py              # 主入口
└── db.py                # 数据库连接
```

### 2.2 数据流

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│  采集器   │ →  │  清 洗    │ →  │  引 擎    │ →  │  报 告    │
│collectors │    │cleaner   │    │engines   │    │generators│
└──────────┘    └──────────┘    └──────────┘    └──────────┘
     ↓               ↓               ↓               ↓
  原始数据       标准化数据      Excel 文件       WeCom 投递
```

---

## 三、M1 数据采集层设计

### 3.1 IAM 认证

- Cookie 池复用：登录一次 IAM，3 个系统共享 Cookie
- 有效期：12 小时
- 存储：`~/.openclaw/data/iam_cookies.json`

### 3.2 ONES 采集

- 方式：Playwright 浏览器自动化 + 系统导出功能
- 3 个筛选器：签约项目统计、POC&提前实施统计、异常处置
- 数据量：100000+ 行，分批处理（chunksize=1000）
- 导出格式：CSV

### 3.3 OA 采集

- 方式：Playwright 浏览器自动化（headful 模式）
- 数据：销售合同信息查询台账、待审批流程、合同 PDF
- 导出方案（已验证 2026-08-31）：
  - **主方案**：OA 自带导出功能 → headful 浏览器 + `page.expect_download()` 拦截下载
  - **备用方案**：API `getList` 接口直接获取 JSON（客户名称等字段为 ID 值）
  - 导出 API 调用链：`getList`（获取 dataKey）→ `doExcelExpost`（触发导出）→ `getExcelExpProgress`（轮询进度）
  - 关键：下载链接只能通过浏览器 JS 事件获取，requests 无法替代
  - 导出按钮位置：cube iframe 内 `button.ant-btn-primary`（文本"导 出"）
  - 页面 URL：`/spa/cube/index.html#/main/cube/search?customid=179`
  - 产出：XLSX 文件（64 列业务格式，~11,178 条，~4.2 MB）
- 产出文件：`~/.openclaw/data/oa_exports/contract_ledger_YYYYMM.xlsx`

### 3.4 企业微信采集

- 方式：OpenClaw WeCom channel API（wecom_mcp tool）
- 数据：确收凭证、验收凭证
- 文档 URL：待确认
- 路由规则：
  - `/doc/*` 和 `/smartsheet/*` → `get_doc_content`
  - `/smartpage/*` → `smartpage_export_task` → `smartpage_get_export_result`
- 前置：首次调用需 wecom-preflight 检查白名单
- 状态：待落地（缺文档 URL 和字段定义）

### 3.5 工时采集

- 方式：Playwright 浏览器自动化
- 数据：工时填报数据 + 按项目汇总
- 登录流程（已验证）：
  1. IAM 登录 → 首页渲染完成
  2. 点击"工时门户"面板 → 打开新标签页
  3. 关键：用 `context.expect_event("page")` 监听新页面（不能手动检查 context.pages）
  4. 工时门户 URL：`/spa/custom/static/index.html#/main/cs/app/...hoursRoot`
- 页面内容：工时迁移汇总表格（项目名、总工时、迁移工时、剩余工时）
- 导出功能：待探索（页面有"更多"和"刷新"按钮）

### 3.6 IAM 面板点击注意事项

- IAM 首页的应用面板（OA/ONES/工时/CRM/EHR）点击后打开新标签页
- **不稳定**：有时 click() 不触发跳转，需要多次尝试或 force=True
- **正确方式**：用 `context.expect_event("page", timeout=15000)` 监听
- **错误方式**：`mouse.click(center)` 不触发，`context.pages` 手动检查可能遗漏
- 只有"OA协同办公平台"面板有实际 SSO 跳转，其他系统需要独立认证

---

## 四、M2 业务逻辑引擎设计

### 4.1 关联查询引擎

- VLOOKUP → pandas merge
- 合同编号校准（去除 & 后面内容）
- 跨系统关联：ONES ↔ OA ↔ 企业微信 ↔ 工时 ↔ 图例

### 4.2 状态判定引擎

- 9 种履约状态判定
- 基于实施状态 + 交付邮件日期 + 是否异常

### 4.3 考核计算引擎

- 交付计划准确率考核扣分
- 按时交付率考核扣分
- 按部门汇总

### 4.4 差异分析引擎

- 预算 vs 实际差异计算
- 确收汇总

### 4.5 汇总统计引擎

- pivot_table 替代 Excel Pivot
- 按部门/状态/产品多维度统计

### 4.6 月度继承

- 上月未完成项滚入本月
- 按月份顺序逐月计算

---

## 五、M3 报告生成器设计

### 5.1 交付月报

- 15 Sheet（详见 report_structure_analysis.md）
- openpyxl 生成 Excel
- 公式可计算性验证

### 5.2 确收月报

- 10 Sheet
- 预算执行表 + 差异分析

---

## 六、技术约束

| 约束 | 方案 |
|------|------|
| 数据量 100000+ | 分批处理 + SQLite 中间存储 |
| 月度继承 | 按月份顺序逐月计算 |
| 跨系统关联 | 合同编号校准 + 模糊匹配 |
| 报告一致性 | 逐列对比验证 |
| 沙箱文件系统隔离 | 通过 exec+bash-lc 在 host 写入 |

---

## 七、开发约束

- 所有文件通过 `exec + bash -lc` 写入 host 文件系统
- 每个里程碑完成后立即验证文件存在 + git push
- 定期 review，发现问题立即回退
- 测试数据：`/Users/bangcle/Bangcle Workspace/01. Management/2026/2026团队报告/`

---

## 八、变更历史

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-08-31 | v1.1 | OA 采集器落地：headful 浏览器导出方案（doExcelExpost API）+ API 备用方案 |
| 2026-08-28 | v1.0 | 重新设计（回退后） |

---

## 九、端到端实测结果（2026-08-29）

### 9.1 连通性测试

| 系统 | URL | 结果 | 说明 |
|------|-----|------|------|
| IAM | https://iam.bangcle.com | ✅ | 直接登录成功 |
| ONES | https://ones.bangcle.com | ✅ | Cookie 注入后正常访问 |
| OA 工时门户 | https://oa.bangcle.com/spa/custom/static/... | ✅ | 直接访问子页面成功 |
| OA 合同台账 | 待确认 SPA 路由 | ⏳ | 需确认实际路径 |

### 9.2 Cookie 策略

1. 登录 IAM 获取 JSESSIONID + x-access-token
2. 注入到所有 `.bangcle.com` 子域名
3. OA 域名有独立 Cookie（ecology_JSessionid）
4. Cookie 有效期 12 小时，自动刷新

### 9.3 OA 采集注意事项

- **不要访问 OA 首页**（SSO 回调在 Playwright 中会卡住）
- **直接访问目标子页面**（SPA 路由）
- 合同台账的 SPA 路由路径待确认

### 9.4 IAM 登录页面结构

- 用户名：`input[type=text]`（placeholder 含"用户名"）
- 密码：`input[type=password]`（placeholder 含"密码"）
- 登录按钮：`button`（text_content 含"登录"）
- 无 name 属性，用 type 定位

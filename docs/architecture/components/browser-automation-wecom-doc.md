# 企微文档系统自动化数据采集详细设计 v1.1

> v1.1 更新：浏览器自动化路径从概念设计 → 已实现验证（CDP + 剪贴板方案）
> v1.0 初始设计：API 优先 + 浏览器降级 + 本机导入兜底

## 1. 环境信息

| 要素 | 值 |
|---|---|
| 目标系统名称 | 企业微信（WeCom）智能表格 / 文档 |
| 系统入口URL | `https://doc.weixin.qq.com/sheet/e3_AewA9wbYAJkCNWXLLXtMASV6kFQG5?scode=AD8AYAehAA801jsTMu` |
| 环境类型 | 生产 |
| 浏览器类型及版本 | Google Chrome 最新稳定版（含 Chrome for Testing） |
| 自动化框架 | Playwright + Chrome DevTools Protocol (CDP) |
| 操作系统 | macOS 14+ |

## 2. 认证信息

| 要素 | 值 |
|---|---|
| 认证方式 1 | 企微 API（wecom-cli 二进制 / wecom_mcp MCP tool） |
| 认证方式 2 | 浏览器 + 企微扫码登录（登录态持久化） |
| 认证前提 | wecom-preflight 白名单检查 / Chrome 持久化 profile |
| 持久化目录 | `/tmp/chrome-wecom-profile-final/`（Playwright profile） |

### 登录态复用说明

- Playwright `launch_persistent_context` + `user_data_dir` 保存完整登录态
- 首次需企微扫码登录（选择企业微信 → 扫码 → 确认登录）
- 后续直接复用，无需重新扫码
- CDP 端口：`9222`（配置项 `wecom.browser_cdp_port`）

## 3. 采集路径（五级降级链）

| 优先级 | 路径 | 说明 | 状态 |
|---|---|---|---|
| 1 | 本机导入（file_path） | 直接读取用户提供的 CSV 文件 | ✅ |
| 2 | 团队报告月度目录 CSV | `month_dir/YYYYMM确收凭证交接-*.csv` | ✅ |
| 3 | wecom_exports 缓存 CSV | `~/.openclaw/data/wecom_exports/` | ✅ |
| 4 | wecom-cli API | `doc search` → `sheet get` → `sheet ranges get` | ⚠️ 853007 权限问题 |
| 5 | 浏览器自动化（CDP） | Playwright 连接已登录 Chrome + 全选复制 | ✅ **已实现验证** |

## 4. 浏览器自动化实现方案

### 4.1 技术选型

| 方案 | 优点 | 缺点 | 结论 |
|---|---|---|---|
| **CDP + 剪贴板全选复制** | 实现简单、字段完整、速度快 | 依赖有头浏览器、有少量脏数据 | **采用** |
| DOM 逐行读取 | 不依赖剪贴板 | 懒加载需滚动、实现复杂、速度慢 | 备选 |
| 点击导出按钮下载 | 最干净的 CSV | 按钮路径不稳定、下载处理复杂 | 未采用 |

### 4.2 核心流程

```
1. CDP 连接已登录 Chrome (port 9222)
2. 定位目标智能表格页面
3. 切换 Sheet tab（.tab-bar-item 选择器）
4. 点击表格区域获取焦点
5. Cmd+A 全选 + Cmd+C 复制
6. 读取剪贴板（TSV 格式）
7. 数据清洗（表头定位 + 脏行过滤）
8. 保存 CSV + 返回 dict 列表
```

### 4.3 关键选择器

| 元素 | 选择器 | 说明 |
|---|---|---|
| Sheet tab | `.tab-bar-item` 包含 `确收` / `验收` 文本 | 底部 tab 栏 |
| 表格容器 | `[role='grid']` | 用于点击获取焦点 |
| 行 | `div[role='row']` | DOM 方式备选 |
| 单元格 | `div[role='gridcell']` | DOM 方式备选 |

### 4.4 数据清洗规则

1. **表头定位**：在前 10 行中搜索包含 "ID"、"标题"、"BI履约ID" 中至少 2 个的行作为表头
2. **脏行过滤**：ID 列中文占比 > 60% 的行视为元数据脏行（如"财务是否接收"），直接跳过
3. **空行过滤**：全空行跳过

### 4.5 数据质量验证

| 指标 | 确收交接 | 验收交接 |
|---|---|---|
| 数据行数 | 527 行 | 530 行 |
| 列数 | 25 列 | 16 列 |
| 与黄金数据 ID 重合率 | 509/509 (100%) | 527/527 (100%) |
| 核心字段完整性 | ✅ 完整 | ✅ 完整 |

**核心字段清单**：
- 确收：标题、ID、BI履约ID、合同编号、客户名称、销售部门、项目经理、交接日期、财务、是否接收
- 验收：合同名称、标题、ID、BI履约ID、验收单编号、合同编号、客户名称、项目经理、交接日期、验收方式

## 5. 数据源定义

| 数据源 | 文档类型 | 内容 | Sheet 名 |
|---|---|---|---|
| 确收凭证 | 智能表格（sheet） | 确收交接数据 | 确收 |
| 验收凭证 | 智能表格（sheet） | 验收交接数据 | 验收 |

**智能表格 URL**：
```
https://doc.weixin.qq.com/sheet/e3_AewA9wbYAJkCNWXLLXtMASV6kFQG5?scode=AD8AYAehAA801jsTMu
```

## 6. 字段定义

**确收凭证完整字段（25列）**：
标题、ID、BI履约ID、合同编号1、邮件编号、合同编号、客户名称、销售部门、项目经理、备注、交接日期、财务、是否接收、财务反馈、交付邮件是否跨月、PMO、PMO备注、是否修改ones状态、是否退回重交、二次提交时间、财务二次反馈、PMO二次反馈、财务确认、补充材料、标签

**验收凭证完整字段（16列）**：
合同名称、标题、ID、BI履约ID、验收单编号-财务端、合同编号1、(空列)、合同编号、客户名称、深圳分公司-营销、项目经理、备注、交接日期、验收方式、截至目前全部/部分验收、是否

## 7. 结果处理

| 要素 | 值 |
|---|---|
| 文件格式 | CSV (UTF-8 BOM) |
| 输出目录 | `bdms/output/wecom/{YYYYMM}/` |
| 缓存目录 | `~/.openclaw/data/wecom_exports/` |
| 文件名格式 | `{YYYYMM}_确收交接.csv` / `{YYYYMM}_验收交接.csv` |

## 8. 异常处理

| 异常场景 | 处理方式 |
|---|---|
| CDP 端口连接失败 | 降级到下一级（缓存/API/本地导入） |
| 找不到目标页面 | 返回 None，走降级链 |
| 找不到 Sheet tab | 返回 None，走降级链 |
| 剪贴板数据为空/过少 | 返回 None，走降级链 |
| 找不到表头行 | 数据不完整，返回 None |
| wecom-cli 853007 权限错误 | 降级到浏览器自动化 |

## 9. 关键经验

1. **wecom-cli 遇 853007**：机器人文档权限需重新授权，阻塞 API 路径
2. **登录态持久化**：Playwright `launch_persistent_context` 是最可靠的方案
3. **全选复制是最快导出方式**：比 DOM 逐行读取快 5-10 倍，字段完整
4. **脏数据处理**：全选复制会带上表格外的筛选器/状态栏文本，需按 ID 列格式过滤
5. **Sheet tab 选择器**：`.tab-bar-item`（不要用 `[role='tab']`，企微没按 ARIA 规范来）
6. **Chrome 实例共享**：`connect_over_cdp` 不要 `browser.close()`（会关掉用户的 Chrome），只断开连接
7. **Mac 上的复制快捷键**：`Meta`（Cmd），不是 `Control`

## 10. 代码位置

| 文件 | 说明 |
|---|---|
| `bdms/modules/integration/connectors/wecom_doc_connector.py` | 主连接器，含五级降级链 |
| `bdms/core/browser.py` | 浏览器上下文管理（CDP 连接 / Cookie 持久化） |
| `bdms/core/config.py` | 配置管理（`wecom.browser_cdp_port` 等） |

## 11. 配置项

| 配置项 | 默认值 | 说明 |
|---|---|---|
| `wecom.enable_api` | `true` | 是否启用 wecom-cli API 路径 |
| `wecom.enable_browser` | `true` | 是否启用浏览器自动化路径 |
| `wecom.browser_cdp_port` | `9222` | Chrome CDP 调试端口 |
| `wecom.doc_url` | `""` | 智能表格 URL（找不到页面时打开） |

---

**变更历史**：
- 2026-10-12 v1.1：浏览器自动化路径完整实现验证 + 数据清洗规则 + 质量报告
- 2026-09-xx v1.0：初始设计（API 优先 + 浏览器降级概念设计）

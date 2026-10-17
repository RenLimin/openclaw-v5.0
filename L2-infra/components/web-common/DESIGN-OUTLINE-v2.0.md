# web-common — 概要设计 (DESIGN-OUTLINE)

> 组件：web-common (L2 基础设施层)
> 版本：v2.0
> 日期：2026-10-17
> 状态：proposed
> 关联 ADR：ADR-033

## 1. 定位

web-common 是 L2 基础设施层的 **Web UI 设计系统公共组件**，为 L3/L4 所有 Web 应用提供：

- **Design Tokens**：统一的设计语言（颜色/间距/字号/圆角/阴影/断点）
- **组件库**：可复用的 Jinja2 模板宏（布局/表单/组件/图标）
- **主题系统**：暗/亮双主题，支持切换
- **视觉回归测试**：自动化截图对比，防止视觉退化
- **UI 验收体系**：Checklist + 流程，确保交付质量

**核心价值**：从"每个项目各写各的 CSS"升级为"统一设计系统 + 质量保障"，消除视觉不一致。

## 2. 整体架构

```
┌─────────────────────────────────────────────────────────┐
│                    web-common (L2)                      │
├─────────────┬─────────────┬─────────────┬───────────────┤
│ Design      │  Component  │   Visual    │  UI Quality   │
│ Tokens      │  Library    │  Regression │  Assurance    │
│ 设计系统    │  组件库     │  Testing    │  质量保障     │
├─────────────┼─────────────┼─────────────┼───────────────┤
│ 颜色 tokens │  layout     │ Playwright  │ Checklist     │
│ 间距 tokens │  forms      │ 截图对比    │ 验收流程      │
│ 字号 tokens │  components │ 基准图管理  │ UI 设计师角色 │
│ 圆角 tokens │  icons      │ Diff 报告   │ 全量走查      │
│ 阴影 tokens │             │             │               │
│ 断点 tokens │             │             │               │
└─────────────┴─────────────┴─────────────┴───────────────┘
          ▲              ▲              ▲
          │              │              │
    L3/L4 Web 组件（finance-engine / BDMS / fin-l4 等 7 个组件，71 个页面）
```

## 3. 模块划分

### 3.1 Design Tokens 设计系统（F1）

**职责**：定义全站统一的设计语言，作为所有组件和页面的视觉基础。

**子模块**：
- **颜色体系**：品牌色 / 功能色（success/warning/error/info）/ 中性色（surface 6 级 + text 4 级 + border 3 级）
- **间距体系**：4px 步长，0.25rem ~ 4rem 共 12 档
- **字号体系**：12px ~ 32px 共 7 档，行高配套
- **圆角体系**：0 / 4px / 8px / 12px / 50% 共 5 档
- **阴影体系**：sm / md / lg 共 3 档
- **断点体系**：480px / 768px / 1024px / 1200px 共 4 档

**实现方式**：CSS 自定义属性（CSS Variables），通过 `:root` 和 `[data-theme="dark"]` 双份定义实现主题切换。

### 3.2 组件库（F2 + F3）

**职责**：封装可复用的 UI 组件，L3/L4 直接调用，不再重复实现。

**子模块**：
- **layout macro**：页面骨架（侧栏 + 主内容区 + 页头）
- **forms macro**：表单控件（input / select / button / checkbox / radio）
- **components macro**：通用组件（卡片 / 表格 / 标签 / 徽章 / 提示 / 进度条）
- **icons macro**：图标集（内联 SVG）
- **主题系统**：暗/亮双主题完整覆盖

**设计原则**：
- 组件优先复用 Tokens，不硬编码颜色/尺寸
- 每个组件有明确的 props 契约
- 暗/亮双主题都要验证

### 3.3 视觉回归测试（F4）

**职责**：自动化检测 UI 视觉变化，防止改 A 页面弄坏 B 页面。

**技术选型**：Playwright Python + 像素级对比

**子模块**：
- **截图引擎**：基于 Playwright Page.screenshot()
- **对比引擎**：PIL 像素对比 + 容忍度阈值
- **基准图管理**：golden/ 目录，版本化管理
- **动态内容 Mask**：对图表/数据列表等动态区域忽略对比
- **Diff 报告**：失败时生成三栏对比图（基准/实际/差异）

**工作流**：
```
首次运行 → 截图保存为基准图（golden）
后续运行 → 截图 → 与基准图对比 → 差异超阈值 → 失败 + 生成 diff 报告
         → 差异在阈值内 → 通过
```

### 3.4 UI 质量保障（F5 + F6 + F7）

**职责**：制度和流程层面确保 UI 质量。

**子模块**：
- **UI 验收 Checklist**：5 大类 25+ 检查项
- **交付流程嵌入**：交付 7 步法新增第 8 步「视觉验收」
- **UI 设计师角色**：role-library 新增 ui-designer 角色
- **全量页面走查**：7 组件 × 71 页面逐一排查修复

## 4. 接口契约

### 4.1 Design Tokens 契约（CSS Variables）

L3/L4 组件通过 CSS 变量使用 Tokens，禁止硬编码：

```css
/* ✅ 正确 */
.card {
  background: var(--c-surface);
  padding: var(--s-4);
  border-radius: var(--radius);
}

/* ❌ 错误 */
.card {
  background: #ffffff;
  padding: 16px;
  border-radius: 8px;
}
```

### 4.2 组件 Macro 契约

Jinja2 macro 调用方式：

```jinja2
{% from "components.html" import card, button %}

{% call card(title="状态概览") %}
  <p>内容...</p>
{% endcall %}

{{ button(text="生成报告", variant="primary") }}
```

### 4.3 视觉测试 API 契约

```python
# 测试用例示例
from web_common.tests.visual import VisualTestBase

class TestBDMSReport(VisualTestBase):
    url = "/report"
    mask_selectors = [".chart-area", ".data-table"]  # 动态区域
    
    def test_report_page(self, page):
        page.goto(self.url)
        self.assert_visual_match(page, "report-page")
```

## 5. 数据流

### 5.1 Design Tokens 数据流

```
Design Tokens 定义 (CSS Variables)
  → L2 组件库使用
    → L3/L4 页面复用
      → 用户浏览器渲染
```

### 5.2 视觉回归测试数据流

```
测试启动 → Playwright 打开页面 → 截图
  → 检查是否有基准图
    → 无基准图：保存为 golden，测试通过
    → 有基准图：像素对比
      → 差异 < 阈值：通过
      → 差异 > 阈值：失败，生成 diff 报告
```

## 6. 依赖关系

### 6.1 上游依赖
- **L1 运行时**：无直接依赖（纯前端 + Python 测试框架）
- **浏览器**：Chromium（Playwright 内置）
- **Python**：Playwright Python / Pillow

### 6.2 下游依赖
- L3 业务层所有 Web 组件
- L4 专有层所有 Web 组件
- 交付 7 步法验收流程

## 7. 非功能设计

### 7.1 向后兼容
- v2.0 Tokens 与 v1.0 CSS 变量并存，逐步迁移
- 现有页面样式不破坏，新增样式只加不改
- 旧变量保留到 v3.0 再清理

### 7.2 性能
- CSS 文件体积增加 < 5KB（Tokens 定义）
- 视觉测试单页面 < 5 秒（不含首次基准图生成）
- 全量 71 页面测试 < 5 分钟

### 7.3 可维护性
- Tokens 单一来源，集中管理
- 组件文档化，用法清晰
- 基准图纳入版本控制

## 8. 演进路线

| Phase | 内容 | 关键里程碑 |
|---|---|---|
| Phase 1 | Design Tokens + 视觉测试框架 + Checklist + UI 角色 | 基础设施可用 |
| Phase 2 | 组件库规范化 + 文档补齐 + CI 接入 | 组件库可复用 |
| Phase 3 | 全量 71 页面走查 + 批量修复 | 视觉质量达标 |
| Phase 4 | 核心交互组件补全（Dropdown/Modal/Tabs/表单/分页/表格） | 交互组件齐备 |
| Phase 5 | 可访问性（WCAG AA）+ 移动适配 | 无障碍/移动达标 |
| Phase 6 | 排版体系 + 阴影层次 + 暗黑模式优化 | 视觉层次专业 |
| Phase 7 | 工程化：Storybook + 构建流程 + ESLint 检查 | 开发体验提升 |
| Phase 8 | 动效体系 + 主题定制能力 | 交互体验完整 |

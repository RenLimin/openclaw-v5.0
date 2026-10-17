# web-common — 详细设计 (DESIGN-DETAIL)

> 组件：web-common (L2 基础设施层)
> 版本：v2.0
> 日期：2026-10-17
> 状态：proposed
> 关联 ADR：ADR-033

## 1. Design Tokens 详细设计

### 1.1 命名规范

统一前缀 `--c-` (color) / `--s-` (space) / `--fs-` (font-size) / `--r-` (radius) / `--sh-` (shadow) / `--bp-` (breakpoint)。

```css
:root {
  /* 颜色前缀: --c- */
  --c-primary: #2563eb;
  --c-surface: #ffffff;
  
  /* 间距前缀: --s- */
  --s-1: 0.25rem;  /* 4px */
  --s-2: 0.5rem;   /* 8px */
  
  /* 字号前缀: --fs- */
  --fs-xs: 0.75rem;  /* 12px */
  --fs-sm: 0.875rem; /* 14px */
}
```

### 1.2 颜色体系

#### 品牌色

| Token | 亮色 | 暗色 | 用途 |
|---|---|---|---|
| `--c-primary` | #2563eb | #3b82f6 | 主按钮、链接、选中态 |
| `--c-primary-hover` | #1d4ed8 | #60a5fa | hover 态 |
| `--c-primary-light` | #dbeafe | #1e3a5f | 轻量背景 |

#### 功能色

| Token | 亮色 | 暗色 | 用途 |
|---|---|---|---|
| `--c-success` | #10b981 | #34d399 | 成功状态、已通过 |
| `--c-warning` | #f59e0b | #fbbf24 | 警告状态、待审核 |
| `--c-error` | #ef4444 | #f87171 | 错误状态、驳回 |
| `--c-info` | #06b6d4 | #22d3ee | 信息提示 |

#### 中性色（Surface 层级）

| Token | 亮色 | 暗色 | 用途 |
|---|---|---|---|
| `--c-bg` | #f8fafc | #0f172a | 页面背景 |
| `--c-surface` | #ffffff | #1e293b | 卡片/面板背景 |
| `--c-surface-2` | #f1f5f9 | #334155 | 次级表面（表格头、侧栏） |
| `--c-surface-3` | #e2e8f0 | #475569 | 三级表面（hover 行、分隔线） |
| `--c-border` | #e2e8f0 | #334155 | 默认边框 |
| `--c-border-light` | #f1f5f9 | #1e293b | 浅色边框 |
| `--c-border-strong` | #cbd5e1 | #475569 | 强调边框 |

#### 文字色

| Token | 亮色 | 暗色 | 用途 |
|---|---|---|---|
| `--c-text` | #0f172a | #f1f5f9 | 正文 |
| `--c-text-secondary` | #475569 | #cbd5e1 | 次要文字 |
| `--c-text-muted` | #94a3b8 | #64748b | 辅助文字、占位符 |
| `--c-text-inverse` | #ffffff | #0f172a | 反色文字（按钮内） |

### 1.3 间距体系

4px 步长（1rem = 16px 基准），共 12 档：

| Token | rem | px | 典型用途 |
|---|---|---|---|
| `--s-0` | 0 | 0 | 无间距 |
| `--s-1` | 0.25rem | 4px | 元素内微间距 |
| `--s-2` | 0.5rem | 8px | 紧凑元素间距 |
| `--s-3` | 0.75rem | 12px | 卡片内间距（小） |
| `--s-4` | 1rem | 16px | 卡片内间距（默认） |
| `--s-5` | 1.5rem | 24px | 区块间距 |
| `--s-6` | 2rem | 32px | 大区块间距 |
| `--s-7` | 2.5rem | 40px | 页面顶部间距 |
| `--s-8` | 3rem | 48px | 页面大间距 |
| `--s-10` | 4rem | 64px | 超大间距 |

### 1.4 字号体系

| Token | rem | px | 用途 |
|---|---|---|---|
| `--fs-xs` | 0.75rem | 12px | 标签、辅助文字 |
| `--fs-sm` | 0.875rem | 14px | 正文（小）、表单文字 |
| `--fs-base` | 1rem | 16px | 正文（默认） |
| `--fs-lg` | 1.125rem | 18px | 小标题、强调文字 |
| `--fs-xl` | 1.25rem | 20px | 卡片标题 |
| `--fs-2xl` | 1.5rem | 24px | 页面二级标题 |
| `--fs-3xl` | 2rem | 32px | 页面主标题 |

### 1.5 行高体系

| Token | 值 | 用途 |
|---|---|---|
| `--lh-tight` | 1.2 | 大标题 |
| `--lh-base` | 1.5 | 正文、段落 |
| `--lh-loose` | 1.6 | 大段落文字 |

### 1.6 字重体系

| Token | 值 | 用途 |
|---|---|---|
| `--fw-light` | 300 | 轻量文字、次要信息 |
| `--fw-normal` | 400 | 普通正文 |
| `--fw-medium` | 500 | 小标题、强调文字 |
| `--fw-semibold` | 600 | 卡片标题、按钮文字 |
| `--fw-bold` | 700 | 大标题、重量级强调 |

### 1.7 字体族体系

| Token | 字体栈 | 用途 |
|---|---|---|
| `--ff-sans` | -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans", sans-serif | 正文、UI 元素（默认） |
| `--ff-mono` | SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace | 代码、等宽文字 |

### 1.8 圆角体系

| Token | 值 | 用途 |
|---|---|---|
| `--r-none` | 0 | 无圆角 |
| `--r-sm` | 4px | 小按钮、标签 |
| `--radius` | 8px | 默认圆角（卡片、按钮、输入框） |
| `--r-lg` | 12px | 大卡片、模态框 |
| `--r-full` | 9999px | 圆形元素、胶囊按钮 |

### 1.9 阴影体系

| Token | 值 | 用途 | 层级 |
|---|---|---|---|
| `--sh-0` | none | 无阴影 | 0 |
| `--sh-sm` | 0 1px 2px rgba(0,0,0,0.05) | 轻微阴影（小卡片） | 1 |
| `--sh-md` | 0 2px 8px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04) | 默认阴影（卡片、浮层） | 2 |
| `--sh-lg` | 0 8px 24px rgba(0,0,0,0.08), 0 2px 4px rgba(0,0,0,0.04) | 大阴影（下拉菜单、模态框） | 3 |
| `--sh-xl` | 0 16px 48px rgba(0,0,0,0.12), 0 4px 8px rgba(0,0,0,0.04) | 超大阴影（浮层、模态框） | 4 |

**设计原则：** 阴影层次越高，浮层层级越高，帮助用户建立清晰的视觉层次结构。

### 1.10 断点体系

| Token | 值 | 设备 |
|---|---|---|
| `--bp-sm` | 480px | 手机横屏 |
| `--bp-md` | 768px | 平板竖屏 |
| `--bp-lg` | 1024px | 平板横屏 / 小屏笔记本 |
| `--bp-xl` | 1200px | 桌面端 |

### 1.11 CSS 变量实现方案

- Tokens 定义在 `static/css/tokens.css`
- `base.css` `@import` tokens.css
- 暗色主题通过 `[data-theme="dark"]` 选择器覆盖
- 与现有变量并存，逐步迁移，不破坏现有页面

---

## 2. 暗黑模式优化

### 2.1 设计目标

- 明暗模式各自适配，保证在两种模式下都有舒适的阅读体验
- 对比度优化，符合 WCAG AA 标准
- 图片/图表适配，暗色模式下调低亮度，避免刺眼

### 2.2 实现方案

- 所有颜色 tokens 在明暗模式下都有不同值，覆盖背景、表面、文字、边框
- 对比度：浅色模式下文字对比 ≥ 4.5:1，深色模式下同样保证
- 图片适配：CSS filter `brightness(0.8)` 在暗色模式下调暗图片
- 品牌区适配：暗色模式下品牌区保证 logo 和文字对比度

### 2.3 主题切换

- 支持读取系统 `prefers-color-scheme` 自动切换
- 用户手动切换后记住选择（localStorage）
- 默认跟随系统，可覆盖

---

## 3. 核心交互组件详细设计

### 3.1 待实现组件清单

| 组件 | 优先级 | 状态 | 描述 |
|---|---|---|---|
| 下拉菜单（Dropdown） | P0 | 待实现 | 点击展开，点击外部关闭，支持分组/搜索 |
| 模态弹窗（Modal） | P0 | 待实现 | 居中弹出，蒙层背景，关闭回调 |
| 标签页（Tabs） | P0 | 待实现 | 切换激活状态，保存历史位置 |
| 表单控件 | P0 | 待实现 | 输入框/单选/多选/开关，统一校验状态 |
| 分页（Pagination） | P0 | 待实现 | 页码跳转，每页大小选择 |
| 表格（Table） | P0 | 待实现 | 固定表头、列排序、筛选、滚动 |
| 面包屑导航（Breadcrumb） | P1 | 待实现 | 自动生成，当前页高亮 |
| 下拉选择（Select） | P1 | 待实现 | 搜索过滤、多选、选项分组 |
| 日期选择器 | P2 | 待实现 | 日期/范围选择 |

### 3.2 通用规范

- 所有组件使用 tokens，不硬编码样式
- 深色模式自动适配
- 可访问性：ARIA 标注 + 键盘导航
- 响应式：移动/桌面分别适配

---

## 4. 可访问性设计

### 4.1 设计目标

- 符合 WCAG 2.1 AA 标准
- 支持键盘导航所有交互元素
- 屏幕阅读器可正确识别所有内容

### 4.2 实现要点

1. **ARIA 标注**
   - 所有交互元素添加正确 ARIA label 和属性
   - 状态变化更新 ARIA 属性（如展开/折叠）

2. **键盘导航**
   - Tab 键可以遍历所有可交互元素
   - Enter / Space 确认激活
   - Esc 关闭弹窗/下拉菜单
   - 方向键在菜单/列表中导航

3. **对比度**
   - 正文文字对比度 ≥ 4.5:1
   - 大文字对比度 ≥ 3:1
   - 边界不依赖颜色 alone 传达信息

4. **语义化 HTML**
   - 使用正确语义标签（nav/header/main/footer/button/a 等）
   - 不使用 div 模拟按钮/链接

---

## 5. 移动适配

### 5.1 断点适配

| 断点 | 设备 | 适配要点 |
|---|---|---|
| < 480px | 手机竖屏 | 侧边栏全屏菜单，内容区 100% 宽度，表格横向滚动 |
| 480px - 768px | 手机横屏 | 侧边栏窄模式，内容区适配 |
| > 768px | 平板/桌面 | 完整侧边栏 |

### 5.2 移动端优化

- 侧边栏移动端：点击菜单按钮全屏展开，点击蒙层关闭
- 表格：内容超出时横向滚动，不折行保证可读性
- 间距：移动端减少间距，节省屏幕空间
- 点击区域：按钮/可点击元素最小 48×48px

---

## 6. 视觉回归测试详细设计

### 2.1 技术选型

**方案**：Playwright Python + Pillow 像素对比

**选型理由**：
- Python 原生支持，与现有技术栈一致
- Playwright 截图稳定，支持多浏览器
- Pillow 像素对比轻量可控
- 零额外 SaaS 依赖，完全本地化

### 2.2 模块结构

```
tests/visual/
├── __init__.py
├── base.py              # VisualTestBase 基类
├── conftest.py          # pytest fixture
├── golden/              # 黄金基准图（按页面分类）
│   ├── bdms/
│   ├── fin-l4/
│   └── ...
├── diff/                # 差异报告（运行时生成）
└── examples/
    └── test_example.py  # 示例测试用例
```

### 2.3 核心类设计

```python
class VisualTestBase:
    """视觉回归测试基类"""
    
    # 子类设置
    url: str = ""                    # 页面 URL
    base_url: str = "http://127.0.0.1:8000"
    viewport: tuple = (1440, 900)   # 视口尺寸
    threshold: float = 0.001         # 差异容忍度（0.1% 像素）
    mask_selectors: list = []        # 动态内容 mask 选择器
    wait_for_selector: str = None    # 等待元素出现再截图
    
    def assert_visual_match(self, page, name: str):
        """截图并与基准图对比"""
        # 1. 设置视口
        # 2. mask 动态区域
        # 3. 截图
        # 4. 检查基准图是否存在
        #    - 不存在 → 保存为 golden，通过
        #    - 存在 → 像素对比
        # 5. 差异超阈值 → 生成 diff 图，断言失败
        # 6. 差异在阈值内 → 通过
```

### 2.4 像素对比算法

使用 Pillow 的 `ImageChops.difference()` + 直方图统计：

```python
def compare_images(img1_path, img2_path, threshold=0.001):
    """对比两张图片，返回 (是否通过, 差异百分比, diff_image)"""
    from PIL import Image, ImageChops
    
    img1 = Image.open(img1_path).convert('RGB')
    img2 = Image.open(img2_path).convert('RGB')
    
    # 尺寸不同直接失败
    if img1.size != img2.size:
        return False, 1.0, None
    
    # 像素对比
    diff = ImageChops.difference(img1, img2)
    # 统计有差异的像素数
    diff_bbox = diff.getbbox()
    if diff_bbox is None:
        return True, 0.0, None
    
    # 直方图法：计算差异像素占比
    hist = diff.histogram()
    total_pixels = img1.size[0] * img1.size[1]
    diff_pixels = sum(v for i, v in enumerate(hist) if i % 256 > 10)
    diff_ratio = diff_pixels / (total_pixels * 3)  # 3 通道
    
    return diff_ratio <= threshold, diff_ratio, diff
```

### 2.5 动态内容 Mask

**机制**：截图前，用 Playwright `locator.evaluate()` 给 mask 元素加半透明黑色覆盖层，消除动态内容干扰。

```python
def mask_dynamic_content(page, selectors):
    """给动态内容区域加 mask"""
    for selector in selectors:
        page.evaluate(f"""(sel) => {{
            document.querySelectorAll(sel).forEach(el => {{
                el.style.visibility = 'hidden';
            }});
        }}""", selector)
```

### 2.6 Diff 报告

测试失败时生成三栏 HTML 报告：
- 左：基准图（golden）
- 中：实际截图（actual）
- 右：差异高亮图（diff，红色标记差异像素）

---

## 7. UI 验收 Checklist 详细设计

### 3.1 布局对齐类（6 项）

| # | 检查项 | 判断标准 | 检查方法 |
|---|---|---|---|
| L1 | 栅格对齐 | 所有内容块对齐到统一的间距网格 | 截图 + 辅助线检查 |
| L2 | 左右边距一致 | 页面左右留白对称且一致 | 像素测量 |
| L3 | 卡片间距统一 | 同级别卡片间距使用相同 Token | 代码审查 + 视觉检查 |
| L4 | 响应式断点 | 各断点下布局不溢出、不错乱 | 多尺寸截图 |
| L5 | 内容溢出 | 文字不超出容器、表格不溢出视口 | 各页面检查 |
| L6 | 空状态布局 | 空状态垂直居中、有合理留白 | 空数据场景测试 |

### 3.2 视觉层次类（5 项）

| # | 检查项 | 判断标准 | 检查方法 |
|---|---|---|---|
| V1 | 标题层级清晰 | H1/H2/H3 字号逐级递减，差 ≥ 2px | 代码审查 |
| V2 | 主次对比明确 | 主要信息突出，次要信息弱化 | 走查 |
| V3 | 信息密度合理 | 不太挤也不太松，符合 Tokens 规范 | 走查 |
| V4 | 颜色使用一致 | 成功/警告/错误使用对应功能色 | 代码审查 |
| V5 | 图标风格统一 | 线性/面性不混用，尺寸一致 | 走查 |

### 3.3 组件一致性类（6 项）

| # | 检查项 | 判断标准 | 检查方法 |
|---|---|---|---|
| C1 | 按钮样式统一 | 主按钮/次按钮/文字按钮风格一致 | 组件级走查 |
| C2 | 输入框样式统一 | 高度、边框、圆角、间距一致 | 组件级走查 |
| C3 | 表格样式统一 | 表头、行高、分隔线一致 | 组件级走查 |
| C4 | 卡片样式统一 | padding、圆角、阴影一致 | 组件级走查 |
| C5 | 标签/徽章统一 | 颜色语义一致、尺寸一致 | 组件级走查 |
| C6 | 分页/加载统一 | 加载状态、空状态、错误态一致 | 组件级走查 |

### 3.4 交互反馈类（5 项）

| # | 检查项 | 判断标准 | 检查方法 |
|---|---|---|---|
| I1 | Hover 状态 | 所有可点击元素有 hover 反馈 | 逐元素测试 |
| I2 | 点击反馈 | 按钮点击有视觉反馈 | 逐元素测试 |
| I3 | 加载状态 | 异步操作有 loading 指示 | 场景测试 |
| I4 | 错误提示 | 表单错误有明确提示和定位 | 场景测试 |
| I5 | Toast 通知 | 操作成功/失败有统一提示 | 场景测试 |

### 3.5 可访问性类（3 项）

| # | 检查项 | 判断标准 | 检查方法 |
|---|---|---|---|
| A1 | 对比度达标 | 文字与背景对比度 ≥ 4.5:1 | 工具检测 |
| A2 | 字号可读 | 最小字号 ≥ 12px | 代码审查 |
| A3 | 键盘导航 | Tab 键可遍历所有交互元素 | 手动测试 |

### 3.6 验收流程

**嵌入交付 7 步法第 8 步**：

```
开发完成
  → 功能自测通过
  → 视觉回归测试通过（无意外差异）
  → UI Checklist 逐项走查
  → 黄金基准图更新（如属预期变更）
  → 交付
```

---

## 8. UI 设计师角色详细设计

### 4.1 角色定义

```yaml
role_id: ui-designer
name: UI 设计师
category: design
description: 负责 UI 走查、布局优化、组件规范、视觉一致性检查
tools: [read, write, exec, visual-test, pixel-analysis]
permissions: [read-write]
```

### 4.2 职责

1. **UI 走查**：按 Checklist 逐项检查页面视觉质量
2. **布局优化**：调整间距、对齐、留白，提升视觉品质
3. **组件规范**：确保所有组件符合设计系统规范
4. **视觉一致性**：跨页面、跨组件的一致性检查
5. **基准图管理**：建立和更新视觉基准图

### 4.3 工作流

```
收到走查请求
  → 启动目标页面服务
  → Playwright 截图
  → 按 Checklist 逐项检查
  → 像素测量布局参数
  → 生成走查报告（问题清单 + 建议 + 截图）
  → （如需修复）生成 CSS 补丁
  → 重新截图验证
  → 输出最终结果
```

### 4.4 输出格式

```markdown
## UI 走查报告 - [页面名]

### 整体评价
- 布局：⭐⭐⭐⭐☆
- 一致性：⭐⭐⭐⭐☆
- 可访问性：⭐⭐⭐⭐☆

### 问题清单
| # | 类别 | 问题 | 严重程度 | 建议 |
|---|---|---|---|---|

### 截图对比
[基准图 vs 实际图]
```

---

## 9. 全量页面 UI 走查方案

### 5.1 范围

| 组件 | 页面数 | 优先级 |
|---|---|---|
| BDMS | 9 | P0（当前问题集中） |
| FIN-L4 | 19 | P1 |
| Finance Engine | 18 | P1 |
| Office Contract | 6 | P2 |
| Delivery Center | 5 | P2 |
| CISSP Trainer | 9 | P2 |
| Bangcle PPT | 5 | P2 |
| **合计** | **71** | |

### 5.2 走查流程

每个页面执行：
1. 启动对应组件的 Web 服务
2. Playwright 截图（桌面端 1440px + 移动端 375px）
3. 自动检查：布局溢出 / 文字截断 / 颜色对比度
4. 人工（UI 设计师角色）按 Checklist 走查
5. 记录问题，分类（布局/间距/对齐/一致性）
6. 批量修复
7. 更新基准图

### 5.3 问题分级

| 级别 | 定义 | 处理 |
|---|---|---|
| P0 | 内容溢出 / 布局错乱 / 影响使用 | 立即修复 |
| P1 | 间距不一致 / 对齐偏差 / 明显不美观 | 走查期间修复 |
| P2 | 细微瑕疵 / 优化建议 | 后续迭代 |

---

## 10. 目录结构

```
web-common/
├── PRD-v2.0.md
├── DESIGN-OUTLINE-v2.0.md
├── DESIGN-DETAIL-v2.0.md
├── VERIFICATION-v2.0.md
├── OPERATIONS-v2.0.md
├── IMPLEMENTATION-PLAN-v2.0.md
├── DESIGN-TOKENS.md          # 新增：设计 Tokens 参考文档
├── UI-CHECKLIST.md           # 新增：UI 验收 Checklist
├── macros/
│   ├── layout.html
│   ├── components.html
│   ├── forms.html
│   └── icons.html
├── static/
│   ├── css/
│   │   ├── tokens.css        # 新增：Design Tokens 定义
│   │   ├── base.css
│   │   ├── layout.css
│   │   ├── components.css
│   │   └── forms.css
│   └── js/
│       ├── theme.js
│       ├── sidebar.js
│       └── toast.js
├── tests/
│   ├── visual/               # 新增：视觉回归测试
│   │   ├── base.py
│   │   ├── conftest.py
│   │   ├── golden/
│   │   └── examples/
│   └── unit/
└── examples/
    └── demo.html
```

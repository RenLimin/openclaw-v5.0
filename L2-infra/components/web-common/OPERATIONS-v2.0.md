# web-common — 操作手册 (OPERATIONS)

> 组件：web-common (L2 基础设施层)
> 版本：v2.0
> 日期：2026-10-17
> 状态：proposed
> 关联 ADR：ADR-033

## 1. 组件概览

web-common 是 L2 层的 Web UI 设计系统公共组件，提供 Design Tokens、组件库、视觉回归测试、UI 验收体系。

- **代码位置**：`L2-infra/components/web-common/`
- **设计文档**：PRD-v2.0 / DESIGN-OUTLINE-v2.0 / DESIGN-DETAIL-v2.0
- **依赖**：Python 3.10+ / Playwright Python / Pillow / Jinja2

## 2. 安装与配置

### 2.1 安装 Playwright

```bash
# 安装 Python 包
pip install playwright pillow

# 安装浏览器
playwright install chromium
```

### 2.2 验证安装

```bash
# 验证 Playwright 可用
python3 -c "from playwright.sync_api import sync_playwright; print('Playwright OK')"

# 验证截图功能
python3 -c "
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={'width': 1440, 'height': 900})
    page.goto('about:blank')
    page.screenshot(path='/tmp/test-screenshot.png')
    browser.close()
    print('Screenshot OK')
"
```

### 2.3 目录结构

```
web-common/
├── macros/              # Jinja2 模板宏
├── static/css/          # CSS 样式 + Design Tokens
├── static/js/           # JS 工具
├── tests/visual/        # 视觉回归测试
├── examples/            # 组件示例
└── docs/                # 参考文档
```

## 3. Design Tokens 使用指南

### 3.1 在 CSS 中使用

```css
/* ✅ 正确：使用 Token */
.card {
  background: var(--c-surface);
  color: var(--c-text);
  padding: var(--s-4);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
}

/* ❌ 错误：硬编码 */
.card {
  background: #fff;
  color: #0f172a;
  padding: 16px;
  border-radius: 8px;
}
```

### 3.2 在 Jinja2 模板中使用

通过 macro 组件间接使用 Tokens，不要在模板里硬编码样式。

```jinja2
{# ✅ 正确：使用组件 macro #}
{% from "components.html" import card, button %}

{% call card(title="状态") %}
  <p>内容</p>
  {{ button(text="操作", variant="primary") }}
{% endcall %}
```

### 3.3 暗色主题

自动通过 `data-theme` 属性切换：

```html
<!-- 亮色主题（默认） -->
<html data-theme="light">

<!-- 暗色主题 -->
<html data-theme="dark">
```

JS 切换：
```javascript
// 切换主题
document.documentElement.setAttribute('data-theme', 'dark');

// 获取当前主题
const theme = document.documentElement.getAttribute('data-theme');
```

## 4. 视觉回归测试操作

### 4.1 快速开始

```bash
# 进入组件目录
cd L4-proprietary/components/bdms/src/bdms/web

# 启动服务
python3 -m uvicorn bdms.web.main:app --host 127.0.0.1 --port 8000 &

# 运行视觉测试
cd L2-infra/components/web-common/tests/visual/
python3 -m pytest test_bdms.py -v
```

### 4.2 编写测试用例

```python
# tests/visual/test_bdms.py
from web_common.tests.visual import VisualTestBase
import pytest

class TestBDMSReport(VisualTestBase):
    base_url = "http://127.0.0.1:8000"
    url = "/report"
    viewport = (1440, 900)
    threshold = 0.001  # 0.1% 容忍度
    mask_selectors = [
        ".chart-area",      # 图表动态内容
        ".data-table",      # 数据表动态内容
    ]
    
    def test_report_page(self, page):
        """报表页视觉回归"""
        page.goto(self.url)
        page.wait_for_selector(".report-container")
        self.assert_visual_match(page, "report-page")
```

### 4.3 常用命令

```bash
# 运行指定测试
pytest test_bdms.py::TestBDMSReport::test_report_page -v

# 更新基准图（确认变更是预期的）
pytest test_bdms.py --update-golden

# 查看 diff 报告
# 测试失败后，diff 图在 tests/visual/diff/ 目录下
open tests/visual/diff/

# 指定视口尺寸
pytest test_bdms.py --viewport 375x812
```

### 4.4 基准图管理

```bash
# 黄金基准图位置
ls tests/visual/golden/bdms/

# 新增页面 → 首次运行自动生成基准图
# 修改页面 → 运行测试对比 → 确认后更新基准图
```

## 5. UI 验收操作

### 5.1 Checklist 使用

```markdown
## UI 验收 Checklist

### 布局对齐
- [ ] 栅格对齐
- [ ] 左右边距一致
- [ ] 卡片间距统一
- [ ] 响应式断点正常
- [ ] 内容无溢出
- [ ] 空状态布局合理

### 视觉层次
- [ ] 标题层级清晰
- [ ] 主次对比明确
- [ ] 信息密度合理
- [ ] 颜色使用一致
- [ ] 图标风格统一
```

完整清单见 `UI-CHECKLIST.md`。

### 5.2 验收流程

```
开发完成
  ↓
1. 功能自测通过
  ↓
2. 运行视觉回归测试
   - 通过 → 继续
   - 失败 → 检查是 bug 还是预期变更 → 更新基准图
  ↓
3. UI Checklist 逐项走查
   - 逐项打勾
   - 记录问题
  ↓
4. 修复问题
  ↓
5. 回归验证
  ↓
交付
```

### 5.3 UI 走查报告模板

```markdown
## UI 走查报告 — [页面名]

### 整体评价
- 布局：⭐⭐⭐⭐☆
- 一致性：⭐⭐⭐⭐☆
- 可访问性：⭐⭐⭐⭐☆

### 问题清单
| # | 类别 | 问题 | 严重程度 | 建议 |
|---|---|---|---|---|
| 1 | 布局 | 状态卡右侧留白过多 | P1 | 调整内容区宽度 |
| 2 | 一致性 | 按钮高度不统一 | P2 | 统一为 36px |

### 截图
[页面截图]
```

## 6. 常见问题

### 6.1 Playwright 安装失败

```bash
# 报错：Playwright installation failed
# 尝试：
pip install --upgrade playwright
playwright install --with-deps chromium

# macOS 权限问题：
xattr -d com.apple.quarantine ~/Library/Caches/ms-playwright/Chromium.app
```

### 6.2 视觉测试误报率高

**原因**：动态内容（图表、数据、时间）导致每次截图不同。

**解决**：
```python
# 增加 mask 选择器
mask_selectors = [".chart", ".data-table", ".timestamp"]

# 或提高容忍度
threshold = 0.005  # 0.5%
```

### 6.3 暗色主题下颜色不对

**检查**：
1. 是否在 `[data-theme="dark"]` 下定义了对应 Token
2. JS 切换是否正确设置了 `data-theme` 属性
3. 浏览器缓存是否需要清

### 6.4 组件样式被覆盖

**原因**：CSS 权重问题，页面内联样式覆盖了组件库样式。

**解决**：
- 优先使用组件 macro，不要直接写内联样式
- 确需覆盖时，使用更具体的选择器或 `!important`
- 特殊情况在页面级 `<style>` 中覆盖

## 7. 故障排查

### 7.1 视觉测试不运行

```bash
# 检查 Playwright 是否安装
python3 -c "import playwright; print(playwright.__version__)"

# 检查浏览器
ls ~/Library/Caches/ms-playwright/
```

### 7.2 Tokens 不生效

```bash
# 检查 tokens.css 是否被正确引入
grep "tokens.css" templates/base.html

# 检查变量名拼写
grep -n "c-primary" static/css/tokens.css
```

### 7.3 主题切换不生效

```javascript
// 控制台检查
console.log(document.documentElement.getAttribute('data-theme'));

// 检查 CSS
getComputedStyle(document.documentElement).getPropertyValue('--c-surface');
```

## 8. 相关文档

- DESIGN-TOKENS.md
- UI-CHECKLIST.md
- PRD-v2.0.md
- DESIGN-DETAIL-v2.0.md
- VERIFICATION-v2.0.md
- IMPLEMENTATION-PLAN-v2.0.md

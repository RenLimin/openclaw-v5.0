# Bangcle 品牌主题 · 使用说明

> 组件：web-common (L2) · 版本 v1.0 · 2026-10-31
> 主题文件：`static/css/theme-bangcle.css`
> 演示：`examples/theme-bangcle.html`

## 1. 设计原则

- **opt-in（可选启用）**：主题只在 `[data-theme="bangcle"]` 选择器下生效，**绝不在 `:root` 覆盖**。
- **零破坏**：现有所有 L3/L4 应用不引入此属性，外观保持不变。
- **可回滚**：移除 `data-theme` 属性即恢复默认，无需删样式或改代码。
- **单一来源**：主题覆盖 v1 颜色变量（`--c-*`）与字体 token，v2 语义别名经桥接自动跟随，不重复定义组件样式。

## 2. 启用方式

在需要品牌化的页面根元素加一个属性，并在标准样式表**之后**引入主题文件：

```html
<html lang="zh-CN" data-theme="bangcle">
<head>
  <link rel="stylesheet" href="/static/web-common/css/base.css">
  <link rel="stylesheet" href="/static/web-common/css/tokens.css">
  <link rel="stylesheet" href="/static/web-common/css/layout.css">
  <link rel="stylesheet" href="/static/web-common/css/components.css">
  <!-- 品牌主题：必须最后加载 -->
  <link rel="stylesheet" href="/static/web-common/css/theme-bangcle.css">
</head>
```

也可只对页面内某个容器加 `data-theme="bangcle"`，实现局部品牌化。

## 3. 品牌色板（VI C-01 ~ C-07）

来源：`L4-proprietary/components/bangcle-ppt/src/bangcle_ppt/theme/design_constants.py`

| Token | 色值 | 名称 | 编号 |
|---|---|---|---|
| `--bangcle-primary` | `#2D74BB` | 梆梆蓝 | C-01 |
| `--bangcle-light` | `#3FA1DA` | 浅蓝 | C-02 |
| `--bangcle-cyan` | `#27AABF` | 青色 | C-03 |
| `--bangcle-teal` | `#33ADA0` | 青绿 | C-04 |
| `--bangcle-gold` | `#EFBA20` | 金色 | C-05 |
| `--bangcle-navy` | `#00122B` | 深藏青 | C-06 |
| `--bangcle-dark-gray` | `#595757` | 深灰 | C-07 |

辅助：`--bangcle-very-light-blue #BEE3FA`。

## 4. 字体

品牌字体统一为 **Source Han Sans（思源黑体）**，字体族变量 `--ff-sans` 已在主题内重写，
`--font-body` / `--font-display` 同步跟随：

```
"Source Han Sans CN", "Source Han Sans SC", "Noto Sans CJK SC", "Source Han Sans",
-apple-system, "PingFang SC", "Microsoft YaHei", sans-serif
```

> 注意：思源黑体未安装时会回退到系统黑体。需要强一致离线显示时，再评估内嵌 woff2（会增加体积）。

## 5. 辅助类

- `.bangcle-surface-dark`：深藏青深色表面（侧栏/页头）。
- `.bangcle-accent`：金色强调文字。

## 6. 验收要点

- 不启用 `data-theme="bangcle"` 的页面，渲染结果与改动前像素一致。
- 启用后，主色按钮、链接、focus 边框、图表强调色均为梆梆蓝；深色侧栏为深藏青。
- 中英数文字统一走思源黑体栈。

# Bangcle PPT 模板系统

> **组件 ID**: CPT-012  
> **层级**: L4 专有业务层  
> **类型**: 设计系统 / 模板引擎  
> **设计规范来源**: 梆梆安全官方 VI 模板（浅色 19 页 + 深色 15 页）

基于梆梆安全官方 VI 规范的 PPT 模板生成系统，提供 DSL + 模板引擎 + 34 个预置模板，一键生成符合品牌规范的演示文稿。

---

## ✨ 特性

- 🎨 **严格遵循 VI 规范** — 所有模板严格对齐官方配色、字体、间距规范
- 📐 **25+ 页面类型** — 封面、目录、章节、图文、数据、图表、时间轴、流程图...
- 🌓 **双主题支持** — 浅色（19页）+ 深色（15页）两套完整模板
- 🏗️ **可扩展架构** — 新增页面 = 新 Schema + 新 Renderer + 注册
- 📝 **DSL 驱动** — YAML 描述模板，版本可控，易维护
- ✅ **完整测试** — 200+ 测试用例，所有模板均通过 schema 校验和渲染测试

---

## 📦 安装

### 依赖

- Python 3.10+
- `python-pptx` — PPT 生成
- `pydantic` v2 — DSL Schema 校验
- `pyyaml` — YAML 模板加载

```bash
pip install python-pptx pydantic pyyaml
```

### 快速开始

```python
from bangcle_ppt.engine import TemplateEngine
from bangcle_ppt.renderers import REGISTRY

# 初始化引擎
engine = TemplateEngine(
    templates_dir="bangcle_ppt/templates",
    theme="light"   # light / dark
)
engine.register_renderers(REGISTRY)

# 一键生成 PPT
engine.render_presentation(
    slides=[
        ("cover-light", {"title": "我的汇报", "presenter": "张三"}),
        ("toc-light", {}),
        ("content-two-col-light", {"title": "内容页"}),
        ("closing-light", {}),
    ],
    output_path="output.pptx"
)
```

---

## 📂 目录结构

```
bangcle-ppt/
├── bangcle_ppt/               # 核心包
│   ├── __init__.py
│   ├── theme/                 # 主题系统
│   │   ├── design_constants.py   # 设计常量（颜色/字体/尺寸）
│   │   ├── theme.py              # Theme 对象（浅色/深色切换）
│   │   └── __init__.py
│   ├── base/                  # 基类
│   │   ├── renderer_base.py      # RendererBase（所有渲染器父类）
│   │   └── __init__.py
│   ├── dsl/                   # DSL 定义
│   │   ├── schema.py             # Pydantic Schema（29 种布局）
│   │   └── __init__.py
│   ├── engine/                # 模板引擎
│   │   ├── template_engine.py    # TemplateEngine（加载/渲染）
│   │   └── __init__.py
│   ├── renderers/             # 页面渲染器（25+ 种）
│   │   ├── cover_renderer.py     # 封面（浅/深）
│   │   ├── toc_renderer.py       # 目录（浅/深）
│   │   ├── section_renderer.py   # 章节过渡（浅/深）
│   │   ├── content_renderer.py   # 内容页（图文/三卡片/时间轴/数据/列表/纯文本/KPI）
│   │   ├── advanced_renderers.py # 高级页面（纵向时间轴/放射/阶段/团队/对比/表格/流程/结束）
│   │   └── __init__.py
│   └── templates/             # 模板 YAML（34 个）
│       ├── shared/               # 共享变量
│       │   └── variables.yaml
│       ├── light/                # 浅色模板（19 个）
│       └── dark/                 # 深色模板（15 个）
├── tests/                     # 测试（200+ 用例）
│   ├── test_dsl_schema.py
│   ├── test_template_engine.py
│   ├── test_all_renderers.py
│   ├── test_templates.py
│   └── conftest.py
├── examples/                  # 示例脚本
│   ├── generate_light_demo.py    # 浅色完整演示（16 页）
│   ├── generate_dark_demo.py     # 深色完整演示（11 页）
│   ├── sample-spec.yaml          # YAML 规格文件示例
│   └── output/                   # 生成的 PPT 输出
└── README.md
```

---

## 🎯 页面类型清单

### 浅色模板（19 页）

| # | 页面类型 | page_type | 分类 | 用途 |
|---|---------|-----------|------|------|
| 1 | 封面页 | `cover-light` | 封面 | 报告封面、会议开场 |
| 2 | 目录页 | `toc-light` | 导航 | 议程导航 |
| 3 | 章节过渡页 | `section-light` | 导航 | 大章节切换 |
| 4 | 图文混排页 | `content-two-col-light` | 内容 | 产品介绍、方案概述 |
| 5 | 三卡片+横幅图 | `content-three-cards-light` | 内容 | 核心能力、三模块 |
| 6 | 时间轴+三卡片 | `timeline-three-cards-light` | 时间轴 | 流程步骤、发展历程 |
| 7 | 数据图表页 | `data-chart-light` | 数据 | 数据分析、成果展示 |
| 8 | 纵向时间轴 | `timeline-vertical-light` | 时间轴 | 里程碑、发展历程 |
| 9 | 放射结构图 | `radial-structure-light` | 架构 | 架构图、生态系统 |
| 10 | 6阶段时间轴 | `phase-timeline-light` | 时间轴 | 路线图、项目阶段 |
| 11 | 团队卡片 | `team-cards-light` | 团队 | 团队介绍、负责人 |
| 12 | 对比页 | `compare-two-col-light` | 内容 | 方案对比、优劣分析 |
| 13 | 列表页 | `list-light` | 内容 | 功能清单、要点列表 |
| 14 | 纯文本页 | `text-only-light` | 内容 | 大段文字、引文 |
| 15 | KPI卡片 | `kpi-cards-light` | 数据 | 关键指标展示 |
| 16 | 表格页 | `table-light` | 数据 | 数据表格 |
| 17 | 流程图 | `flow-light` | 流程 | 工作流程、步骤 |
| 18 | 空白页 | `blank-light` | 通用 | 自由排版 |
| 19 | 结束页 | `closing-light` | 结尾 | 谢谢观看、二维码 |

### 深色模板（15 页）

| # | 页面类型 | page_type | 分类 | 用途 |
|---|---------|-----------|------|------|
| 1 | 深色封面 | `cover-dark` | 封面 | 发布会、产品推介 |
| 2 | 深色目录 | `toc-dark` | 导航 | 议程导航 |
| 3 | 深色章节 | `section-dark` | 导航 | 大章节切换 |
| 4 | 节点关系图 | `node-graph-dark` | 架构 | 技术架构、关系网络 |
| 5 | 四卡片图文 | `four-cards-dark` | 内容 | 核心能力展示 |
| 6 | 左图右列表 | `list-image-dark` | 内容 | 功能清单、特性 |
| 7 | 蜂巢布局 | `honeycomb-dark` | 架构 | 产品矩阵、生态 |
| 8 | 金字塔对比 | `pyramid-compare-dark` | 架构 | 层级结构、对比分析 |
| 9 | 6阶段时间轴 | `phase-timeline-dark` | 时间轴 | 路线图 |
| 10-15 | 通用页 | （见浅色） | 通用 | 数据/表格/文本/KPI/空白/结束 |

> 深色模板中的数据页、表格页、文本页等复用浅色页面类型的渲染器，通过 theme="dark" 参数切换配色。

---

## 🚀 使用方法

### 方法一：Python API（推荐）

```python
from bangcle_ppt.engine import TemplateEngine
from bangcle_ppt.renderers import REGISTRY

engine = TemplateEngine(
    templates_dir="bangcle_ppt/templates",
    theme="light"
)
engine.register_renderers(REGISTRY)

# 定义幻灯片
slides = [
    ("cover-light", {"title": "汇报标题", "presenter": "张三"}),
    ("toc-light", {}),  # 使用模板默认数据
    ("content-two-col-light", {
        "title": "自定义标题",
        "highlights": [
            {"title": "要点1", "description": "描述"},
            {"title": "要点2", "description": "描述"},
        ],
    }),
    ("closing-light", {}),
]

# 生成 PPT
output = engine.render_presentation(slides, output_path="my-ppt.pptx")
print(f"✅ 生成成功: {output}")
```

### 方法二：YAML 规格文件

编写 YAML 文件描述整份 PPT：

```yaml
title: "我的汇报"
theme: "light"
slides:
  - meta:
      name: "封面"
      page_type: "cover-light"
    data:
      title: "我的汇报"
      presenter: "张三"
  - meta:
      name: "目录"
      page_type: "toc-light"
    data: {}
  # ... 更多页面
```

```python
engine.render_from_yaml("my-spec.yaml", "output.pptx")
```

### 方法三：命令行示例

```bash
# 生成浅色完整演示
python examples/generate_light_demo.py

# 生成深色完整演示
python examples/generate_dark_demo.py

# 指定输出路径
python examples/generate_light_demo.py /path/to/output.pptx
```

---

## 🎨 设计规范

### 色彩体系

| 色号 | 名称 | HEX | 用途 |
|------|------|-----|------|
| C-01 | 主色（梆梆蓝） | `#2D74BB` | 标题、重点元素、Logo |
| C-02 | 浅蓝 | `#3FA1DA` | 辅助背景、渐变起始 |
| C-03 | 青色 | `#27AABF` | 辅助色、图表色 |
| C-04 | 青绿 | `#33ADA0` | 成功/正面指标 |
| C-05 | 金色 | `#EFBA20` | 强调色、高亮点缀 |
| C-06 | 深藏青 | `#00122B` | 深色模板背景 |
| C-07 | 深灰 | `#595757` | 辅助文字、分割线 |

### 字体

- **中文字体**: 思源黑体（Source Han Sans）
- **英文字体**: 思源黑体（Source Han Sans）
- **Fallback**: Microsoft YaHei
- **字重**: Heavy（标题）/ Medium（正文）

### 画布

- 尺寸: 13.333" × 7.5"（16:9）
- 标题左距: 0.54"
- 标题顶距: 0.47"

---

## 🔧 扩展开发

### 新增页面类型

1. **定义 Schema** — 在 `dsl/schema.py` 中添加 Layout 类
2. **实现 Renderer** — 在 `renderers/` 中创建渲染器，继承 `RendererBase`
3. **注册映射** — 在 `renderers/__init__.py` 的 `REGISTRY` 中添加
4. **创建模板** — 在 `templates/light/` 和 `templates/dark/` 中添加 YAML
5. **添加测试** — 在 `tests/` 中添加对应测试用例

### 示例：新增一个页面类型

```python
# 1. Schema
class MyLayout(BaseLayout):
    feature_name: str = ""
    description: str = ""

# 2. Renderer
class MyRenderer(RendererBase):
    page_type = "my-page-light"

    def render(self, prs, data=None):
        slide = self.add_blank_slide(prs)
        # ... 绘制元素
        return slide

# 3. 注册
REGISTRY["my-page-light"] = MyRenderer
```

---

## ✅ 测试

```bash
# 运行全部测试
cd bangcle-ppt
python -m pytest tests/ -v

# 运行特定测试
python -m pytest tests/test_all_renderers.py -v

# 统计测试数量
python -m pytest tests/ --co -q | wc -l
```

当前测试覆盖:
- ✅ 209 个测试用例
- ✅ 25 种页面类型渲染烟雾测试
- ✅ 34 个模板 YAML schema 校验
- ✅ 浅色/深色主题切换
- ✅ 完整 PPT 生成端到端测试

---

## 📚 相关文档

- **设计规范详情**: `docs/architecture/components/bangcle-ppt-template/DESIGN.md`
- **架构决策记录**: `docs/knowledge-base/by-category/project-experience/adr/ADR-202608-017-bangcle-ppt-template.md`
- **L2 底层组件**: `L2-infra/components/office-generation/`（ppt_engine）

---

## 📋 Changelog

### v1.0.0 (2025-09-10)
- 🎉 首个完整版本
- 25+ 页面类型渲染器
- 34 个预置模板（浅色 19 + 深色 15）
- DSL Schema + 模板引擎
- 200+ 测试用例
- 完整文档与示例

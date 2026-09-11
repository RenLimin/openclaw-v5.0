# bangcle-ppt

## 设计目标

基于梆梆安全官方 VI 规范，提供 PPT 模板生成系统。通过 DSL + 模板引擎 + 25+ 页面类型渲染器，一键生成符合品牌规范的演示文稿。解决手工排版效率低、品牌一致性差的问题。

## 架构决策

- **DSL 驱动**：YAML 描述模板规格，版本可控、易维护
- **渲染器注册模式**：新增页面 = 新 Schema + 新 Renderer + 注册到 REGISTRY，开闭原则
- **双主题支持**：浅色（19页）+ 深色（15页）两套完整模板，通过 Theme 对象切换
- **Pydantic Schema 校验**：DSL 使用 Pydantic v2 做严格类型校验
- **模板与逻辑分离**：YAML 模板定义数据，Python 渲染器定义绘制逻辑
- **三入口**：Python API / YAML 规格文件 / 命令行示例脚本

## 模块划分

```
bangcle-ppt/
├── src/bangcle_ppt/
│   ├── theme/                  # 主题系统
│   │   ├── design_constants.py # 设计常量（颜色/字体/尺寸）
│   │   └── theme.py            # Theme 对象（浅色/深色切换）
│   ├── base/                   # 基类
│   │   └── renderer_base.py    # RendererBase（所有渲染器父类）
│   ├── dsl/                    # DSL 定义
│   │   └── schema.py           # Pydantic Schema（29 种布局）
│   ├── engine/                 # 模板引擎
│   │   └── template_engine.py  # TemplateEngine（加载/渲染）
│   ├── renderers/              # 页面渲染器（25+ 种）
│   │   ├── cover_renderer.py   # 封面
│   │   ├── toc_renderer.py     # 目录
│   │   ├── section_renderer.py # 章节过渡
│   │   ├── content_renderer.py # 内容页（图文/三卡片/时间轴/数据/列表/纯文本/KPI）
│   │   └── advanced_renderers.py # 高级页（纵向时间轴/放射/阶段/团队/对比/表格/流程/结束）
│   ├── templates/              # 模板 YAML（34 个）
│   │   ├── shared/variables.yaml
│   │   ├── light/              # 浅色模板（19 个）
│   │   └── dark/               # 深色模板（15 个）
│   ├── web/                    # Web UI
│   │   ├── main.py             # Flask 入口
│   │   ├── api.py              # REST API
│   │   └── templates/          # Jinja2 模板
│   └── cli/                    # CLI
│       ├── pptgen.py           # 生成命令
│       └── __main__.py         # 入口
├── tests/                      # 200+ 测试用例
└── examples/                   # 示例脚本 + 输出
```

## 关键接口/数据结构

- `TemplateEngine`：核心引擎，`register_renderers(registry)` / `render_presentation(slides, output_path)` / `render_from_yaml(yaml_path, output_path)`
- `RendererBase`：渲染器基类，`render(prs, data)` / `add_blank_slide(prs)`
- `Theme`：主题对象，管理配色方案切换
- `design_constants.py`：设计常量（颜色 HEX、字体、间距、画布尺寸）
- `REGISTRY`：`Dict[str, Type[RendererBase]]`，page_type → 渲染器类映射
- `BaseLayout`：Pydantic 基类，所有页面 Schema 继承

## 依赖关系

- **依赖**：python-pptx、Pydantic v2、PyYAML、Flask（Web UI）
- **被依赖**：`office-business`（模板层，bangcle-ppt 是 office-business 模板的渲染引擎）

## 演进方向

1. **模板扩充**：覆盖更多页面类型（SWOT、甘特图、鱼骨图）
2. **数据绑定**：支持从 CSV/JSON 自动填充图表数据
3. **主题自定义**：允许用户上传品牌色生成自定义主题
4. **在线编辑器**：Web UI 升级为可视化拖拽编辑
5. **导出格式**：支持 PDF/图片导出

# DESIGN-DETAIL-v1.0: Bangcle PPT 模板系统

## 1. 整体架构图

```
┌─────────────────────────────────────────────────────────────┐
│                      User Input                               │
│  (Python API / YAML Spec / CLI / Web UI)                     │
└──────────────┬──────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────┐
│  TemplateEngine                                              │
│  ├─ load templates from YAML                                 │
│  ├─ validate DSL with Pydantic Schema                       │
│  ├─ get renderer from registry by page_type                 │
│  └─ call renderer.render() for each slide                   │
└──────────────┬──────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────┐
│  Theme + design_constants                                   │
│  ├─ provides color hex / fonts / spacing / canvas size      │
│  └─ switch light/dark theme colors                          │
└──────────────┬──────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────┐
│  Renderers (25+ types)                                       │
│  ├─ all inherit from RendererBase                           │
│  ├─ each renderer implements render()                       │
│  └─ draw shapes/text/placeholders on slide                  │
└──────────────┬──────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────┐
│  python-pptx                                                 │
│  └─ output .pptx file                                        │
└─────────────────────────────────────────────────────────────┘
```

## 2. 核心接口与数据结构

### 2.1 Theme 类

**路径**: `src/bangcle_ppt/theme/theme.py`

```python
class Theme:
    theme_name: str  # "light" / "dark"
    def get_color(self, color_name: str) -> tuple[int, int, int]:
        # 返回 RGB 元组
```

**职责**: 管理主题配色，根据颜色名返回对应 RGB。

### 2.2 RendererBase 抽象基类

**路径**: `src/bangcle_ppt/base/renderer_base.py`

```python
class RendererBase:
    page_type: str  # 页面类型标识，如 "cover-light"
    theme: Theme

    def add_blank_slide(self, prs: Presentation) -> Slide:
        # 添加空白幻灯片，设置正确尺寸
        return slide

    def render(self, prs: Presentation, data: BaseLayout) -> Slide:
        # 抽象方法，子类实现具体绘制逻辑
        raise NotImplementedError
```

**职责**: 所有渲染器的基类，定义统一接口。

### 2.3 TemplateEngine 核心引擎

**路径**: `src/bangcle_ppt/engine/template_engine.py`

```python
class TemplateEngine:
    def __init__(self, templates_dir: str, theme: str = "light"):
        # 初始化引擎，设置模板目录和默认主题
        pass

    def register_renderers(self, registry: dict[str, Type[RendererBase]]) -> None:
        # 注册渲染器到引擎注册表
        pass

    def get_renderer(self, page_type: str) -> RendererBase:
        # 根据 page_type 获取渲染器实例
        pass

    def render_presentation(self, slides: list[tuple[str, dict]], output_path: str) -> str:
        # 渲染整份 PPT，输出到指定路径
        return output_path

    def render_from_yaml(self, yaml_path: str, output_path: str) -> str:
        # 从 YAML 规格文件渲染 PPT
        return output_path

    def list_templates(self, theme: Optional[str] = None) -> list[dict]:
        # 列出所有可用模板
        pass
```

**职责**: 核心入口，管理整个渲染流程。

### 2.4 Pydantic Schema 定义

**路径**: `src/bangcle_ppt/dsl/schema.py`

```python
class BaseLayout(BaseModel):
    # 所有页面 Schema 基类
    pass

class CoverLayout(BaseLayout):
    title: str = ""
    subtitle: str = ""
    presenter: str = ""
    date: str = ""
    # ... 更多字段

class TocLayout(BaseLayout):
    title: str = ""
    items: list[str] = []
    # ... 更多字段

# 每个页面类型对应一个 Schema 类
```

**职责**: 定义 DSL 数据结构，提供自动校验。

### 2.5 设计常量

**路径**: `src/bangcle_ppt/theme/design_constants.py`

定义官方 VI 规范所有常量：
- 配色方案：HEX 色值定义
- 字体：字体名、字重、大小
- 尺寸：画布尺寸、边距、间距

## 3. 模块详细设计

### 3.1 theme 模块

- `design_constants.py`: 硬编码所有设计常量，来自官方 VI 文档
- `theme.py`: Theme 类封装，提供颜色获取方法，支持浅色/深色切换
- 设计原则：所有设计规范统一在这里管理，修改规范只改这一处

### 3.2 base 模块

- `renderer_base.py`: 只定义抽象基类和通用方法（如 `add_blank_slide`），不包含具体业务逻辑

### 3.3 dsl 模块

- `schema.py`: 所有页面类型的 Pydantic Schema 定义，每个页面类型对应一个 Schema 类
- 使用继承减少重复代码：`BaseLayout` 定义通用字段，具体页面类继承扩展
- Pydantic 自动校验数据类型、必填字段，提前发现错误

### 3.4 engine 模块

- `template_engine.py`: 核心流程控制，从模板加载 → 校验 → 获取渲染器 → 调用渲染，串联整个流程
- 注册表保存 `page_type → 渲染器类` 映射，支持动态注册

### 3.5 renderers 模块

- 按功能拆分文件：`cover_renderer.py` / `toc_renderer.py` / `content_renderer.py` / `advanced_renderers.py`
- 每个渲染器对应一个或多个 page_type（浅色/深色复用同一个渲染器，只通过 theme 切换配色）
- 每个渲染器只负责自己页面类型的绘制逻辑，遵循单一职责

### 3.6 templates 模块

- YAML 文件存储预置模板，每个 page_type 对应一个 YAML 文件
- 分 `light` / `dark` 两个目录，分别存放浅色和深色模板
- `shared/variables.yaml` 存放共享变量，便于统一修改

### 3.7 cli 模块

- `pptgen.py`: 命令行实现，支持 `list` / `info` / `validate` / `render` 子命令
- `__main__.py`: 模块入口，支持 `python -m bangcle_ppt.cli`

### 3.8 web 模块

- `main.py`: Flask 入口
- `api.py`: REST API 实现
- `templates/`: Jinja2 HTML 模板，提供 Web UI

## 4. 数据流

1. **用户调用**：用户通过 API/YAML/CLI/Web UI 传入幻灯片列表和数据
2. **引擎初始化**：TemplateEngine 根据主题创建 Theme 对象，加载渲染器注册表
3. **循环处理每张幻灯片**：
   - 根据 page_type 获取对应渲染器
   - 数据通过 Pydantic Schema 校验
   - 调用渲染器 `render()` 方法绘制幻灯片
4. **保存输出**：所有幻灯片绘制完成后，保存 .pptx 文件到输出路径

## 5. 错误处理

- **Schema 校验错误**：Pydantic 自动抛出校验错误，包含具体字段和错误信息
- **未知 page_type**：TemplateEngine 抛出 `ValueError`，提示不存在该页面类型
- **YAML 文件不存在**：加载模板时抛出 `FileNotFoundError`
- **渲染错误**：错误向上抛出，包含具体页面类型信息，便于定位

## 6. 扩展性

- **新增页面类型**：
  1. 在 `dsl/schema.py` 新增 Schema 类
  2. 在 `renderers/` 新增渲染器类，继承 `RendererBase`
  3. 在 `renderers/__init__.py` 的 `REGISTRY` 注册
  4. （可选）在 `templates/` 添加预置 YAML 模板
  5. （可选）添加测试用例
- **新增主题**：新增配色常量，扩展 Theme 类即可，所有渲染器复用
- **自定义模板**：用户可以自己写 YAML 模板，使用现有渲染器渲染


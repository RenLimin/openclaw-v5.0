# OPERATIONS-v1.0: Bangcle PPT 模板系统

## 1. 依赖环境

### Python 版本

- Python 3.10+

### 依赖包

```bash
pip install python-pptx pydantic pyyaml flask
```

| 包 | 版本要求 | 用途 |
|----|----------|------|
| `python-pptx` | >=0.6.21 | PPT 文件生成 |
| `pydantic` | >=2.0 | DSL Schema 校验 |
| `pyyaml` | >=6.0 | YAML 模板加载 |
| `flask` | >=2.0 | Web UI（可选，不需要 Web 可不用安装） |

### 系统依赖

- 无特殊系统依赖，全 Python 实现

## 2. 运行方式

### 方法一：Python API（推荐）

```python
from bangcle_ppt.engine import TemplateEngine
from bangcle_ppt.renderers import REGISTRY

# 初始化引擎
engine = TemplateEngine(
    templates_dir="src/bangcle_ppt/templates",
    theme="light"   # light / dark
)
engine.register_renderers(REGISTRY)

# 定义幻灯片并生成 PPT
slides = [
    ("cover-light", {"title": "我的汇报", "presenter": "张三"}),
    ("toc-light", {}),
    ("content-two-col-light", {"title": "内容页"}),
    ("closing-light", {}),
]
output_path = engine.render_presentation(slides, output_path="output.pptx")
print(f"生成成功: {output_path}")
```

### 方法二：YAML 规格文件

编写 YAML 文件：

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
```

渲染：

```python
engine.render_from_yaml("my-spec.yaml", "output.pptx")
```

### 方法三：CLI 命令行

```bash
# 列出所有浅色模板
python -m src.bangcle_ppt.cli list --theme light

# 查看模板信息
python -m src.bangcle_ppt.cli info cover-light

# 验证 YAML 规格文件
python -m src.bangcle_ppt.cli validate my-spec.yaml

# 渲染 PPT
python -m src.bangcle_ppt.cli render my-spec.yaml output.pptx --theme light
```

### 方法四：Web UI

```bash
cd src/bangcle_ppt/web
python main.py
```

访问 `http://localhost:5000` 即可使用可视化界面。

## 3. 常见问题排查

### Q1: 导入模块报错 `ModuleNotFoundError: No module named 'bangcle_ppt'`

**原因**：Python 搜索路径没有包含当前项目目录。

**解决方案**：在项目根目录运行，或者添加当前目录到 PYTHONPATH：

```bash
export PYTHONPATH=$PYTHONPATH:.
```

### Q2: 生成的 PPT 字体不对/显示不正常

**原因**：系统缺少思源黑体字体。

**解决方案**：安装思源黑体字体：
- macOS: `brew install --cask font-source-han-sans-cn`
- 其他系统：从 [Google Fonts](https://fonts.google.com/specimen/Source+Sans+Pro) 下载安装，或者配置 Fallback 字体（修改 `design_constants.py`）。

### Q3: Pydantic 警告 `Support for class-based config is deprecated`

**原因**：Pydantic v2 废弃了 class-based `config`，未来版本会移除。当前不影响使用。

**解决方案**：当前版本（v1.0）不影响功能，后续版本会升级为 `ConfigDict`。

### Q4: 新增页面后提示找不到渲染器

**原因**：没有在 `REGISTRY` 注册。

**解决方案**：在 `src/bangcle_ppt/renderers/__init__.py` 的 `REGISTRY` 字典中添加你的 page_type 和渲染器类映射。

### Q5: Web UI 启动失败，提示找不到 Flask

**原因**：没有安装 Flask。

**解决方案**：`pip install flask`。

### Q6: 生成 PPT 后打不开/文件损坏

**原因**：输出路径目录不存在，或者没有写入权限。

**解决方案**：确保输出目录存在，并且有写入权限。

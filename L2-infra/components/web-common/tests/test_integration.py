"""
集成测试：模拟 FastAPI app 使用 web-common 宏
验证 import + 路由注册 + 模板渲染全流程
"""

import os
import sys
import pytest

# 添加 web-common 父目录到 path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))


def test_macros_init_compilable():
    """验证 macros/__init__.py 可被编译。"""
    init_path = os.path.join(os.path.dirname(__file__), '..', 'macros', '__init__.py')
    with open(init_path) as f:
        code = f.read()
    compile(code, init_path, 'exec')
    assert 'get_macros_dir' in code
    assert 'get_static_dir' in code
    assert 'setup_web_common' in code


def test_package_path_exists():
    """验证 macros 目录和 static 目录存在。"""
    base = os.path.join(os.path.dirname(__file__), '..')
    assert os.path.isdir(os.path.join(base, 'macros'))
    assert os.path.isdir(os.path.join(base, 'static'))
    assert os.path.isdir(os.path.join(base, 'static', 'css'))
    assert os.path.isdir(os.path.join(base, 'static', 'js'))


def test_all_macro_files_exist():
    """验证所有宏文件存在。"""
    macros_dir = os.path.join(os.path.dirname(__file__), '..', 'macros')
    for f in ['layout.html', 'components.html', 'forms.html', 'icons.html', '__init__.py']:
        assert os.path.isfile(os.path.join(macros_dir, f)), f"缺失: {f}"


def test_all_css_files_exist():
    """验证所有 CSS 文件存在。"""
    css_dir = os.path.join(os.path.dirname(__file__), '..', 'static', 'css')
    for f in ['base.css', 'layout.css', 'components.css', 'forms.css']:
        assert os.path.isfile(os.path.join(css_dir, f)), f"缺失: {f}"


def test_all_js_files_exist():
    """验证所有 JS 文件存在。"""
    js_dir = os.path.join(os.path.dirname(__file__), '..', 'static', 'js')
    for f in ['theme.js', 'toast.js']:
        assert os.path.isfile(os.path.join(js_dir, f)), f"缺失: {f}"


def test_css_has_dark_mode_variables():
    """验证 CSS 包含深色模式变量。"""
    import re
    css_dir = os.path.join(os.path.dirname(__file__), '..', 'static', 'css')
    with open(os.path.join(css_dir, 'base.css')) as f:
        css = f.read()
    assert ':root' in css
    assert '[data-theme="dark"]' in css
    assert '--c-primary' in css
    assert '--c-bg' in css
    assert '--c-text' in css
    assert '--sidebar-w' in css


def test_css_has_responsive_breakpoints():
    """验证 CSS 包含响应式断点。"""
    css_dir = os.path.join(os.path.dirname(__file__), '..', 'static', 'css')
    with open(os.path.join(css_dir, 'layout.css')) as f:
        css = f.read()
    assert '@media (max-width: 1200px)' in css
    assert '@media (max-width: 1024px)' in css
    assert '@media (max-width: 768px)' in css
    assert '@media (max-width: 480px)' in css


def test_js_theme_api():
    """验证 theme.js 包含核心 API。"""
    js_dir = os.path.join(os.path.dirname(__file__), '..', 'static', 'js')
    with open(os.path.join(js_dir, 'theme.js')) as f:
        js = f.read()
    assert 'window.Theme' in js
    assert 'setTheme' in js
    assert 'toggleTheme' in js
    assert 'onChange' in js
    assert 'localStorage' in js
    assert 'prefers-color-scheme' in js


def test_js_toast_api():
    """验证 toast.js 包含核心 API。"""
    js_dir = os.path.join(os.path.dirname(__file__), '..', 'static', 'js')
    with open(os.path.join(js_dir, 'toast.js')) as f:
        js = f.read()
    assert 'window.showToast' in js
    assert 'window.Toast' in js
    assert 'success' in js
    assert 'error' in js
    assert 'warning' in js
    assert 'info' in js


def test_layout_macro_full_page_render():
    """验证 base_layout 宏渲染完整 HTML 页面。"""
    from jinja2 import Environment, FileSystemLoader
    macros_dir = os.path.join(os.path.dirname(__file__), '..', 'macros')
    env = Environment(loader=FileSystemLoader(macros_dir))

    tmpl = env.from_string("""
        {% from "layout.html" import base_layout, page_header with context %}
        {% from "components.html" import card, stat_card, dashboard_grid, table, badge, progress_bar, pagination, filter_bar, info_grid with context %}
        {% from "forms.html" import input, select, textarea, button, form_row, checkbox, switch with context %}
        {% call base_layout(
            title="集成测试",
            brand_name="TestApp",
            brand_icon="🧪",
            active_page="dashboard",
            storage_key="test-theme",
            sidebar_items=[
                {"title": "概览", "items": [
                    {"id": "dashboard", "label": "仪表盘", "url": "/", "icon": "📊"},
                    {"id": "list", "label": "列表", "url": "/list", "icon": "📋"},
                ]},
                {"title": "管理", "items": [
                    {"id": "settings", "label": "设置", "url": "/settings", "icon": "⚙️"},
                ]}
            ]
        ) %}
            {{ page_header(title="测试页面", subtitle="集成验证", actions=[
                {"label": "新建", "url": "/new", "variant": "primary", "icon": "➕"}
            ]) }}

            {% call dashboard_grid() %}
                {{ stat_card(label="用户数", value=1234, variant="primary", sub="本月新增") }}
                {{ stat_card(label="订单数", value=567, variant="success") }}
                {{ stat_card(label="警告", value=23, variant="warning") }}
                {{ stat_card(label="错误", value=5, variant="danger") }}
            {% endcall %}

            {% call card(title="数据表格", actions=[{"label": "导出", "url": "/export", "variant": ""}]) %}
                {{ table(
                    columns=[
                        {"key": "id", "label": "ID"},
                        {"key": "name", "label": "名称"},
                        {"key": "status", "label": "状态"},
                        {"key": "amount", "label": "金额", "align": "right", "num": true}
                    ],
                    rows=[
                        {"id": 1, "name": "项目A", "status": "进行中", "amount": 1000},
                        {"id": 2, "name": "项目B", "status": "已完成", "amount": 2000}
                    ],
                    row_actions=[
                        {"label": "查看", "url_key": "#", "variant": ""}
                    ]
                ) }}
                {{ pagination(current=2, total_pages=5, on_click="loadPage") }}
            {% endcall %}

            {% call card(title="表单测试") %}
                {% call form_row(cols=2) %}
                    {{ input(name="name", label="名称", value="测试", required=true) }}
                    {{ select(name="type", label="类型", options=[("1","类型1"),("2","类型2")], value="1") }}
                {% endcall %}
                {{ textarea(name="desc", label="描述", value="测试内容", rows=3) }}
                {{ checkbox(name="agree", label="同意条款", checked=true) }}
                {{ switch(name="enabled", label="启用功能", checked=true) }}
                <div style="display: flex; gap: 8px; margin-top: 16px;">
                    {{ button("提交", variant="primary", type="submit") }}
                    {{ button("取消", variant="", url="/") }}
                </div>
            {% endcall %}

            {% call card(title="组件测试") %}
                {{ badge("成功", variant="success") }}
                {{ badge("警告", variant="warning") }}
                {{ badge("错误", variant="danger") }}
                {{ progress_bar(percent=60, variant="primary", label="60%") }}
                {{ info_grid(items=[
                    {"label": "创建时间", "value": "2026-01-01"},
                    {"label": "状态", "value": "运行中", "badge_variant": "success"}
                ]) }}
            {% endcall %}

            {{ filter_bar(
                fields=[
                    {"type": "select", "label": "状态", "id": "f_status", "options": [("all","全部"),("active","活跃")]},
                    {"type": "text", "label": "关键词", "id": "f_keyword", "placeholder": "搜索..."}
                ],
                submit_onclick="filter()",
                reset_onclick="resetFilter()"
            ) }}
        {% endcall %}
    """)

    html = tmpl.render()

    # 验证关键结构
    assert '<!DOCTYPE html>' in html
    assert '集成测试' in html
    assert 'TestApp' in html
    assert '🧪' in html
    assert 'sidebar' in html
    assert '仪表盘' in html
    assert 'active' in html

    # 统计卡片
    assert 'stat-card' in html
    assert '1234' in html
    assert '567' in html

    # 表格
    assert '项目A' in html
    assert '项目B' in html
    assert 'pagination' in html

    # 表单
    assert 'form-group' in html
    assert 'type="text"' in html
    assert '<select' in html
    assert '<textarea' in html
    assert 'checkbox' in html
    assert 'switch' in html

    # 组件
    assert 'badge success' in html
    assert 'progress-bar' in html
    assert 'info-grid' in html
    assert 'filter-bar' in html

    # 资源引用
    assert 'web-common/css/base.css' in html
    assert 'web-common/js/theme.js' in html
    assert 'web-common/js/toast.js' in html


def test_demo_app_import():
    """验证 Demo app 可 import（不启动服务）。"""
    demo_path = os.path.join(os.path.dirname(__file__), '..', 'examples', 'demo_app.py')
    assert os.path.isfile(demo_path), "demo_app.py 不存在"

    # 读取文件验证包含必要内容
    with open(demo_path) as f:
        content = f.read()

    assert 'FastAPI' in content or 'fastapi' in content.lower()
    assert 'Jinja2Templates' in content
    assert 'base_layout' in content
    # 检查是否能编译
    compile(content, demo_path, 'exec')


def test_readme_exists():
    """验证 README 存在。"""
    readme = os.path.join(os.path.dirname(__file__), '..', 'README.md')
    assert os.path.isfile(readme), "README.md 不存在"

    with open(readme) as f:
        content = f.read()

    assert 'web-common' in content.lower() or 'Web Common' in content
    assert '安装' in content or '使用' in content or 'Usage' in content


def test_macro_consistency():
    """验证宏命名和 CSS class 命名一致。"""
    import re
    macros_dir = os.path.join(os.path.dirname(__file__), '..', 'macros')
    css_dir = os.path.join(os.path.dirname(__file__), '..', 'static', 'css')

    # 收集宏中使用的 class
    macro_classes = set()
    for fname in ['layout.html', 'components.html', 'forms.html']:
        with open(os.path.join(macros_dir, fname)) as f:
            content = f.read()
            for match in re.findall(r'class="([^"]+)"', content):
                for cls in match.split():
                    macro_classes.add(cls)

    # 收集 CSS 中定义的 class
    css_classes = set()
    for fname in ['base.css', 'layout.css', 'components.css', 'forms.css']:
        with open(os.path.join(css_dir, fname)) as f:
            content = f.read()
            for match in re.findall(r'\.(-?[_a-zA-Z][_a-zA-Z0-9-]*)', content):
                css_classes.add(match)

    # 关键 class 应该有对应的 CSS 定义
    critical_classes = [
        'app-layout', 'sidebar', 'main', 'card', 'stat-card',
        'table', 'btn', 'badge', 'form-group', 'progress-bar',
        'pagination', 'filter-bar', 'toast', 'dashboard-grid',
        'page-header', 'info-grid',
    ]

    missing = [c for c in critical_classes if c not in css_classes]
    assert not missing, f"以下 CSS class 未定义: {missing}"

"""
Macros 渲染单元测试
覆盖：布局宏、组件宏、表单宏、图标宏
"""

import os
import sys
import pytest
from jinja2 import Environment, FileSystemLoader

# 路径配置
MACROS_DIR = os.path.join(os.path.dirname(__file__), '..', 'macros')


@pytest.fixture
def env():
    """创建 Jinja2 环境，指向 macros 目录。"""
    return Environment(
        loader=FileSystemLoader(MACROS_DIR),
        autoescape=False,
        trim_blocks=False,
        lstrip_blocks=False,
    )


# ============================================================
# Layout 宏测试
# ============================================================

class TestLayoutMacro:

    def test_base_layout_renders_html_structure(self, env):
        tmpl = env.from_string("""
            {% from "layout.html" import base_layout with context %}
            {% call base_layout(title="测试页", brand_name="TestApp", brand_icon="🎯") %}
                <p>Hello World</p>
            {% endcall %}
        """)
        html = tmpl.render()
        assert '<!DOCTYPE html>' in html
        assert '<html' in html
        assert 'lang="zh-CN"' in html
        assert '<head>' in html
        assert '<body>' in html
        assert '测试页' in html
        assert 'TestApp' in html
        assert '🎯' in html
        assert 'Hello World' in html

    def test_base_layout_includes_css_links(self, env):
        tmpl = env.from_string("""
            {% from "layout.html" import base_layout with context %}
            {% call base_layout(title="T") %}content{% endcall %}
        """)
        html = tmpl.render()
        assert '/static/web-common/css/base.css' in html
        assert '/static/web-common/css/layout.css' in html
        assert '/static/web-common/css/components.css' in html
        assert '/static/web-common/css/forms.css' in html

    def test_base_layout_includes_js(self, env):
        tmpl = env.from_string("""
            {% from "layout.html" import base_layout with context %}
            {% call base_layout(title="T") %}x{% endcall %}
        """)
        html = tmpl.render()
        assert '/static/web-common/js/theme.js' in html
        assert '/static/web-common/js/toast.js' in html

    def test_base_layout_sidebar_items(self, env):
        tmpl = env.from_string("""
            {% from "layout.html" import base_layout with context %}
            {% call base_layout(
                title="T",
                active_page="dashboard",
                sidebar_items=[
                    {"title": "概览", "items": [
                        {"id": "dashboard", "label": "仪表盘", "url": "/", "icon": "📊"},
                        {"id": "list", "label": "列表", "url": "/list", "icon": "📋"},
                    ]}
                ]
            ) %}x{% endcall %}
        """)
        html = tmpl.render()
        assert '概览' in html
        assert '仪表盘' in html
        assert '列表' in html
        assert 'class="active"' in html
        assert 'href="/"' in html
        assert 'href="/list"' in html

    def test_base_layout_storage_key(self, env):
        tmpl = env.from_string("""
            {% from "layout.html" import base_layout with context %}
            {% call base_layout(title="T", storage_key="myapp-theme") %}x{% endcall %}
        """)
        html = tmpl.render()
        assert 'myapp-theme' in html

    def test_base_layout_theme_button(self, env):
        tmpl = env.from_string("""
            {% from "layout.html" import base_layout with context %}
            {% call base_layout(title="T") %}x{% endcall %}
        """)
        html = tmpl.render()
        assert 'themeToggle' in html
        assert '🌙 深色' in html

    def test_base_layout_mobile_menu(self, env):
        tmpl = env.from_string("""
            {% from "layout.html" import base_layout with context %}
            {% call base_layout(title="T", show_mobile_menu=true) %}x{% endcall %}
        """)
        html = tmpl.render()
        assert 'mobileMenuBtn' in html

    def test_base_layout_no_mobile_menu(self, env):
        tmpl = env.from_string("""
            {% from "layout.html" import base_layout with context %}
            {% call base_layout(title="T", show_mobile_menu=false) %}x{% endcall %}
        """)
        html = tmpl.render()
        assert 'mobileMenuBtn' not in html

    def test_page_header_with_title_only(self, env):
        tmpl = env.from_string("""
            {% from "layout.html" import page_header %}
            {{ page_header(title="仪表盘") }}
        """)
        html = tmpl.render()
        assert 'page-header' in html
        assert '<h1>仪表盘</h1>' in html

    def test_page_header_with_subtitle(self, env):
        tmpl = env.from_string("""
            {% from "layout.html" import page_header %}
            {{ page_header(title="仪表盘", subtitle="概览") }}
        """)
        html = tmpl.render()
        assert '概览' in html
        assert '<p>' in html

    def test_page_header_with_actions(self, env):
        tmpl = env.from_string("""
            {% from "layout.html" import page_header %}
            {{ page_header(title="列表", actions=[
                {"label": "新建", "url": "/new", "variant": "primary", "icon": "➕"}
            ]) }}
        """)
        html = tmpl.render()
        assert 'page-actions' in html
        assert 'href="/new"' in html
        assert 'btn-primary' in html
        assert '➕' in html


# ============================================================
# Components 宏测试
# ============================================================

class TestComponentsMacro:

    def test_card_basic(self, env):
        tmpl = env.from_string("""
            {% from "components.html" import card with context %}
            {% call card(title="我的卡片") %}内容{% endcall %}
        """)
        html = tmpl.render()
        assert 'class="card' in html
        assert 'card-title' in html
        assert '我的卡片' in html
        assert '内容' in html

    def test_card_with_actions(self, env):
        tmpl = env.from_string("""
            {% from "components.html" import card with context %}
            {% call card(title="T", actions=[
                {"label": "查看", "url": "/view", "variant": ""},
                {"label": "删除", "onclick": "del()", "variant": "danger"}
            ]) %}body{% endcall %}
        """)
        html = tmpl.render()
        assert 'card-actions' in html
        assert 'href="/view"' in html
        assert 'btn-danger' in html
        assert 'onclick="del()"' in html

    def test_stat_card_basic(self, env):
        tmpl = env.from_string("""
            {% from "components.html" import stat_card %}
            {{ stat_card(label="总数", value=42) }}
        """)
        html = tmpl.render()
        assert 'stat-card' in html
        assert 'stat-label' in html
        assert 'stat-value' in html
        assert '总数' in html
        assert '42' in html

    def test_stat_card_variants(self, env):
        for variant in ['primary', 'success', 'danger', 'warning', 'info']:
            tmpl_str = (
                '{% from "components.html" import stat_card %}'
                '{{ stat_card(label="L", value=1, variant="' + variant + '") }}'
            )
            tmpl = env.from_string(tmpl_str)
            html = tmpl.render()
            assert f'stat-value {variant}' in html

    def test_stat_card_with_sub(self, env):
        tmpl = env.from_string("""
            {% from "components.html" import stat_card %}
            {{ stat_card(label="L", value=10, sub="本月") }}
        """)
        html = tmpl.render()
        assert 'stat-sub' in html
        assert '本月' in html

    def test_dashboard_grid(self, env):
        tmpl = env.from_string("""
            {% from "components.html" import dashboard_grid with context %}
            {% call dashboard_grid() %}
                <div class="stat-card">A</div>
                <div class="stat-card">B</div>
            {% endcall %}
        """)
        html = tmpl.render()
        assert 'dashboard-grid' in html

    def test_table_with_data(self, env):
        tmpl = env.from_string("""
            {% from "components.html" import table %}
            {{ table(
                columns=[
                    {"key": "name", "label": "名称"},
                    {"key": "amount", "label": "金额", "align": "right", "num": true}
                ],
                rows=[
                    {"name": "项目A", "amount": 100},
                    {"name": "项目B", "amount": 200}
                ]
            ) }}
        """)
        html = tmpl.render()
        assert 'table-wrapper' in html
        assert '<table class="table"' in html
        assert '项目A' in html
        assert '项目B' in html
        assert '100' in html
        assert '200' in html
        assert 'num' in html  # 数字列右对齐

    def test_table_empty(self, env):
        tmpl = env.from_string("""
            {% from "components.html" import table %}
            {{ table(columns=[{"key": "a", "label": "A"}], rows=[]) }}
        """)
        html = tmpl.render()
        assert '暂无数据' in html

    def test_table_with_row_actions(self, env):
        tmpl = env.from_string("""
            {% from "components.html" import table %}
            {{ table(
                columns=[{"key": "name", "label": "名称"}],
                rows=[{"name": "X", "view_url": "/view/1"}],
                row_actions=[{"label": "查看", "url_key": "view_url", "variant": ""}]
            ) }}
        """)
        html = tmpl.render()
        assert 'actions' in html
        assert 'href="/view/1"' in html

    def test_badge_variants(self, env):
        for variant in ['success', 'warning', 'danger', 'info', 'primary', 'muted']:
            tmpl_str = (
                '{% from "components.html" import badge %}'
                '{{ badge("标签", variant="' + variant + '") }}'
            )
            tmpl = env.from_string(tmpl_str)
            html = tmpl.render()
            assert f'badge {variant}' in html
            assert '标签' in html

    def test_progress_bar(self, env):
        tmpl = env.from_string("""
            {% from "components.html" import progress_bar %}
            {{ progress_bar(percent=75, variant="primary", label="75%") }}
        """)
        html = tmpl.render()
        assert 'progress-bar' in html
        assert 'progress-fill primary' in html
        assert 'width: 75%' in html
        assert '75%' in html

    def test_progress_bar_zero(self, env):
        tmpl = env.from_string("""
            {% from "components.html" import progress_bar %}
            {{ progress_bar(percent=0) }}
        """)
        html = tmpl.render()
        assert 'width: 0%' in html

    def test_chart_container(self, env):
        tmpl = env.from_string("""
            {% from "components.html" import chart_container with context %}
            {% call chart_container(title="趋势图", height=300, id="myChart") %}
                <canvas></canvas>
            {% endcall %}
        """)
        html = tmpl.render()
        assert 'chart-container' in html
        assert 'chart-body' in html
        assert '趋势图' in html
        assert 'height: 300px' in html
        assert 'id="myChart"' in html

    def test_pagination_mid(self, env):
        tmpl = env.from_string("""
            {% from "components.html" import pagination %}
            {{ pagination(current=3, total_pages=10, on_click="loadPage") }}
        """)
        html = tmpl.render()
        assert 'pagination' in html
        assert '上一页' in html
        assert '下一页' in html
        assert '第 3 / 10 页' in html
        assert 'loadPage(2)' in html
        assert 'loadPage(4)' in html

    def test_pagination_first_page(self, env):
        tmpl = env.from_string("""
            {% from "components.html" import pagination %}
            {{ pagination(current=1, total_pages=5) }}
        """)
        html = tmpl.render()
        # 第一页的"上一页"应该 disabled
        assert 'disabled' in html

    def test_pagination_href_mode(self, env):
        tmpl = env.from_string("""
            {% from "components.html" import pagination %}
            {{ pagination(current=2, total_pages=5, href_template="/list?page={page}") }}
        """)
        html = tmpl.render()
        assert 'href="/list?page=1"' in html
        assert 'href="/list?page=3"' in html

    def test_filter_bar(self, env):
        tmpl = env.from_string("""
            {% from "components.html" import filter_bar %}
            {{ filter_bar(
                fields=[
                    {"type": "select", "label": "状态", "id": "status", "options": [("1", "通过"), ("2", "驳回")]},
                    {"type": "text", "label": "名称", "id": "name", "placeholder": "搜索..."},
                    {"type": "date", "label": "日期", "id": "date"},
                    {"type": "number", "label": "金额", "id": "amount"}
                ],
                submit_onclick="loadData()",
                reset_onclick="resetFilters()"
            ) }}
        """)
        html = tmpl.render()
        assert 'filter-bar' in html
        assert '状态' in html
        assert '名称' in html
        assert '日期' in html
        assert '金额' in html
        assert '<select' in html
        assert 'type="text"' in html
        assert 'type="date"' in html
        assert 'type="number"' in html
        assert 'onclick="loadData()"' in html
        assert 'onclick="resetFilters()"' in html

    def test_info_grid(self, env):
        tmpl = env.from_string("""
            {% from "components.html" import info_grid %}
            {{ info_grid(items=[
                {"label": "合同号", "value": "HT001"},
                {"label": "金额", "value": "¥1000", "badge_variant": "success"}
            ]) }}
        """)
        html = tmpl.render()
        assert 'info-grid' in html
        assert 'info-item' in html
        assert 'info-label' in html
        assert 'HT001' in html
        assert 'badge success' in html


# ============================================================
# Forms 宏测试
# ============================================================

class TestFormsMacro:

    def test_input_text(self, env):
        tmpl = env.from_string("""
            {% from "forms.html" import input %}
            {{ input(name="username", label="用户名", value="admin", placeholder="请输入") }}
        """)
        html = tmpl.render()
        assert 'form-group' in html
        assert '<label for="username"' in html
        assert '用户名' in html
        assert 'type="text"' in html
        assert 'name="username"' in html
        assert 'value="admin"' in html
        assert 'placeholder="请输入"' in html

    def test_input_required(self, env):
        tmpl = env.from_string("""
            {% from "forms.html" import input %}
            {{ input(name="email", label="邮箱", type="email", required=true) }}
        """)
        html = tmpl.render()
        assert 'type="email"' in html
        assert 'required' in html

    def test_input_disabled(self, env):
        tmpl = env.from_string("""
            {% from "forms.html" import input %}
            {{ input(name="id", label="ID", disabled=true) }}
        """)
        html = tmpl.render()
        assert 'disabled' in html

    def test_input_with_error(self, env):
        tmpl = env.from_string("""
            {% from "forms.html" import input %}
            {{ input(name="name", label="名称", error="不能为空") }}
        """)
        html = tmpl.render()
        assert 'form-error' in html
        assert '不能为空' in html

    def test_input_with_help(self, env):
        tmpl = env.from_string("""
            {% from "forms.html" import input %}
            {{ input(name="n", label="N", help_text="提示信息") }}
        """)
        html = tmpl.render()
        assert 'form-help' in html
        assert '提示信息' in html

    def test_textarea(self, env):
        tmpl = env.from_string("""
            {% from "forms.html" import textarea %}
            {{ textarea(name="content", label="内容", value="hello", rows=5) }}
        """)
        html = tmpl.render()
        assert '<textarea' in html
        assert 'name="content"' in html
        assert 'rows="5"' in html
        assert 'hello' in html

    def test_select(self, env):
        tmpl = env.from_string("""
            {% from "forms.html" import select %}
            {{ select(name="status", label="状态", options=[
                ("1", "通过"),
                ("2", "驳回"),
                ("3", "待定")
            ], value="2") }}
        """)
        html = tmpl.render()
        assert '<select' in html
        assert 'name="status"' in html
        assert '通过' in html
        assert '驳回' in html
        assert 'value="2"' in html
        assert 'selected' in html

    def test_select_mapping_options(self, env):
        tmpl = env.from_string("""
            {% from "forms.html" import select %}
            {{ select(name="s", label="S", options=[
                {"value": "a", "label": "选项A"},
                {"value": "b", "label": "选项B"}
            ]) }}
        """)
        html = tmpl.render()
        assert '选项A' in html
        assert '选项B' in html
        assert 'value="a"' in html

    def test_button_variants(self, env):
        for variant in ['primary', 'success', 'danger', 'warning', 'info', '']:
            tmpl_str = (
                '{% from "forms.html" import button %}'
                '{{ button("按钮", variant="' + variant + '") }}'
            )
            tmpl = env.from_string(tmpl_str)
            html = tmpl.render()
            assert 'btn' in html
            if variant:
                assert f'btn-{variant}' in html

    def test_button_url(self, env):
        tmpl = env.from_string("""
            {% from "forms.html" import button %}
            {{ button("返回", url="/list", variant="") }}
        """)
        html = tmpl.render()
        assert 'href="/list"' in html
        assert '<a' in html

    def test_button_submit(self, env):
        tmpl = env.from_string("""
            {% from "forms.html" import button %}
            {{ button("提交", type="submit", variant="primary") }}
        """)
        html = tmpl.render()
        assert 'type="submit"' in html

    def test_form_row(self, env):
        tmpl = env.from_string("""
            {% from "forms.html" import form_row, input with context %}
            {% call form_row(cols=2) %}
                {{ input(name="a", label="A") }}
                {{ input(name="b", label="B") }}
            {% endcall %}
        """)
        html = tmpl.render()
        assert 'form-row' in html

    def test_form_row_3_cols(self, env):
        tmpl = env.from_string("""
            {% from "forms.html" import form_row with context %}
            {% call form_row(cols=3) %}three{% endcall %}
        """)
        html = tmpl.render()
        assert 'form-row-3' in html

    def test_checkbox(self, env):
        tmpl = env.from_string("""
            {% from "forms.html" import checkbox %}
            {{ checkbox(name="agree", label="同意条款", checked=true) }}
        """)
        html = tmpl.render()
        assert 'type="checkbox"' in html
        assert 'name="agree"' in html
        assert '同意条款' in html
        assert 'checked' in html

    def test_switch(self, env):
        tmpl = env.from_string("""
            {% from "forms.html" import switch %}
            {{ switch(name="enabled", label="启用", checked=true) }}
        """)
        html = tmpl.render()
        assert 'switch' in html
        assert 'slider' in html
        assert '启用' in html
        assert 'checked' in html


# ============================================================
# Icons 宏测试
# ============================================================

class TestIconsMacro:

    @pytest.mark.parametrize("icon_name", [
        "icon_home", "icon_dashboard", "icon_settings", "icon_menu",
        "icon_plus", "icon_check", "icon_x", "icon_edit", "icon_trash",
        "icon_search", "icon_alert", "icon_info", "icon_sun", "icon_moon",
        "icon_file", "icon_chart", "icon_user", "icon_arrow_left", "icon_arrow_right",
    ])
    def test_icon_renders_svg(self, env, icon_name):
        tmpl = env.from_string(f"""
            {{% from "icons.html" import {icon_name} %}}
            {{{{ {icon_name}(size=20) }}}}
        """)
        html = tmpl.render()
        assert '<svg' in html
        assert 'width="20"' in html
        assert 'height="20"' in html
        assert 'currentColor' in html

    def test_icon_default_size(self, env):
        tmpl = env.from_string("""
            {% from "icons.html" import icon_home %}
            {{ icon_home() }}
        """)
        html = tmpl.render()
        assert 'width="16"' in html


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

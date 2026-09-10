"""
Web Common Demo App — 最小 FastAPI Demo，展示所有组件

运行:
    python examples/demo_app.py

然后访问 http://localhost:8000
"""

import os
import sys
from pathlib import Path

# 添加项目根目录到 path（L2-infra 所在目录）
PROJECT_ROOT = Path(__file__).resolve().parents[3]  # openclaw-v5.0/
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jinja2 import FileSystemLoader

# --- 路径配置 ---
WEB_COMMON_DIR = Path(__file__).resolve().parent.parent  # web-common/
MACROS_DIR = WEB_COMMON_DIR / "macros"
STATIC_DIR = WEB_COMMON_DIR / "static"
TEMPLATES_DIR = WEB_COMMON_DIR / "examples" / "templates"

# 创建示例模板目录
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

# --- 创建示例页面模板 ---
demo_template = """
{% from "layout.html" import base_layout, page_header with context %}
{% from "components.html" import card, stat_card, dashboard_grid, table, badge, progress_bar, chart_container, pagination, filter_bar, info_grid with context %}
{% from "forms.html" import input, select, textarea, button, form_row, checkbox, switch with context %}
{% from "icons.html" import icon_home, icon_settings, icon_plus, icon_check with context %}

{% call base_layout(
    title="组件演示",
    brand_name="Web Common",
    brand_icon="🧩",
    active_page=active_page,
    storage_key="web-common-demo-theme",
    sidebar_items=[
        {"title": "演示", "items": [
            {"id": "dashboard", "label": "仪表盘", "url": "/", "icon": "📊"},
            {"id": "tables", "label": "表格", "url": "/tables", "icon": "📋"},
            {"id": "forms", "label": "表单", "url": "/forms", "icon": "📝"},
            {"id": "components", "label": "组件", "url": "/components", "icon": "🧩"},
        ]}
    ]
) %}
    {% block content %}{% endblock %}
{% endcall %}
"""

# 写一个示例 index 模板
index_template = demo_template.replace(
    "{% block content %}{% endblock %}",
    """
    {{ page_header(title="仪表盘演示", subtitle="统计卡片 + 图表 + 列表", actions=[
        {"label": "新建", "url": "#", "variant": "primary", "icon": "➕"}
    ]) }}

    {% call dashboard_grid() %}
        {{ stat_card(label="总用户", value=12847, variant="primary", sub="较上月 +12%") }}
        {{ stat_card(label="活跃用户", value=8932, variant="success", sub="日活 DAU") }}
        {{ stat_card(label="待处理", value=256, variant="warning", sub="需要审核") }}
        {{ stat_card(label="异常数", value=12, variant="danger", sub="需关注") }}
    {% endcall %}

    <div class="grid-2">
        {% call chart_container(title="近 30 天趋势", height=200) %}
            <div class="trend-chart" style="display:flex;align-items:flex-end;gap:3px;height:160px;width:100%;">
                {% for i in range(30) %}
                    <div style="flex:1;background:var(--c-primary);border-radius:3px 3px 0 0;opacity:0.7;height:{{ (i % 10 + 1) * 10 }}%;"></div>
                {% endfor %}
            </div>
        {% endcall %}

        {% call card(title="状态分布") %}
            <div style="display:flex;flex-direction:column;gap:12px;">
                <div>
                    <div style="display:flex;justify-content:space-between;font-size:0.85rem;margin-bottom:4px;">
                        <span>已完成</span><span class="mono">65%</span>
                    </div>
                    {{ progress_bar(percent=65, variant="success") }}
                </div>
                <div>
                    <div style="display:flex;justify-content:space-between;font-size:0.85rem;margin-bottom:4px;">
                        <span>进行中</span><span class="mono">25%</span>
                    </div>
                    {{ progress_bar(percent=25, variant="primary") }}
                </div>
                <div>
                    <div style="display:flex;justify-content:space-between;font-size:0.85rem;margin-bottom:4px;">
                        <span>待处理</span><span class="mono">10%</span>
                    </div>
                    {{ progress_bar(percent=10, variant="warning") }}
                </div>
            </div>
        {% endcall %}
    </div>

    {% call card(title="最近活动", actions=[{"label": "查看全部", "url": "#", "variant": ""}]) %}
        {{ table(
            columns=[
                {"key": "time", "label": "时间"},
                {"key": "user", "label": "用户"},
                {"key": "action", "label": "操作"},
                {"key": "status", "label": "状态"}
            ],
            rows=[
                {"time": "10:32", "user": "张三", "action": "登录系统", "status": badge("成功", "success")|safe},
                {"time": "10:15", "user": "李四", "action": "提交审批", "status": badge("进行中", "warning")|safe},
                {"time": "09:48", "user": "王五", "action": "上传文件", "status": badge("成功", "success")|safe},
                {"time": "09:20", "user": "赵六", "action": "删除记录", "status": badge("失败", "danger")|safe},
            ]
        ) }}
    {% endcall %}
    """
)

tables_template = demo_template.replace(
    "{% block content %}{% endblock %}",
    """
    {{ page_header(title="表格演示", subtitle="数据表格 + 筛选 + 分页") }}

    {{ filter_bar(
        fields=[
            {"type": "select", "label": "状态", "id": "status", "options": [("all","全部"),("active","活跃"),("inactive","停用")]},
            {"type": "text", "label": "关键词", "id": "keyword", "placeholder": "搜索名称..."},
            {"type": "date", "label": "开始日期", "id": "date_from"},
            {"type": "date", "label": "结束日期", "id": "date_to"},
        ],
        submit_onclick="showToast('筛选已应用', 'success')",
        reset_onclick="showToast('已重置', 'info')"
    ) }}

    {% call card(title="用户列表") %}
        {{ table(
            columns=[
                {"key": "id", "label": "ID"},
                {"key": "name", "label": "姓名"},
                {"key": "email", "label": "邮箱"},
                {"key": "role", "label": "角色"},
                {"key": "amount", "label": "金额", "align": "right", "num": true},
                {"key": "status", "label": "状态"}
            ],
            rows=[
                {"id": 1, "name": "张三", "email": "zhang@example.com", "role": "管理员", "amount": 12500, "status": badge("活跃", "success")|safe},
                {"id": 2, "name": "李四", "email": "li@example.com", "role": "编辑", "amount": 8300, "status": badge("活跃", "success")|safe},
                {"id": 3, "name": "王五", "email": "wang@example.com", "role": "用户", "amount": 3200, "status": badge("待审核", "warning")|safe},
                {"id": 4, "name": "赵六", "email": "zhao@example.com", "role": "用户", "amount": 1500, "status": badge("停用", "muted")|safe},
                {"id": 5, "name": "孙七", "email": "sun@example.com", "role": "编辑", "amount": 9800, "status": badge("活跃", "success")|safe},
            ],
            row_actions=[
                {"label": "查看", "url_key": "#", "variant": ""},
                {"label": "编辑", "url_key": "#", "variant": "primary"},
            ]
        ) }}
        {{ pagination(current=3, total_pages=10, on_click="showToast('切换到第 ' + arguments[0] + ' 页', 'info')") }}
    {% endcall %}
    """
)

forms_template = demo_template.replace(
    "{% block content %}{% endblock %}",
    """
    {{ page_header(title="表单演示", subtitle="输入框 / 选择器 / 开关 / 按钮") }}

    <div class="grid-2">
        {% call card(title="基础表单") %}
            {{ input(name="username", label="用户名", value="", placeholder="请输入用户名", required=true) }}
            {{ input(name="email", label="邮箱", type="email", placeholder="name@example.com") }}
            {{ input(name="password", label="密码", type="password", placeholder="至少 8 位") }}
            {{ select(name="role", label="角色", options=[
                ("admin", "管理员"),
                ("editor", "编辑"),
                ("user", "普通用户"),
            ], placeholder="请选择角色") }}
            {{ textarea(name="bio", label="个人简介", placeholder="介绍一下自己...", rows=4, help_text="最多 500 字") }}
            {{ checkbox(name="agree", label="我已阅读并同意用户协议", checked=false) }}
            <div style="display: flex; gap: 8px; margin-top: 16px;">
                {{ button("提交", variant="primary", type="submit", onclick="showToast('提交成功！', 'success')") }}
                {{ button("重置", variant="", onclick="showToast('已重置', 'info')") }}
            </div>
        {% endcall %}

        {% call card(title="更多组件") %}
            {% call form_row(cols=2) %}
                {{ input(name="first_name", label="名", value="") }}
                {{ input(name="last_name", label="姓", value="") }}
            {% endcall %}
            {{ input(name="age", label="年龄", type="number", value="25") }}
            {{ input(name="birthday", label="生日", type="date") }}
            {{ switch(name="notifications", label="邮件通知", checked=true) }}
            {{ switch(name="dark_mode", label="深色模式", checked=false) }}
            {{ input(name="disabled_field", label="只读字段", value="不可编辑", readonly=true, help_text="该字段为系统自动生成") }}
            {{ input(name="error_field", label="有错误的字段", value="", error="该字段不能为空") }}
        {% endcall %}
    </div>
    """
)

components_template = demo_template.replace(
    "{% block content %}{% endblock %}",
    """
    {{ page_header(title="组件演示", subtitle="徽章 / 进度条 / 信息网格 / 时间线") }}

    <div class="grid-2">
        {% call card(title="徽章 Badges") %}
            <div style="display: flex; flex-wrap: wrap; gap: 8px;">
                {{ badge("成功", "success") }}
                {{ badge("警告", "warning") }}
                {{ badge("错误", "danger") }}
                {{ badge("信息", "info") }}
                {{ badge("主要", "primary") }}
                {{ badge("次要", "muted") }}
            </div>
        {% endcall %}

        {% call card(title="进度条 Progress") %}
            <div style="display: flex; flex-direction: column; gap: 16px;">
                <div>{{ progress_bar(percent=100, variant="success", label="100% 完成") }}</div>
                <div>{{ progress_bar(percent=75, variant="primary", label="75% 进行中") }}</div>
                <div>{{ progress_bar(percent=50, variant="warning", label="50% 待处理") }}</div>
                <div>{{ progress_bar(percent=25, variant="danger", label="25% 延迟") }}</div>
            </div>
        {% endcall %}
    </div>

    {% call card(title="信息网格 Info Grid") %}
        {{ info_grid(items=[
            {"label": "订单号", "value": "ORD-2026-001234"},
            {"label": "客户名称", "value": "某某科技有限公司"},
            {"label": "订单金额", "value": "¥128,500.00"},
            {"label": "订单状态", "value": "处理中", "badge_variant": "warning"},
            {"label": "创建时间", "value": "2026-01-15 10:30"},
            {"label": "负责人", "value": "张三"},
            {"label": "交付日期", "value": "2026-02-28"},
            {"label": "优先级", "value": "高", "badge_variant": "danger"},
        ]) }}
    {% endcall %}

    {% call card(title="按钮 Buttons") %}
        <div style="display: flex; flex-wrap: wrap; gap: 8px; align-items: center;">
            {{ button("主要按钮", variant="primary", onclick="showToast('主要按钮', 'success')") }}
            {{ button("成功", variant="success", onclick="showToast('成功', 'success')") }}
            {{ button("警告", variant="warning", onclick="showToast('警告', 'warning')") }}
            {{ button("危险", variant="danger", onclick="showToast('危险', 'error')") }}
            {{ button("默认", variant="", onclick="showToast('默认', 'info')") }}
            {{ button("禁用", variant="", disabled=true) }}
        </div>
        <div style="margin-top: 16px; display: flex; flex-wrap: wrap; gap: 8px; align-items: center;">
            {{ button("小按钮", variant="primary", size="sm") }}
            {{ button("默认大小", variant="primary") }}
            {{ button("大按钮", variant="primary", size="lg") }}
        </div>
    {% endcall %}
    """
)

# 写入模板文件
(TEMPLATES_DIR / "index.html").write_text(index_template)
(TEMPLATES_DIR / "tables.html").write_text(tables_template)
(TEMPLATES_DIR / "forms.html").write_text(forms_template)
(TEMPLATES_DIR / "components.html").write_text(components_template)

# --- FastAPI App ---
def create_app() -> FastAPI:
    app = FastAPI(title="Web Common Demo", version="1.0.0")

    # 挂载 web-common 静态资源
    app.mount(
        "/static/web-common",
        StaticFiles(directory=str(STATIC_DIR)),
        name="web-common-static"
    )

    # 配置模板：业务模板目录 + 宏目录
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    templates.env.loader = FileSystemLoader([str(TEMPLATES_DIR), str(MACROS_DIR)])

    @app.get("/")
    async def dashboard(request: Request):
        return templates.TemplateResponse(
            "index.html",
            {"request": request, "active_page": "dashboard"}
        )

    @app.get("/tables")
    async def tables_page(request: Request):
        return templates.TemplateResponse(
            "tables.html",
            {"request": request, "active_page": "tables"}
        )

    @app.get("/forms")
    async def forms_page(request: Request):
        return templates.TemplateResponse(
            "forms.html",
            {"request": request, "active_page": "forms"}
        )

    @app.get("/components")
    async def components_page(request: Request):
        return templates.TemplateResponse(
            "components.html",
            {"request": request, "active_page": "components"}
        )

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    print("🚀 Web Common Demo 启动中...")
    print("📊 仪表盘:  http://localhost:8000/")
    print("📋 表格:    http://localhost:8000/tables")
    print("📝 表单:    http://localhost:8000/forms")
    print("🧩 组件:    http://localhost:8000/components")
    uvicorn.run(app, host="0.0.0.0", port=8000)

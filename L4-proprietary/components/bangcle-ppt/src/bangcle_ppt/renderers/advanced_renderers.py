"""
高级页面渲染器：
- 纵向时间轴
- 放射结构图
- 阶段时间轴（6阶段）
- 团队/人员介绍
- 对比页
- 表格页
- 流程图
- 结束/感谢页
- 空白页
- 深色特有页面
"""

from __future__ import annotations

import math
from typing import Any

from pptx import Presentation

from ..base.renderer_base import RendererBase


# ── 纵向时间轴 ──────────────────────────────────────────────────────

class VTimelineLightRenderer(RendererBase):
    """纵向时间轴 + 右侧图片（浅色）。"""
    page_type = "timeline-vertical-light"

    def __init__(self, theme=None):
        super().__init__(theme=theme or "light")

    def render(self, prs: Presentation, data: dict[str, Any] | None = None):
        data = data or {}
        slide = self.add_blank_slide(prs)

        content_top = self.add_page_header(
            slide,
            data.get("title", "发展历程"),
            data.get("subtitle", "MILESTONES"),
        )

        s = self.theme.sizes

        # 左侧：纵向时间线
        tl_x = s.margins.content_left + 0.5
        tl_top = content_top + 0.3
        tl_bottom = s.slide.height - s.margins.bottom_safe - 0.3
        tl_height = tl_bottom - tl_top

        # 时间轴线
        self.add_line(
            slide, tl_x, tl_top, tl_x, tl_bottom,
            color="#BEE3FA",
            width=1.5,
        )

        items = data.get("items", [])
        if not items:
            items = [
                {"date": "2018", "title": "成立之初", "body": "公司成立，启动移动安全业务。"},
                {"date": "2020", "title": "快速发展", "body": "产品矩阵完善，服务客户突破百家。"},
                {"date": "2023", "title": "行业领先", "body": "成为移动安全领域头部厂商。"},
            ]

        # 节点
        item_count = len(items[:5])
        step = tl_height / max(item_count + 1, 2)

        for i, item in enumerate(items[:5]):
            y = tl_top + step * (i + 1) - step / 2

            # 双圆环节点
            self.add_circle(slide, tl_x - 0.08, y - 0.08, 0.16,
                           fill_color="#FFFFFF", border_color=self.theme.primary, border_width=2)
            self.add_circle(slide, tl_x - 0.03, y - 0.03, 0.06,
                           fill_color=self.theme.primary)

            # 日期标签
            date = item.get("date", "")
            self.add_text(
                slide, date,
                tl_x + 0.2, y - 0.25,
                2, 0.35,
                font_size=14,
                bold=True,
                color=self.theme.primary,
            )

            # 标题
            title = item.get("title", "")
            self.add_text(
                slide, title,
                tl_x + 0.9, y - 0.25,
                2.5, 0.35,
                font_size=self.theme.font_size.h5 if hasattr(self.theme.font_size, 'h5') else 20,
                bold=True,
                color=self.theme.title_color,
            )

            # 正文
            body = item.get("body", "")
            self.add_text(
                slide, body,
                tl_x + 0.9, y + 0.08,
                3.5, 0.7,
                font_size=self.theme.font_size.body_sm if hasattr(self.theme.font_size, 'body_sm') else 12,
                color=self.theme.body_color,
                line_spacing=1.4,
            )

        # 右侧图片占位
        img_x = 7.2
        img_y = content_top + 0.2
        img_w = s.slide.width - img_x - 0.8
        img_h = tl_bottom - img_y
        img_path = data.get("image_path", "")
        if img_path:
            try:
                self.add_image(slide, img_path, img_x, img_y, img_w, img_h)
            except FileNotFoundError:
                self._img_placeholder(slide, img_x, img_y, img_w, img_h)
        else:
            self._img_placeholder(slide, img_x, img_y, img_w, img_h)

        return slide

    def _img_placeholder(self, slide, x, y, w, h):
        self.add_rect(slide, x, y, w, h, fill_color="#F0F4F8",
                      border_color="#D0D8E0", corner_radius=0.1)
        self.add_text(slide, "📷\n配图区域", x, y + h/2 - 0.5, w, 1,
                      font_size=16, color="#99AABB", align="center", anchor="middle")


# ── 放射结构图 ──────────────────────────────────────────────────────

class RadialStructureLightRenderer(RendererBase):
    """放射结构图（中心圆 + 6 节点，浅色）。"""
    page_type = "radial-structure-light"

    def __init__(self, theme=None):
        super().__init__(theme=theme or "light")

    def render(self, prs: Presentation, data: dict[str, Any] | None = None):
        data = data or {}
        slide = self.add_blank_slide(prs)

        content_top = self.add_page_header(
            slide,
            data.get("title", "产品架构"),
            data.get("subtitle", "ARCHITECTURE"),
        )

        s = self.theme.sizes

        # 中心圆
        center_x = s.slide.width / 2
        center_y = content_top + 2.5
        center_r = 0.9

        self.add_circle(slide, center_x - center_r, center_y - center_r, center_r * 2,
                       fill_color=self.theme.primary)

        center_title = data.get("center_title", "核心能力")
        self.add_text(slide, center_title,
                      center_x - center_r, center_y - 0.4,
                      center_r * 2, 0.5,
                      font_size=18, bold=True, color="#FFFFFF", align="center", anchor="middle")

        center_sub = data.get("center_subtitle", "")
        if center_sub:
            self.add_text(slide, center_sub,
                          center_x - center_r, center_y + 0.1,
                          center_r * 2, 0.35,
                          font_size=11, color="#BEE3FA", align="center")

        # 6 个外围节点
        nodes = data.get("nodes", [])
        if not nodes:
            nodes = [
                {"label": "能力一", "icon": "①"},
                {"label": "能力二", "icon": "②"},
                {"label": "能力三", "icon": "③"},
                {"label": "能力四", "icon": "④"},
                {"label": "能力五", "icon": "⑤"},
                {"label": "能力六", "icon": "⑥"},
            ]

        orbit_r = 2.2
        node_r = 0.55

        for i, node in enumerate(nodes[:6]):
            angle = -math.pi / 2 + i * (2 * math.pi / 6)  # 从顶部开始
            nx = center_x + orbit_r * math.cos(angle)
            ny = center_y + orbit_r * math.sin(angle)

            # 连线
            self.add_line(slide, center_x, center_y, nx, ny,
                         color="#BEE3FA", width=1.5)

            # 节点圆
            self.add_circle(slide, nx - node_r, ny - node_r, node_r * 2,
                           fill_color="#FFFFFF",
                           border_color=self.theme.primary,
                           border_width=2)

            # icon / 编号
            icon = node.get("icon", "")
            if icon:
                self.add_text(slide, icon,
                              nx - node_r, ny - node_r + 0.1,
                              node_r * 2, node_r,
                              font_size=14, bold=True,
                              color=self.theme.primary,
                              align="center", anchor="middle")

            # 标签（节点下方或上方）
            label = node.get("label", "")
            label_y = ny + node_r + 0.05
            if ny < center_y:
                label_y = ny - node_r - 0.35
            self.add_text(slide, label,
                          nx - 1, label_y,
                          2, 0.35,
                          font_size=12, bold=True,
                          color=self.theme.title_color,
                          align="center")

        return slide


# ── 阶段时间轴（6 阶段） ─────────────────────────────────────────────

class PhaseTimelineLightRenderer(RendererBase):
    """6 阶段时间轴（上下交错，浅色）。"""
    page_type = "phase-timeline-light"

    def __init__(self, theme=None):
        super().__init__(theme=theme or "light")

    def render(self, prs: Presentation, data: dict[str, Any] | None = None):
        data = data or {}
        slide = self.add_blank_slide(prs)

        content_top = self.add_page_header(
            slide,
            data.get("title", "项目路线图"),
            data.get("subtitle", "ROADMAP"),
        )

        s = self.theme.sizes
        items = data.get("items", [])
        if not items:
            items = [
                {"phase": "阶段1", "title": "需求分析", "body": "项目启动与需求梳理"},
                {"phase": "阶段2", "title": "方案设计", "body": "技术方案与架构设计"},
                {"phase": "阶段3", "title": "开发实施", "body": "核心功能开发实现"},
                {"phase": "阶段4", "title": "测试验证", "body": "功能测试与性能调优"},
                {"phase": "阶段5", "title": "试点部署", "body": "小范围试点上线"},
                {"phase": "阶段6", "title": "全面推广", "body": "全量上线与运营支持"},
            ]

        # 中间主线
        line_y = content_top + 2.2
        line_left = s.margins.content_left + 0.3
        line_right = s.slide.width - 0.8
        self.add_line(slide, line_left, line_y, line_right, line_y,
                     color=self.theme.primary, width=2.5)

        count = len(items[:6])
        step = (line_right - line_left) / count
        node_r = 0.12

        for i, item in enumerate(items[:6]):
            nx = line_left + step * (i + 0.5)

            # 节点圆
            self.add_circle(slide, nx - node_r, line_y - node_r, node_r * 2,
                           fill_color="#FFFFFF",
                           border_color=self.theme.primary,
                           border_width=2.5)

            is_top = i % 2 == 0  # 上下交错
            if is_top:
                # 上方卡片
                card_h = 1.5
                card_y = line_y - card_h - 0.3
                # 连接线
                self.add_line(slide, nx, line_y - 0.15, nx, card_y + card_h,
                             color="#BEE3FA", width=1)
            else:
                # 下方卡片
                card_h = 1.5
                card_y = line_y + 0.3
                self.add_line(slide, nx, line_y + 0.15, nx, card_y,
                             color="#BEE3FA", width=1)

            card_w = step * 0.85
            card_x = nx - card_w / 2

            # 卡片
            self.add_rect(slide, card_x, card_y, card_w, card_h,
                         fill_color="#FFFFFF",
                         border_color="#BEE3FA",
                         border_width=1,
                         corner_radius=0.06)

            # 阶段标签
            phase = item.get("phase", f"阶段{i+1}")
            self.add_text(slide, phase,
                          card_x + 0.15, card_y + 0.1,
                          card_w - 0.3, 0.25,
                          font_size=10, color=self.theme.primary)

            # 标题
            title = item.get("title", "")
            self.add_text(slide, title,
                          card_x + 0.15, card_y + 0.35,
                          card_w - 0.3, 0.3,
                          font_size=13, bold=True, color=self.theme.title_color)

            # 正文
            body = item.get("body", "")
            self.add_text(slide, body,
                          card_x + 0.15, card_y + 0.65,
                          card_w - 0.3, card_h - 0.75,
                          font_size=10, color=self.theme.body_color, line_spacing=1.3)

        return slide


# ── 团队卡片 ────────────────────────────────────────────────────────

class TeamCardsLightRenderer(RendererBase):
    """4 人团队介绍卡片（浅色）。"""
    page_type = "team-cards-light"

    def __init__(self, theme=None):
        super().__init__(theme=theme or "light")

    def render(self, prs: Presentation, data: dict[str, Any] | None = None):
        data = data or {}
        slide = self.add_blank_slide(prs)

        content_top = self.add_page_header(
            slide,
            data.get("title", "核心团队"),
            data.get("subtitle", "OUR TEAM"),
        )

        s = self.theme.sizes
        members = data.get("members", [])
        if not members:
            members = [
                {"name": "张三", "role": "CEO / 创始人", "description": "10年行业经验"},
                {"name": "李四", "role": "CTO", "description": "技术架构专家"},
                {"name": "王五", "role": "产品总监", "description": "产品规划专家"},
                {"name": "赵六", "role": "运营总监", "description": "增长运营专家"},
            ]

        card_w = 2.8
        card_h = 3.2
        gap = 0.25
        start_x = s.margins.content_left + 0.2
        start_y = content_top + 0.4

        for i, member in enumerate(members[:4]):
            x = start_x + i * (card_w + gap)
            y = start_y

            # 卡片底
            self.add_rect(slide, x, y, card_w, card_h,
                         fill_color="#FFFFFF",
                         border_color="#E7E6E6",
                         border_width=1,
                         corner_radius=0.08)

            # 上半部分（头像区背景）
            self.add_rect(slide, x, y, card_w, 1.3,
                         fill_color="#F5F9FF",
                         corner_radius=0.08)

            # 头像圆
            avatar_r = 0.5
            avatar_x = x + card_w / 2 - avatar_r
            avatar_y = y + 0.4
            avatar = member.get("avatar", "")
            if avatar:
                try:
                    self.add_image(slide, avatar, avatar_x, avatar_y, avatar_r * 2, avatar_r * 2)
                except FileNotFoundError:
                    self._draw_avatar(slide, avatar_x, avatar_y, avatar_r * 2)
            else:
                self._draw_avatar(slide, avatar_x, avatar_y, avatar_r * 2)

            # 姓名
            name = member.get("name", "")
            self.add_text(slide, name,
                          x, y + 1.45,
                          card_w, 0.4,
                          font_size=18, bold=True,
                          color=self.theme.title_color, align="center")

            # 职位
            role = member.get("role", "")
            self.add_text(slide, role,
                          x, y + 1.85,
                          card_w, 0.3,
                          font_size=12, color=self.theme.primary, align="center")

            # 分割线
            self.add_line(slide,
                         x + card_w/2 - 0.4, y + 2.2,
                         x + card_w/2 + 0.4, y + 2.2,
                         color=self.theme.divider_color, width=1)

            # 描述
            desc = member.get("description", "")
            self.add_text(slide, desc,
                          x + 0.2, y + 2.35,
                          card_w - 0.4, 0.7,
                          font_size=11, color=self.theme.body_color,
                          align="center", line_spacing=1.4)

        return slide

    def _draw_avatar(self, slide, x, y, size):
        self.add_circle(slide, x, y, size,
                       fill_color="#E0EAF5",
                       border_color=self.theme.primary, border_width=2)
        # 简化的人物图标
        self.add_text(slide, "👤",
                      x, y + size/2 - 0.35,
                      size, 0.7,
                      font_size=28, color=self.theme.primary,
                      align="center", anchor="middle")


# ── 对比页 ──────────────────────────────────────────────────────────

class CompareTwoColLightRenderer(RendererBase):
    """两栏对比页（浅色）。"""
    page_type = "compare-two-col-light"

    def __init__(self, theme=None):
        super().__init__(theme=theme or "light")

    def render(self, prs: Presentation, data: dict[str, Any] | None = None):
        data = data or {}
        slide = self.add_blank_slide(prs)

        content_top = self.add_page_header(
            slide,
            data.get("title", "方案对比"),
            data.get("subtitle", "COMPARISON"),
        )

        s = self.theme.sizes
        columns = data.get("columns", [])
        if not columns:
            columns = [
                {"title": "方案 A", "items": ["特性一", "特性二", "特性三"], "highlight": False},
                {"title": "方案 B", "items": ["特性一", "特性二", "特性三", "特性四"], "highlight": True},
            ]

        col_count = len(columns[:3])
        col_w = 5.5 if col_count == 2 else 3.8
        col_h = 4.2
        gap = 0.4
        start_x = (s.slide.width - col_count * col_w - (col_count - 1) * gap) / 2
        start_y = content_top + 0.4

        for i, col in enumerate(columns[:3]):
            x = start_x + i * (col_w + gap)
            y = start_y

            is_highlight = col.get("highlight", False)
            border_color = self.theme.primary if is_highlight else "#E7E6E6"
            border_w = 2 if is_highlight else 1

            # 卡片
            self.add_rect(slide, x, y, col_w, col_h,
                         fill_color="#FFFFFF",
                         border_color=border_color,
                         border_width=border_w,
                         corner_radius=0.1)

            # 标题栏
            header_h = 0.6
            header_bg = self.theme.primary if is_highlight else "#F5F9FF"
            header_text = "#FFFFFF" if is_highlight else self.theme.title_color
            self.add_rect(slide, x, y, col_w, header_h,
                         fill_color=header_bg,
                         corner_radius=0.1)

            self.add_text(slide, col.get("title", f"方案 {i+1}"),
                          x, y + 0.1,
                          col_w, 0.4,
                          font_size=18, bold=True,
                          color=header_text, align="center")

            # 列表项
            items = col.get("items", [])
            item_y = y + header_h + 0.3
            for j, item in enumerate(items[:8]):
                # checkmark / bullet
                self.add_text(slide, "✓",
                              x + 0.3, item_y + j * 0.4,
                              0.4, 0.35,
                              font_size=14, color=self.theme.primary, bold=True)

                self.add_text(slide, str(item),
                              x + 0.7, item_y + j * 0.4,
                              col_w - 1.0, 0.35,
                              font_size=13, color=self.theme.body_color)

            # 推荐标签（高亮时）
            if is_highlight:
                badge_y = y - 0.25
                self.add_rect(slide, x + col_w/2 - 0.6, badge_y, 1.2, 0.35,
                             fill_color=self.theme.gold, corner_radius=0.08)
                self.add_text(slide, "推荐",
                              x + col_w/2 - 0.6, badge_y + 0.03,
                              1.2, 0.3,
                              font_size=11, bold=True,
                              color="#FFFFFF", align="center")

        return slide


# ── 表格页 ──────────────────────────────────────────────────────────

class TableLightRenderer(RendererBase):
    """数据表格页（浅色）。"""
    page_type = "table-light"

    def __init__(self, theme=None):
        super().__init__(theme=theme or "light")

    def render(self, prs: Presentation, data: dict[str, Any] | None = None):
        data = data or {}
        slide = self.add_blank_slide(prs)

        content_top = self.add_page_header(
            slide,
            data.get("title", "数据表格"),
            data.get("subtitle", "DATA TABLE"),
        )

        s = self.theme.sizes
        table_data = data.get("table_data", [])
        has_header = data.get("has_header", True)

        if not table_data:
            table_data = [
                ["指标", "Q1", "Q2", "Q3", "Q4"],
                ["收入", "100万", "120万", "150万", "180万"],
                ["客户数", "50", "80", "120", "200"],
                ["满意度", "95%", "96%", "97%", "98%"],
                ["转化率", "5%", "6%", "7%", "8%"],
            ]

        rows = len(table_data)
        cols = len(table_data[0]) if table_data else 0

        table_x = s.margins.content_left
        table_y = content_top + 0.3
        table_w = s.slide.width - s.margins.content_right - table_x + 0.2
        table_h = 4.5

        self.add_table(
            slide, table_x, table_y, table_w, table_h,
            rows, cols,
            data=table_data,
            header=has_header,
            header_bg=self.theme.primary,
            font_size=12,
            header_font_size=14,
        )

        return slide


# ── 流程图 ──────────────────────────────────────────────────────────

class FlowLightRenderer(RendererBase):
    """步骤流程图（横向，浅色）。"""
    page_type = "flow-light"

    def __init__(self, theme=None):
        super().__init__(theme=theme or "light")

    def render(self, prs: Presentation, data: dict[str, Any] | None = None):
        data = data or {}
        slide = self.add_blank_slide(prs)

        content_top = self.add_page_header(
            slide,
            data.get("title", "工作流程"),
            data.get("subtitle", "WORKFLOW"),
        )

        s = self.theme.sizes
        steps = data.get("steps", [])
        if not steps:
            steps = [
                {"step": "01", "title": "需求收集", "body": "收集业务需求"},
                {"step": "02", "title": "方案设计", "body": "制定技术方案"},
                {"step": "03", "title": "开发实现", "body": "编码与单元测试"},
                {"step": "04", "title": "测试验证", "body": "集成测试与验收"},
                {"step": "05", "title": "部署上线", "body": "生产环境部署"},
            ]

        count = len(steps[:5])
        step_w = 1.8
        step_h = 1.8
        gap = 0.8
        total_w = count * step_w + (count - 1) * gap
        start_x = (s.slide.width - total_w) / 2
        start_y = content_top + 1.5

        for i, step in enumerate(steps[:5]):
            x = start_x + i * (step_w + gap)
            y = start_y

            # 步骤框
            self.add_rect(slide, x, y, step_w, step_h,
                         fill_color="#FFFFFF",
                         border_color=self.theme.primary,
                         border_width=2,
                         corner_radius=0.12)

            # 编号圆
            num_r = 0.35
            self.add_circle(slide, x + step_w/2 - num_r, y - num_r, num_r * 2,
                           fill_color=self.theme.primary)
            self.add_text(slide, step.get("step", f"{i+1:02d}"),
                          x + step_w/2 - num_r, y - num_r + 0.1,
                          num_r * 2, 0.5,
                          font_size=12, bold=True,
                          color="#FFFFFF", align="center", anchor="middle")

            # 标题
            self.add_text(slide, step.get("title", f"步骤 {i+1}"),
                          x, y + 0.5,
                          step_w, 0.4,
                          font_size=16, bold=True,
                          color=self.theme.title_color, align="center")

            # 分割线
            self.add_line(slide,
                         x + 0.3, y + 0.95,
                         x + step_w - 0.3, y + 0.95,
                         color=self.theme.divider_color, width=0.5)

            # 正文
            self.add_text(slide, step.get("body", ""),
                          x + 0.2, y + 1.1,
                          step_w - 0.4, 0.6,
                          font_size=11,
                          color=self.theme.body_color,
                          align="center", line_spacing=1.3)

            # 箭头（除了最后一个）
            if i < count - 1:
                arrow_x = x + step_w + 0.1
                arrow_y = y + step_h / 2 - 0.12
                self.add_text(slide, "→",
                              arrow_x, arrow_y,
                              gap - 0.2, 0.3,
                              font_size=24, color=self.theme.primary, align="center")

        return slide


# ── 结束/感谢页（浅色） ──────────────────────────────────────────────

class ClosingLightRenderer(RendererBase):
    """结束/感谢页（浅色，二维码结尾）。"""
    page_type = "closing-light"

    def __init__(self, theme=None):
        super().__init__(theme=theme or "light")

    def render(self, prs: Presentation, data: dict[str, Any] | None = None):
        data = data or {}
        slide = self.add_blank_slide(prs)
        s = self.theme.sizes

        # 顶部装饰条
        self.add_rect(slide, 0, 0, s.slide.width, 0.08,
                     fill_color=self.theme.primary)

        # 左侧装饰
        self.add_rect(slide, 0, 0, 0.3, s.slide.height,
                     fill_color=self.theme.primary)

        # 主标题
        main_text = data.get("main_text", "谢谢观看")
        self.add_text(slide, main_text,
                      1.5, 2.2,
                      8, 1.2,
                      font_size=60, bold=True,
                      color=self.theme.title_color)

        # 英文副标题
        subtitle = data.get("subtitle", "THANK YOU")
        self.add_text(slide, subtitle,
                      1.5, 3.4,
                      8, 0.5,
                      font_size=24, color=self.theme.caption_color)

        # 分割线
        self.add_line(slide, 1.5, 4.0, 4.5, 4.0,
                     color=self.theme.primary, width=2)

        # 联系方式
        contact = data.get("contact", "联系我们：bangcle@example.com")
        if contact:
            self.add_text(slide, contact,
                          1.5, 4.2,
                          6, 0.4,
                          font_size=14, color=self.theme.body_color)

        # Slogan
        slogan = data.get("slogan", "")
        if slogan:
            self.add_text(slide, slogan,
                          1.5, 4.7,
                          6, 0.4,
                          font_size=14, color=self.theme.primary, bold=True)

        # 右侧二维码占位
        qr_x = 9.5
        qr_y = 2.5
        qr_size = 2.5
        qr_code = data.get("qr_code", "")
        if qr_code:
            try:
                self.add_image(slide, qr_code, qr_x, qr_y, qr_size, qr_size)
            except FileNotFoundError:
                self._draw_qr_placeholder(slide, qr_x, qr_y, qr_size)
        else:
            self._draw_qr_placeholder(slide, qr_x, qr_y, qr_size)

        # 底部装饰
        self.add_rect(slide, 0, s.slide.height - 0.15, s.slide.width, 0.15,
                     fill_color=self.theme.primary)

        return slide

    def _draw_qr_placeholder(self, slide, x, y, size):
        self.add_rect(slide, x, y, size, size,
                     fill_color="#FFFFFF",
                     border_color=self.theme.primary, border_width=2,
                     corner_radius=0.05)
        self.add_text(slide, "二维码\n扫码关注",
                      x, y + size/2 - 0.5,
                      size, 1,
                      font_size=14, color=self.theme.primary,
                      align="center", anchor="middle")


# ── 空白页 ──────────────────────────────────────────────────────────

class BlankLightRenderer(RendererBase):
    """空白模板页（仅左侧装饰条 + 标题）。"""
    page_type = "blank-light"

    def __init__(self, theme=None):
        super().__init__(theme=theme or "light")

    def render(self, prs: Presentation, data: dict[str, Any] | None = None):
        data = data or {}
        slide = self.add_blank_slide(prs)
        s = self.theme.sizes

        # 左侧装饰条
        if data.get("show_left_bar", True):
            self.add_rect(slide, 0.2, 0.5, 0.08, s.slide.height - 1.0,
                         fill_color=self.theme.primary)

        # 标题（可选）
        title = data.get("title", "")
        if title:
            content_top = self.add_page_header(
                slide, title, data.get("subtitle", ""),
            )
            data.setdefault("_content_top", content_top)

        # Logo 占位
        logo_path = data.get("logo_path", "")
        if logo_path:
            try:
                self.add_image(slide, logo_path, s.logo.left, s.logo.top, s.logo.width, s.logo.height)
            except FileNotFoundError:
                self._draw_logo_badge(slide, s)
        else:
            self._draw_logo_badge(slide, s)

        # 底部装饰条
        self.add_rect(slide, 0, s.slide.height - 0.06, s.slide.width, 0.06,
                     fill_color=self.theme.primary)

        return slide

    def _draw_logo_badge(self, slide, s):
        self.add_rect(slide, s.logo.left, s.logo.top, s.logo.width, s.logo.height,
                     fill_color=self.theme.primary, corner_radius=0.05)
        self.add_text(slide, "Bangcle",
                      s.logo.left, s.logo.top + 0.12,
                      s.logo.width, 0.25,
                      font_size=12, bold=True,
                      color="#FFFFFF", align="center")


# ── 深色特有：节点关系图 ─────────────────────────────────────────────

class NodeGraphDarkRenderer(RendererBase):
    """节点关系图（深色）：4 个圆形节点 + 连线。"""
    page_type = "node-graph-dark"

    def __init__(self, theme=None):
        super().__init__(theme=theme or "dark")

    def render(self, prs: Presentation, data: dict[str, Any] | None = None):
        data = data or {}
        slide = self.add_blank_slide(prs)

        content_top = self.add_page_header_dark(slide,
            data.get("title", "技术架构"),
            data.get("subtitle", "TECHNOLOGY STACK"))

        s = self.theme.sizes

        # 中心节点
        center_x = s.slide.width / 2
        center_y = content_top + 2.2
        center_r = 0.7

        self.add_circle(slide, center_x - center_r, center_y - center_r, center_r * 2,
                       fill_color=self.theme.primary,
                       border_color="#FFFFFF", border_width=2)

        center_text = data.get("center_text", "核心平台")
        self.add_text(slide, center_text,
                      center_x - center_r, center_y - 0.3,
                      center_r * 2, 0.6,
                      font_size=16, bold=True,
                      color="#FFFFFF", align="center", anchor="middle")

        # 4 个外围节点（上下左右）
        nodes = data.get("nodes", [])
        if not nodes:
            nodes = [
                {"label": "数据层", "icon": "📊"},
                {"label": "服务层", "icon": "⚙️"},
                {"label": "应用层", "icon": "📱"},
                {"label": "安全层", "icon": "🔒"},
            ]

        positions = [
            (center_x, center_y - 2.0),      # 上
            (center_x + 2.5, center_y),      # 右
            (center_x, center_y + 2.0),      # 下
            (center_x - 2.5, center_y),      # 左
        ]

        node_r = 0.55

        for i, (node, pos) in enumerate(zip(nodes[:4], positions[:4])):
            nx, ny = pos
            # 连线
            self.add_line(slide, center_x, center_y, nx, ny,
                         color="#2874BB", width=2)

            # 节点圆
            self.add_circle(slide, nx - node_r, ny - node_r, node_r * 2,
                           fill_color="#0a2540",
                           border_color=self.theme.primary, border_width=2)

            # 标签
            label = node.get("label", "")
            self.add_text(slide, label,
                          nx - 1, ny - 0.2,
                          2, 0.4,
                          font_size=13, bold=True,
                          color="#FFFFFF", align="center")

        return slide

    def add_page_header_dark(self, slide, title, subtitle):
        """深色页面标题。"""
        s = self.theme.sizes
        self.add_left_accent_line(slide, s.margins.title_left, s.margins.title_top, 0.5, width=3)
        self.add_text(slide, title,
                      s.margins.title_left + 0.15, s.margins.title_top - 0.05,
                      10, 0.55,
                      font_size=28, bold=True, color="#FFFFFF")
        if subtitle:
            self.add_text(slide, subtitle.upper(),
                          s.margins.title_left + 0.15, s.margins.title_top + 0.55,
                          10, 0.25,
                          font_size=12, color=self.theme.caption_color)
        line_y = s.margins.title_top + 0.85
        self.add_line(slide,
                     s.margins.title_left, line_y,
                     s.margins.content_right, line_y,
                     color="#2874BB", width=0.75)
        return line_y + 0.15


# ── 深色特有：四卡片 ────────────────────────────────────────────────

class FourCardsDarkRenderer(RendererBase):
    """四卡片图文（深色）。"""
    page_type = "four-cards-dark"

    def __init__(self, theme=None):
        super().__init__(theme=theme or "dark")

    def render(self, prs: Presentation, data: dict[str, Any] | None = None):
        data = data or {}
        slide = self.add_blank_slide(prs)
        s = self.theme.sizes

        # 标题
        self.add_page_header_dark(slide, data)

        cards = data.get("cards", [])
        if not cards:
            cards = [
                {"number": "01", "title": "能力一", "body": "描述文本"},
                {"number": "02", "title": "能力二", "body": "描述文本"},
                {"number": "03", "title": "能力三", "body": "描述文本"},
                {"number": "04", "title": "能力四", "body": "描述文本"},
            ]

        content_top = 1.4
        card_w = 2.8
        card_h = 1.8
        gap = 0.3
        start_x = s.margins.content_left + 0.2

        for i, card in enumerate(cards[:4]):
            col = i % 4
            x = start_x + col * (card_w + gap)
            y = content_top

            self.add_rect(slide, x, y, card_w, card_h,
                         fill_color="#0a2540",
                         border_color=self.theme.primary,
                         border_width=1.5,
                         corner_radius=0.08)

            # 编号
            self.add_text(slide, str(card.get("number", f"0{i+1}")),
                          x + 0.2, y + 0.15,
                          1, 0.4,
                          font_size=24, bold=True,
                          color=self.theme.gold)

            # 标题
            self.add_text(slide, card.get("title", ""),
                          x + 0.2, y + 0.6,
                          card_w - 0.4, 0.35,
                          font_size=16, bold=True,
                          color="#FFFFFF")

            # 正文
            self.add_text(slide, card.get("body", ""),
                          x + 0.2, y + 1.0,
                          card_w - 0.4, 0.6,
                          font_size=11, color=self.theme.caption_color,
                          line_spacing=1.3)

        # 下方数据图占位
        chart_y = content_top + card_h + 0.3
        chart_h = 2.5
        self.add_rect(slide, start_x, chart_y, 11, chart_h,
                     fill_color="#0a2540",
                     border_color="#2874BB", border_width=1,
                     corner_radius=0.08)
        self.add_text(slide, "📊 数据展示区域",
                      start_x, chart_y + chart_h/2 - 0.2,
                      11, 0.4,
                      font_size=14, color="#5B9BD5", align="center")

        return slide

    def add_page_header_dark(self, slide, data):
        s = self.theme.sizes
        title = data.get("title", "核心能力")
        subtitle = data.get("subtitle", "CORE CAPABILITIES")
        self.add_left_accent_line(slide, s.margins.title_left, s.margins.title_top, 0.5, width=3)
        self.add_text(slide, title,
                      s.margins.title_left + 0.15, s.margins.title_top - 0.05,
                      10, 0.55, font_size=28, bold=True, color="#FFFFFF")
        if subtitle:
            self.add_text(slide, subtitle.upper(),
                          s.margins.title_left + 0.15, s.margins.title_top + 0.55,
                          10, 0.25, font_size=12, color=self.theme.caption_color)


# ── 深色特有：左图右列表 ─────────────────────────────────────────────

class ListImageDarkRenderer(RendererBase):
    """左图 + 右列表（深色）。"""
    page_type = "list-image-dark"

    def __init__(self, theme=None):
        super().__init__(theme=theme or "dark")

    def render(self, prs: Presentation, data: dict[str, Any] | None = None):
        data = data or {}
        slide = self.add_blank_slide(prs)
        s = self.theme.sizes

        # 标题
        self._add_header(slide, data)

        content_top = 1.4

        # 左侧图片占位
        img_x = s.margins.content_left
        img_y = content_top + 0.2
        img_w = 5.5
        img_h = 4.5
        img_path = data.get("image_path", "")
        if img_path:
            try:
                self.add_image(slide, img_path, img_x, img_y, img_w, img_h)
            except FileNotFoundError:
                self._img_ph(slide, img_x, img_y, img_w, img_h)
        else:
            self._img_ph(slide, img_x, img_y, img_w, img_h)

        # 右侧列表
        items = data.get("items", [])
        if not items:
            items = ["特性功能一", "特性功能二", "特性功能三", "特性功能四", "特性功能五", "特性功能六"]

        list_x = img_x + img_w + 0.5
        list_y = content_top + 0.3
        item_h = 0.55

        for i, item in enumerate(items[:8]):
            y = list_y + i * item_h
            # 金色菱形/圆点
            self.add_circle(slide, list_x, y + 0.12, 0.12,
                           fill_color=self.theme.gold)
            # 文字
            self.add_text(slide, str(item),
                          list_x + 0.3, y + 0.05,
                          5, 0.4,
                          font_size=14, color="#FFFFFF")

        return slide

    def _add_header(self, slide, data):
        s = self.theme.sizes
        title = data.get("title", "功能特性")
        subtitle = data.get("subtitle", "FEATURES")
        self.add_left_accent_line(slide, s.margins.title_left, s.margins.title_top, 0.5, width=3)
        self.add_text(slide, title,
                      s.margins.title_left + 0.15, s.margins.title_top - 0.05,
                      10, 0.55, font_size=28, bold=True, color="#FFFFFF")
        if subtitle:
            self.add_text(slide, subtitle.upper(),
                          s.margins.title_left + 0.15, s.margins.title_top + 0.55,
                          10, 0.25, font_size=12, color=self.theme.caption_color)

    def _img_ph(self, slide, x, y, w, h):
        self.add_rect(slide, x, y, w, h, fill_color="#0a2540",
                     border_color="#2874BB", corner_radius=0.1)
        self.add_text(slide, "📷 配图区域",
                      x, y + h/2 - 0.2, w, 0.4,
                      font_size=14, color="#5B9BD5", align="center")


# ── 深色特有：蜂巢布局 ───────────────────────────────────────────────

class HoneycombDarkRenderer(RendererBase):
    """蜂巢/六边形布局（深色）。"""
    page_type = "honeycomb-dark"

    def __init__(self, theme=None):
        super().__init__(theme=theme or "dark")

    def render(self, prs: Presentation, data: dict[str, Any] | None = None):
        data = data or {}
        slide = self.add_blank_slide(prs)
        s = self.theme.sizes

        self._add_header(slide, data)

        # 中心 + 周围6个蜂巢（简化：用圆代替六边形）
        center_x = s.slide.width / 2
        center_y = 3.8
        center_r = 0.8

        # 中心
        self.add_circle(slide, center_x - center_r, center_y - center_r, center_r * 2,
                       fill_color=self.theme.primary)
        center_title = data.get("center_title", "产品矩阵")
        self.add_text(slide, center_title,
                      center_x - center_r, center_y - 0.3,
                      center_r * 2, 0.6,
                      font_size=16, bold=True,
                      color="#FFFFFF", align="center", anchor="middle")

        # 6 个外围节点
        nodes = data.get("nodes", [])
        if not nodes:
            nodes = [
                {"label": "产品一", "icon": "①"},
                {"label": "产品二", "icon": "②"},
                {"label": "产品三", "icon": "③"},
                {"label": "产品四", "icon": "④"},
                {"label": "产品五", "icon": "⑤"},
                {"label": "产品六", "icon": "⑥"},
            ]

        orbit_r = 1.8
        node_r = 0.55

        for i, node in enumerate(nodes[:6]):
            angle = -math.pi / 2 + i * (math.pi / 3)
            nx = center_x + orbit_r * math.cos(angle)
            ny = center_y + orbit_r * math.sin(angle)

            # 连线
            self.add_line(slide, center_x, center_y, nx, ny,
                         color="#2874BB", width=1.5)

            # 节点
            self.add_circle(slide, nx - node_r, ny - node_r, node_r * 2,
                           fill_color="#0a2540",
                           border_color=self.theme.primary, border_width=2)

            # 标签
            label = node.get("label", f"模块{i+1}")
            self.add_text(slide, label,
                          nx - 1, ny - 0.15,
                          2, 0.3,
                          font_size=12, bold=True,
                          color="#FFFFFF", align="center")

        return slide

    def _add_header(self, slide, data):
        s = self.theme.sizes
        title = data.get("title", "产品生态")
        subtitle = data.get("subtitle", "ECOSYSTEM")
        self.add_left_accent_line(slide, s.margins.title_left, s.margins.title_top, 0.5, width=3)
        self.add_text(slide, title,
                      s.margins.title_left + 0.15, s.margins.title_top - 0.05,
                      10, 0.55, font_size=28, bold=True, color="#FFFFFF")
        if subtitle:
            self.add_text(slide, subtitle.upper(),
                          s.margins.title_left + 0.15, s.margins.title_top + 0.55,
                          10, 0.25, font_size=12, color=self.theme.caption_color)


# ── 深色特有：金字塔对比 ─────────────────────────────────────────────

class PyramidCompareDarkRenderer(RendererBase):
    """金字塔 + 对比卡片（深色）。"""
    page_type = "pyramid-compare-dark"

    def __init__(self, theme=None):
        super().__init__(theme=theme or "dark")

    def render(self, prs: Presentation, data: dict[str, Any] | None = None):
        data = data or {}
        slide = self.add_blank_slide(prs)
        s = self.theme.sizes

        self._add_header(slide, data)

        content_top = 1.4

        # 左侧金字塔（简化：用梯形/矩形堆叠）
        levels = data.get("pyramid_levels", [])
        if not levels:
            levels = ["战略层", "业务层", "技术层", "数据层"]

        pyr_center_x = 3.5
        pyr_bottom_y = content_top + 3.8
        level_h = 0.7
        base_w = 4.0
        top_w = 1.2

        for i, level in enumerate(reversed(levels[:4])):
            # 每层宽度从底到顶递减
            ratio = (i + 1) / len(levels)
            w = base_w - (base_w - top_w) * (1 - ratio) * 0
            # 更接近真实金字塔：线性递减
            w = top_w + (base_w - top_w) * (i / len(levels))
            x = pyr_center_x - w / 2
            y = pyr_bottom_y - (i + 1) * level_h

            colors = [self.theme.primary, "#387BBE", "#5B9BD5", "#8BC4F0"]
            color = colors[i % len(colors)]

            self.add_rect(slide, x, y, w, level_h - 0.05,
                         fill_color=color, corner_radius=0.03)

            self.add_text(slide, level,
                          x, y + 0.18,
                          w, 0.35,
                          font_size=14, bold=True,
                          color="#FFFFFF", align="center")

        # 右侧对比卡片
        card_x = 7.5
        card_y = content_top + 0.2
        card_w = 5.0
        card_h = 4.2

        self.add_rect(slide, card_x, card_y, card_w, card_h,
                     fill_color="#0a2540",
                     border_color=self.theme.primary,
                     border_width=1.5, corner_radius=0.08)

        compare_title = data.get("compare_title", "方案对比")
        self.add_text(slide, compare_title,
                      card_x + 0.3, card_y + 0.25,
                      card_w - 0.6, 0.4,
                      font_size=18, bold=True, color="#FFFFFF")

        self.add_line(slide,
                     card_x + 0.3, card_y + 0.75,
                     card_x + 1.2, card_y + 0.75,
                     color=self.theme.gold, width=2)

        compare_items = data.get("compare_items", [])
        if not compare_items:
            compare_items = [
                "传统方案：功能单一、扩展困难",
                "我们的方案：全栈覆盖、弹性扩展",
                "• 性能提升 300%",
                "• 成本降低 40%",
                "• 运维效率提升 200%",
            ]

        for i, item in enumerate(compare_items[:8]):
            self.add_text(slide, f"• {item}",
                          card_x + 0.3, card_y + 0.95 + i * 0.4,
                          card_w - 0.6, 0.35,
                          font_size=12, color=self.theme.caption_color)

        return slide

    def _add_header(self, slide, data):
        s = self.theme.sizes
        title = data.get("title", "架构分层")
        subtitle = data.get("subtitle", "ARCHITECTURE")
        self.add_left_accent_line(slide, s.margins.title_left, s.margins.title_top, 0.5, width=3)
        self.add_text(slide, title,
                      s.margins.title_left + 0.15, s.margins.title_top - 0.05,
                      10, 0.55, font_size=28, bold=True, color="#FFFFFF")
        if subtitle:
            self.add_text(slide, subtitle.upper(),
                          s.margins.title_left + 0.15, s.margins.title_top + 0.55,
                          10, 0.25, font_size=12, color=self.theme.caption_color)


# ── 深色结束页 ──────────────────────────────────────────────────────

class ClosingDarkRenderer(RendererBase):
    """深色结束页。"""
    page_type = "closing-dark"

    def __init__(self, theme=None):
        super().__init__(theme=theme or "dark")

    def render(self, prs: Presentation, data: dict[str, Any] | None = None):
        data = data or {}
        slide = self.add_blank_slide(prs)
        s = self.theme.sizes

        # 装饰圆
        self.add_circle(slide, 10.5, -2.0, 6,
                       fill_color=None, border_color=self.theme.primary, border_width=1)
        self.add_circle(slide, -1.5, 5.5, 4,
                       fill_color=None, border_color="#1a3a5c", border_width=1)

        # 主标题
        main_text = data.get("main_text", "谢谢观看")
        self.add_text(slide, main_text,
                      s.margins.title_left, 2.5,
                      10, 1.2,
                      font_size=56, bold=True, color="#FFFFFF")

        # 英文
        subtitle = data.get("subtitle", "THANK YOU")
        self.add_text(slide, subtitle,
                      s.margins.title_left, 3.7,
                      10, 0.5,
                      font_size=24, color=self.theme.caption_color)

        # 金色分割线
        self.add_line(slide,
                     s.margins.title_left, 4.3,
                     s.margins.title_left + 3, 4.3,
                     color=self.theme.gold, width=2)

        # 联系方式
        contact = data.get("contact", "")
        if contact:
            self.add_text(slide, contact,
                          s.margins.title_left, 4.5,
                          6, 0.4,
                          font_size=14, color="#FFFFFF")

        # Slogan
        slogan = data.get("slogan", "稳如泰山·值得托付")
        if slogan:
            self.add_text(slide, slogan,
                          s.margins.title_left, 5.0,
                          6, 0.4,
                          font_size=14, color=self.theme.gold)

        # 底部装饰条
        self.add_rect(slide, 0, s.slide.height - 0.06, s.slide.width, 0.06,
                     fill_color=self.theme.primary)

        return slide

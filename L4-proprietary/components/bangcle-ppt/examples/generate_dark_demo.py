#!/usr/bin/env python3
"""
示例 2: 一键生成完整的深色主题演示 PPT。

用法:
    python examples/generate_dark_demo.py [output_path]

输出:
    output/深色演示-完整版.pptx (10+ 页)
"""

from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PKG_ROOT = os.path.dirname(_HERE)
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from bangcle_ppt.engine import TemplateEngine
from bangcle_ppt.renderers import REGISTRY


def main():
    output_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(_HERE, "output", "深色演示-完整版.pptx")

    templates_dir = os.path.join(_PKG_ROOT, "bangcle_ppt", "templates")
    engine = TemplateEngine(templates_dir=templates_dir, theme="dark")
    engine.register_renderers(REGISTRY)

    slides = [
        ("cover-dark", {
            "title": "新品发布会",
            "subtitle": "PRODUCT LAUNCH 2025",
            "presenter": "梆梆安全",
            "date": "2025.01",
            "slogan": "稳如泰山·值得托付",
        }),
        ("toc-dark", {
            "items": [
                {"number": "01", "title": "产品概览", "subtitle": "OVERVIEW"},
                {"number": "02", "title": "核心功能", "subtitle": "FEATURES"},
                {"number": "03", "title": "技术架构", "subtitle": "ARCHITECTURE"},
                {"number": "04", "title": "方案优势", "subtitle": "ADVANTAGES"},
            ],
        }),
        ("section-dark", {
            "title": "产品概览",
            "subtitle": "新一代移动安全平台",
            "part_label": "PART ONE",
            "chapter_number": "01",
        }),
        ("four-cards-dark", {
            "title": "四大核心功能",
            "subtitle": "FOUR CORE FEATURES",
            "cards": [
                {"number": "01", "title": "智能检测", "body": "AI驱动的深度安全检测"},
                {"number": "02", "title": "硬核加固", "body": "全方位应用安全保护"},
                {"number": "03", "title": "实时监测", "body": "7×24运行态安全监控"},
                {"number": "04", "title": "快速响应", "body": "分钟级安全事件处置"},
            ],
        }),
        ("list-image-dark", {
            "title": "产品特性",
            "subtitle": "KEY FEATURES",
            "items": [
                "静态应用安全测试（SAST）",
                "动态应用安全测试（DAST）",
                "移动应用安全加固",
                "运行时应用自保护（RASP）",
                "威胁情报实时推送",
                "安全态势可视化分析",
            ],
        }),
        ("section-dark", {
            "title": "技术架构",
            "subtitle": "新一代智能安全引擎",
            "part_label": "PART TWO",
            "chapter_number": "02",
        }),
        ("node-graph-dark", {
            "title": "技术架构",
            "subtitle": "TECHNOLOGY ARCHITECTURE",
            "center_text": "AI 安全引擎",
            "nodes": [
                {"label": "数据层", "icon": "📊"},
                {"label": "算法层", "icon": "🧠"},
                {"label": "服务层", "icon": "⚙️"},
                {"label": "应用层", "icon": "📱"},
            ],
        }),
        ("honeycomb-dark", {
            "title": "产品矩阵",
            "subtitle": "PRODUCT PORTFOLIO",
            "center_title": "安全大脑",
            "nodes": [
                {"label": "App检测", "icon": ""},
                {"label": "App加固", "icon": ""},
                {"label": "小程序", "icon": ""},
                {"label": "SDK安全", "icon": ""},
                {"label": "威胁情报", "icon": ""},
                {"label": "合规服务", "icon": ""},
            ],
        }),
        ("pyramid-compare-dark", {
            "title": "方案对比",
            "subtitle": "SOLUTION COMPARISON",
            "pyramid_levels": ["决策层", "应用层", "能力层", "数据层"],
            "compare_title": "为什么选择我们",
            "compare_items": [
                "传统方案：单点工具、被动防御",
                "我们的方案：平台化、主动防御",
                "• 检测率提升 300%",
                "• 误报率降低 80%",
                "• 运营效率提升 200%",
                "• TCO 降低 50%",
            ],
        }),
        ("phase-timeline-dark", {
            "title": "发展路线图",
            "subtitle": "ROADMAP 2025",
            "items": [
                {"phase": "Q1", "title": "基础版本", "body": "核心功能MVP发布"},
                {"phase": "Q2", "title": "AI增强", "body": "智能检测全面升级"},
                {"phase": "Q3", "title": "平台化", "body": "开放平台与生态"},
                {"phase": "Q4", "title": "国际化", "body": "海外市场拓展"},
                {"phase": "Q1", "title": "新领域", "body": "AI安全新方向"},
                {"phase": "Q2", "title": "领导者", "body": "行业领导者"},
            ],
        }),
        ("closing-dark", {
            "main_text": "谢谢观看",
            "subtitle": "THANK YOU",
            "contact": "www.bangcle.com | 400-123-4567",
            "slogan": "稳如泰山·值得托付",
        }),
    ]

    result = engine.render_presentation(slides, output_path=output_path)
    print(f"✅ 深色演示 PPT 已生成: {result}")
    print(f"   共 {len(slides)} 页")

    size_kb = os.path.getsize(result) / 1024
    print(f"   文件大小: {size_kb:.1f} KB")


if __name__ == "__main__":
    main()

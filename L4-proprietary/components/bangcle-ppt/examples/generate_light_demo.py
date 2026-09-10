#!/usr/bin/env python3
"""
示例 1: 一键生成完整的浅色主题演示 PPT。

用法:
    python examples/generate_light_demo.py [output_path]

输出:
    output/浅色演示-完整版.pptx (15+ 页)
"""

from __future__ import annotations

import os
import sys

# 确保包可导入
_HERE = os.path.dirname(os.path.abspath(__file__))
_PKG_ROOT = os.path.dirname(_HERE)
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from bangcle_ppt.engine import TemplateEngine
from bangcle_ppt.renderers import REGISTRY


def main():
    output_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(_HERE, "output", "浅色演示-完整版.pptx")

    # 初始化引擎
    templates_dir = os.path.join(_PKG_ROOT, "bangcle_ppt", "templates")
    engine = TemplateEngine(templates_dir=templates_dir, theme="light")
    engine.register_renderers(REGISTRY)

    # 定义幻灯片序列：(page_type, custom_data)
    # 使用模板默认数据，也可传入自定义数据覆盖
    slides = [
        # 封面
        ("cover-light", {
            "title": "2025年度安全汇报",
            "subtitle": "ANNUAL SECURITY REPORT",
            "presenter": "张安全",
            "company": "梆梆安全",
            "date": "2025年1月",
        }),
        # 目录
        ("toc-light", {
            "items": [
                {"number": "01", "title": "项目概述", "subtitle": "OVERVIEW"},
                {"number": "02", "title": "核心能力", "subtitle": "CAPABILITIES"},
                {"number": "03", "title": "技术方案", "subtitle": "SOLUTION"},
                {"number": "04", "title": "成果展示", "subtitle": "ACHIEVEMENTS"},
            ],
        }),
        # 第一章
        ("section-light", {
            "title": "项目概述",
            "subtitle": "BACKGROUND & OVERVIEW",
            "part_label": "PART ONE",
            "chapter_number": "01",
        }),
        ("content-two-col-light", {
            "title": "项目背景",
            "subtitle": "PROJECT BACKGROUND",
            "highlights": [
                {"title": "业务挑战", "description": "移动应用威胁持续增长"},
                {"title": "合规要求", "description": "等保2.0、数据安全法"},
                {"title": "安全缺口", "description": "现有防护手段不足"},
                {"title": "效率瓶颈", "description": "人工检测效率低下"},
            ],
            "card_title": "解决方案",
            "card_body": "基于梆梆安全多年技术积累，\n构建一站式移动安全防护平台。\n\n• 检测+加固+监测全链路\n• AI智能威胁分析\n• 自动化安全运营",
        }),
        ("content-three-cards-light", {
            "title": "三大核心能力",
            "subtitle": "THREE CORE CAPABILITIES",
            "cards": [
                {"number": "01", "title": "安全检测", "body": "静态+动态双引擎，全面发现应用安全漏洞与风险。支持Android/iOS双平台。"},
                {"number": "02", "title": "应用加固", "body": "DEX加密、资源混淆、防调试、防篡改，全方位保护应用安全。"},
                {"number": "03", "title": "监测预警", "body": "7×24小时实时监测，威胁秒级响应，全面掌控应用安全态势。"},
            ],
        }),
        # 第二章
        ("section-light", {
            "title": "技术方案",
            "subtitle": "TECHNICAL SOLUTION",
            "part_label": "PART TWO",
            "chapter_number": "02",
        }),
        ("timeline-three-cards-light", {
            "title": "技术演进路线",
            "subtitle": "TECH EVOLUTION",
            "items": [
                {"step": "01", "title": "基础建设", "body": "2018-2019：核心引擎研发，完成基础检测能力构建。"},
                {"step": "02", "title": "能力完善", "body": "2020-2021：完善产品矩阵，支持多平台多场景。"},
                {"step": "03", "title": "智能升级", "body": "2022-2023：AI技术深度融合，检测准确率大幅提升。"},
            ],
        }),
        ("radial-structure-light", {
            "title": "系统架构",
            "subtitle": "SYSTEM ARCHITECTURE",
            "center_title": "安全大脑",
            "center_subtitle": "SECURITY BRAIN",
            "nodes": [
                {"label": "数据采集", "icon": "①"},
                {"label": "智能分析", "icon": "②"},
                {"label": "威胁检测", "icon": "③"},
                {"label": "自动响应", "icon": "④"},
                {"label": "可视化", "icon": "⑤"},
                {"label": "开放API", "icon": "⑥"},
            ],
        }),
        ("flow-light", {
            "title": "工作流程",
            "subtitle": "WORKFLOW",
            "steps": [
                {"step": "01", "title": "应用上传", "body": "提交应用进行检测"},
                {"step": "02", "title": "安全检测", "body": "多引擎深度扫描"},
                {"step": "03", "title": "报告生成", "body": "输出详细检测报告"},
                {"step": "04", "title": "一键加固", "body": "自动应用安全加固"},
                {"step": "05", "title": "上线监测", "body": "运行态持续监控"},
            ],
        }),
        # 第三章
        ("section-light", {
            "title": "成果展示",
            "subtitle": "ACHIEVEMENTS & DATA",
            "part_label": "PART THREE",
            "chapter_number": "03",
        }),
        ("data-chart-light", {
            "title": "年度数据概览",
            "subtitle": "ANNUAL DATA REVIEW",
            "kpis": [
                {"value": "99.9%", "label": "检测准确率", "suffix": ""},
                {"value": "500", "label": "服务企业", "suffix": "+"},
                {"value": "10亿", "label": "累计检测", "suffix": "次"},
                {"value": "5min", "label": "响应时间", "suffix": ""},
            ],
            "chart_title": "2024年安全事件趋势",
            "right_title": "核心发现",
            "right_body": "本年度安全防护成效显著：\n\n• 攻击拦截量同比+45%\n• 客户满意度达98%\n• 零重大安全事故\n• 威胁响应时间-60%",
        }),
        ("table-light", {
            "title": "关键指标对比",
            "subtitle": "KEY METRICS COMPARISON",
            "table_data": [
                ["指标", "2023年", "2024年", "同比变化"],
                ["检测准确率", "95%", "99.9%", "+4.9%"],
                ["响应时间", "30min", "5min", "-83%"],
                ["服务客户数", "300家", "500家", "+67%"],
                ["误报率", "5%", "0.5%", "-90%"],
                ["系统可用性", "99.5%", "99.99%", "+0.49%"],
            ],
        }),
        ("timeline-vertical-light", {
            "title": "年度里程碑",
            "subtitle": "YEAR MILESTONES",
            "items": [
                {"date": "2024.Q1", "title": "产品升级", "body": "V3.0版本发布，AI引擎升级。"},
                {"date": "2024.Q2", "title": "客户突破", "body": "服务企业客户突破400家。"},
                {"date": "2024.Q3", "title": "技术获奖", "body": "荣获网络安全创新奖。"},
                {"date": "2024.Q4", "title": "生态完善", "body": "合作伙伴生态初步建成。"},
            ],
        }),
        # 第四章
        ("section-light", {
            "title": "团队介绍",
            "subtitle": "OUR TEAM",
            "part_label": "PART FOUR",
            "chapter_number": "04",
        }),
        ("team-cards-light", {
            "title": "核心团队",
            "subtitle": "CORE TEAM",
            "members": [
                {"name": "张安全", "role": "CEO / 创始人", "description": "15年信息安全经验\n前360安全总监"},
                {"name": "李技术", "role": "CTO", "description": "12年安全技术经验\n前阿里P8架构师"},
                {"name": "王产品", "role": "产品总监", "description": "10年ToB产品经验\n资深安全产品专家"},
                {"name": "赵运营", "role": "运营总监", "description": "8年SaaS运营经验\n增长黑客专家"},
            ],
        }),
        # 结束
        ("closing-light", {
            "main_text": "谢谢观看",
            "subtitle": "THANK YOU",
            "contact": "www.bangcle.com | 400-123-4567",
            "slogan": "稳如泰山·值得托付",
        }),
    ]

    # 生成 PPT
    result = engine.render_presentation(slides, output_path=output_path)
    print(f"✅ 浅色演示 PPT 已生成: {result}")
    print(f"   共 {len(slides)} 页")

    # 统计文件大小
    size_kb = os.path.getsize(result) / 1024
    print(f"   文件大小: {size_kb:.1f} KB")


if __name__ == "__main__":
    main()

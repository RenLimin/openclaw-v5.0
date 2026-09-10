#!/usr/bin/env python3
"""
Bangcle PPT CLI — pptgen
L4 专有业务层 — PPT 模板生成命令行工具

用法:
  python -m bangcle_ppt.cli.pptgen render <dsl_file> [--output out.pptx] [--theme light|dark]
  python -m bangcle_ppt.cli.pptgen list-templates [--theme light|dark]
  python -m bangcle_ppt.cli.pptgen info <template_name>
  python -m bangcle_ppt.cli.pptgen demo [--theme light|dark] [--output out.pptx]
  python -m bangcle_ppt.cli.pptgen validate <dsl_file>
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import yaml
from pathlib import Path
from typing import Any

# 确保包可导入
_HERE = os.path.dirname(os.path.abspath(__file__))
_PKG_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from bangcle_ppt import TemplateEngine, REGISTRY
from bangcle_ppt.dsl.schema import PresentationSpec, PAGE_LAYOUT_MAP, SlideTemplate


# ── 工具函数 ────────────────────────────────────────────────────────

def _get_engine(theme: str = "light") -> TemplateEngine:
    """创建并注册全部 renderer 的引擎实例。"""
    templates_dir = os.path.join(_PKG_ROOT, "bangcle_ppt", "templates")
    engine = TemplateEngine(templates_dir=templates_dir, theme=theme)
    engine.register_renderers(REGISTRY)
    return engine


def _load_spec(path: str) -> PresentationSpec:
    """加载 YAML DSL 文件并构造成 PresentationSpec。"""
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, dict):
        raise ValueError(f"DSL 文件格式错误：顶层必须是 dict，实际是 {type(raw).__name__}")
    return PresentationSpec(**raw)


# ── render ──────────────────────────────────────────────────────────

def cmd_render(args: argparse.Namespace) -> int:
    """渲染 DSL 为 PPT。"""
    if not os.path.exists(args.dsl_file):
        print(f"❌ DSL 文件不存在: {args.dsl_file}")
        return 1

    try:
        spec = _load_spec(args.dsl_file)
    except Exception as e:
        print(f"❌ DSL 解析失败: {e}")
        return 1

    theme = args.theme or spec.theme
    output = args.output or "output.pptx"

    engine = _get_engine(theme=theme)

    try:
        out_path = engine.render_from_spec(spec, output)
    except Exception as e:
        print(f"❌ 渲染失败: {e}")
        return 1

    size_kb = os.path.getsize(out_path) / 1024
    print(f"✅ PPT 生成成功")
    print(f"   输出文件: {out_path}")
    print(f"   幻灯片数: {len(spec.slides)}")
    print(f"   主题:     {theme}")
    print(f"   文件大小: {size_kb:.1f} KB")
    return 0


# ── list-templates ──────────────────────────────────────────────────

def cmd_list_templates(args: argparse.Namespace) -> int:
    """列出所有内置模板。"""
    theme = args.theme or "light"
    engine = _get_engine(theme=theme)

    try:
        templates = sorted(engine.list_templates(theme=theme))
    except Exception as e:
        print(f"❌ 读取模板列表失败: {e}")
        return 1

    if args.json:
        print(json.dumps({"theme": theme, "templates": templates}, ensure_ascii=False, indent=2))
        return 0

    print(f"\n📦 内置模板列表（{theme} 主题, 共 {len(templates)} 个）")
    print("=" * 60)
    for i, name in enumerate(templates, 1):
        # 尝试读取 meta 里的描述
        try:
            tpl = engine.load_template(name, theme=theme)
            desc = tpl.meta.description or tpl.meta.name
            print(f"  {i:>2}. {name:<35} {desc}")
        except Exception:
            print(f"  {i:>2}. {name}")
    print("=" * 60)
    return 0


# ── info ────────────────────────────────────────────────────────────

def cmd_info(args: argparse.Namespace) -> int:
    """查看模板 schema 详情。"""
    template_name = args.template_name

    # 推断主题
    theme = "dark" if template_name.endswith("-dark") else "light"
    engine = _get_engine(theme=theme)

    try:
        tpl = engine.load_template(template_name, theme=theme)
    except FileNotFoundError:
        # 可能是跨主题的模板名，尝试两个主题
        for t in ["light", "dark"]:
            try:
                tpl = engine.load_template(template_name, theme=t)
                theme = t
                break
            except FileNotFoundError:
                continue
        else:
            print(f"❌ 模板不存在: {template_name}")
            print(f"   可用模板: {sorted(REGISTRY.keys())}")
            return 1
    except Exception as e:
        print(f"❌ 加载模板失败: {e}")
        return 1

    layout_cls = PAGE_LAYOUT_MAP.get(template_name)
    layout_fields = []
    if layout_cls:
        for fname, field in layout_cls.model_fields.items():
            ftype = field.annotation.__name__ if hasattr(field.annotation, '__name__') else str(field.annotation)
            default = field.default if field.default is not None else "—"
            desc = field.description or ""
            layout_fields.append((fname, ftype, str(default), desc))

    if args.json:
        result = {
            "name": tpl.meta.name,
            "page_type": tpl.meta.page_type,
            "theme": theme,
            "description": tpl.meta.description,
            "version": tpl.meta.version,
            "category": tpl.meta.category,
            "layout_fields": [
                {"name": n, "type": t, "default": d, "description": desc}
                for n, t, d, desc in layout_fields
            ],
            "sample_data": tpl.data,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    print(f"\n📄 模板详情: {template_name}")
    print("=" * 60)
    print(f"  名称:        {tpl.meta.name}")
    print(f"  页面类型:    {tpl.meta.page_type}")
    print(f"  主题:        {theme}")
    print(f"  描述:        {tpl.meta.description or '—'}")
    print(f"  版本:        {tpl.meta.version}")
    print(f"  分类:        {tpl.meta.category}")
    print(f"\n  Layout 字段 ({len(layout_fields)} 个):")
    print(f"  {'字段名':<20} {'类型':<15} {'默认值':<10} 描述")
    print(f"  {'-'*20} {'-'*15} {'-'*10} {'-'*20}")
    for name, ftype, default, desc in layout_fields:
        default_display = default[:10] if len(default) > 10 else default
        print(f"  {name:<20} {ftype:<15} {default_display:<10} {desc}")

    if tpl.data:
        print(f"\n  示例数据 (data):")
        sample_str = yaml.dump(tpl.data, allow_unicode=True, default_flow_style=False)
        for line in sample_str.strip().split("\n"):
            print(f"    {line}")
    print("=" * 60)
    return 0


# ── demo ────────────────────────────────────────────────────────────

def cmd_demo(args: argparse.Namespace) -> int:
    """生成全模板示例 PPT。"""
    theme = args.theme or "light"
    output = args.output or f"bangcle-ppt-demo-{theme}.pptx"

    engine = _get_engine(theme=theme)
    templates = sorted(engine.list_templates(theme=theme))

    if not templates:
        print(f"❌ {theme} 主题下没有可用模板")
        return 1

    slides: list[tuple[str, dict[str, Any]]] = []
    skipped = []

    import os as _os
    for tpl_name in templates:
        # 先检查 renderer 是否注册（有些模板 YAML 可能没有对应 renderer）
        if tpl_name not in engine._renderers:
            skipped.append((tpl_name, 'no renderer registered'))
            continue
        try:
            tpl = engine.load_template(tpl_name, theme=theme)
            # 用模板自带的示例 data
            slides.append((tpl_name, tpl.data))
        except Exception as e:
            skipped.append((tpl_name, str(e)))

    if not slides:
        print("❌ 没有可渲染的模板")
        return 1

    try:
        out_path = engine.render_presentation(slides, output, theme=theme)
    except Exception as e:
        print(f"❌ 渲染失败: {e}")
        return 1

    size_kb = os.path.getsize(out_path) / 1024
    print(f"✅ 全模板示例 PPT 生成成功")
    print(f"   输出文件: {out_path}")
    print(f"   主题:     {theme}")
    print(f"   渲染:     {len(slides)} 个模板")
    if skipped:
        print(f"   跳过:     {len(skipped)} 个 ({', '.join(s[0] for s in skipped)})")
    print(f"   文件大小: {size_kb:.1f} KB")
    return 0


# ── validate ────────────────────────────────────────────────────────

def cmd_validate(args: argparse.Namespace) -> int:
    """校验 DSL 合法性。"""
    if not os.path.exists(args.dsl_file):
        print(f"❌ DSL 文件不存在: {args.dsl_file}")
        return 1

    try:
        spec = _load_spec(args.dsl_file)
    except Exception as e:
        print(f"❌ DSL 校验失败: {e}")
        return 1

    errors: list[str] = []
    for i, slide in enumerate(spec.slides, 1):
        try:
            slide.validate_layout_against_type()
        except Exception as e:
            errors.append(f"  第 {i} 页 ({slide.meta.page_type}): {e}")

    if args.json:
        result = {
            "valid": len(errors) == 0,
            "title": spec.title,
            "theme": spec.theme,
            "slide_count": len(spec.slides),
            "errors": errors,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if not errors else 1

    if errors:
        print(f"❌ DSL 校验未通过（{len(errors)} 个错误）")
        for e in errors:
            print(e)
        return 1

    print(f"✅ DSL 校验通过")
    print(f"   标题:    {spec.title}")
    print(f"   主题:    {spec.theme}")
    print(f"   幻灯片:  {len(spec.slides)} 页")
    for i, slide in enumerate(spec.slides, 1):
        print(f"     {i:>2}. {slide.meta.page_type:<30} {slide.meta.name}")
    return 0


# ── Main ────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pptgen",
        description="Bangcle PPT 模板生成 CLI (CPT-012)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  pptgen render spec.yaml --output report.pptx --theme dark
  pptgen list-templates
  pptgen info cover-light
  pptgen demo --theme light
  pptgen validate spec.yaml
        """,
    )
    sub = parser.add_subparsers(dest="command", help="子命令")

    # render
    p = sub.add_parser("render", help="渲染 DSL 为 PPT")
    p.add_argument("dsl_file", help="DSL YAML 文件路径")
    p.add_argument("--output", "-o", help="输出 PPT 路径 (默认: output.pptx)")
    p.add_argument("--theme", choices=["light", "dark"], help="覆盖主题")

    # list-templates
    p = sub.add_parser("list-templates", help="列出所有内置模板")
    p.add_argument("--theme", choices=["light", "dark"], help="指定主题 (默认: light)")
    p.add_argument("--json", action="store_true", help="JSON 格式输出")

    # info
    p = sub.add_parser("info", help="查看模板 schema 详情")
    p.add_argument("template_name", help="模板名称 (如 cover-light)")
    p.add_argument("--json", action="store_true", help="JSON 格式输出")

    # demo
    p = sub.add_parser("demo", help="生成全模板示例 PPT")
    p.add_argument("--theme", choices=["light", "dark"], default="light", help="主题 (默认: light)")
    p.add_argument("--output", "-o", help="输出 PPT 路径")

    # validate
    p = sub.add_parser("validate", help="校验 DSL 合法性")
    p.add_argument("dsl_file", help="DSL YAML 文件路径")
    p.add_argument("--json", action="store_true", help="JSON 格式输出")

    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    handlers = {
        "render": cmd_render,
        "list-templates": cmd_list_templates,
        "info": cmd_info,
        "demo": cmd_demo,
        "validate": cmd_validate,
    }

    try:
        return handlers[args.command](args)
    except KeyboardInterrupt:
        print("\n⏹ 已中断")
        return 130


if __name__ == "__main__":
    sys.exit(main())

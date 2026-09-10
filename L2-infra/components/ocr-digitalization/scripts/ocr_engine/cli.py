#!/usr/bin/env python3
"""
OCR 文档数字化 - CLI 入口

用法:
    python cli.py <input> [output] [options]

示例:
    # 图片 OCR
    python cli.py scan.jpg output.md

    # PDF 数字化
    python cli.py document.pdf output.md --dpi 300

    # 批量处理目录
    python cli.py ./scans/ ./output/ --batch

    # 输出生成 JSON
    python cli.py scan.jpg --json result.json
"""
from __future__ import annotations

import os
import sys
import argparse
from pathlib import Path
from typing import List


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="OCR 文档数字化组件 (OCR-001)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python cli.py scan.jpg output.md                    # 单图 OCR
  python cli.py document.pdf output.md --dpi 300      # PDF 数字化
  python cli.py ./imgs/ --batch -o ./out/             # 批量处理
  python cli.py scan.jpg --json result.json           # 输出 JSON
  python cli.py scan.jpg --engine tesseract           # 指定后端
  python cli.py scan.jpg --preset strong              # 预处理预设
        """,
    )

    parser.add_argument(
        "input",
        nargs="?",
        help="输入文件路径（图片/PDF）或目录（批量模式）",
    )
    parser.add_argument(
        "output",
        nargs="?",
        default=None,
        help="输出文件路径（默认：输入同目录，加 _ocr 后缀）",
    )
    parser.add_argument(
        "-o", "--output",
        dest="output_opt",
        default=None,
        help="输出文件路径（同 output 参数）",
    )

    # 引擎选项
    parser.add_argument(
        "-e", "--engine",
        default="auto",
        help="OCR 后端引擎（默认 auto）",
    )
    parser.add_argument(
        "-l", "--lang",
        default="chi_sim+eng",
        help="语言代码（默认 chi_sim+eng）",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=300,
        help="PDF 渲染 DPI（默认 300）",
    )
    parser.add_argument(
        "--no-multi-version",
        action="store_true",
        help="禁用多版本预处理投票（更快但可能准确率稍低）",
    )

    # 预处理选项
    parser.add_argument(
        "--no-preprocess",
        action="store_true",
        help="禁用图像预处理",
    )
    parser.add_argument(
        "--preset",
        default="default",
        choices=["default", "light", "strong", "photo", "fax"],
        help="预处理预设（默认 default）",
    )

    # 后处理选项
    parser.add_argument(
        "--correct",
        default=None,
        choices=["general", "contract", "none"],
        help="纠错领域（默认 general）",
    )
    parser.add_argument(
        "--no-quality",
        action="store_true",
        help="禁用质量评分分析",
    )

    # 输出选项
    parser.add_argument(
        "-f", "--format",
        default="markdown",
        choices=["text", "markdown", "json"],
        help="输出格式（默认 markdown）",
    )
    parser.add_argument(
        "--json",
        default=None,
        help="额外输出 JSON 结果到指定文件",
    )
    parser.add_argument(
        "--text",
        default=None,
        help="额外输出纯文本到指定文件",
    )

    # 批量模式
    parser.add_argument(
        "--batch",
        action="store_true",
        help="批量处理模式（输入为目录）",
    )

    # 其他
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="静默模式，不输出进度信息",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="详细输出",
    )
    parser.add_argument(
        "--list-backends",
        action="store_true",
        help="列出所有可用后端并退出",
    )

    args = parser.parse_args(argv)

    # 列出后端
    if args.list_backends:
        return _list_backends()

    # 确定输出路径
    output_path = args.output or args.output_opt

    # 导入引擎（延迟导入，--help 时不加载重依赖）
    from .engine import OCREngine
    from .preprocess import PreprocessConfig
    from .postprocess import PostprocessConfig

    # 构建配置
    pp_config = None if args.no_preprocess else PreprocessConfig.preset(args.preset)
    post_config = PostprocessConfig()
    if args.correct == "none":
        post_config.correct_domain = ""
    elif args.correct:
        post_config.correct_domain = args.correct

    # 初始化引擎
    if not args.quiet:
        print(f"🔍 OCR 文档数字化")
        print(f"   输入: {args.input}")
        print(f"   引擎: {args.engine} | 语言: {args.lang}")
        print(f"   正在初始化引擎...")

    engine = OCREngine(
        backend=args.engine,
        lang=args.lang,
        preprocess_config=pp_config,
        postprocess_config=post_config,
        multi_version=not args.no_multi_version,
        quality_analysis=not args.no_quality,
    )
    engine.load()

    if not args.quiet:
        print(f"   可用后端: {', '.join(engine.available_backends)}")

    # 批量模式
    if args.batch:
        return _process_batch(engine, args, output_path)

    # 单文件模式
    return _process_single(engine, args, output_path)


def _list_backends() -> int:
    """列出所有可用后端"""
    from .backends import list_available_backends, discover_backends

    registered = list_available_backends()
    print(f"已注册的后端: {', '.join(registered) if registered else '(无)'}")

    try:
        available = discover_backends()
        print(f"系统中可用的后端: {', '.join(b.name for b in available) if available else '(无)'}")
        for b in available:
            print(f"  - {b.name} (priority={b.priority})")
    except Exception as e:
        print(f"探测失败: {e}")

    return 0


def _process_single(engine, args, output_path: str | None) -> int:
    """处理单个文件"""
    from .engine import OCREngine

    input_path = args.input

    if not input_path:
        print(f"❌ 错误: 请指定输入文件路径", file=sys.stderr)
        return 1

    if not os.path.exists(input_path):
        print(f"❌ 错误: 输入文件不存在: {input_path}", file=sys.stderr)
        return 1

    # 识别
    if not args.quiet:
        print(f"   正在识别...")

    try:
        result = engine.recognize_document(
        input_path,
        dpi=args.dpi,
        preprocess=not args.no_preprocess,
    )

    except ValueError as e:
        print(f"❌ 错误: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"❌ 识别失败: {e}", file=sys.stderr)
        return 1

    # 确定输出路径
    if not output_path:
        base = Path(input_path).stem
        ext_map = {"markdown": ".md", "text": ".txt", "json": ".json"}
        output_path = str(Path(input_path).with_name(f"{base}_ocr{ext_map[args.format]}"))

    # 写主输出
    os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
    if args.format == "text":
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(result.to_text())
    elif args.format == "json":
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(result.to_json())
    else:  # markdown
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(result.to_markdown())

    # 额外输出
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            f.write(result.to_json())
    if args.text:
        with open(args.text, "w", encoding="utf-8") as f:
            f.write(result.to_text())

    # 输出摘要
    if not args.quiet:
        quality = result.quality_score
        print(f"\n✅ 完成！")
        print(f"   页数: {result.total_pages}")
        print(f"   行数: {result.total_lines}")
        print(f"   字符数: {result.total_chars}")
        print(f"   置信度: {result.confidence:.2f}")
        print(f"   质量评级: {quality.grade} ({quality.overall:.1f}/100)")
        print(f"   输出: {output_path}")

    if args.verbose:
        print(f"\n📊 质量详情:")
        q = result.quality_score
        print(f"   置信度得分: {q.confidence:.1f}")
        print(f"   清晰度得分: {q.clarity:.1f}")
        print(f"   文本密度得分: {q.text_density:.1f}")
        print(f"   布局完整性得分: {q.layout_completeness:.1f}")

    return 0


def _process_batch(engine, args, output_path: str | None) -> int:
    """批量处理目录"""
    from .document import list_input_files
    from .engine import OCREngine

    input_dir = args.input

    if not os.path.isdir(input_dir):
        print(f"❌ 错误: 批量模式下输入必须是目录: {input_dir}", file=sys.stderr)
        return 1

    files = list_input_files(input_dir)
    if not files:
        print(f"❌ 错误: 目录中没有找到支持的文件: {input_dir}", file=sys.stderr)
        return 1

    output_dir = output_path or os.path.join(input_dir, "ocr_output")
    os.makedirs(output_dir, exist_ok=True)

    if not args.quiet:
        print(f"   批量模式: 找到 {len(files)} 个文件")
        print(f"   输出目录: {output_dir}")

    success = 0
    failed = 0

    for i, filepath in enumerate(files, 1):
        rel_path = os.path.relpath(filepath, input_dir)
        if not args.quiet:
            print(f"\n[{i}/{len(files)}] 处理: {rel_path}")

        try:
            result = engine.recognize_document(
                filepath,
                dpi=args.dpi,
                preprocess=not args.no_preprocess,
            )

            # 生成输出文件名
            base_name = Path(rel_path).stem
            ext_map = {"markdown": ".md", "text": ".txt", "json": ".json"}
            out_file = os.path.join(output_dir, f"{base_name}_ocr{ext_map[args.format]}")
            os.makedirs(os.path.dirname(out_file), exist_ok=True)

            if args.format == "text":
                with open(out_file, "w", encoding="utf-8") as f:
                    f.write(result.to_text())
            elif args.format == "json":
                with open(out_file, "w", encoding="utf-8") as f:
                    f.write(result.to_json())
            else:
                with open(out_file, "w", encoding="utf-8") as f:
                    f.write(result.to_markdown())

            success += 1
            if not args.quiet:
                print(f"   ✓ {result.total_pages} 页, {result.total_lines} 行, "
                      f"质量 {result.quality_score.grade}")
        except Exception as e:
            failed += 1
            print(f"   ✗ 失败: {e}", file=sys.stderr)

    if not args.quiet:
        print(f"\n🎉 批量处理完成: 成功 {success}, 失败 {failed}")
        print(f"   输出目录: {output_dir}")

    return 0 if failed == 0 else 2


if __name__ == "__main__":
    sys.exit(main())

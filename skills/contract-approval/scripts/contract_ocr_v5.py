#!/usr/bin/env python3
"""
OCR 文档数字化组件 (OCR-001) v5 - 签名增强版

在 v4 基础上新增：
  1. 原生 PDF 文本提取优先（PyMuPDF）— 非扫描件直接抽文字，100%准确
  2. 红色印章自动检测 + 截图保存
  3. 手写签名区域自动检测 + 截图保存
  4. 签名/印章位置标注到输出文本
  5. 双引擎融合（RapidOCR + PaddleOCR）— 只对扫描件生效

用法：
  CLI: python3 contract_ocr_v5.py <input.pdf> <output.md> [--extract-signatures]
  API: from contract_ocr_v5 import digitalize_document_v5
"""
import os
import re
import sys
import json
import argparse
import numpy as np
from PIL import Image
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict

# ============================================================
# 数据结构
# ============================================================

@dataclass
class OCRLine:
    """OCR 识别行"""
    text: str
    bbox: Tuple[float, float, float, float]  # x1, y1, x2, y2
    confidence: float = 0.9
    source: str = "ocr"  # ocr / native

@dataclass
class SignatureRegion:
    """签名/印章区域"""
    type: str  # signature / seal
    page: int
    bbox: Tuple[int, int, int, int]  # x1, y1, x2, y2
    confidence: float
    image_path: str = ""
    label: str = ""  # 关联的关键词，如"甲方签字"

@dataclass
class PageResult:
    """单页OCR结果"""
    page_num: int
    lines: List[OCRLine]
    signatures: List[SignatureRegion] = field(default_factory=list)
    seals: List[SignatureRegion] = field(default_factory=list)
    is_scanned: bool = True  # 是否扫描件（原生文本提取失败则为扫描件）

@dataclass
class OCRResultV5:
    """OCR 完整结果"""
    text: str  # 合并后的纯文本
    markdown: str  # Markdown 格式（含签名标注）
    pages: List[PageResult]
    meta: Dict
    signatures: List[SignatureRegion] = field(default_factory=list)
    seals: List[SignatureRegion] = field(default_factory=list)

# ============================================================
# 原生 PDF 文本提取（PyMuPDF）
# ============================================================

def extract_native_text(pdf_path: str) -> Tuple[List[PageResult], bool]:
    """尝试用 PyMuPDF 提取原生文本
    
    Returns:
        (pages, success): pages 是提取结果，success 表示是否成功提取到足够文本
    """
    try:
        import pymupdf
    except ImportError:
        return [], False
    
    try:
        doc = pymupdf.open(pdf_path)
    except Exception:
        return [], False
    
    pages = []
    total_chars = 0
    
    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text("text")
        
        # 提取带坐标的文本块
        blocks = page.get_text("blocks")
        lines = []
        
        for block in blocks:
            if len(block) < 5:
                continue
            x0, y0, x1, y1, block_text = block[:5]
            if not block_text.strip():
                continue
            
            # 按行拆分
            for line_text in block_text.strip().split('\n'):
                line_text = line_text.strip()
                if not line_text:
                    continue
                lines.append(OCRLine(
                    text=line_text,
                    bbox=(x0, y0, x1, y1),
                    confidence=1.0,
                    source="native"
                ))
                total_chars += len(line_text)
        
        pages.append(PageResult(
            page_num=page_num + 1,
            lines=lines,
            is_scanned=False
        ))
    
    doc.close()
    
    # 判断是否是扫描件：每页平均字符数少于 50 认为是扫描件
    avg_chars = total_chars / max(1, len(pages))
    is_scanned = avg_chars < 50
    
    if is_scanned:
        return [], True  # 返回空列表，调用方应该走 OCR 路径
    
    return pages, False


# ============================================================
# 签名/印章检测
# ============================================================

def detect_red_seals(image: Image.Image, page_num: int, output_dir: str) -> List[SignatureRegion]:
    """检测红色印章（公章/合同章）
    
    原理：红色通道值明显高于绿蓝通道，且区域面积适中
    """
    img_array = np.array(image.convert('RGB'))
    h, w = img_array.shape[:2]
    
    r = img_array[:, :, 0].astype(int)
    g = img_array[:, :, 1].astype(int)
    b = img_array[:, :, 2].astype(int)
    
    # 红色像素判定
    red_mask = (r > 120) & (r - g > 50) & (r - b > 50)
    
    # 形态学闭运算填充孔洞
    try:
        from scipy import ndimage
        struct = np.ones((5, 5))
        red_mask = ndimage.binary_closing(red_mask, structure=struct).astype(bool)
        labeled, num_features = ndimage.label(red_mask)
    except ImportError:
        # 没有 scipy 就用简单方法
        labeled, num_features = None, 0
        # 简化版：直接统计
        pass
    
    if num_features == 0:
        return []
    
    regions = []
    min_area = 3000
    max_area = w * h * 0.25
    
    for i in range(1, num_features + 1):
        ys, xs = np.where(labeled == i)
        area = len(ys)
        if area < min_area or area > max_area:
            continue
        
        x1, x2 = int(xs.min()), int(xs.max())
        y1, y2 = int(ys.min()), int(ys.max())
        
        bw = x2 - x1
        bh = y2 - y1
        if bw == 0 or bh == 0:
            continue
        
        aspect = bw / bh
        if aspect < 0.4 or aspect > 2.5:
            continue
        
        # 红色占比
        roi = red_mask[y1:y2+1, x1:x2+1]
        red_ratio = roi.sum() / (roi.size + 1e-6)
        if red_ratio < 0.25:
            continue
        
        # 保存截图
        os.makedirs(output_dir, exist_ok=True)
        pad = 15
        crop = image.crop((max(0, x1-pad), max(0, y1-pad), min(w, x2+pad), min(h, y2+pad)))
        save_path = os.path.join(output_dir, f"page_{page_num}_seal_{len(regions)+1}.png")
        crop.save(save_path)
        
        regions.append(SignatureRegion(
            type="seal",
            page=page_num,
            bbox=(x1, y1, x2, y2),
            confidence=min(0.95, 0.5 + red_ratio * 0.5),
            image_path=save_path
        ))
    
    return regions


def detect_signatures(image: Image.Image, page_num: int, output_dir: str,
                     ocr_lines: List[OCRLine]) -> List[SignatureRegion]:
    """检测手写签名区域
    
    原理：在"签字/签名/盖章"等关键词附近，找低OCR置信度/墨色密集区域
    """
    img_gray = np.array(image.convert('L'))
    h, w = img_gray.shape[:2]
    
    # 找签名关键词位置
    keywords = ["签字", "签名", "盖章", "签章", "签署", "签约", "法定代表人", "委托代理人", "经办人"]
    keyword_hits = []
    
    for line in ocr_lines:
        for kw in keywords:
            if kw in line.text:
                keyword_hits.append({"keyword": kw, "line": line})
                break
    
    regions = []
    ink_thresh = 130
    
    for hit in keyword_hits:
        line = hit["line"]
        kw = hit["keyword"]
        x1, y1, x2, y2 = line.bbox
        
        # 搜索区域：关键词右侧 + 下方
        search_x1 = min(int(x2) + 15, w - 1)
        search_y1 = max(0, int(y1) - 20)
        search_x2 = w - 1
        search_y2 = min(h - 1, int(y2) + 80)
        
        if search_x2 <= search_x1 or search_y2 <= search_y1:
            continue
        
        roi = img_gray[search_y1:search_y2, search_x1:search_x2]
        
        ink_pixels = (roi < ink_thresh).sum()
        total = roi.size
        if total == 0:
            continue
        
        ink_ratio = ink_pixels / total
        
        # 签名区域墨色比例：0.02-0.5
        if ink_ratio < 0.02 or ink_ratio > 0.5:
            continue
        
        # 找笔迹边界
        ink_mask = roi < ink_thresh
        ys, xs = np.where(ink_mask)
        if len(xs) < 50:  # 像素太少，可能不是签名
            continue
        
        lx1, lx2 = int(xs.min()), int(xs.max())
        ly1, ly2 = int(ys.min()), int(ys.max())
        
        bw = lx2 - lx1
        bh = ly2 - ly1
        if bw < 40 or bh < 25:
            continue
        
        abs_x1 = search_x1 + lx1
        abs_y1 = search_y1 + ly1
        abs_x2 = search_x1 + lx2
        abs_y2 = search_y1 + ly2
        
        # 保存截图
        os.makedirs(output_dir, exist_ok=True)
        pad = 15
        crop = image.crop((
            max(0, abs_x1 - pad), max(0, abs_y1 - pad),
            min(w, abs_x2 + pad), min(h, abs_y2 + pad)
        ))
        save_path = os.path.join(output_dir, f"page_{page_num}_signature_{len(regions)+1}.png")
        crop.save(save_path)
        
        # 确定标签
        label = kw
        if "甲" in line.text or "甲方" in line.text or "买" in line.text:
            label = "甲方" + kw
        elif "乙" in line.text or "乙方" in line.text or "卖" in line.text:
            label = "乙方" + kw
        
        regions.append(SignatureRegion(
            type="signature",
            page=page_num,
            bbox=(abs_x1, abs_y1, abs_x2, abs_y2),
            confidence=min(0.80, 0.4 + ink_ratio * 0.6),
            image_path=save_path,
            label=label
        ))
    
    return regions


# ============================================================
# PDF 转图片
# ============================================================

def pdf_to_images(pdf_path: str, dpi: int = 600) -> List[Image.Image]:
    """PDF 转高分辨率图片"""
    import subprocess
    import tempfile
    
    # 优先用 PyMuPDF（更快）
    try:
        import fitz
        doc = pymupdf.open(pdf_path)
        images = []
        zoom = dpi / 72
        mat = pymupdf.Matrix(zoom, zoom)
        for page in doc:
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            images.append(img)
        doc.close()
        return images
    except ImportError:
        pass
    
    # 回退：macOS sips 命令（无需额外依赖）
    try:
        from PyPDF2 import PdfReader
        reader = PdfReader(pdf_path)
        images = []
        with tempfile.TemporaryDirectory() as tmp_dir:
            for i in range(len(reader.pages)):
                from PyPDF2 import PdfWriter
                writer = PdfWriter()
                writer.add_page(reader.pages[i])
                single_pdf = os.path.join(tmp_dir, f"page_{i+1}.pdf")
                with open(single_pdf, "wb") as f:
                    writer.write(f)
                
                out_png = os.path.join(tmp_dir, f"page_{i+1}.png")
                r = subprocess.run(
                    ["sips", "-s", "format", "png",
                     "-s", "dpiHeight", str(dpi),
                     "-s", "dpiWidth", str(dpi),
                     single_pdf, "--out", out_png],
                    capture_output=True, text=True
                )
                if os.path.exists(out_png):
                    images.append(Image.open(out_png).copy())
        if images:
            return images
    except (ImportError, Exception):
        pass
    
    # 回退：pdf2image
    try:
        from pdf2image import convert_from_path
        return convert_from_path(pdf_path, dpi=dpi)
    except ImportError:
        pass
    
    raise RuntimeError("无法将 PDF 转图片，请安装 PyMuPDF / PyPDF2+sips / pdf2image")


# ============================================================
# OCR 识别（调用 v4 的引擎）
# ============================================================

def ocr_image(image: Image.Image, engine: str = "rapidocr") -> List[OCRLine]:
    """OCR 识别单页图片，返回按阅读顺序排列的行
    
    复用 v4 的多版本预处理 + 最优结果选择逻辑
    """
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    
    # 动态导入 v4 组件
    from contract_ocr import (
        RapidOCRBackend, PaddleOCRBackend,
        preprocess_image, sort_text_lines
    )
    
    # 初始化后端
    backends = {}
    rb = RapidOCRBackend()
    rb.load()
    backends['rapidocr'] = rb
    
    if engine in ('paddle', 'auto'):
        pb = PaddleOCRBackend()
        pb.load()
        if pb.available():
            backends['paddle'] = pb
    
    # 多版本预处理 + 多引擎，取最优
    versions = preprocess_image(image)
    best_result = None
    best_score = 0
    
    def score_result(result):
        if not result: return 0
        n = len(result)
        ac = sum(float(r[2]) for r in result) / n
        at = ''.join(r[1] for r in result)
        import re
        cn = len(re.findall(r'[\u4e00-\u9fff]', at))
        cr = cn / max(len(at), 1)
        return n * 10 + ac * 50 + cr * 30
    
    for vname, vimg in versions.items():
        for bname, backend in backends.items():
            result = backend.recognize(vimg)
            if not result:
                continue
            s = score_result(result)
            if s > best_score:
                best_score = s
                best_result = result
    
    if not best_result:
        return []
    
    # 排序
    sorted_lines = sort_text_lines(best_result)
    
    # 转换为 OCRLine
    # sorted_lines 格式: [(y, text), ...]
    lines = []
    
    # 先建立 text -> bbox/conf 的映射（从 best_result 里取）
    text_info = {}
    for r in best_result:
        if len(r) >= 3:
            box, text, conf = r[0], r[1], float(r[2])
            x_coords = [p[0] for p in box]
            y_coords = [p[1] for p in box]
            text_info[text] = {
                "xmin": min(x_coords),
                "ymin": min(y_coords),
                "xmax": max(x_coords),
                "ymax": max(y_coords),
                "conf": conf
            }
    
    for y, text in sorted_lines:
        if not text:
            continue
        info = text_info.get(text, {"xmin": 0, "ymin": y, "xmax": 0, "ymax": y + 20, "conf": 0.8})
        lines.append(OCRLine(
            text=text,
            bbox=(info["xmin"], info["ymin"], info["xmax"], info["ymax"]),
            confidence=info["conf"],
            source="ocr"
        ))
    
    return lines

def sort_lines_reading_order(lines: List[OCRLine]) -> List[OCRLine]:
    """按阅读顺序排序：先按行（y坐标聚类），行内按 x 坐标"""
    if not lines:
        return []
    
    # 计算行高估计
    heights = [line.bbox[3] - line.bbox[1] for line in lines]
    avg_height = sum(heights) / len(heights) if heights else 20
    line_threshold = avg_height * 0.5
    
    # 按 y1 排序
    sorted_by_y = sorted(lines, key=lambda l: l.bbox[1])
    
    # 聚类成行
    rows = []
    current_row = [sorted_by_y[0]]
    current_y = sorted_by_y[0].bbox[1]
    
    for line in sorted_by_y[1:]:
        if abs(line.bbox[1] - current_y) < line_threshold:
            current_row.append(line)
        else:
            rows.append(current_row)
            current_row = [line]
            current_y = line.bbox[1]
    rows.append(current_row)
    
    # 每行内按 x 排序
    result = []
    for row in rows:
        row_sorted = sorted(row, key=lambda l: l.bbox[0])
        result.extend(row_sorted)
    
    return result


# ============================================================
# 合同场景后处理（纠错）
# ============================================================

def correct_contract_text(lines: List[OCRLine]) -> List[OCRLine]:
    """合同场景常见OCR错误纠错"""
    corrections = [
        # 金额/数字常见错误
        (r"(\d)O(\d)", r"\g<1>0\g<2>"),  # 数字中间的 O -> 0
        (r"(\d)o(\d)", r"\g<1>0\g<2>"),
        (r"(\d)l(\d)", r"\g<1>1\g<2>"),  # 数字中间的 l -> 1
        (r"(\d)I(\d)", r"\g<1>1\g<2>"),
        # 合同术语常见错误
        (r"买受方", "买受人"),
        (r"出受方", "出卖人"),
        (r"违约全", "违约金"),
        (r"定金罚则", "定金罚则"),  # 正确的
        (r"不可抗", "不可抗力"),
        (r"争仪解决", "争议解决"),
        (r"知识产杈", "知识产权"),
        (r"保秘条款", "保密条款"),
        (r"验收标谁", "验收标准"),
        (r"有限公可", "有限公司"),
        (r"有限公同", "有限公司"),
        (r"股份有限公", "股份有限公司"),
    ]
    
    for line in lines:
        for pattern, repl in corrections:
            line.text = re.sub(pattern, repl, line.text)
    
    return lines


# ============================================================
# 主入口
# ============================================================

def digitalize_document_v5(
    pdf_path: str,
    output_path: Optional[str] = None,
    engine: str = "auto",
    dpi: int = 600,
    extract_signatures: bool = True,
    signature_dir: Optional[str] = None
) -> OCRResultV5:
    """文档数字化 v5
    
    Args:
        pdf_path: PDF 或图片路径
        output_path: 输出文本/markdown 文件路径
        engine: OCR 引擎 (rapidocr/paddle/auto)
        dpi: 渲染 DPI
        extract_signatures: 是否提取签名/印章截图
        signature_dir: 签名截图保存目录，默认同目录下 signatures/
    
    Returns:
        OCRResultV5 对象
    """
    # 设置签名输出目录
    if extract_signatures and not signature_dir:
        base_dir = os.path.dirname(os.path.abspath(pdf_path)) if os.path.dirname(pdf_path) else "."
        signature_dir = os.path.join(base_dir, "signatures")
    
    # 1. 尝试原生文本提取
    native_pages, is_scanned = extract_native_text(pdf_path)
    
    if not is_scanned and native_pages:
        # 原生 PDF，直接用提取结果
        pages = native_pages
        text_source = "native"
        
        # 原生 PDF 也提取签名/印章
        all_signatures = []
        all_seals = []
        
        if extract_signatures:
            # 原生 PDF 用 300DPI 渲染图片来检测签名
            images = pdf_to_images(pdf_path, dpi=300)
            for i, image in enumerate(images):
                page_num = i + 1
                page = pages[i] if i < len(pages) else None
                
                seals = detect_red_seals(image, page_num, signature_dir)
                all_seals.extend(seals)
                if page:
                    page.seals = seals
                
                if page and page.lines:
                    sigs = detect_signatures(image, page_num, signature_dir, page.lines)
                    all_signatures.extend(sigs)
                    page.signatures = sigs
    else:
        # 扫描件，走 OCR + 签名检测
        text_source = "ocr"
        pages = []
        all_signatures = []
        all_seals = []
        
        # 用 v4 的 pdf_to_images 转图（sips方式，经过验证稳定）
        try:
            import sys
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from contract_ocr import pdf_to_images as v4_pdf_to_images
            images = v4_pdf_to_images(pdf_path, dpi)
            image_list = [img for _, img in images]
        except Exception as e:
            print(f"警告: v4 图片转换失败，尝试 PyMuPDF: {e}")
            image_list = pdf_to_images(pdf_path, dpi=dpi)
        
        for i, img in enumerate(image_list):
            page_num = i + 1
            pass  # 静默处理
            
            # OCR
            lines = ocr_image(img, engine=engine)
            lines = correct_contract_text(lines)
            
            page_result = PageResult(
                page_num=page_num,
                lines=lines,
                is_scanned=True
            )
            
            # 签名/印章检测（用高分辨率图片单独渲染，提高检测精度）
            if extract_signatures:
                try:
                    import pymupdf
                    doc = pymupdf.open(pdf_path)
                    page = doc[i]
                    mat = pymupdf.Matrix(3, 3)  # 216 DPI，足够检测印章
                    pix = page.get_pixmap(matrix=mat, alpha=False)
                    hi_img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                    doc.close()
                    
                    seals = detect_red_seals(hi_img, page_num, signature_dir)
                    all_seals.extend(seals)
                    page_result.seals = seals
                    
                    if lines:
                        sigs = detect_signatures(hi_img, page_num, signature_dir, lines)
                        all_signatures.extend(sigs)
                        page_result.signatures = sigs
                    
                    del hi_img, pix
                except Exception as e:
                    pass  # 静默失败
            
            pages.append(page_result)
    
    # 3. 生成输出文本
    text_lines = []
    md_lines = []
    
    for page in pages:
        text_lines.append(f"\n{'='*50}")
        text_lines.append(f"第 {page.page_num} 页")
        text_lines.append(f"{'='*50}")
        
        md_lines.append(f"\n## 第 {page.page_num} 页")
        md_lines.append("")
        
        for line in page.lines:
            text_lines.append(line.text)
            md_lines.append(line.text)
        
        # 添加签名/印章标注
        if page.seals:
            md_lines.append("")
            md_lines.append(f"**🔴 印章 ({len(page.seals)} 处):**")
            for seal in page.seals:
                md_lines.append(f"  - 位置: ({seal.bbox[0]}, {seal.bbox[1]})  置信度: {seal.confidence:.0%}")
                if seal.image_path:
                    md_lines.append(f"  - 截图: `{seal.image_path}`")
        
        if page.signatures:
            md_lines.append("")
            md_lines.append(f"**✍️  签名 ({len(page.signatures)} 处):**")
            for sig in page.signatures:
                label = f"「{sig.label}」" if sig.label else ""
                md_lines.append(f"  - {label}位置: ({sig.bbox[0]}, {sig.bbox[1]})  置信度: {sig.confidence:.0%}")
                if sig.image_path:
                    md_lines.append(f"  - 截图: `{sig.image_path}`")
    
    full_text = "\n".join(text_lines)
    full_md = "\n".join(md_lines)
    
    # 4. 保存输出
    if output_path:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(full_md if output_path.endswith(".md") else full_text)
    
    # 5. 元信息
    total_lines = sum(len(p.lines) for p in pages)
    total_chars = sum(len(l.text) for p in pages for l in p.lines)
    
    meta = {
        "pages": len(pages),
        "total_lines": total_lines,
        "total_chars": total_chars,
        "engine": engine,
        "source": text_source,
        "dpi": dpi,
        "signatures_found": len(all_signatures),
        "seals_found": len(all_seals),
    }
    
    return OCRResultV5(
        text=full_text,
        markdown=full_md,
        pages=pages,
        meta=meta,
        signatures=all_signatures,
        seals=all_seals
    )


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="OCR 文档数字化 v5 - 签名增强版")
    parser.add_argument("input", help="输入 PDF 或图片路径")
    parser.add_argument("output", nargs="?", default="output.md", help="输出文件路径 (默认 output.md)")
    parser.add_argument("--engine", default="auto", choices=["rapidocr", "paddle", "auto"], help="OCR 引擎")
    parser.add_argument("--dpi", type=int, default=600, help="渲染 DPI (默认 600)")
    parser.add_argument("--no-signatures", action="store_true", help="不提取签名/印章")
    parser.add_argument("--signature-dir", help="签名截图保存目录")
    
    args = parser.parse_args()
    
    print(f"🔍 开始数字化: {args.input}")
    print(f"   引擎: {args.engine} | DPI: {args.dpi}")
    print(f"   签名提取: {'关闭' if args.no_signatures else '开启'}")
    
    result = digitalize_document_v5(
        args.input,
        output_path=args.output,
        engine=args.engine,
        dpi=args.dpi,
        extract_signatures=not args.no_signatures,
        signature_dir=args.signature_dir
    )
    
    print(f"\n✅ 完成！")
    print(f"   页数: {result.meta['pages']}")
    print(f"   总行数: {result.meta['total_lines']}")
    print(f"   总字符: {result.meta['total_chars']}")
    print(f"   文本来源: {result.meta['source']}")
    print(f"   印章: {result.meta['seals_found']} 处")
    print(f"   签名: {result.meta['signatures_found']} 处")
    print(f"   输出: {args.output}")
    
    if result.signatures:
        print(f"\n✍️  找到的签名：")
        for sig in result.signatures:
            label = f"「{sig.label}」" if sig.label else ""
            print(f"   - 第{sig.page}页 {label}: {sig.image_path}")
    
    if result.seals:
        print(f"\n🔴 找到的印章：")
        for seal in result.seals:
            print(f"   - 第{seal.page}页: {seal.image_path}")


if __name__ == "__main__":
    main()

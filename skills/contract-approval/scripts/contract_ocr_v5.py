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


def detect_signature_page_v2(image: Image.Image, page_num: int, output_dir: str,
                            ocr_lines, ocr_scale: float = 1.0) -> tuple:
    """签署页智能检测 v2
    
    直接在传入的 image 上做图像处理，不依赖 OCR 坐标。
    返回 (seals_list, signatures_list)
    """
    import numpy as np
    import os
    
    img_array = np.array(image)
    h, w = img_array.shape[:2]
    
    # 0. OCR 坐标到图像坐标的比例
    # 调用方传入优先（最准确），否则自动估算
    # 自动估算：用 OCR 行的 y 范围和图像高度的比例估算
    if ocr_scale <= 0 and ocr_lines:
        # 自动估算：用所有 OCR 行的 y 范围估算
        ocr_ys = [l.bbox[1] for l in ocr_lines] + [l.bbox[3] for l in ocr_lines]
        ocr_ys = [y for y in ocr_ys if y > 0]
        if ocr_ys:
            ocr_max_y = max(ocr_ys)
            if ocr_max_y > 0 and ocr_max_y < h * 0.5:
                # 粗略估算，可能不准，仅作回退
                ocr_scale = h / ocr_max_y * 0.6
    
    def ocr_y_to_img_y(ocr_y):
        return int(ocr_y * ocr_scale)
    
    def ocr_x_to_img_x(ocr_x):
        return int(ocr_x * ocr_scale)
    
    # 1. 判断是否签署页（OCR 文本关键词）
    page_text = " ".join(l.text for l in ocr_lines) if ocr_lines else ""
    has_seal_kw = any(kw in page_text for kw in ["盖章", "签章", "公章", "合同专用章"])
    has_sign_kw = any(kw in page_text for kw in ["签字", "签名", "法定代表人", "授权代表"])
    has_sign_page = "签署页" in page_text
    if not has_sign_page and not (has_seal_kw and has_sign_kw):
        return [], []
    
    # 2. 左右分栏
    split_x = w // 2
    columns = [
        {"name": "甲方", "x1": 0, "x2": split_x},
        {"name": "乙方", "x1": split_x, "x2": w},
    ]
    
    seals_out = []
    sigs_out = []
    
    for col in columns:
        col_x1, col_x2 = int(col["x1"]), int(col["x2"])
        col_name = col["name"]
        col_img = image.crop((col_x1, 0, col_x2, h))
        col_array = np.array(col_img)
        col_h, col_w = col_array.shape[:2]
        
        # 3. 检测红色印章
        r = col_array[:, :, 0].astype(int)
        g = col_array[:, :, 1].astype(int)
        b = col_array[:, :, 2].astype(int)
        red_mask_col = (r > 80) & (r - g > 25) & (r - b > 25)
        
        seal_bbox = None
        
        try:
            from scipy import ndimage
            struct = np.ones((5, 5))
            red_closed = ndimage.binary_closing(red_mask_col, structure=struct).astype(bool)
            labeled, num_features = ndimage.label(red_closed)
            
            if num_features > 0:
                max_area = 0
                best_idx = -1
                min_area = 500
                for i in range(1, num_features + 1):
                    ys, xs = np.where(labeled == i)
                    area = len(ys)
                    if area < min_area:
                        continue
                    sx1, sx2 = int(xs.min()), int(xs.max())
                    sy1, sy2 = int(ys.min()), int(ys.max())
                    bw, bh = sx2 - sx1, sy2 - sy1
                    if bw == 0 or bh == 0:
                        continue
                    aspect = bw / bh
                    if aspect < 0.5 or aspect > 2.0:
                        continue
                    roi = red_mask_col[sy1:sy2+1, sx1:sx2+1]
                    red_ratio = roi.sum() / (roi.size + 1e-6)
                    if red_ratio < 0.1:
                        continue
                    if area > max_area:
                        max_area = area
                        best_idx = i
                
                if best_idx > 0:
                    ys, xs = np.where(labeled == best_idx)
                    sx1, sx2 = int(xs.min()), int(xs.max())
                    sy1, sy2 = int(ys.min()), int(ys.max())
                    seal_bbox = (col_x1 + sx1, sy1, col_x1 + sx2, sy2)
        except ImportError:
            pass
        
        # 4. 检测手写签名（OCR 文字锚定 + 像素验证）
        # 策略：用 OCR 找到"签字"标签行 和 "签订时间"行，用它们的 y 坐标精确框定签名区
        sig_bbox = None
        sig_is_precise = False
        
        # 4.1 在当前栏内找 OCR 锚点行
        label_line = None  # "法定代表人...签字:" 行
        date_line = None   # "签订时间：..." 行
        
        if ocr_lines:
            for line in ocr_lines:
                lx1, ly1, lx2, ly2 = line.bbox
                # 注意：OCR 可能把左右两栏识别成同一行（x 横跨整页）
                # 所以不用 x 过滤，只判断文字内容，用 y 坐标确定范围
                # 横向裁剪按当前栏的 x 范围即可
                
                text = line.text.strip()
                # 签字标签行（匹配多种表述）
                if any(kw in text for kw in ["法定代表人", "授权代表", "委托代理人"]) and "签" in text:
                    label_line = line
                # 签订时间行
                if ("签订时间" in text or "签署日期" in text or "签约日期" in text) and len(text) > 4:
                    date_line = line
        
        # 4.2 如果找到了 OCR 锚点，直接用文字坐标精确裁剪
        if label_line and date_line:
            ly1 = ocr_y_to_img_y(label_line.bbox[1])  # 签字标签行顶部（转图像坐标）
            dy2 = ocr_y_to_img_y(date_line.bbox[3])   # 签订时间行底部（转图像坐标）
            
            # 横向范围：用当前栏的 x 范围（OCR 行可能跨整页，不准）
            # 左右各留 10% padding
            col_width = col_x2 - col_x1
            pad_x = int(col_width * 0.05)
            
            # 纵向 padding
            pad_y_top = max(15, int((dy2 - ly1) * 0.05))
            pad_y_bot = max(15, int((dy2 - ly1) * 0.05))
            
            sig_y1 = max(0, ly1 - pad_y_top)
            sig_y2 = min(h, dy2 + pad_y_bot)
            sig_x1 = max(0, col_x1 + pad_x)
            sig_x2 = min(w, col_x2 - pad_x)
            
            # 验证：区域内确实有墨迹（不是空的）
            col_gray = np.array(col_img.convert('L'))
            sig_roi_local = col_gray[sig_y1:sig_y2, sig_x1 - col_x1:sig_x2 - col_x1]
            if sig_roi_local.size > 0:
                ink_ratio = (sig_roi_local < 130).sum() / sig_roi_local.size
                if ink_ratio > 0.02:  # 有 >2% 墨迹，确认有效
                    sig_bbox = (sig_x1, sig_y1, sig_x2, sig_y2)
                    sig_is_precise = True  # OCR 锚定，范围精确
        
        # 4.3 回退：如果 OCR 锚点不全，用印章 + 像素投影法（旧逻辑）
        if sig_bbox is None and seal_bbox:
            seal_top = seal_bbox[1]
            seal_bot = seal_bbox[3]
            seal_h = seal_bot - seal_top
            
            # 搜索：印章底部 0.3 ~ 4 倍印章高度
            search_y1 = seal_bot + int(seal_h * 0.3)
            search_y2 = min(h, seal_bot + int(seal_h * 4))
            
            col_gray = np.array(col_img.convert('L'))
            roi = col_gray[search_y1:search_y2, :]
            
            if roi.size > 0:
                # 找每行墨像素
                row_ink = (roi < 130).sum(axis=1)
                
                if row_ink.size > 0 and row_ink.max() > 10:
                    # 分割连续墨迹段
                    threshold = row_ink.max() * 0.12
                    has_ink = row_ink > threshold
                    segments = []
                    in_seg = False
                    seg_start = 0
                    for i in range(len(has_ink)):
                        if has_ink[i] and not in_seg:
                            seg_start = i
                            in_seg = True
                        elif not has_ink[i] and in_seg:
                            segments.append((seg_start, i - 1))
                            in_seg = False
                    if in_seg:
                        segments.append((seg_start, len(has_ink) - 1))
                    
                    # 分析每个段
                    best_seg = None
                    best_score = 0
                    candidates = []
                    
                    for sy1, sy2 in segments:
                        seg_h = sy2 - sy1 + 1
                        if seg_h < 10 or seg_h > 150:
                            continue
                        
                        seg_mask = (roi[sy1:sy2+1, :] < 130)
                        col_ink = seg_mask.sum(axis=0)
                        ink_cols = np.where(col_ink > 0)[0]
                        if len(ink_cols) < 20:
                            continue
                        
                        sx1, sx2 = ink_cols[0], ink_cols[-1]
                        seg_w = sx2 - sx1 + 1
                        
                        # 太宽（>栏宽70%）→ 印刷体字行，跳过
                        if seg_w > col_w * 0.7:
                            continue
                        # 太窄 → 不是签名
                        if seg_w < 40:
                            continue
                        
                        total_ink = seg_mask.sum()
                        density = total_ink / (seg_w * seg_h + 1e-6)
                        
                        # 太密（>30%）→ 印刷体，跳过
                        if density > 0.30:
                            continue
                        
                        aspect = seg_w / max(seg_h, 1)
                        score = seg_w * total_ink * (1 - density)
                        
                        if aspect > 0.8:
                            candidates.append({
                                'y1': sy1, 'y2': sy2, 'x1': sx1, 'x2': sx2,
                                'h': seg_h, 'w': seg_w,
                                'density': density, 'score': score, 'aspect': aspect
                            })
                    
                    # 策略：找到最靠下的"宽印刷体行"（签订时间行），在它上方找签名
                    if candidates:
                        candidates.sort(key=lambda c: -c['y2'])
                        
                        date_line_idx = -1
                        for i, c in enumerate(candidates):
                            if c['w'] > col_w * 0.55 or c['density'] > 0.35:
                                date_line_idx = i
                                break
                        
                        if date_line_idx >= 0:
                            if date_line_idx + 1 < len(candidates):
                                sig_candidate = candidates[date_line_idx + 1]
                                best_seg = (sig_candidate['x1'], sig_candidate['y1'],
                                           sig_candidate['x2'], sig_candidate['y2'])
                        else:
                            candidates.sort(key=lambda c: -c['score'])
                            best_seg = (candidates[0]['x1'], candidates[0]['y1'],
                                       candidates[0]['x2'], candidates[0]['y2'])
                    
                    if best_seg:
                        sx1, sy1, sx2, sy2 = best_seg
                        # 回退模式下，扩大范围到"签字标签 + 签名 + 日期"整块
                        # 向上找"签字"关键词的 OCR 行
                        expand_y1 = search_y1 + sy1
                        expand_y2 = search_y1 + sy2
                        
                        if ocr_lines:
                            for line in ocr_lines:
                                lx1, ly1, lx2, ly2 = line.bbox
                                if lx1 < col_x1 - 20 or lx2 > col_x2 + 20:
                                    continue
                                text = line.text.strip()
                                if "签" in text and ("字" in text or "章" in text or "代表" in text or "法定" in text):
                                    expand_y1 = min(expand_y1, ocr_y_to_img_y(ly1))
                                if "签订时间" in text or "签署日期" in text:
                                    expand_y2 = max(expand_y2, ocr_y_to_img_y(ly2))
                        
                        sig_bbox = (
                            col_x1 + max(0, sx1 - 50),
                            max(0, expand_y1 - 20),
                            col_x1 + min(col_w, sx2 + 50),
                            min(h, expand_y2 + 20)
                        )
                        sig_is_precise = False  # 像素回退，范围不精确
        
                # 5. 整列截图
        elems = []
        if seal_bbox:
            elems.append(seal_bbox)
        if sig_bbox:
            elems.append(sig_bbox)
        
        if elems:
            all_x1 = min(e[0] for e in elems)
            all_y1 = min(e[1] for e in elems)
            all_x2 = max(e[2] for e in elems)
            all_y2 = max(e[3] for e in elems)
            
            pad_top = max(150, int((all_y2 - all_y1) * 0.6))
            pad_bot = max(120, int((all_y2 - all_y1) * 0.5))
            pad_x = max(80, int((all_x2 - all_x1) * 0.3))
            
            col_top = max(0, all_y1 - pad_top)
            col_bot = min(h, all_y2 + pad_bot)
            col_left = max(0, all_x1 - pad_x)
            col_right = min(w, all_x2 + pad_x)
            
            os.makedirs(output_dir, exist_ok=True)
            col_path = os.path.join(output_dir, f"page_{page_num}_{col_name}_column.png")
            image.crop((col_left, col_top, col_right, col_bot)).save(col_path)
        
        # 输出印章
        if seal_bbox:
            sx1, sy1, sx2, sy2 = seal_bbox
            pad = max(40, int((sx2 - sx1) * 0.4))
            seal_path = os.path.join(output_dir, f"page_{page_num}_seal_{col_name}.png")
            image.crop((
                max(0, sx1 - pad), max(0, sy1 - pad),
                min(w, sx2 + pad), min(h, sy2 + pad)
            )).save(seal_path)
            
            seals_out.append(SignatureRegion(
                type="seal",
                page=page_num,
                bbox=(int(sx1), int(sy1), int(sx2), int(sy2)),
                confidence=0.85,
                image_path=seal_path,
                label=f"{col_name}公章"
            ))
        
        # 输出签名
        if sig_bbox and seal_bbox:  # 必须同页有印章才输出
            sx1, sy1, sx2, sy2 = sig_bbox
            if sig_is_precise:
                # OCR 锚定模式：已精确裁剪，只加极小 padding
                pad_x = max(10, int((sx2 - sx1) * 0.02))
                pad_y = max(8, int((sy2 - sy1) * 0.02))
            else:
                # 回退模式：加较大 padding 避免裁掉内容
                pad_x = max(50, int((sx2 - sx1) * 0.5))
                pad_y = max(40, int((sy2 - sy1) * 1.2))
            sig_path = os.path.join(output_dir, f"page_{page_num}_signature_{col_name}.png")
            image.crop((
                max(0, sx1 - pad_x), max(0, sy1 - pad_y),
                min(w, sx2 + pad_x), min(h, sy2 + pad_y)
            )).save(sig_path)
            
            sigs_out.append(SignatureRegion(
                type="signature",
                page=page_num,
                bbox=(int(sx1), int(sy1), int(sx2), int(sy2)),
                confidence=0.8,
                image_path=sig_path,
                label=f"{col_name}签字"
            ))
    
    return seals_out, sigs_out


def detect_red_seals(image: Image.Image, page_num: int, output_dir: str,
                      ocr_lines: Optional[List[OCRLine]] = None) -> List[SignatureRegion]:
    """检测红色印章（公章/合同章）
    
    原理：红色通道值明显高于绿蓝通道，且区域面积适中
    ocr_lines: 可选，用于给印章关联"甲方/乙方"标签
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
        
        # 保存截图（加大 padding，确保印章+周围公司名完整可见）
        os.makedirs(output_dir, exist_ok=True)
        pad = max(150, int((x2-x1) * 1.0))  # 至少150px，或印章尺寸100%
        crop = image.crop((max(0, x1-pad), max(0, y1-pad), min(w, x2+pad), min(h, y2+pad)))
        save_path = os.path.join(output_dir, f"page_{page_num}_seal_{len(regions)+1}.png")
        crop.save(save_path)
        
        # 关联甲方/乙方标签（基于印章中心与"甲方（盖章）"文本的距离）
        # 注意：OCR 行坐标来自 72DPI 低分辨率图，印章坐标来自高分辨率图，
        # 需要先缩放 OCR 坐标到同一坐标系。
        label = ""
        if ocr_lines:
            center_y = (y1 + y2) / 2
            center_x = (x1 + x2) / 2
            
            # 缩放因子：OCR 图 → 当前图
            # 用 OCR 行中最大 y 估计 OCR 图高度
            ocr_h = max((line.bbox[3] for line in ocr_lines), default=1)
            scale = h / max(ocr_h, 1) if ocr_h > 0 else 1.0
            
            best_label = ""
            best_dist = float("inf")
            for line in ocr_lines:
                text = line.text
                # 找包含"甲方"或"乙方"且含"盖章/签章/公章"的行
                if ("甲方" in text or "乙方" in text) and ("盖章" in text or "签章" in text or "章" in text):
                    lx1, ly1, lx2, ly2 = line.bbox
                    # 缩放到当前坐标系
                    lx1, lx2 = lx1 * scale, lx2 * scale
                    ly1, ly2 = ly1 * scale, ly2 * scale
                    line_center_y = (ly1 + ly2) / 2
                    line_center_x = (lx1 + lx2) / 2
                    # 距离（垂直距离为主）
                    dist = abs(line_center_y - center_y) * 0.7 + abs(line_center_x - center_x) * 0.3
                    if dist < best_dist:
                        best_dist = dist
                        best_label = "甲方公章" if "甲方" in text else "乙方公章"
            # 距离阈值：页面高度的 15% 以内才算关联
            if best_label and best_dist < h * 0.15:
                label = best_label
        
        regions.append(SignatureRegion(
            type="seal",
            page=page_num,
            bbox=(x1, y1, x2, y2),
            confidence=min(0.95, 0.5 + red_ratio * 0.5),
            image_path=save_path,
            label=label
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
        
        # 保存截图（大幅加大 padding，确保签字+标签+日期栏完整可见）
        os.makedirs(output_dir, exist_ok=True)
        pad_x = max(300, int((abs_x2 - abs_x1) * 2.0))   # 横向：至少300px，2倍宽（含整行）
        pad_y_top = max(200, int((abs_y2 - abs_y1) * 4.0))  # 上方：至少200px，4倍高（含甲方/乙方签字标签）
        pad_y_bot = max(150, int((abs_y2 - abs_y1) * 3.0))  # 下方：至少150px，3倍高（含日期/授权代表）
        crop = image.crop((
            max(0, abs_x1 - pad_x), max(0, abs_y1 - pad_y_top),
            min(w, abs_x2 + pad_x), min(h, abs_y2 + pad_y_bot)
        ))
        save_path = os.path.join(output_dir, f"page_{page_num}_signature_{len(regions)+1}.png")
        crop.save(save_path)
        
        # 确定标签
        label = kw
        if "甲" in line.text or "甲方" in line.text or "买" in line.text:
            label = "甲方" + kw
        elif "乙" in line.text or "乙方" in line.text or "卖" in line.text:
            label = "乙方" + kw
        else:
            # 基于位置关联甲方/乙方（搜索签名中心附近的甲乙文本）
            # 坐标系：OCR 行坐标是 72DPI，需要缩放到当前图坐标系
            ocr_h = max((ol.bbox[3] for ol in ocr_lines), default=1)
            scale = h / max(ocr_h, 1) if ocr_h > 0 else 1.0
            
            sig_center_y = (abs_y1 + abs_y2) / 2
            sig_center_x = (abs_x1 + abs_x2) / 2
            party_label = ""
            party_dist = float("inf")
            for ol in ocr_lines:
                ot = ol.text
                if ("甲方" in ot or "乙方" in ot or "供方" in ot or "需方" in ot):
                    ox1, oy1, ox2, oy2 = ol.bbox
                    ox1, ox2 = ox1 * scale, ox2 * scale
                    oy1, oy2 = oy1 * scale, oy2 * scale
                    o_center_y = (oy1 + oy2) / 2
                    o_center_x = (ox1 + ox2) / 2
                    # 距离（垂直为主）
                    d = abs(o_center_y - sig_center_y) * 0.7 + abs(o_center_x - sig_center_x) * 0.3
                    if d < party_dist:
                        party_dist = d
                        if "甲方" in ot or "供方" in ot:
                            party_label = "甲方"
                        elif "乙方" in ot or "需方" in ot:
                            party_label = "乙方"
            # 阈值：页面高度 20% 内
            if party_label and party_dist < h * 0.2:
                label = party_label + kw
        
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
                
                # 优先用 v2 签署页检测
                ocr_lines_ref = page.lines if page and page.lines else []
                # 原生 PDF：OCR 坐标是 pt 单位 (72 DPI)，图像是 300 DPI，scale = 300/72
                ocr_scale_native = 300.0 / 72.0
                seals_v2, sigs_v2 = detect_signature_page_v2(image, page_num, signature_dir, ocr_lines_ref, ocr_scale_native)
                if seals_v2 or sigs_v2:
                    if seals_v2:
                        seals = seals_v2
                        all_seals.extend(seals)
                        if page:
                            page.seals = seals
                    if sigs_v2 and page:
                        all_signatures.extend(sigs_v2)
                        page.signatures = sigs_v2
                else:
                    # 回退到老方法（只检印章，签名只在有印章时检）
                    seals = detect_red_seals(image, page_num, signature_dir, page.lines if page else None)
                    all_seals.extend(seals)
                    if page:
                        page.seals = seals
                    if page and page.lines and page.seals:
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
                    
                    # 优先用 v2 签署页检测（印章+签名一体化，准确率更高）
                    # 扫描件：OCR 图是 sips 转的(像素=72DPI尺寸)，hi_img 是 Matrix(3,3)=216DPI，scale = 3.0
                    ocr_scale_scan = 3.0
                    seals_v2, sigs_v2 = detect_signature_page_v2(hi_img, page_num, signature_dir, lines, ocr_scale_scan)
                    if seals_v2 or sigs_v2:
                        if seals_v2:
                            seals = seals_v2
                            all_seals.extend(seals)
                            page_result.seals = seals
                        if sigs_v2:
                            all_signatures.extend(sigs_v2)
                            page_result.signatures = sigs_v2
                    else:
                        # v2 没检测到，回退到老方法（只检测印章）
                        seals = detect_red_seals(hi_img, page_num, signature_dir, lines)
                        all_seals.extend(seals)
                        page_result.seals = seals
                    
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
    parser.add_argument("--json", help="额外输出 OCR 检测结果 JSON 路径（供 Excel 报告使用）")
    
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
    
    # 导出 JSON（供 Excel 报告使用）
    if args.json:
        import json as _json
        ocr_data = {
            "seals": [
                {"type": s.type, "page": s.page, "label": s.label,
                 "confidence": round(s.confidence, 4),
                 "image_path": s.image_path,
                 "bbox": list(s.bbox)}
                for s in result.seals
            ],
            "signatures": [
                {"type": s.type, "page": s.page, "label": s.label,
                 "confidence": round(s.confidence, 4),
                 "image_path": s.image_path,
                 "bbox": list(s.bbox)}
                for s in result.signatures
            ],
            "text": result.text,
            "meta": result.meta,
        }
        with open(args.json, "w", encoding="utf-8") as f:
            _json.dump(ocr_data, f, ensure_ascii=False, indent=2)
        print(f"\n📄 JSON 已导出: {args.json}")


if __name__ == "__main__":
    main()

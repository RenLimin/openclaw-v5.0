"""
OCR 质量检测与评分

对 OCR 识别结果进行多维度质量评估，输出 0-100 的综合得分。
评估维度：
- 置信度得分（confidence）：基于 OCR 引擎返回的置信度
- 清晰度得分（clarity）：基于图像的方差、边缘密度等估计
- 文本密度得分（text_density）：文本占比是否合理
- 布局完整性得分（layout_completeness）：文本分布是否均匀
"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple
from PIL import Image
import numpy as np

from .types import OCRLine, QualityScore, OCRPage


# ============================================================
# 图像清晰度评估
# ============================================================

def estimate_image_clarity(image: Image.Image) -> float:
    """估计图像清晰度（0-100）

    基于拉普拉斯方差（Laplacian variance）的清晰度指标。
    方差越大，图像越清晰；模糊图像方差小。

    Args:
        image: 输入图像

    Returns:
        清晰度得分 0-100
    """
    if image.mode != "L":
        gray = image.convert("L")
    else:
        gray = image

    arr = np.array(gray).astype(np.float32)

    # 拉普拉斯算子
    laplacian_kernel = np.array([
        [0, 1, 0],
        [1, -4, 1],
        [0, 1, 0],
    ], dtype=np.float32)

    # 简单实现：用 scipy 或手动卷积
    try:
        from scipy.ndimage import convolve
        laplacian = convolve(arr, laplacian_kernel)
    except ImportError:
        # 手动实现（较慢但不依赖 scipy）
        h, w = arr.shape
        laplacian = np.zeros_like(arr)
        for i in range(1, h - 1):
            for j in range(1, w - 1):
                laplacian[i, j] = (
                    arr[i-1, j] + arr[i+1, j] +
                    arr[i, j-1] + arr[i, j+1] -
                    4 * arr[i, j]
                )

    variance = float(np.var(laplacian))

    # 归一化到 0-100
    # 经验值：variance=0 完全模糊得0分，variance>1000 非常清晰得100分
    # 用对数映射使评分更均匀
    clarity = min(100.0, max(0.0, 100.0 * np.log1p(variance) / np.log1p(1000)))

    return clarity


def estimate_contrast(image: Image.Image) -> float:
    """估计图像对比度（0-100）

    基于图像灰度直方图的分布范围。
    """
    if image.mode != "L":
        gray = image.convert("L")
    else:
        gray = image

    arr = np.array(gray)

    # 用第 5 和 95 百分位的差估计对比度范围
    p5 = float(np.percentile(arr, 5))
    p95 = float(np.percentile(arr, 95))
    contrast_range = p95 - p5

    # 归一化：200+ 范围算很好（0-255）
    contrast = min(100.0, max(0.0, contrast_range / 200.0 * 100.0))
    return contrast


# ============================================================
# 文本密度评估
# ============================================================

def estimate_text_density(lines: List[OCRLine], image_size: Tuple[int, int]) -> float:
    """评估文本密度（0-100）

    合理的文本密度大约在 5%-30% 的覆盖率。
    过高（>60%）可能是噪声或误识别，过低（<2%）可能没识别到内容。
    """
    if not lines:
        return 0.0

    w, h = image_size
    total_area = w * h
    if total_area == 0:
        return 0.0

    # 计算所有文本行的总面积（有重叠的话简化处理）
    text_area = sum(
        max(0, (l.bbox[2] - l.bbox[0])) * max(0, (l.bbox[3] - l.bbox[1]))
        for l in lines
    )
    coverage = text_area / total_area

    # 理想密度：5%-20% 覆盖率 = 100分
    # 用高斯函数评分
    ideal_coverage = 0.12  # 12% 覆盖率为理想值
    sigma = 0.15
    density_score = 100.0 * np.exp(-0.5 * ((coverage - ideal_coverage) / sigma) ** 2)

    return min(100.0, max(0.0, density_score))


# ============================================================
# 布局完整性评估
# ============================================================

def estimate_layout_completeness(lines: List[OCRLine], image_size: Tuple[int, int]) -> float:
    """评估布局完整性（0-100）

    检查文本分布是否均匀，是否覆盖了页面的主要区域。
    指标：
    - 垂直分布均匀度
    - 水平边缘留白合理性
    - 行数量合理性
    """
    if not lines:
        return 0.0

    w, h = image_size

    # 1. 垂直覆盖范围
    y_min = min(l.bbox[1] for l in lines)
    y_max = max(l.bbox[3] for l in lines)
    v_coverage = (y_max - y_min) / max(h, 1)

    # 2. 水平边缘留白
    x_min = min(l.bbox[0] for l in lines)
    x_max = max(l.bbox[2] for l in lines)
    left_margin_ratio = x_min / max(w, 1)
    right_margin_ratio = (w - x_max) / max(w, 1)

    # 合理边距：5%-20%
    margin_score = 0.0
    if 0.03 <= left_margin_ratio <= 0.25 and 0.03 <= right_margin_ratio <= 0.25:
        margin_score = 100.0
    else:
        margin_score = 50.0  # 边距异常，给个基础分

    # 3. 行数合理性（与页数相关，简化处理）
    n_lines = len(lines)
    # 假设每页合理行数在 10-100 之间
    if n_lines < 3:
        line_score = 30.0
    elif n_lines < 10:
        line_score = 60.0 + (n_lines - 3) * (40.0 / 7.0)
    elif n_lines <= 100:
        line_score = 100.0
    else:
        line_score = max(50.0, 100.0 - (n_lines - 100) * 0.5)

    # 4. 垂直均匀度（行间距方差）
    sorted_lines = sorted(lines, key=lambda l: l.bbox[1])
    gaps = []
    for i in range(1, len(sorted_lines)):
        gap = sorted_lines[i].bbox[1] - sorted_lines[i-1].bbox[3]
        if gap > 0:
            gaps.append(gap)
    if len(gaps) >= 3:
        gap_mean = sum(gaps) / len(gaps)
        gap_var = sum((g - gap_mean) ** 2 for g in gaps) / len(gaps)
        gap_cv = np.sqrt(gap_var) / max(gap_mean, 1)  # 变异系数
        # 变异系数越小越均匀
        uniformity = max(0.0, 100.0 - gap_cv * 100.0)
    else:
        uniformity = 70.0  # 行数太少，给中等分

    # 综合布局分
    layout_score = (
        v_coverage * 30.0 +          # 垂直覆盖 30%
        margin_score * 0.20 +         # 边距合理性 20%
        line_score * 0.25 +           # 行数合理性 25%
        uniformity * 0.25             # 均匀度 25%
    )

    return min(100.0, max(0.0, layout_score))


# ============================================================
# 置信度评分
# ============================================================

def compute_confidence_score(lines: List[OCRLine]) -> float:
    """基于 OCR 引擎置信度的得分（0-100）"""
    if not lines:
        return 0.0
    avg_conf = sum(l.confidence for l in lines) / len(lines)
    return avg_conf * 100.0


# ============================================================
# 综合质量评分
# ============================================================

def compute_quality_score(
    lines: List[OCRLine],
    image: Optional[Image.Image] = None,
    image_size: Optional[Tuple[int, int]] = None,
    weights: Optional[dict] = None,
) -> QualityScore:
    """计算综合质量评分

    Args:
        lines: OCR 识别结果行列表
        image: 原始图像（用于清晰度评估）
        image_size: 图像尺寸（如果没传 image，需要手动传尺寸）
        weights: 各维度权重字典

    Returns:
        QualityScore 对象
    """
    if image is not None:
        img_size = image.size
        clarity = estimate_image_clarity(image)
    else:
        img_size = image_size or (0, 0)
        clarity = 70.0  # 无图像时给个默认分

    # 默认权重
    w = weights or {
        "confidence": 0.35,
        "clarity": 0.25,
        "text_density": 0.20,
        "layout_completeness": 0.20,
    }

    conf_score = compute_confidence_score(lines)
    density_score = estimate_text_density(lines, img_size)
    layout_score = estimate_layout_completeness(lines, img_size)

    overall = (
        w["confidence"] * conf_score +
        w["clarity"] * clarity +
        w["text_density"] * density_score +
        w["layout_completeness"] * layout_score
    )

    details = {
        "num_lines": len(lines),
        "avg_confidence": sum(l.confidence for l in lines) / len(lines) if lines else 0,
        "image_size": list(img_size),
    }

    return QualityScore(
        overall=round(overall, 2),
        confidence=round(conf_score, 2),
        clarity=round(clarity, 2),
        text_density=round(density_score, 2),
        layout_completeness=round(layout_score, 2),
        details=details,
    )


# ============================================================
# 中文文本质量辅助评估
# ============================================================

def chinese_text_quality(text: str) -> dict:
    """中文文本质量辅助检查

    检查：
    - 中文字符占比
    - 乱码字符比例
    - 常见 OCR 错误模式
    """
    # 中文字符占比
    cn_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
    total_chars = len(text.replace(" ", "").replace("\n", ""))
    cn_ratio = cn_chars / max(total_chars, 1)

    # 乱码检测：非中文、非英文、非数字、非标点的字符
    messy_pattern = r'[^\u4e00-\u9fff\u3000-\u303f\uff00-\uffef' \
                    r'a-zA-Z0-9\s\.\,\;\:\!\?\(\)\[\]\{\}\<\>' \
                    r'\-\+\=\*\/\%\@\#\$\&\~\`\'\"\_\|\\\/]'
    messy_chars = len(re.findall(messy_pattern, text))
    messy_ratio = messy_chars / max(total_chars, 1)

    # 常见 OCR 错误
    error_indicators = [
        r'[里][甲乙丙丁]',  # 里方 → 甲方
        r'[各务]',           # 各 → 服 / 务 → 各
    ]
    error_count = 0
    for pat in error_indicators:
        error_count += len(re.findall(pat, text))

    return {
        "chinese_ratio": round(cn_ratio, 4),
        "messy_ratio": round(messy_ratio, 4),
        "error_pattern_count": error_count,
        "total_chars": total_chars,
        "chinese_chars": cn_chars,
    }

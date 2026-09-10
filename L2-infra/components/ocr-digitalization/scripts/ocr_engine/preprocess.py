"""
图像预处理流水线

提供可配置的图像预处理步骤，提升 OCR 识别准确率。
处理步骤：灰度化 → 二值化 → 去噪 → 倾斜校正 → 对比度增强
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple
from PIL import Image, ImageEnhance, ImageFilter

import numpy as np


@dataclass
class PreprocessConfig:
    """预处理配置"""
    grayscale: bool = True          # 灰度化
    binarize: bool = False          # 二值化（阈值法）
    binarize_threshold: int = 150   # 二值化阈值（0-255）
    denoise: bool = True            # 去噪
    denoise_strength: int = 1       # 去噪强度（1=轻, 2=中, 3=重）
    deskew: bool = False            # 倾斜校正
    contrast_enhance: bool = True   # 对比度增强
    contrast_factor: float = 1.5    # 对比度增强因子
    sharpen: bool = False           # 锐化
    sharpen_factor: float = 2.0     # 锐化因子
    upscale: bool = False           # 放大（低分辨率图片）
    upscale_factor: float = 1.5     # 放大倍数
    adaptive_binarize: bool = False # 自适应二值化

    @classmethod
    def preset(cls, name: str = "default") -> "PreprocessConfig":
        """获取预设配置"""
        presets = {
            "default": cls(),
            "light": cls(  # 轻度处理，保留原图信息
                grayscale=True,
                denoise=True,
                denoise_strength=1,
                contrast_enhance=True,
                contrast_factor=1.2,
            ),
            "strong": cls(  # 强力处理，针对低质量扫描件
                grayscale=True,
                binarize=True,
                binarize_threshold=140,
                denoise=True,
                denoise_strength=2,
                deskew=True,
                contrast_enhance=True,
                contrast_factor=2.0,
                sharpen=True,
                sharpen_factor=1.5,
            ),
            "photo": cls(  # 拍照文档
                grayscale=True,
                adaptive_binarize=True,
                denoise=True,
                denoise_strength=2,
                deskew=True,
                contrast_enhance=True,
                contrast_factor=1.8,
                upscale=True,
                upscale_factor=1.5,
            ),
            "fax": cls(  # 传真/低质量文档
                grayscale=True,
                binarize=True,
                binarize_threshold=160,
                denoise=True,
                denoise_strength=3,
                contrast_enhance=True,
                contrast_factor=2.5,
                sharpen=True,
                sharpen_factor=2.0,
            ),
        }
        if name not in presets:
            raise ValueError(f"未知预设: {name}, 可用: {list(presets.keys())}")
        return presets[name]


def to_grayscale(image: Image.Image) -> Image.Image:
    """灰度化"""
    return image.convert("L")


def binarize(image: Image.Image, threshold: int = 150) -> Image.Image:
    """二值化（全局阈值）"""
    if image.mode != "L":
        image = image.convert("L")
    arr = np.array(image)
    binary = np.where(arr > threshold, 255, 0).astype(np.uint8)
    return Image.fromarray(binary)


def adaptive_binarize(image: Image.Image, block_size: int = 35, C: int = 10) -> Image.Image:
    """自适应二值化（高斯加权平均）

    对光照不均的拍照文档效果更好。
    不依赖 OpenCV，纯 NumPy 实现。
    """
    if image.mode != "L":
        image = image.convert("L")
    arr = np.array(image).astype(np.float32)

    # 用 scipy 的高斯滤波实现自适应阈值
    try:
        from scipy.ndimage import gaussian_filter
        local_mean = gaussian_filter(arr, sigma=block_size / 4.0)
    except ImportError:
        # scipy 不可用时回退到简单均值滤波
        kernel_size = block_size
        kernel = np.ones((kernel_size, kernel_size)) / (kernel_size ** 2)
        try:
            from scipy.ndimage import convolve
            local_mean = convolve(arr, kernel)
        except ImportError:
            # 最后回退：全局阈值
            return binarize(image, threshold=128)

    binary = np.where(arr > local_mean - C, 255, 0).astype(np.uint8)
    return Image.fromarray(binary)


def denoise_image(image: Image.Image, strength: int = 1) -> Image.Image:
    """去噪

    Args:
        image: 输入图像
        strength: 去噪强度 1-3
    """
    if strength <= 1:
        return image.filter(ImageFilter.SMOOTH)
    elif strength == 2:
        img = image.filter(ImageFilter.SMOOTH)
        return img.filter(ImageFilter.SMOOTH_MORE)
    else:  # strength >= 3
        img = image.filter(ImageFilter.MedianFilter(size=3))
        img = img.filter(ImageFilter.SMOOTH_MORE)
        return img


def deskew_image(image: Image.Image, max_angle: float = 15.0) -> Tuple[Image.Image, float]:
    """倾斜校正

    通过检测文本行的倾斜角度来校正。
    简化实现：基于投影剖面法（projection profile method）。

    Returns:
        (校正后图像, 倾斜角度)
    """
    if image.mode != "L":
        gray = image.convert("L")
    else:
        gray = image

    arr = np.array(gray)
    h, w = arr.shape

    # 缩小图像加速计算
    scale = min(1.0, 800 / max(h, w))
    if scale < 1.0:
        small = gray.resize((int(w * scale), int(h * scale)), Image.BILINEAR)
        small_arr = np.array(small)
    else:
        small_arr = arr

    # 在 [-max_angle, max_angle] 范围内搜索最佳角度
    best_angle = 0.0
    best_score = -1

    angles = np.linspace(-max_angle, max_angle, 61)  # 0.5度步长

    for angle in angles:
        # 旋转图像
        rotated = Image.fromarray(small_arr).rotate(
            angle, resample=Image.BILINEAR, fillcolor=255
        )
        rot_arr = np.array(rotated)

        # 计算行方向的投影方差（文本行越水平，方差越大）
        row_mean = rot_arr.mean(axis=1)
        # 反转：文字是暗的，背景是亮的，投影变化对应文字行
        score = np.var(row_mean)

        if score > best_score:
            best_score = score
            best_angle = float(angle)

    # 用最佳角度旋转原图
    corrected = image.rotate(
        best_angle, resample=Image.BICUBIC, fillcolor=255
    )
    return corrected, best_angle


def enhance_contrast(image: Image.Image, factor: float = 1.5) -> Image.Image:
    """对比度增强"""
    enhancer = ImageEnhance.Contrast(image)
    return enhancer.enhance(factor)


def sharpen_image(image: Image.Image, factor: float = 2.0) -> Image.Image:
    """锐化"""
    enhancer = ImageEnhance.Sharpness(image)
    return enhancer.enhance(factor)


def upscale_image(image: Image.Image, factor: float = 1.5) -> Image.Image:
    """放大（低分辨率图片）"""
    w, h = image.size
    return image.resize((int(w * factor), int(h * factor)), Image.LANCZOS)


def preprocess_pipeline(image: Image.Image,
                        config: Optional[PreprocessConfig] = None) -> Tuple[Image.Image, Dict]:
    """完整的预处理流水线

    Args:
        image: 输入图像
        config: 预处理配置，None 则用默认配置

    Returns:
        (处理后图像, 处理信息字典)
    """
    if config is None:
        config = PreprocessConfig()

    info = {
        "steps_applied": [],
        "original_size": image.size,
        "deskew_angle": 0.0,
    }

    img = image.copy()

    # 1. 放大（先放大再处理，效果更好）
    if config.upscale:
        img = upscale_image(img, config.upscale_factor)
        info["steps_applied"].append("upscale")

    # 2. 灰度化
    if config.grayscale:
        img = to_grayscale(img)
        info["steps_applied"].append("grayscale")

    # 3. 去噪
    if config.denoise:
        img = denoise_image(img, config.denoise_strength)
        info["steps_applied"].append(f"denoise(strength={config.denoise_strength})")

    # 4. 倾斜校正（在灰度图上做）
    if config.deskew:
        img, angle = deskew_image(img)
        info["steps_applied"].append(f"deskew(angle={angle:.2f}°)")
        info["deskew_angle"] = angle

    # 5. 对比度增强
    if config.contrast_enhance:
        img = enhance_contrast(img, config.contrast_factor)
        info["steps_applied"].append(f"contrast(factor={config.contrast_factor})")

    # 6. 锐化
    if config.sharpen:
        img = sharpen_image(img, config.sharpen_factor)
        info["steps_applied"].append(f"sharpen(factor={config.sharpen_factor})")

    # 7. 二值化（最后一步）
    if config.adaptive_binarize:
        img = adaptive_binarize(img)
        info["steps_applied"].append("adaptive_binarize")
    elif config.binarize:
        img = binarize(img, config.binarize_threshold)
        info["steps_applied"].append(f"binarize(threshold={config.binarize_threshold})")

    # 确保输出是 RGB（OCR 后端通常期望 RGB）
    if img.mode != "RGB":
        img = img.convert("RGB")

    info["output_size"] = img.size
    return img, info


def generate_preprocess_variants(image: Image.Image) -> Dict[str, Image.Image]:
    """生成多种预处理版本（用于多版本投票选最优）

    这是从原 skill v4 继承的策略：生成 8 种预处理版本，
    分别送入 OCR 引擎，取结果最好的。

    Returns:
        字典: {版本名: 处理后图像}
    """
    results = {}
    results["original"] = image.convert("RGB")

    # 对比度增强
    enh = ImageEnhance.Contrast(image)
    results["contrast_1.5"] = enh.enhance(1.5).convert("RGB")
    results["contrast_2.0"] = enh.enhance(2.0).convert("RGB")

    # 锐化
    sh = ImageEnhance.Sharpness(image)
    results["sharp_2.0"] = sh.enhance(2.0).convert("RGB")

    # 灰度 + 对比度
    gray = image.convert("L")
    ge = ImageEnhance.Contrast(gray).enhance(2.0)
    results["gray_contrast"] = ge.convert("RGB")

    # 去噪 + 对比度
    dn = image.filter(ImageFilter.SMOOTH)
    dn = ImageEnhance.Contrast(dn).enhance(1.8)
    results["denoised"] = dn.convert("RGB")

    # 放大
    w, h = image.size
    results["scaled_1.5x"] = image.resize(
        (int(w * 1.5), int(h * 1.5)), Image.LANCZOS
    ).convert("RGB")

    # 放大 + 对比度增强
    big = image.resize((int(w * 1.5), int(h * 1.5)), Image.LANCZOS)
    big_enh = ImageEnhance.Contrast(big).enhance(1.5)
    results["scaled_enh"] = big_enh.convert("RGB")

    return results

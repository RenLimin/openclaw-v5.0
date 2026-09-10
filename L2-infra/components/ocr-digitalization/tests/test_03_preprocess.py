"""
测试 3: 图像预处理

覆盖：
- 灰度化
- 二值化（全局/自适应）
- 去噪
- 对比度增强
- 锐化
- 放大
- 预设配置
- 完整流水线
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from ocr_engine.preprocess import (
    PreprocessConfig,
    to_grayscale,
    binarize,
    adaptive_binarize,
    denoise_image,
    enhance_contrast,
    sharpen_image,
    upscale_image,
    preprocess_pipeline,
    generate_preprocess_variants,
)
import numpy as np
from PIL import Image


class TestPreprocessConfig:
    def test_default_config(self):
        cfg = PreprocessConfig()
        assert cfg.grayscale is True
        assert cfg.binarize is False
        assert cfg.denoise is True
        assert cfg.contrast_enhance is True

    def test_presets(self):
        presets = ["default", "light", "strong", "photo", "fax"]
        for name in presets:
            cfg = PreprocessConfig.preset(name)
            assert isinstance(cfg, PreprocessConfig)

    def test_invalid_preset(self):
        import pytest
        with pytest.raises(ValueError):
            PreprocessConfig.preset("nonexistent_preset_xyz")


class TestGrayscale:
    def test_basic(self, white_image):
        result = to_grayscale(white_image)
        assert result.mode == "L"

    def test_color_image(self):
        img = Image.new("RGB", (100, 100), color=(255, 0, 0))
        gray = to_grayscale(img)
        assert gray.mode == "L"
        # 红色转灰度后应该是较暗的值
        pixel = gray.getpixel((50, 50))
        assert 0 < pixel < 255


class TestBinarize:
    def test_binarize_white(self, white_image):
        result = binarize(white_image, threshold=150)
        assert result.mode == "L"
        # 全白图应该全部变为 255
        pixel = result.getpixel((10, 10))
        assert pixel == 255

    def test_binarize_black(self):
        img = Image.new("RGB", (100, 100), color="black")
        result = binarize(img, threshold=150)
        pixel = result.getpixel((50, 50))
        assert pixel == 0

    def test_binarize_threshold(self):
        # 灰色值刚好在阈值两边
        img = Image.new("L", (2, 1))
        img.putpixel((0, 0), 100)  # 低于阈值
        img.putpixel((1, 0), 200)  # 高于阈值
        result = binarize(img, threshold=150)
        assert result.getpixel((0, 0)) == 0
        assert result.getpixel((1, 0)) == 255

    def test_adaptive_binarize(self, gradient_image):
        result = adaptive_binarize(gradient_image)
        assert result.mode == "L"
        # 自适应二值化后应该有黑白分布
        arr = np.array(result)
        assert arr.min() == 0
        assert arr.max() == 255


class TestDenoise:
    def test_denoise_returns_image(self, noisy_image):
        result = denoise_image(noisy_image, strength=1)
        assert isinstance(result, Image.Image)

    def test_denoise_strengths(self, noisy_image):
        for strength in [1, 2, 3]:
            result = denoise_image(noisy_image, strength=strength)
            assert isinstance(result, Image.Image)


class TestEnhance:
    def test_contrast(self, gradient_image):
        result = enhance_contrast(gradient_image, factor=2.0)
        assert result.size == gradient_image.size

    def test_contrast_factor_1(self, white_image):
        # factor=1 应该不变
        result = enhance_contrast(white_image, factor=1.0)
        assert result.size == white_image.size

    def test_sharpen(self, gradient_image):
        result = sharpen_image(gradient_image, factor=2.0)
        assert result.size == gradient_image.size


class TestUpscale:
    def test_upscale_size(self, white_image):
        w, h = white_image.size
        result = upscale_image(white_image, factor=2.0)
        assert result.size == (w * 2, h * 2)

    def test_upscale_factor_1(self, white_image):
        result = upscale_image(white_image, factor=1.0)
        assert result.size == white_image.size


class TestPreprocessPipeline:
    def test_default_pipeline(self, white_image):
        result, info = preprocess_pipeline(white_image)
        assert isinstance(result, Image.Image)
        assert "steps_applied" in info
        assert "original_size" in info
        assert "output_size" in info
        assert len(info["steps_applied"]) > 0

    def test_pipeline_returns_rgb(self, white_image):
        result, _ = preprocess_pipeline(white_image)
        assert result.mode == "RGB"

    def test_custom_config(self, white_image):
        cfg = PreprocessConfig(
            grayscale=True,
            denoise=False,
            contrast_enhance=False,
            binarize=True,
            binarize_threshold=128,
        )
        result, info = preprocess_pipeline(white_image, cfg)
        assert result.mode == "RGB"
        assert "grayscale" in info["steps_applied"]
        assert any(s.startswith("binarize") for s in info["steps_applied"])
        assert not any(s.startswith("denoise") for s in info["steps_applied"])


class TestGenerateVariants:
    def test_variant_count(self, white_image):
        variants = generate_preprocess_variants(white_image)
        assert len(variants) == 8
        assert "original" in variants
        assert "contrast_1.5" in variants
        assert "contrast_2.0" in variants
        assert "sharp_2.0" in variants
        assert "gray_contrast" in variants
        assert "denoised" in variants
        assert "scaled_1.5x" in variants
        assert "scaled_enh" in variants

    def test_all_variants_are_rgb(self, white_image):
        variants = generate_preprocess_variants(white_image)
        for name, img in variants.items():
            assert img.mode == "RGB", f"{name} 不是 RGB 模式"
            assert isinstance(img, Image.Image)

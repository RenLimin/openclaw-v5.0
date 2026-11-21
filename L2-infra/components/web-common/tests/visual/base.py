"""
visual/base.py — 视觉回归测试基类 (同步版)
组件: web-common v2.0
用法: 继承 VisualTestBase，设置 url 等参数，调用 assert_visual_match()
注意: 与 pytest-playwright 同步 page fixture 配合，测试方法为普通同步函数
"""

import errno
import os
import socket
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image, ImageChops, ImageDraw
import pytest


class VisualTestBase:
    """视觉回归测试基类

    子类需要设置:
    - url: 测试页面路径（相对于 base_url）或完整 URL
    - [可选] viewport: 视口尺寸 (width, height)，默认 (1440, 900)
    - [可选] threshold: 差异容忍度（百分比），默认 0.1% = 0.001
    - [可选] mask_selectors: 需要隐藏的动态内容 CSS 选择器列表，默认 []
    - [可选] wait_for_selector: 等待该选择器出现再截图，默认 None
    - [可选] base_url: 测试服务器基础 URL，默认 http://127.0.0.1:8000
    - [可选] allowed_status_codes: 允许的 HTTP 状态码集合，默认 {200}。
      错误页测试（如 404 页面视觉验证）应设为 {200, 404}。
    """

    url: str = ""
    base_url: str = "http://127.0.0.1:8000"
    viewport: tuple[int, int] = (1440, 900)
    threshold: float = 0.001  # 0.1% 像素差异容忍
    mask_selectors: list[str] = []
    wait_for_selector: str | None = None
    full_page: bool = False  # 是否整页截图
    settle_time: float = 0.0  # 截图前稳定等待秒数（等图表动画/异步渲染完成）
    allowed_status_codes: set[int] = {200}  # 允许的 HTTP 状态码

    def get_full_url(self) -> str:
        """获取完整测试 URL"""
        if self.url.startswith("http://") or self.url.startswith("file://"):
            return self.url
        return f"{self.base_url.rstrip('/')}/{self.url.lstrip('/')}"

    @staticmethod
    def ensure_http_service_available(full_url: str, timeout: float = 0.5) -> None:
        """视觉测试前置检查：HTTP 服务未启动时 skip，而不是误报页面失败。

        只把 ECONNREFUSED 视为“服务缺失”。服务已监听但返回 4xx/5xx、页面渲染异常、
        HTTP 超时等仍由后续真实浏览器检查暴露，避免用 skip 掩盖产品缺陷。
        """
        parsed = urlparse(full_url)
        if parsed.scheme != "http" or not parsed.hostname:
            return

        port = parsed.port or 80
        try:
            with socket.create_connection((parsed.hostname, port), timeout=timeout):
                pass
        except OSError as exc:
            if isinstance(exc, ConnectionRefusedError) or exc.errno == errno.ECONNREFUSED:
                pytest.skip(
                    f"视觉回归依赖的预览服务未启动，已跳过: {parsed.scheme}://{parsed.hostname}:{port}\n"
                    "请先启动对应组件的预览服务，再运行 visual 测试。"
                )
            raise

    def get_golden_path(self, name: str) -> Path:
        """获取基准图路径"""
        # 按测试类分组存放
        test_name = self.__class__.__name__.lower().replace("test", "").strip("_")
        golden_dir = Path(__file__).parent / "golden" / test_name
        golden_dir.mkdir(parents=True, exist_ok=True)
        suffix = "_full" if self.full_page else ""
        return golden_dir / f"{name}_{self.viewport[0]}x{self.viewport[1]}{suffix}.png"

    def get_diff_path(self, name: str) -> Path:
        """获取差异图输出路径"""
        diff_dir = Path(__file__).parent / "diff"
        diff_dir.mkdir(parents=True, exist_ok=True)
        test_name = self.__class__.__name__.lower().replace("test", "").strip("_")
        suffix = "_full" if self.full_page else ""
        return diff_dir / f"{test_name}_{name}_{self.viewport[0]}x{self.viewport[1]}{suffix}_diff.png"

    @staticmethod
    def compare_images(
        golden_path: Path,
        actual_path: Path,
        threshold: float
    ) -> tuple[bool, float, Image.Image | None]:
        """对比两张图片，返回是否通过、差异比例、差异图

        Returns:
            (passed: bool, diff_ratio: float, diff_image: Image or None)
        """
        golden = Image.open(golden_path).convert("RGB")
        actual = Image.open(actual_path).convert("RGB")

        # 尺寸不同直接失败
        if golden.size != actual.size:
            return False, 1.0, None

        # 像素差异计算
        diff = ImageChops.difference(golden, actual)
        bbox = diff.getbbox()
        if bbox is None:
            # 完全无差异
            return True, 0.0, None

        # 统计差异像素比例
        # 使用直方图计算差异大于 10 的像素数量
        hist = diff.histogram()
        total_pixels = golden.size[0] * golden.size[1]
        diff_pixels = 0
        # 每个通道 256 个值，跳过差异 <= 10 的
        for i, count in enumerate(hist):
            if (i % 256) > 10:
                diff_pixels += count
        # 三个通道，所以除以 3
        diff_ratio = diff_pixels / (total_pixels * 3)

        # 生成差异高亮图（左: golden | 中: actual | 右: diff 红框）
        if diff_ratio > threshold:
            width, height = golden.size
            diff_image = Image.new("RGB", (width * 3, height))
            diff_image.paste(golden, (0, 0))
            diff_image.paste(actual, (width, 0))
            diff_image.paste(diff, (width * 2, 0))

            # 在第三张图上用红框标出差异区域
            draw = ImageDraw.Draw(diff_image)
            x0, y0, x1, y1 = bbox
            draw.rectangle(
                [(width * 2 + x0, y0), (width * 2 + x1, y1)],
                outline=(255, 0, 0),
                width=2
            )
            return False, diff_ratio, diff_image

        return True, diff_ratio, None

    def mask_dynamic_content(self, page):
        """隐藏动态内容区域，避免误报

        对不同类型元素采用不同策略：
        - canvas / svg: 用 visibility:hidden 隐藏，保留布局占位但不参与像素对比
        - 动态文本/图片: 清空内容 + 半透明黑色背景
        """
        for selector in self.mask_selectors:
            page.evaluate("""(selector) => {
                document.querySelectorAll(selector).forEach(el => {
                    const tag = el.tagName;
                    if (tag === 'CANVAS' || tag === 'SVG') {
                        // 图表类元素：隐藏渲染内容，保留布局占位
                        el.style.visibility = 'hidden';
                    } else {
                        el.style.backgroundColor = '#000000';
                        el.style.opacity = '0.5';
                        el.textContent = '';
                    }
                });
            }""", selector)

    def assert_visual_match(self, page, name: str):
        """截图并与基准图对比，断言视觉一致（同步版）"""
        golden_path = self.get_golden_path(name)

        full_url = self.get_full_url()

        # 预览服务缺失属于环境未就绪，应显式 skip；不能让浏览器把 ERR_CONNECTION_REFUSED
        # 记成视觉回归失败。服务存在时，后续仍执行真实 HTTP/像素校验。
        self.ensure_http_service_available(full_url)

        # 设置视口
        page.set_viewport_size({"width": self.viewport[0], "height": self.viewport[1]})

        # 导航到测试页面
        response = page.goto(full_url, wait_until="networkidle")

        # HTTP 状态码校验：非允许状态码一律视为失败，禁止错误页存为基准图
        if response is None:
            pytest.fail(f"页面无响应: {full_url}")
        status = response.status
        if status not in self.allowed_status_codes:
            pytest.fail(
                f"页面返回非允许状态码 ({status})，拒绝作为视觉基准: {full_url}\n"
                f"请检查路由是否真实存在，或服务是否正常启动"
            )

        # 等待指定元素出现
        if self.wait_for_selector:
            page.wait_for_selector(self.wait_for_selector, timeout=5000)

        # 处理动态内容 mask
        self.mask_dynamic_content(page)

        # 等待动态内容稳定（图表动画/异步渲染）
        if self.settle_time > 0:
            page.wait_for_timeout(int(self.settle_time * 1000))

        # 截图
        screenshot = page.screenshot(full_page=self.full_page)
        actual_path = golden_path.with_suffix(".actual.png")
        with open(actual_path, "wb") as f:
            f.write(screenshot)

        # 如果基准图不存在，保存当前截图作为基准，通过测试
        if not golden_path.exists():
            os.rename(actual_path, golden_path)
            pytest.skip(f"基准图 {golden_path} 不存在，已保存当前截图作为基准")
            return  # unreachable

        # 对比基准图和实际截图
        passed, diff_ratio, diff_image = self.compare_images(
            golden_path, actual_path, self.threshold
        )

        # 如果差异超过阈值，保存差异图
        if not passed:
            diff_path = self.get_diff_path(name)
            if diff_image:
                diff_image.save(diff_path)

            pytest.fail(
                f"视觉差异超过阈值 ({diff_ratio:.2%} > {self.threshold:.2%})\n"
                f"基准图: {golden_path}\n"
                f"差异图: {diff_path}"
            )

        # 清理实际截图
        if actual_path.exists():
            os.remove(actual_path)

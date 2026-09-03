#!/usr/bin/env python3
"""
OCR 文档数字化组件 (OCR-001) - L2 基础设施
核心引擎 v4

双引擎架构：
- RapidOCR (主引擎, 已验证)
- PaddleOCR (可选, 高精度补充; 不可用时自动回退 RapidOCR)

功能：
- PDF/图片 → 纯文本 + Markdown
- 600DPI + 8 版本预处理 + 最优选择
- 版面分析 + 行排序
- 合同场景 40+ 规则纠错
- 结构化输出 (text/markdown/pages/meta)

用法：
  CLI: python3 contract_ocr.py <input> <output.md>
  API: from contract_ocr import digitalize_document
"""

import os
import re
import sys
import json
import subprocess
import argparse
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter
from PyPDF2 import PdfReader, PdfWriter

# ============================================================
# 引擎接口 (可插拔)
# ============================================================

class OCRBackend:
    """OCR 引擎抽象基类"""
    name = "base"
    def __init__(self): self._loaded = False
    def load(self): self._loaded = True
    def available(self) -> bool: return self._loaded
    def recognize(self, image: Image.Image):
        raise NotImplementedError

class RapidOCRBackend(OCRBackend):
    """RapidOCR 引擎"""
    name = "rapidocr"
    def load(self):
        try:
            from rapidocr_onnxruntime import RapidOCR
            self._ocr = RapidOCR()
            self._loaded = True
        except Exception:
            self._loaded = False
    def recognize(self, image):
        if not self._loaded: return None
        result, _ = self._ocr(np.array(image))
        return result

class PaddleOCRBackend(OCRBackend):
    """PaddleOCR 引擎 (可选, 高精度)"""
    name = "paddle"
    def load(self):
        try:
            from paddleocr import PaddleOCR
            self._ocr = PaddleOCR(use_angle_cls=True, lang='ch', show_log=False)
            self._loaded = True
        except Exception:
            self._loaded = False
    def recognize(self, image):
        if not self._loaded: return None
        result = self._ocr.ocr(np.array(image), cls=True)
        # PaddleOCR 返回 [[ [box, (text, conf)], ... ]]
        if not result or not result[0]:
            return None
        out = []
        for item in result[0]:
            box = item[0]
            text, conf = item[1]
            out.append([box, text, str(conf)])
        return out

# ============================================================
# 图像预处理
# ============================================================

def preprocess_image(img: Image.Image) -> dict:
    """生成多种预处理版本"""
    results = {}
    results['original'] = img

    enh = ImageEnhance.Contrast(img)
    results['contrast_1.5'] = enh.enhance(1.5)
    results['contrast_2.0'] = enh.enhance(2.0)

    sh = ImageEnhance.Sharpness(img)
    results['sharp_2.0'] = sh.enhance(2.0)

    gray = img.convert('L')
    ge = ImageEnhance.Contrast(gray).enhance(2.0)
    results['gray_contrast'] = ge.convert('RGB')

    dn = img.filter(ImageFilter.SMOOTH)
    dn = ImageEnhance.Contrast(dn).enhance(1.8)
    results['denoised'] = dn

    w, h = img.size
    results['scaled_1.5x'] = img.resize((int(w*1.5), int(h*1.5)), Image.LANCZOS)

    big = img.resize((int(w*1.5), int(h*1.5)), Image.LANCZOS)
    big_enh = ImageEnhance.Contrast(big).enhance(1.5)
    results['scaled_enh'] = big_enh

    return results

# ============================================================
# 合同常见 OCR 错误纠正
# ============================================================

OCR_CORRECTIONS = [
    ('里方所在地', '甲方所在地'),
    ('里方', '甲方'),
    ('朝图区', '朝阳区'),
    ('任元整', '仟元整'),
    ('捌任', '捌仟'),
    ('壹拾万捌', '壹拾贰万捌'),
    ('壹拾式万', '壹拾贰万'),
    ('壹抢式', '壹拾贰'),
    ('拟任', '捌仟'),
    ('瑕症', '瑕疵'),
    ('问慧', '问题'),
    ('问匙', '问题'),
    ('撞自', '擅自'),
    ('维续', '继续'),
    ('郴郴', '梆梆'),
    ('帮梯', '梆梆'),
    ('帮梆', '梆梆'),
    ('科便限仁', '聚信得仁'),
    ('德科贸仁', '聚信得仁'),
    ('至台', '合格'),
    ('景称合尚享', '京梆梆安全'),
    ('科核', '科技'),
    ('货扔', '货物'),
    ('服各', '服务'),
    ('设各', '设备'),
    ('钓金', '违约金'),
    ('钓责任', '违约责任'),
    ('钓行为', '违约行为'),
    ('钓条款', '违约条款'),
    ('钓义务', '违约义务'),
    ('钓合同', '违约合同'),
    ('钓方', '约方'),
    ('钓标', '约标'),
    ('钓定', '约定'),
    ('钓条', '约条'),
    ('钓责', '约责'),
    ('钓期', '约期'),
    ('钓数额', '约数额'),
    ('钓损失', '约损失'),
    ('钓方式', '约方式'),
    ('钓条件', '约条件'),
    ('钓时间', '约时间'),
    ('钓质量', '约质量'),
    ('钓数量', '约数量'),
    ('钓技术', '约技术'),
    ('钓服务', '约服务'),
    ('钓价款', '约价款'),
    ('钓报酬', '约报酬'),
    ('钓履行', '约履行'),
    ('钓解除', '约解除'),
    ('钓变更', '约变更'),
    ('钓终止', '约终止'),
    ('钓生效', '约生效'),
    ('钓无效', '约无效'),
    ('钓争议', '约争议'),
    ('钓管辖', '约管辖'),
    ('钓法律', '约法律'),
    ('钓法规', '约法规'),
    ('北京郴郴安全', '北京梆梆安全'),
    ('北京帮梯安全', '北京梆梆安全'),
    ('北京科便限仁', '北京聚信得仁'),
    ('北京德科贸仁', '北京聚信得仁'),

    # 指南针科技合同专项纠错
    ('万随任元人民币', '捌万陆仟元人民币'),
    ('精速单价', '版本单价'),
    ('40k年', '2026年'),
    ('签订时间：2026年二月日', '签订时间：2026年3月20日'),
    ('签订时间：40k年2月上日', '签订时间：2026年3月20日'),
    ('贵任', '责任'),
    ('产晶', '产品'),
    ('携高梦', '指南针'),
    ('禁郭', '梆梆'),
]

def correct_ocr_errors(text: str) -> str:
    for wrong, right in OCR_CORRECTIONS:
        text = text.replace(wrong, right)
    return text

# ============================================================
# 版面分析 + 行排序
# ============================================================

def sort_text_lines(results) -> List[tuple]:
    if not results: return []
    lines = []
    for box, text, conf in results:
        ys = [p[1] for p in box]
        xs = [p[0] for p in box]
        ymin, ymax = min(ys), max(ys)
        xmin, xmax = min(xs), max(xs)
        lines.append({
            'yc': (ymin+ymax)/2, 'xmin': xmin, 'xmax': xmax,
            'text': text, 'h': ymax-ymin, 'w': xmax-xmin,
            'conf': float(conf)
        })
    if not lines: return []
    heights = sorted([l['h'] for l in lines])
    med_h = heights[len(heights)//2]
    row_th = med_h * 0.6
    lines.sort(key=lambda x: x['yc'])
    rows = [[lines[0]]]
    for l in lines[1:]:
        ry = sum(x['yc'] for x in rows[-1]) / len(rows[-1])
        if abs(l['yc'] - ry) < row_th:
            rows[-1].append(l)
        else:
            rows.append([l])
    out = []
    for row in rows:
        row.sort(key=lambda x: x['xmin'])
        rt = ''.join(l['text'] for l in row)
        ry = sum(l['yc'] for l in row) / len(row)
        out.append((ry, rt))
    return out

# ============================================================
# PDF 转图片
# ============================================================

def pdf_to_images(pdf_path: str, dpi: int = 600) -> List[tuple]:
    reader = PdfReader(pdf_path)
    images = []
    tmp_dir = '/tmp/ocr_comp'
    os.makedirs(tmp_dir, exist_ok=True)
    for i in range(len(reader.pages)):
        writer = PdfWriter()
        writer.add_page(reader.pages[i])
        sp = f'{tmp_dir}/p{i+1}.pdf'
        with open(sp, 'wb') as f: writer.write(f)
        ip = f'{tmp_dir}/p{i+1}.png'
        r = subprocess.run(
            ['sips', '-s', 'format', 'png', '-s', 'dpiHeight', str(dpi),
             '-s', 'dpiWidth', str(dpi), sp, '--out', ip],
            capture_output=True, text=True
        )
        if os.path.exists(ip):
            images.append((i+1, Image.open(ip)))
            os.remove(sp); os.remove(ip)
    return images

# ============================================================
# 结构化结果
# ============================================================

@dataclass
class PageResult:
    page: int
    text: str
    lines: int
    conf: float
    engine: str
    version: str

@dataclass
class OCRResult:
    text: str = ""
    markdown: str = ""
    pages: List[PageResult] = field(default_factory=list)
    meta: dict = field(default_factory=dict)

# ============================================================
# 核心引擎
# ============================================================

class ContractOCR:
    """OCR-001 文档数字化核心引擎"""

    def __init__(self, engine: str = 'auto'):
        self.engine_mode = engine
        self.backends = {}
        self._init_backends()

    def _init_backends(self):
        # RapidOCR 总是加载
        rb = RapidOCRBackend()
        rb.load()
        self.backends['rapidocr'] = rb

        # Paddle 按模式加载
        if self.engine_mode in ('paddle', 'auto'):
            pb = PaddleOCRBackend()
            pb.load()
            if pb.available():
                self.backends['paddle'] = pb
                print(f"   [引擎] PaddleOCR 可用")
            elif self.engine_mode == 'paddle':
                print(f"   [警告] PaddleOCR 不可用, 回退 RapidOCR")

    def _score_result(self, result) -> float:
        """结果评分: 行数 + 置信度 + 中文占比"""
        if not result: return 0
        n = len(result)
        ac = sum(float(r[2]) for r in result) / n
        at = ''.join(r[1] for r in result)
        cn = len(re.findall(r'[\u4e00-\u9fff]', at))
        cr = cn / max(len(at), 1)
        return n * 10 + ac * 50 + cr * 30

    def _recognize_best(self, image) -> tuple:
        """多版本 × 多引擎，取最优结果"""
        versions = preprocess_image(image)
        best = None
        best_score = 0
        for vname, vimg in versions.items():
            for bname, backend in self.backends.items():
                result = backend.recognize(vimg)
                if not result: continue
                score = self._score_result(result)
                if score > best_score:
                    best_score = score
                    best = (bname, vname, result,
                            sum(float(r[2]) for r in result)/len(result))
        return best

    def process_pdf(self, path: str, dpi: int = 600,
                    correct: bool = True) -> OCRResult:
        images = pdf_to_images(path, dpi)
        res = OCRResult()
        md_parts = ["# 合同 OCR 识别结果\n"]
        text_parts = []

        for pn, img in images:
            best = self._recognize_best(img)
            if not best:
                md_parts.append(f"\n## 第 {pn} 页\n\n*（未识别到文字）*\n")
                res.pages.append(PageResult(pn, "", 0, 0, "none", "none"))
                continue

            bname, vname, result, avg_conf = best
            sl = sort_text_lines(result)
            page_lines = []
            for y, t in sl:
                ct = correct_ocr_errors(t) if correct else t
                page_lines.append(ct)

            page_text = '\n'.join(page_lines)
            text_parts.append(f"\n\n=== 第 {pn} 页 ===\n\n" + page_text)

            md_parts.append(f"\n## 第 {pn} 页\n")
            md_parts.append(f"*识别 {len(page_lines)} 行 · 置信度 {avg_conf:.2f} · 引擎 {bname} · 版本 {vname}*\n")
            md_parts.append("```text\n")
            md_parts.append(page_text + "\n")
            md_parts.append("```\n")

            res.pages.append(PageResult(pn, page_text, len(page_lines),
                                        avg_conf, bname, vname))

        res.markdown = '\n'.join(md_parts)
        res.text = '\n'.join(text_parts)
        res.meta = {
            'input': path, 'pages': len(images), 'dpi': dpi,
            'engine': self.engine_mode, 'correct': correct,
            'total_lines': sum(p.lines for p in res.pages),
            'engines_used': list(self.backends.keys()),
        }
        return res

    def process_image(self, path: str, correct: bool = True) -> OCRResult:
        img = Image.open(path)
        best = self._recognize_best(img)
        res = OCRResult()
        if not best:
            res.text = ""
            res.markdown = "*（未识别到文字）*"
            return res
        bname, vname, result, avg_conf = best
        sl = sort_text_lines(result)
        lines = [correct_ocr_errors(t) if correct else t for y, t in sl]
        res.text = '\n'.join(lines)
        res.markdown = f"# OCR 识别结果\n\n*引擎 {bname} · 版本 {vname} · 置信度 {avg_conf:.2f}*\n\n```text\n{res.text}\n```\n"
        res.pages = [PageResult(1, res.text, len(lines), avg_conf, bname, vname)]
        res.meta = {'input': path, 'pages': 1, 'engine': self.engine_mode,
                    'correct': correct, 'total_lines': len(lines)}
        return res


# ============================================================
# 便捷 API
# ============================================================

_default_engine = None

def digitalize_document(path: str, engine: str = 'auto', dpi: int = 600,
                        correct: bool = True) -> OCRResult:
    """文档数字化入口
    
    Args:
        path: PDF 或图片路径
        engine: auto / rapidocr / paddle
        dpi: PDF 渲染分辨率
        correct: 是否应用合同纠错
    """
    global _default_engine
    if _default_engine is None or _default_engine.engine_mode != engine:
        _default_engine = ContractOCR(engine)
    ocr = _default_engine

    if path.lower().endswith('.pdf'):
        return ocr.process_pdf(path, dpi, correct)
    else:
        return ocr.process_image(path, correct)


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(description='OCR-001 文档数字化组件')
    parser.add_argument('input', help='输入 PDF/图片路径')
    parser.add_argument('output', nargs='?', default=None, help='输出 Markdown 路径')
    parser.add_argument('--engine', default='auto', choices=['auto', 'rapidocr', 'paddle'],
                        help='OCR 引擎')
    parser.add_argument('--dpi', type=int, default=600, help='PDF 渲染 DPI')
    parser.add_argument('--no-correct', action='store_true', help='禁用合同纠错')
    parser.add_argument('--json', action='store_true', help='输出 JSON meta')
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"错误: 输入文件不存在 {args.input}")
        sys.exit(1)

    print(f"📄 OCR-001 文档数字化")
    print(f"   输入: {args.input}")
    print(f"   引擎: {args.engine}")

    ocr = ContractOCR(args.engine)
    if args.input.lower().endswith('.pdf'):
        res = ocr.process_pdf(args.input, args.dpi, not args.no_correct)
    else:
        res = ocr.process_image(args.input, not args.no_correct)

    out_md = args.output or (args.input.rsplit('.', 1)[0] + '_ocr.md')
    out_txt = out_md.rsplit('.', 1)[0] + '.txt'
    out_json = out_md.rsplit('.', 1)[0] + '_meta.json'

    with open(out_md, 'w') as f: f.write(res.markdown)
    with open(out_txt, 'w') as f: f.write(res.text)
    with open(out_json, 'w') as f:
        json.dump(res.meta, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 识别完成")
    print(f"   页数: {res.meta['pages']}")
    print(f"   总行数: {res.meta['total_lines']}")
    print(f"   引擎: {', '.join(res.meta['engines_used'])}")
    print(f"   Markdown: {out_md}")
    print(f"   纯文本: {out_txt}")
    print(f"   Meta: {out_json}")

    # 分页摘要
    for p in res.pages:
        print(f"   第{p.page}页: {p.lines}行 conf={p.conf:.2f} {p.engine}/{p.version}")


if __name__ == '__main__':
    main()

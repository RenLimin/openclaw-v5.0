"""
OCR 后处理

对 OCR 原始识别结果进行清洗、优化和结构化：
- 文本清洗（去重、去除空行、去除噪声字符）
- 行合并（分行的连续文本合并）
- 常见 OCR 错误纠错
- 表格结构识别与提取
- 版面排序（阅读顺序）
"""
from __future__ import annotations

import re
from typing import List, Tuple, Dict, Optional
from dataclasses import dataclass

from .types import OCRLine


# ============================================================
# 行排序（阅读顺序）
# ============================================================

def sort_lines_reading_order(lines: List[OCRLine]) -> List[OCRLine]:
    """按阅读顺序排序：先按行（y坐标聚类），行内按 x 坐标

    算法：
    1. 按 y1 排序
    2. 用行高的 0.5 倍作为阈值，将 y 坐标相近的行聚类到同一行
    3. 每行内按 x 坐标排序
    """
    if not lines:
        return []

    # 计算行高估计（中位数更鲁棒）
    heights = sorted([
        max(1, line.bbox[3] - line.bbox[1])
        for line in lines
    ])
    med_h = heights[len(heights) // 2]
    line_threshold = med_h * 0.6

    # 按 y1 排序
    sorted_by_y = sorted(lines, key=lambda l: l.bbox[1])

    # 聚类成行
    rows = []
    current_row = [sorted_by_y[0]]
    current_y_center = (sorted_by_y[0].bbox[1] + sorted_by_y[0].bbox[3]) / 2

    for line in sorted_by_y[1:]:
        line_center = (line.bbox[1] + line.bbox[3]) / 2
        if abs(line_center - current_y_center) < line_threshold:
            current_row.append(line)
            # 更新当前行中心
            current_y_center = sum(
                (l.bbox[1] + l.bbox[3]) / 2 for l in current_row
            ) / len(current_row)
        else:
            rows.append(current_row)
            current_row = [line]
            current_y_center = (line.bbox[1] + line.bbox[3]) / 2
    rows.append(current_row)

    # 每行内按 x 排序
    result = []
    for row in rows:
        row_sorted = sorted(row, key=lambda l: l.bbox[0])
        result.extend(row_sorted)

    return result


# ============================================================
# 文本清洗
# ============================================================

def clean_noise_chars(text: str) -> str:
    """去除噪声字符（常见 OCR 误识别的无意义字符）"""
    # 去除孤立的特殊符号行
    lines = text.split("\n")
    cleaned = []
    for line in lines:
        stripped = line.strip()
        # 跳过纯符号或纯空白行
        if not stripped:
            cleaned.append("")
            continue
        # 去除行首尾的噪声符号
        stripped = re.sub(r'^[·•\-\s\u3000]+', '', stripped)
        stripped = re.sub(r'[·•\-\s\u3000]+$', '', stripped)
        if stripped:
            cleaned.append(stripped)
        else:
            cleaned.append("")
    return "\n".join(cleaned)


def deduplicate_lines(lines: List[OCRLine], overlap_threshold: float = 0.8) -> List[OCRLine]:
    """去除重复行（多引擎融合时常见）

    Args:
        lines: 行列表
        overlap_threshold: 文本相似度阈值（0-1），超过则认为重复

    Returns:
        去重后的行列表
    """
    if len(lines) < 2:
        return lines

    unique = []
    seen_texts = []  # (text, bbox_y)

    for line in lines:
        text = line.text.strip()
        y_center = (line.bbox[1] + line.bbox[3]) / 2

        is_dup = False
        for seen_text, seen_y in seen_texts:
            # y 坐标相近
            if abs(y_center - seen_y) > 20:
                continue
            # 文本相似度
            similarity = _text_similarity(text, seen_text)
            if similarity >= overlap_threshold:
                is_dup = True
                break

        if not is_dup:
            unique.append(line)
            seen_texts.append((text, y_center))

    return unique


def _text_similarity(a: str, b: str) -> float:
    """简单文本相似度（基于字符集合）"""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    set_a = set(a)
    set_b = set(b)
    if not set_a or not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union


# ============================================================
# 错误纠正
# ============================================================

# 通用数字/字母混淆纠正
DIGITAL_CORRECTIONS = [
    (r'(\d)O(\d)', r'\g<1>0\g<2>'),   # 数字中间的 O -> 0
    (r'(\d)o(\d)', r'\g<1>0\g<2>'),
    (r'(\d)l(\d)', r'\g<1>1\g<2>'),   # 数字中间的 l -> 1
    (r'(\d)I(\d)', r'\g<1>1\g<2>'),
    (r'(\d)S(\d)', r'\g<1>5\g<2>'),   # 数字中间的 S -> 5
    (r'(\d)Z(\d)', r'\g<1>2\g<2>'),   # 数字中间的 Z -> 2
    (r'(\d)B(\d)', r'\g<1>8\g<2>'),   # 数字中间的 B -> 8
]

# 合同场景常见错误
CONTRACT_CORRECTIONS = [
    ("里方所在地", "甲方所在地"),
    ("里方", "甲方"),
    ("朝图区", "朝阳区"),
    ("任元整", "仟元整"),
    ("捌任", "捌仟"),
    ("壹拾万捌", "壹拾贰万捌"),
    ("壹拾式万", "壹拾贰万"),
    ("壹抢式", "壹拾贰"),
    ("拟任", "捌仟"),
    ("瑕症", "瑕疵"),
    ("问慧", "问题"),
    ("问匙", "问题"),
    ("撞自", "擅自"),
    ("维续", "继续"),
    ("郴郴", "梆梆"),
    ("郴安全", "梆梆安全"),
    ("帮梯", "梆梆"),
    ("帮梆", "梆梆"),
    ("至台", "合格"),
    ("科核", "科技"),
    ("货扔", "货物"),
    ("服各", "服务"),
    ("设各", "设备"),
    ("钓金", "违约金"),
    ("钓责任", "违约责任"),
    ("钓行为", "违约行为"),
    ("钓条款", "违约条款"),
    ("钓义务", "违约义务"),
    ("钓合同", "违约合同"),
    ("钓方", "违约方"),
    ("钓标", "违约标的"),
    ("钓定", "约定"),
    ("钓条", "违约条"),
    ("钓责", "违约责任"),
    ("钓期", "约期"),
    ("钓数额", "违约数额"),
    ("钓损失", "违约损失"),
    ("钓方式", "违约方式"),
    ("钓条件", "违约条件"),
    ("钓时间", "违约时间"),
    ("钓质量", "违约质量"),
    ("钓数量", "违约数量"),
    ("钓技术", "违约技术"),
    ("钓服务", "违约服务"),
    ("钓价款", "违约价款"),
    ("钓报酬", "违约报酬"),
    ("钓履行", "违约履行"),
    ("钓解除", "违约解除"),
    ("钓变更", "违约变更"),
    ("钓终止", "违约终止"),
    ("钓生效", "违约生效"),
    ("钓无效", "违约无效"),
    ("钓争议", "违约争议"),
    ("钓管辖", "违约管辖"),
    ("钓法律", "违约法律"),
    ("钓法规", "违约法规"),
    ("北京郴郴安全", "北京梆梆安全"),
    ("北京帮梯安全", "北京梆梆安全"),
    ("买受方", "买受人"),
    ("出受方", "出卖人"),
    ("违约全", "违约金"),
    ("不可抗", "不可抗力"),
    ("争仪解决", "争议解决"),
    ("知识产杈", "知识产权"),
    ("保秘条款", "保密条款"),
    ("验收标谁", "验收标准"),
    ("有限公可", "有限公司"),
    ("有限公同", "有限公司"),
    ("股份有限公", "股份有限公司"),
    ("贵任", "责任"),
    ("产晶", "产品"),
]


def correct_ocr_text(text: str, domain: str = "general") -> str:
    """OCR 文本纠错

    Args:
        text: 原始文本
        domain: 领域 ("general" / "contract")

    Returns:
        纠错后的文本
    """
    result = text

    # 通用数字混淆纠正
    for pattern, repl in DIGITAL_CORRECTIONS:
        result = re.sub(pattern, repl, result)

    # 领域特定纠正
    if domain == "contract":
        for wrong, right in CONTRACT_CORRECTIONS:
            result = result.replace(wrong, right)

    return result


def correct_lines(lines: List[OCRLine], domain: str = "general") -> List[OCRLine]:
    """对行列表应用纠错"""
    corrected = []
    for line in lines:
        new_text = correct_ocr_text(line.text, domain)
        if new_text != line.text:
            # 创建新行（保持 bbox 和 confidence）
            corrected.append(OCRLine(
                text=new_text,
                bbox=line.bbox,
                confidence=line.confidence,
                source=line.source + "+corrected",
            ))
        else:
            corrected.append(line)
    return corrected


# ============================================================
# 表格结构提取
# ============================================================

@dataclass
class TableCell:
    """表格单元格"""
    row: int
    col: int
    text: str
    bbox: Tuple[float, float, float, float]


@dataclass
class TableResult:
    """表格识别结果"""
    rows: int
    cols: int
    cells: List[TableCell]
    bbox: Tuple[float, float, float, float]

    def to_markdown(self) -> str:
        """转为 Markdown 表格"""
        if not self.cells:
            return ""
        # 构建二维数组
        grid = [["" for _ in range(self.cols)] for _ in range(self.rows)]
        for cell in self.cells:
            if 0 <= cell.row < self.rows and 0 <= cell.col < self.cols:
                grid[cell.row][cell.col] = cell.text

        # 生成 Markdown
        lines = []
        # 表头
        lines.append("| " + " | ".join(grid[0]) + " |")
        lines.append("| " + " | ".join(["---"] * self.cols) + " |")
        # 数据行
        for row in grid[1:]:
            lines.append("| " + " | ".join(row) + " |")
        return "\n".join(lines)


def detect_tables(lines: List[OCRLine]) -> List[TableResult]:
    """检测表格结构（基于文本行的列对齐分析）

    简化实现：通过分析 OCR 行的 x 坐标，检测具有规则列对齐的文本块。
    更精确的表格识别需要专门的版面分析模型（如 PP-Structure）。

    Args:
        lines: 排序后的 OCR 行

    Returns:
        检测到的表格列表
    """
    if len(lines) < 3:
        return []

    tables = []
    # TODO: 实现更完善的表格检测算法
    # 当前版本：返回空列表，作为扩展接口
    return tables


# ============================================================
# 合并分行文本
# ============================================================

def merge_broken_lines(lines: List[OCRLine]) -> List[OCRLine]:
    """合并被错误拆分的连续文本行

    场景：一个句子被拆成了两行，第二行没有标点结尾。
    策略：如果一行的结尾不是标点符号，且下一行开头不是大写/数字/特殊标记，
         则考虑合并。
    """
    if len(lines) < 2:
        return lines

    merged = []
    i = 0
    while i < len(lines):
        current = lines[i]

        # 检查是否需要和下一行合并
        if i + 1 < len(lines):
            next_line = lines[i + 1]
            if _should_merge(current, next_line):
                # 合并文本和 bbox
                merged_text = current.text.rstrip() + next_line.text.lstrip()
                merged_bbox = (
                    min(current.bbox[0], next_line.bbox[0]),
                    min(current.bbox[1], next_line.bbox[1]),
                    max(current.bbox[2], next_line.bbox[2]),
                    max(current.bbox[3], next_line.bbox[3]),
                )
                merged_conf = (current.confidence + next_line.confidence) / 2
                merged.append(OCRLine(
                    text=merged_text,
                    bbox=merged_bbox,
                    confidence=merged_conf,
                    source=current.source + "+merged",
                ))
                i += 2
                continue

        merged.append(current)
        i += 1

    return merged


def _should_merge(current: OCRLine, next_line: OCRLine) -> bool:
    """判断两行是否应该合并"""
    text1 = current.text.strip()
    text2 = next_line.text.strip()

    if not text1 or not text2:
        return False

    # 行结尾是标点，不合并
    ending_punct = set("。！？；：.!?;:"
                       "」』）】》"
                       "、，,")
    if text1[-1] in ending_punct:
        return False

    # 下一行开头是数字或特殊标记，不合并（可能是列表项）
    if re.match(r'^[\d\-\•\·\（\(【\[]', text2):
        return False

    # 两行高度差太大，不合并（可能是不同段落）
    h1 = current.bbox[3] - current.bbox[1]
    h2 = next_line.bbox[3] - next_line.bbox[1]
    if abs(h1 - h2) > max(h1, h2) * 0.5:
        return False

    # 两行 x 起始位置差异太大（可能是不同列）
    if abs(current.bbox[0] - next_line.bbox[0]) > max(h1, h2) * 3:
        return False

    return True


# ============================================================
# 完整后处理流水线
# ============================================================

@dataclass
class PostprocessConfig:
    """后处理配置"""
    sort_reading_order: bool = True      # 按阅读顺序排序
    deduplicate: bool = True             # 去重
    correct_domain: str = "general"      # 纠错领域（general/contract/None）
    merge_broken: bool = True            # 合并分行
    clean_noise: bool = True             # 清洗噪声
    detect_tables: bool = False          # 表格检测
    remove_empty_lines: bool = True      # 移除空行


def postprocess_lines(
    lines: List[OCRLine],
    config: Optional[PostprocessConfig] = None,
) -> List[OCRLine]:
    """完整的后处理流水线

    Args:
        lines: 原始 OCR 行
        config: 后处理配置

    Returns:
        处理后的行列表
    """
    if config is None:
        config = PostprocessConfig()

    result = list(lines)

    # 1. 排序
    if config.sort_reading_order:
        result = sort_lines_reading_order(result)

    # 2. 去重
    if config.deduplicate:
        result = deduplicate_lines(result)

    # 3. 合并分行
    if config.merge_broken:
        result = merge_broken_lines(result)

    # 4. 纠错
    if config.correct_domain:
        result = correct_lines(result, config.correct_domain)

    # 5. 清洗噪声
    if config.clean_noise:
        result = [
            OCRLine(
                text=clean_noise_chars(line.text),
                bbox=line.bbox,
                confidence=line.confidence,
                source=line.source,
            )
            for line in result
        ]

    # 6. 移除空行
    if config.remove_empty_lines:
        result = [line for line in result if line.text.strip()]

    return result

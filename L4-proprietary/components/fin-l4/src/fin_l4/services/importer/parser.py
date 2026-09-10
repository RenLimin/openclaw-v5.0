"""流水解析引擎 — 支持 CSV/Excel + 多银行模板 + 自动识别"""

import csv
import io
import os
import re
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from decimal import Decimal, InvalidOperation
from pathlib import Path
import hashlib

try:
    import yaml
except ImportError:
    yaml = None

try:
    import openpyxl
except ImportError:
    openpyxl = None


TEMPLATE_DIR = Path(__file__).parent / "bank_templates"


@dataclass
class ParsedTransaction:
    """解析后的交易记录（中间格式）"""
    txn_date: str = ""          # YYYY-MM-DD
    txn_time: str = ""          # HH:MM:SS
    amount: Decimal = Decimal("0")
    direction: str = ""         # income / expense / unknown
    currency: str = "CNY"
    counterparty: str = ""
    counterparty_account: str = ""
    summary: str = ""
    product: str = ""
    category: str = ""
    balance: str = ""
    txn_type: str = ""
    status: str = ""
    source_bank: str = ""       # cmb / icbc / alipay / wechat
    raw_row: Dict = field(default_factory=dict)
    row_num: int = 0
    error: str = ""

    @property
    def is_valid(self) -> bool:
        return not self.error and self.txn_date and self.amount != 0

    def import_hash(self, family_id: str) -> str:
        """去重哈希：日期 + 金额 + 方向 + 对方 + 摘要"""
        raw = "|".join([
            family_id,
            self.txn_date,
            str(self.amount),
            self.direction,
            self.counterparty,
            self.summary,
        ])
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


@dataclass
class BankTemplate:
    """银行模板配置"""
    bank_id: str
    bank_name: str
    encoding: List[str]
    skip_rows: int
    has_header: bool
    column_mapping: Dict[str, List[str]]
    direction_rules: Dict
    detection: Dict

    @classmethod
    def from_yaml(cls, path: Path) -> 'BankTemplate':
        if yaml is None:
            raise ImportError("PyYAML not installed")
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return cls(
            bank_id=data["bank_id"],
            bank_name=data["bank_name"],
            encoding=data.get("encoding", ["utf-8"]),
            skip_rows=data.get("skip_rows", 0),
            has_header=data.get("has_header", True),
            column_mapping=data.get("column_mapping", {}),
            direction_rules=data.get("direction_rules", {}),
            detection=data.get("detection", {}),
        )


def load_templates(template_dir: Path = None) -> List[BankTemplate]:
    """加载所有银行模板"""
    if template_dir is None:
        template_dir = TEMPLATE_DIR
    templates = []
    for f in sorted(template_dir.glob("*.yaml")):
        try:
            templates.append(BankTemplate.from_yaml(f))
        except Exception:
            pass
    return templates


# ==================== 文件读取 ====================

def _detect_encoding(raw_bytes: bytes, candidates: List[str]) -> str:
    """检测文件编码"""
    for enc in candidates:
        try:
            raw_bytes.decode(enc)
            return enc
        except (UnicodeDecodeError, LookupError):
            continue
    # 兜底用 utf-8 加 errors 替换
    return "utf-8"


def _detect_delimiter(sample: str) -> str:
    """自动检测 CSV 分隔符"""
    candidates = [",", "	", ";", "|"]
    counts = {}
    for d in candidates:
        first_line = sample.split("\n")[0] if "\n" in sample else sample
        counts[d] = first_line.count(d)
    # 选出现次数最多且 > 0 的
    best = max(counts, key=counts.get)
    return best if counts[best] > 0 else ","


def _read_file(file_path: str) -> bytes:
    """读取文件内容为 bytes"""
    with open(file_path, "rb") as f:
        return f.read()


# ==================== CSV 解析 ====================

def parse_csv_rows(raw_bytes: bytes, encoding_candidates: List[str] = None,
                   skip_rows: int = 0, has_header: bool = True) -> Tuple[List[str], List[Dict], str]:
    """
    解析 CSV 为行列表
    返回: (headers, rows, encoding_used)
    """
    if encoding_candidates is None:
        encoding_candidates = ["utf-8", "gbk", "gb2312"]

    encoding = _detect_encoding(raw_bytes, encoding_candidates)
    text = raw_bytes.decode(encoding, errors="replace")

    # 跳过前 N 行
    lines = text.splitlines()
    if skip_rows and skip_rows < len(lines):
        lines = lines[skip_rows:]
    text = "\n".join(lines)

    if not text.strip():
        return [], [], encoding

    delimiter = _detect_delimiter(text)

    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    headers = reader.fieldnames or []
    rows = [dict(row) for row in reader]
    return headers, rows, encoding


# ==================== Excel 解析 ====================

def parse_excel_rows(raw_bytes: bytes, skip_rows: int = 0,
                     has_header: bool = True) -> Tuple[List[str], List[Dict]]:
    """
    解析 Excel (.xlsx/.xls) 为行列表
    返回: (headers, rows)
    """
    if openpyxl is None:
        raise ImportError("openpyxl not installed")

    wb = openpyxl.load_workbook(io.BytesIO(raw_bytes), read_only=True, data_only=True)
    ws = wb.active

    rows_iter = ws.iter_rows(values_only=True)
    all_rows = list(rows_iter)
    wb.close()

    if skip_rows and skip_rows < len(all_rows):
        all_rows = all_rows[skip_rows:]

    if not all_rows:
        return [], []

    if has_header:
        headers = [str(h).strip() if h is not None else "" for h in all_rows[0]]
        data_rows = all_rows[1:]
    else:
        headers = [f"col_{i}" for i in range(len(all_rows[0]))]
        data_rows = all_rows

    result = []
    for row in data_rows:
        row_dict = {}
        for i, h in enumerate(headers):
            if i < len(row):
                val = row[i]
                if val is None:
                    row_dict[h] = ""
                elif hasattr(val, 'strftime'):
                    row_dict[h] = val.strftime("%Y-%m-%d")
                else:
                    row_dict[h] = str(val)
            else:
                row_dict[h] = ""
        result.append(row_dict)

    return headers, result


# ==================== 银行识别 + 字段映射 ====================

def detect_bank(headers: List[str], templates: List[BankTemplate]) -> Optional[BankTemplate]:
    """
    根据表头自动识别银行模板
    评分规则：header_keywords 命中数 + column_keywords 命中数
    """
    best_template = None
    best_score = 0

    headers_lower = [h.strip().lower() for h in headers]
    headers_str = " ".join(headers_lower)

    for tpl in templates:
        score = 0
        det = tpl.detection

        for kw in det.get("column_keywords", []):
            if kw.lower() in headers_str:
                score += 3

        for kw in det.get("header_keywords", []):
            if kw.lower() in headers_str:
                score += 1

        if score > best_score:
            best_score = score
            best_template = tpl

    # 至少命中 2 个关键词才算识别成功
    return best_template if best_score >= 2 else None


def _map_column(row: Dict, candidates: List[str]) -> str:
    """根据候选列名列表，从行中取出第一个匹配的值"""
    for col in candidates:
        if col in row and row[col] is not None and str(row[col]).strip():
            return str(row[col]).strip()
    return ""


def _parse_amount(val: str) -> Decimal:
    """解析金额字符串（去除逗号、货币符号等）"""
    if not val:
        return Decimal("0")
    # 去除常见格式字符：逗号、空格、¥、￥、CNY
    cleaned = re.sub(r"[,\s¥￥$€£]", "", val)
    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _normalize_date(date_str: str, time_str: str = "") -> str:
    """将各种日期格式统一为 YYYY-MM-DD"""
    if not date_str:
        return ""

    s = date_str.strip()

    # 已经是 YYYY-MM-DD
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        return s

    # YYYY/MM/DD
    m = re.match(r"^(\d{4})/(\d{1,2})/(\d{1,2})", s)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"

    # YYYYMMDD
    m = re.match(r"^(\d{4})(\d{2})(\d{2})", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

    # MM/DD/YYYY
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        return f"{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"

    # 带中文年月
    m = re.match(r"^(\d{4})年(\d{1,2})月(\d{1,2})日", s)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"

    return s  # 返回原值，交给上层判断


def _detect_direction(direction_str: str, amount: Decimal,
                      rules: Dict) -> str:
    """根据方向列和金额符号判断收入/支出"""
    d = direction_str.strip() if direction_str else ""

    # 优先用 direction 列关键词
    for kw in rules.get("income_keywords", []):
        if kw in d:
            return "income"
    for kw in rules.get("expense_keywords", []):
        if kw in d:
            return "expense"

    # 用金额符号
    if rules.get("amount_sign", True):
        if amount > 0:
            return "income"
        elif amount < 0:
            return "expense"

    return "unknown"


def apply_template(rows: List[Dict], template: BankTemplate) -> List[ParsedTransaction]:
    """
    应用银行模板，将原始行映射为标准交易记录
    """
    results = []
    mapping = template.column_mapping
    dir_rules = template.direction_rules

    for i, row in enumerate(rows):
        txn = ParsedTransaction()
        txn.row_num = i + 1 + template.skip_rows
        txn.raw_row = row
        txn.source_bank = template.bank_id

        try:
            date_str = _map_column(row, mapping.get("txn_date", []))
            time_str = _map_column(row, mapping.get("txn_time", []))
            txn.txn_date = _normalize_date(date_str, time_str)
            txn.txn_time = time_str

            amount_str = _map_column(row, mapping.get("amount", []))
            raw_amount = _parse_amount(amount_str)

            direction_str = _map_column(row, mapping.get("direction", []))
            txn.direction = _detect_direction(direction_str, raw_amount, dir_rules)

            # 金额统一为正数（用 direction 区分收支）
            txn.amount = abs(raw_amount)

            txn.currency = _map_column(row, mapping.get("currency", [])) or "CNY"
            txn.counterparty = _map_column(row, mapping.get("counterparty", []))
            txn.counterparty_account = _map_column(
                row, mapping.get("counterparty_account", []))
            txn.summary = _map_column(row, mapping.get("summary", []))
            txn.product = _map_column(row, mapping.get("product", []))
            txn.category = _map_column(row, mapping.get("category", []))
            txn.balance = _map_column(row, mapping.get("balance", []))
            txn.txn_type = _map_column(row, mapping.get("txn_type", []))
            txn.status = _map_column(row, mapping.get("status", []))

            # 跳过无效行（无日期或金额为 0）
            if not txn.txn_date or txn.amount == 0:
                txn.error = "缺少日期或金额为0"

        except Exception as e:
            txn.error = f"解析错误: {str(e)}"

        results.append(txn)

    return results


# ==================== 高层入口 ====================

class StatementParser:
    """
    流水解析器 — 自动检测格式+银行，输出标准交易列表

    Usage:
        parser = StatementParser()
        result = parser.parse_file("statement.csv")
        print(result.transactions, result.bank, result.errors)
    """

    def __init__(self, templates: List[BankTemplate] = None):
        self.templates = templates or load_templates()

    def parse_file(self, file_path: str, source_type: str = "auto"
                    ) -> 'ParseResult':
        """解析文件，返回 ParseResult"""
        raw = _read_file(file_path)
        return self.parse_bytes(raw, file_path, source_type)

    def parse_bytes(self, raw_bytes: bytes, file_name: str = "",
                    source_type: str = "auto") -> 'ParseResult':
        """解析 bytes，自动判断格式"""
        file_name_lower = file_name.lower()
        is_excel = (
            file_name_lower.endswith(".xlsx") or
            file_name_lower.endswith(".xls") or
            raw_bytes[:2] == b"PK"  # ZIP 格式 = xlsx
        )

        if is_excel:
            return self._parse_excel(raw_bytes, source_type)
        else:
            return self._parse_csv(raw_bytes, source_type)

    def _parse_csv(self, raw_bytes: bytes, source_type: str) -> 'ParseResult':
        if source_type != "auto":
            # 指定银行：用对应模板的编码
            tpl = self._find_template(source_type)
            if tpl:
                headers, rows, encoding = parse_csv_rows(
                    raw_bytes, encoding_candidates=tpl.encoding,
                    skip_rows=tpl.skip_rows, has_header=tpl.has_header,
                )
                transactions = apply_template(rows, tpl)
                return ParseResult(
                    transactions=transactions,
                    bank=tpl.bank_id,
                    bank_name=tpl.bank_name,
                    format="csv",
                    encoding=encoding,
                    headers=headers,
                )

        # 自动识别：先尝试通用解析
        headers, rows, encoding = parse_csv_rows(raw_bytes)

        # 自动识别银行
        tpl = detect_bank(headers, self.templates)
        if tpl:
            # 重新用模板正确的 skip_rows 和编码解析
            headers2, rows2, _ = parse_csv_rows(
                raw_bytes, encoding_candidates=tpl.encoding,
                skip_rows=tpl.skip_rows, has_header=tpl.has_header,
            )
            transactions = apply_template(rows2, tpl)
            return ParseResult(
                transactions=transactions,
                bank=tpl.bank_id,
                bank_name=tpl.bank_name,
                format="csv",
                encoding=encoding,
                headers=headers2,
            )

        # 未识别：返回原始行（通用模式）
        return ParseResult(
            transactions=[],
            bank="unknown",
            bank_name="未知格式",
            format="csv",
            encoding=encoding,
            headers=headers,
            errors=["未能识别银行模板"],
        )

    def _parse_excel(self, raw_bytes: bytes, source_type: str) -> 'ParseResult':
        if source_type != "auto":
            tpl = self._find_template(source_type)
            if tpl:
                headers, rows = parse_excel_rows(
                    raw_bytes, skip_rows=tpl.skip_rows,
                    has_header=tpl.has_header,
                )
                transactions = apply_template(rows, tpl)
                return ParseResult(
                    transactions=transactions,
                    bank=tpl.bank_id,
                    bank_name=tpl.bank_name,
                    format="excel",
                    headers=headers,
                )

        # 自动识别
        headers, rows = parse_excel_rows(raw_bytes)
        tpl = detect_bank(headers, self.templates)
        if tpl:
            headers2, rows2 = parse_excel_rows(
                raw_bytes, skip_rows=tpl.skip_rows,
                has_header=tpl.has_header,
            )
            transactions = apply_template(rows2, tpl)
            return ParseResult(
                transactions=transactions,
                bank=tpl.bank_id,
                bank_name=tpl.bank_name,
                format="excel",
                headers=headers2,
            )

        return ParseResult(
            transactions=[],
            bank="unknown",
            bank_name="未知格式",
            format="excel",
            headers=headers,
            errors=["未能识别银行模板"],
        )

    def _find_template(self, bank_id: str) -> Optional[BankTemplate]:
        for t in self.templates:
            if t.bank_id == bank_id:
                return t
        return None


@dataclass
class ParseResult:
    transactions: List[ParsedTransaction] = field(default_factory=list)
    bank: str = ""
    bank_name: str = ""
    format: str = ""         # csv / excel
    encoding: str = ""
    headers: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    @property
    def valid_count(self) -> int:
        return sum(1 for t in self.transactions if t.is_valid)

    @property
    def error_count(self) -> int:
        return sum(1 for t in self.transactions if t.error)

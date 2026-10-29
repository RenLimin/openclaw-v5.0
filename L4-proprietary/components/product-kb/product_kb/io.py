"""
IO module: Price sheet import, document scanning, text extraction
"""
import os
import re
import hashlib
import openpyxl
from docx import Document as DocxDocument
from pptx import Presentation
from PyPDF2 import PdfReader
from typing import List, Dict, Optional, Tuple, Any
from .db import ProductKBDB

# Regex for version extraction
VERSION_PATTERN = re.compile(r'[Vv](?:ersion)?\s*(\d+(?:\.\d+)+)')
VERSION_PATTERN2 = re.compile(r'(\d+(?:\.\d+)+)')


class PriceImporter:
    def __init__(self, db: ProductKBDB):
        self.db = db
        # Map raw line name to normalized code
        self.line_name_map = {
            "内容安全产品线": "content_security",
            "安全保护线": "security_protect",
            "安全保护产品线": "security_protect",
            "安全服务产品线": "security_service",
            "安全检测线": "security_detect",
            "安全监测线": "security_monitor",
            "物联网服务产品线": "iot_service",
            "安全产品": "security_product",
            "未分类": "uncategorized"
        }

    def normalize_line_name(self, raw_name: str) -> Tuple[str, str]:
        """Return (code, normalized name)"""
        for name, code in self.line_name_map.items():
            if raw_name.startswith(name) or name.startswith(raw_name):
                # Map "安全保护线" -> "安全保护产品线"; keep "安全服务产品线" as-is
                if raw_name.endswith("线") and not raw_name.endswith("产品线"):
                    display_name = raw_name[:-1] + "产品线"
                else:
                    display_name = raw_name
                return code, display_name
        # Fallback
        code = raw_name.lower().replace(" ", "_")
        return code, raw_name

    def extract_version(self, text: str) -> Optional[str]:
        """Extract version from text"""
        match = VERSION_PATTERN.search(text)
        if match:
            return match.group(1)
        match = VERSION_PATTERN2.search(text)
        if match:
            return match.group(1)
        return None

    def import_from_xlsx(self, xlsx_path: str) -> Dict[str, int]:
        """Import all SKUs from price sheet"""
        wb = openpyxl.load_workbook(xlsx_path, data_only=True)
        ws = wb.active

        stats = {
            "lines": 0,
            "categories": 0,
            "products": 0,
            "skus": 0
        }

        # Skip header row
        rows = list(ws.iter_rows(values_only=True))[1:]
        for row in rows:
            if len(row) < 17:
                continue  # Skip incomplete rows

            # Columns from price sheet (0-indexed):
            # 0: ID, 1:销售模式, 2:销售状态, 3:注意事项, 4:货物或应税服务名称,
            # 5:是否定制, 6:关联产品编码, 7:产品服务编码, 8:产品服务类别, 9:类别,
            # 10:产品服务名称, 11:产品服务型号, 12:产品服务单价, 13:报价基准,
            # 14:服务描述, 15:折扣类型, 16:产品线类别, 17:启用状态

            id_col = row[0]
            sale_mode = row[1] or "未指定"
            sale_status = row[2] or "未知"
            notes = row[3]
            full_name = row[4] or ""
            product_name = row[10] or full_name
            if not product_name:
                product_name = full_name
            product_code = row[7]
            category_name = row[9]
            sku_code = row[7]  # Use product service code as SKU code
            model = row[11]
            unit_price = row[12]
            if isinstance(unit_price, str):
                try:
                    unit_price = float(unit_price.replace(',', ''))
                except:
                    unit_price = None
            price_base = row[13]
            service_desc = row[14]
            discount_type = row[15]
            line_name_raw = row[16] or "未分类"
            enabled = row[17] or "启用"

            # Extract version from product name
            version = self.extract_version(product_name)

            # Determine product type from sale_mode
            product_type = "product"
            if "服务" in sale_mode:
                product_type = "service"
            elif "硬件" in sale_mode:
                product_type = "hardware"

            # Get or create product line
            line_code, line_display = self.normalize_line_name(line_name_raw)
            line_id = self.db.get_or_create_product_line(line_display, line_code, None)
            if "line_ids" not in stats:
                stats["line_ids"] = set()
            stats["line_ids"].add(line_id)
            stats["lines"] = len(stats["line_ids"])

            # Get or create category
            category_id = None
            if category_name and category_name.strip():
                category_id = self.db.get_or_create_category(line_id, category_name.strip())
                if "category_ids" not in stats:
                    stats["category_ids"] = set()
                stats["category_ids"].add(category_id)
                stats["categories"] = len(stats["category_ids"])

            # Get existing product
            product = self.db.get_product_by_name(product_name.strip())
            product_id = None
            if not product:
                # Create new product
                product_id = self.db.create_product(
                    line_id=line_id,
                    category_id=category_id,
                    family=(row[8] or "").strip() or None,
                    name=product_name.strip(),
                    aliases=None,
                    code=product_code,
                    version_latest=version,
                    type_=product_type,
                    status=("第三方产品/服务" if "非梆梆" in product_name else (sale_status.strip() if sale_status else "正常销售")),
                    summary=service_desc
                )
                stats["products"] += 1
            else:
                product_id = product["id"]
                # Update version if newer
                if version and (not product["version_latest"] or version > product["version_latest"]):
                    self.db.update_product(product_id, version_latest=version)

            # Create/update SKU
            sku_id = self.db.create_or_update_sku(
                product_id=product_id,
                sku_code=sku_code,
                model=model,
                unit_price=unit_price,
                price_base=price_base,
                discount_type=discount_type,
                sale_mode=sale_mode,
                sale_status=enabled,
                notes=notes,
                service_desc=service_desc
            )
            stats["skus"] += 1

        self.db.commit()
        wb.close()
        return stats


class DocScanner:
    def __init__(self, db: ProductKBDB, root_path: str):
        self.db = db
        self.root_path = os.path.abspath(root_path)
        # Doc type mapping by file name pattern
        self.doc_type_map = [
            ("白皮书", "white_paper"),
            ("一指禅", "sales_note"),
            ("功能清单", "func_list"),
            ("常见问题", "faq"),
            ("FAQ", "faq"),
            ("用户手册", "manual"),
            ("技术白皮书", "tech_white_paper"),
            ("版本更新", "version_note"),
            (".pptx?", "ppt"),
            (".pdf", "pdf"),
        ]

    def get_file_md5(self, path: str) -> str:
        hash_md5 = hashlib.md5()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

    def guess_doc_type(self, filename: str) -> str:
        filename_lower = filename.lower()
        for pattern, dtype in self.doc_type_map:
            if re.search(pattern, filename_lower):
                return dtype
        return "other"

    def extract_version(self, path: str) -> Optional[str]:
        """Try extract version from path"""
        name = os.path.basename(path)
        dirname = os.path.basename(os.path.dirname(path))
        for text in [name, dirname]:
            match = VERSION_PATTERN.search(text)
            if match:
                return match.group(1)
            match = VERSION_PATTERN2.search(text)
            if match:
                return match.group(1)
        return None

    def _strip_brackets(self, text: str) -> str:
        """Remove decorative brackets like 【梆梆安全】 and prefixes"""
        text = re.sub(r'[【\[\(（][^】\]\)）]*[】\]\)）]', '', text)
        return text.strip()

    # Generic suffixes/prefixes that differ between price sheet naming and
    # directory naming conventions
    GENERIC_WORDS = ["软件", "系统", "平台", "服务", "SDK", "sdk"]

    def _match_score(self, product_name: str, text: str) -> float:
        """Score how well a product name matches a text string (0 or positive)."""
        # Strip version suffix from product name
        base_name = re.sub(r'[Vv]\d+(?:\.\d+)*', '', product_name).strip()
        if len(base_name) >= 4 and base_name in text:
            return len(base_name)
        # Strip "梆梆安全" prefix
        stripped = base_name.replace("梆梆安全", "").replace("梆梆", "").strip()
        if len(stripped) >= 4 and stripped in text:
            return len(stripped) * 0.95
        # Fuzzy: strip generic suffix words from both sides and compare cores
        def core(s):
            for w in self.GENERIC_WORDS:
                s = s.replace(w, "")
            return re.sub(r'[\s（）()]', "", s)
        cn, tn = core(base_name), core(text)
        if len(cn) >= 4 and cn in tn:
            return len(cn) * 0.8
        return 0.0

    def fuzzy_match_product(self, filename: str, dirpath: str = "") -> Optional[int]:
        """Match product by filename and directory name.

        Directory name is a strong signal: docs are organized in
        per-product directories, e.g. "红队攻防演练服务/".
        Filename is a secondary signal.
        """
        if not hasattr(self, "_products_cache"):
            cursor = self.db.execute("SELECT id, name, family, aliases FROM product")
            self._products_cache = cursor.fetchall()

        clean_file = self._strip_brackets(filename)
        best_id = None
        best_score = 0.0

        for row in self._products_cache:
            pid, name, family, aliases = row[0], row[1], row[2], row[3]
            score = 0.0
            # family (产品服务类别) is the product-family name; directory names
            # usually correspond to family or product name
            if family:
                if dirpath:
                    score = max(score, self._match_score(family, dirpath) * 1.2)
                score = max(score, self._match_score(family, clean_file) * 1.1)
            if dirpath:
                score = max(score, self._match_score(name, dirpath) * 1.0)
            score = max(score, self._match_score(name, clean_file) * 0.9)
            if aliases:
                try:
                    import json as _json
                    for alias in _json.loads(aliases):
                        if not alias:
                            continue
                        if dirpath:
                            score = max(score, self._match_score(alias, dirpath) * 1.0)
                        score = max(score, self._match_score(alias, clean_file) * 0.9)
                except Exception:
                    pass
            if score > best_score:
                best_score = score
                best_id = pid
        return best_id if best_score > 0 else None

    def scan_directory(self) -> Dict[str, Any]:
        """Scan all documents in root directory"""
        stats = {
            "total": 0,
            "skipped": 0,
            "added": 0,
            "updated": 0,
            "unmatched": 0,
            "unmatched_files": []
        }

        supported_formats = {".docx", ".doc", ".xlsx", ".pptx", ".pdf"}

        for root, dirs, files in os.walk(self.root_path):
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext not in supported_formats:
                    stats["skipped"] += 1
                    continue
                stats["total"] += 1

                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, self.root_path)
                md5 = self.get_file_md5(full_path)

                # Check if already exists and unchanged
                existing = self.db.get_doc_by_md5(md5)
                if existing:
                    stats["updated"] += 1
                    continue  # No change, skip

                # Try match product (use filename + parent dir name)
                product_id = self.fuzzy_match_product(file, os.path.basename(root))
                if not product_id:
                    stats["unmatched"] += 1
                    stats["unmatched_files"].append(full_path)
                    continue

                # Extract version
                version = self.extract_version(full_path)

                # Guess doc type
                dtype = self.guess_doc_type(file)

                # Create doc asset
                doc_id = self.db.create_doc_asset(
                    product_id=product_id,
                    doc_type=dtype,
                    original_path=full_path,
                    relative_path=rel_path,
                    file_name=file,
                    version=version,
                    format_=ext.lstrip('.'),
                    md5=md5
                )
                stats["added"] += 1

        self.db.commit()
        return stats


class TextExtractor:
    @staticmethod
    def extract_text(path: str) -> Optional[str]:
        """Extract text from document based on format"""
        ext = os.path.splitext(path)[1].lower()
        try:
            if ext in (".docx", ".doc"):
                return TextExtractor.extract_docx(path)
            elif ext == ".xlsx":
                return TextExtractor.extract_xlsx(path)
            elif ext in (".pptx", ".ppt"):
                return TextExtractor.extract_pptx(path)
            elif ext == ".pdf":
                return TextExtractor.extract_pdf(path)
            else:
                return None
        except Exception as e:
            print(f"Error extracting {path}: {e}")
            return None

    @staticmethod
    def extract_docx(path: str) -> str:
        doc = DocxDocument(path)
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n\n".join(paragraphs)

    @staticmethod
    def extract_xlsx(path: str) -> str:
        wb = openpyxl.load_workbook(path, data_only=True)
        text_blocks = []
        for ws in wb.worksheets:
            for row in ws.iter_rows(values_only=True):
                row_text = " | ".join([str(cell) for cell in row if cell is not None])
                if row_text.strip():
                    text_blocks.append(row_text)
        wb.close()
        return "\n".join(text_blocks)

    @staticmethod
    def extract_pptx(path: str) -> str:
        prs = Presentation(path)
        text_blocks = []
        for slide in prs.slides:
            for shape in slide.shapes:
                if hasattr(shape, "text") and shape.text.strip():
                    text_blocks.append(shape.text)
        prs = None
        return "\n\n".join(text_blocks)

    @staticmethod
    def extract_pdf(path: str) -> str:
        reader = PdfReader(path)
        text_blocks = []
        for page in reader.pages:
            text = page.extract_text()
            if text and text.strip():
                text_blocks.append(text)
        return "\n\n".join(text_blocks)

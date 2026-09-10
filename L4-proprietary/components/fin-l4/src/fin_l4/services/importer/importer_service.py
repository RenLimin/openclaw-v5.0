"""银行流水导入服务 — 整合解析 + 分类 + 去重 + 入库"""

import json
import uuid
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from decimal import Decimal
from pathlib import Path

from fin_l4.db.repositories import (
    TransactionRepository, AccountRepository, CategoryRepository,
    AuditLogRepository,
)

from .parser import StatementParser, ParseResult, ParsedTransaction
from .classifier import RuleClassifier, ClassifyResult


def _uid() -> str:
    return str(uuid.uuid4())


@dataclass
class ImportPreview:
    """导入预览结果"""
    import_id: str = ""
    file_name: str = ""
    source_type: str = "auto"
    detected_bank: str = ""
    detected_bank_name: str = ""
    format: str = ""
    total_count: int = 0
    valid_count: int = 0
    error_count: int = 0
    duplicate_count: int = 0
    new_count: int = 0
    transactions: List[Dict] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    confidence_stats: Dict[str, int] = field(default_factory=dict)
    category_stats: Dict[str, int] = field(default_factory=dict)


@dataclass
class ImportResult:
    """导入完成结果"""
    import_id: str = ""
    status: str = ""
    total_count: int = 0
    new_count: int = 0
    duplicate_count: int = 0
    error_count: int = 0
    high_confidence: int = 0
    medium_confidence: int = 0
    low_confidence: int = 0
    category_stats: Dict[str, int] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)


class TransactionImporter:
    """
    银行流水导入服务

    流程：
    1. 解析文件（CSV/Excel，自动识别银行）
    2. 智能分类（规则引擎 + 置信度）
    3. 去重检查（import_hash）
    4. 预览 / 确认导入
    5. 批量入库
    """

    def __init__(self, conn):
        self.conn = conn
        self.txn_repo = TransactionRepository(conn)
        self.account_repo = AccountRepository(conn)
        self.cat_repo = CategoryRepository(conn)
        self.audit = AuditLogRepository(conn)
        self.parser = StatementParser()
        self.classifier = RuleClassifier.default()

        # 预览缓存（内存）— 生产环境应存 DB
        self._previews: Dict[str, ImportPreview] = {}

    # ==================== 核心 API ====================

    def preview_import(self, family_id: str, file_path: str,
                       source_type: str = "auto") -> ImportPreview:
        """
        预览导入结果（只解析不入库）
        """
        import_id = _uid()
        file_name = Path(file_path).name

        # 1. 解析
        try:
            parse_result = self.parser.parse_file(file_path, source_type)
        except Exception as e:
            return ImportPreview(
                import_id=import_id,
                file_name=file_name,
                errors=[f"文件解析失败: {str(e)}"],
            )

        if not parse_result.transactions and parse_result.errors:
            return ImportPreview(
                import_id=import_id,
                file_name=file_name,
                detected_bank=parse_result.bank,
                detected_bank_name=parse_result.bank_name,
                format=parse_result.format,
                errors=parse_result.errors,
            )

        # 2. 分类 + 去重检查
        preview = self._build_preview(
            import_id, family_id, file_name, parse_result, source_type
        )

        # 3. 缓存预览数据
        self._previews[import_id] = preview

        # 4. 保存批次记录到 DB
        self._save_batch(import_id, family_id, preview, status="previewed")

        return preview

    def import_file(self, family_id: str, file_path: str,
                    source_type: str = "auto",
                    default_debit_id: str = None,
                    default_credit_id: str = None) -> ImportResult:
        """
        直接导入文件（一步到位，不预览）
        """
        # 先预览
        preview = self.preview_import(family_id, file_path, source_type)
        if preview.errors and preview.new_count == 0:
            return ImportResult(
                import_id=preview.import_id,
                status="failed",
                errors=preview.errors,
            )

        # 确认导入
        return self.confirm_import(
            preview.import_id, family_id,
            default_debit_id=default_debit_id,
            default_credit_id=default_credit_id,
        )

    def confirm_import(self, import_id: str, family_id: str,
                       adjustments: Dict = None,
                       default_debit_id: str = None,
                       default_credit_id: str = None) -> ImportResult:
        """
        确认导入（可调整分类）
        adjustments: {txn_index: {"category_id": "xxx", ...}}
        """
        preview = self._previews.get(import_id)
        if not preview:
            # 尝试从 DB 恢复
            batch = self._load_batch(import_id)
            if not batch:
                return ImportResult(
                    import_id=import_id,
                    status="failed",
                    errors=["预览数据不存在或已过期"],
                )
            preview = batch

        adjustments = adjustments or {}
        new_count = 0
        dup_count = 0
        error_count = 0
        conf_stats = {"high": 0, "medium": 0, "low": 0}
        cat_stats: Dict[str, int] = {}
        errors: List[str] = []

        # 获取默认账户
        default_debit_id = default_debit_id or self._get_default_debit(family_id)
        default_credit_id = default_credit_id or self._get_default_credit(family_id)
        default_expense_debit = self._get_default_expense_debit(family_id)
        default_income_credit = self._get_default_income_credit(family_id)

        for idx, txn_dict in enumerate(preview.transactions):
            try:
                # 跳过重复
                if txn_dict.get("is_duplicate"):
                    dup_count += 1
                    continue

                # 跳过无效
                if not txn_dict.get("is_valid"):
                    error_count += 1
                    continue

                # 应用调整
                adj = adjustments.get(str(idx), {})
                direction = txn_dict.get("direction", "expense")
                amount = txn_dict.get("amount", "0")
                confidence = adj.get("confidence") or txn_dict.get("confidence", "low")

                raw_cat_id = adj.get("category_id") or txn_dict.get("category_id", "cat_other")
                # 确保分类存在（自动创建标准分类）
                category_id = self.ensure_category(family_id, raw_cat_id,
                    "income" if direction == "income" else "expense") or None

                # 确定借贷账户
                if direction == "income":
                    debit_id = default_debit_id     # 借：银行存款（资产增加）
                    credit_id = default_income_credit  # 贷：收入
                else:
                    debit_id = default_expense_debit   # 借：费用
                    credit_id = default_credit_id     # 贷：银行存款（资产减少）

                if not debit_id or not credit_id:
                    errors.append(f"第{idx+1}行: 无法确定账户映射")
                    error_count += 1
                    continue

                # 生成去重哈希
                import_hash = txn_dict.get("import_hash") or self._make_hash(
                    family_id, txn_dict
                )

                # 入库（使用 INSERT OR IGNORE 防重复）
                try:
                    self.conn.execute(
                        "INSERT OR IGNORE INTO fin4_transactions "
                        "(id, family_id, date, amount, note, category_id, "
                        "debit_account_id, credit_account_id, source, "
                        "import_hash, import_batch_id, category_confidence, "
                        "source_bank, counterparty) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            _uid(), family_id,
                            txn_dict.get("txn_date", ""),
                            str(amount),
                            txn_dict.get("summary", ""),
                            category_id if category_id.startswith("cat_") else None,
                            debit_id, credit_id,
                            "imported",
                            import_hash, import_id, confidence,
                            preview.detected_bank,
                            txn_dict.get("counterparty", ""),
                        ),
                    )
                    rows_affected = self.conn.total_changes
                    if rows_affected > 0:
                        new_count += 1
                        conf_stats[confidence] = conf_stats.get(confidence, 0) + 1
                        cat_stats[category_id] = cat_stats.get(category_id, 0) + 1
                    else:
                        dup_count += 1
                except Exception as e:
                    errors.append(f"第{idx+1}行: 入库失败 {str(e)}")
                    error_count += 1

            except Exception as e:
                errors.append(f"第{idx+1}行: {str(e)}")
                error_count += 1

        self.conn.commit()

        # 更新批次状态
        self._update_batch(import_id, status="completed",
                          new_count=new_count, dup_count=dup_count,
                          error_count=error_count,
                          high_conf=conf_stats.get("high", 0),
                          medium_conf=conf_stats.get("medium", 0),
                          low_conf=conf_stats.get("low", 0))

        # 审计日志
        self.audit.log(
            family_id=family_id, user="system",
            action="import_complete", entity_type="import_batch",
            entity_id=import_id,
            details={
                "new": new_count, "duplicate": dup_count,
                "errors": error_count, "bank": preview.detected_bank,
            },
        )

        return ImportResult(
            import_id=import_id,
            status="completed",
            total_count=preview.total_count,
            new_count=new_count,
            duplicate_count=dup_count,
            error_count=error_count,
            high_confidence=conf_stats.get("high", 0),
            medium_confidence=conf_stats.get("medium", 0),
            low_confidence=conf_stats.get("low", 0),
            category_stats=cat_stats,
            errors=errors,
        )

    def get_import_history(self, family_id: str,
                           limit: int = 50) -> List[Dict]:
        """获取历史导入记录"""
        rows = self.conn.execute(
            "SELECT * FROM fin4_import_batches WHERE family_id = ? "
            "ORDER BY created_at DESC LIMIT ?",
            (family_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    # ==================== 内部方法 ====================

    def ensure_category(self, family_id: str, category_id: str,
                        cat_type: str = "expense") -> Optional[str]:
        """确保分类存在，不存在则自动创建。返回分类 ID 或 None。"""
        # 检查是否已存在
        cat = self.cat_repo.get(category_id)
        if cat:
            return category_id

        # 规则分类名映射
        name_map = {
            "cat_salary": "工资薪资",
            "cat_invest_income": "投资收益",
            "cat_other_income": "其他收入",
            "cat_food": "餐饮美食",
            "cat_transport": "交通出行",
            "cat_shopping": "购物消费",
            "cat_housing": "居家生活",
            "cat_medical": "医疗健康",
            "cat_education": "教育学习",
            "cat_entertainment": "休闲娱乐",
            "cat_insurance": "保险",
            "cat_telecom": "通讯",
            "cat_transfer": "转账",
            "cat_other": "其他",
        }

        name = name_map.get(category_id, category_id)

        # 判断收入/支出
        if "income" in category_id or "salary" in category_id or "invest" in category_id:
            cat_type = "income"

        try:
            # 手动插入，指定 ID
            import uuid
            uid = category_id if category_id.startswith("cat_") else str(uuid.uuid4())
            self.conn.execute(
                "INSERT OR IGNORE INTO fin4_categories (id, family_id, name, type) "
                "VALUES (?, ?, ?, ?)",
                (uid, family_id, name, cat_type),
            )
            self.conn.commit()
            return uid
        except Exception:
            return None


    def _build_preview(self, import_id: str, family_id: str,
                       file_name: str, parse_result: ParseResult,
                       source_type: str) -> ImportPreview:
        """构建预览数据"""
        txns = parse_result.transactions
        total = len(txns)
        valid = 0
        errors = list(parse_result.errors)
        dup_count = 0
        new_count = 0
        conf_stats = {"high": 0, "medium": 0, "low": 0}
        cat_stats: Dict[str, int] = {}
        preview_txns: List[Dict] = []

        for txn in txns:
            is_valid = txn.is_valid
            if not is_valid:
                errors.append(f"第{txn.row_num}行: {txn.error}")
                preview_txns.append({
                    "row": txn.row_num,
                    "is_valid": False,
                    "error": txn.error,
                    "txn_date": txn.txn_date,
                    "amount": str(txn.amount),
                    "counterparty": txn.counterparty,
                    "summary": txn.summary,
                })
                continue

            valid += 1

            # 分类
            cls_result = self.classifier.classify_txn(txn)

            # 去重检查
            import_hash = txn.import_hash(family_id)
            is_dup = self._check_duplicate(family_id, import_hash)

            if is_dup:
                dup_count += 1
            else:
                new_count += 1
                conf_stats[cls_result.confidence] = conf_stats.get(
                    cls_result.confidence, 0) + 1
                cat_stats[cls_result.category_id] = cat_stats.get(
                    cls_result.category_id, 0) + 1

            preview_txns.append({
                "row": txn.row_num,
                "is_valid": True,
                "is_duplicate": is_dup,
                "txn_date": txn.txn_date,
                "txn_time": txn.txn_time,
                "amount": str(txn.amount),
                "direction": txn.direction,
                "currency": txn.currency,
                "counterparty": txn.counterparty,
                "summary": txn.summary,
                "product": txn.product,
                "category_id": cls_result.category_id,
                "category_name": cls_result.category_name,
                "confidence": cls_result.confidence,
                "matched_rules": cls_result.matched_rules,
                "import_hash": import_hash,
                "source_bank": txn.source_bank,
            })

        return ImportPreview(
            import_id=import_id,
            file_name=file_name,
            source_type=source_type,
            detected_bank=parse_result.bank,
            detected_bank_name=parse_result.bank_name,
            format=parse_result.format,
            total_count=total,
            valid_count=valid,
            error_count=total - valid,
            duplicate_count=dup_count,
            new_count=new_count,
            transactions=preview_txns,
            errors=errors,
            confidence_stats=conf_stats,
            category_stats=cat_stats,
        )

    def _check_duplicate(self, family_id: str, import_hash: str) -> bool:
        """检查交易是否已存在（去重）"""
        row = self.conn.execute(
            "SELECT id FROM fin4_transactions "
            "WHERE family_id = ? AND import_hash = ? LIMIT 1",
            (family_id, import_hash),
        ).fetchone()
        return row is not None

    def _make_hash(self, family_id: str, txn_dict: Dict) -> str:
        import hashlib
        raw = "|".join([
            family_id,
            txn_dict.get("txn_date", ""),
            str(txn_dict.get("amount", "0")),
            txn_dict.get("direction", ""),
            txn_dict.get("counterparty", ""),
            txn_dict.get("summary", ""),
        ])
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]

    # ==================== 账户映射 ====================

    def _get_default_debit(self, family_id: str) -> Optional[str]:
        """收入类交易的默认借方（资产账户）"""
        accounts = self.account_repo.list_by_family(family_id)
        asset_accounts = [a for a in accounts if a["type"] == "ASSET"]
        for acc in asset_accounts:
            if "银行" in acc["name"] or "bank" in acc["name"].lower():
                return acc["id"]
        return asset_accounts[0]["id"] if asset_accounts else None

    def _get_default_credit(self, family_id: str) -> Optional[str]:
        """支出类交易的默认贷方（资产账户，钱从这出）"""
        return self._get_default_debit(family_id)

    def _get_default_expense_debit(self, family_id: str) -> Optional[str]:
        """支出类交易的默认借方（费用账户）"""
        accounts = self.account_repo.list_by_family(family_id)
        expense_accounts = [a for a in accounts if a["type"] == "EXPENSE"]
        return expense_accounts[0]["id"] if expense_accounts else None

    def _get_default_income_credit(self, family_id: str) -> Optional[str]:
        """收入类交易的默认贷方（收入账户）"""
        accounts = self.account_repo.list_by_family(family_id)
        income_accounts = [a for a in accounts if a["type"] == "INCOME"]
        return income_accounts[0]["id"] if income_accounts else None

    # ==================== 批次持久化 ====================

    def _save_batch(self, import_id: str, family_id: str,
                    preview: ImportPreview, status: str = "previewed"):
        """保存导入批次到 DB"""
        self.conn.execute(
            "INSERT OR REPLACE INTO fin4_import_batches "
            "(id, family_id, file_name, source_type, detected_bank, "
            "total_count, new_count, duplicate_count, error_count, "
            "high_confidence, medium_confidence, low_confidence, "
            "status, preview_data) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                import_id, family_id, preview.file_name,
                preview.source_type, preview.detected_bank,
                preview.total_count, preview.new_count,
                preview.duplicate_count, preview.error_count,
                preview.confidence_stats.get("high", 0),
                preview.confidence_stats.get("medium", 0),
                preview.confidence_stats.get("low", 0),
                status,
                json.dumps([t for t in preview.transactions],
                           ensure_ascii=False),
            ),
        )
        self.conn.commit()

    def _load_batch(self, import_id: str) -> Optional[ImportPreview]:
        """从 DB 恢复预览数据"""
        row = self.conn.execute(
            "SELECT * FROM fin4_import_batches WHERE id = ?",
            (import_id,),
        ).fetchone()
        if not row:
            return None
        try:
            txns = json.loads(row["preview_data"] or "[]")
        except (json.JSONDecodeError, TypeError):
            txns = []

        return ImportPreview(
            import_id=row["id"],
            file_name=row["file_name"] or "",
            detected_bank=row["detected_bank"] or "",
            total_count=row["total_count"] or 0,
            new_count=row["new_count"] or 0,
            duplicate_count=row["duplicate_count"] or 0,
            error_count=row["error_count"] or 0,
            transactions=txns,
            confidence_stats={
                "high": row["high_confidence"] or 0,
                "medium": row["medium_confidence"] or 0,
                "low": row["low_confidence"] or 0,
            },
        )

    def _update_batch(self, import_id: str, status: str,
                      new_count: int, dup_count: int, error_count: int,
                      high_conf: int, medium_conf: int, low_conf: int):
        """更新批次状态"""
        from datetime import datetime
        self.conn.execute(
            "UPDATE fin4_import_batches SET status = ?, new_count = ?, "
            "duplicate_count = ?, error_count = ?, high_confidence = ?, "
            "medium_confidence = ?, low_confidence = ?, completed_at = ? "
            "WHERE id = ?",
            (
                status, new_count, dup_count, error_count,
                high_conf, medium_conf, low_conf,
                datetime.now().isoformat(), import_id,
            ),
        )
        self.conn.commit()

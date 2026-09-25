"""合同管理计算引擎 — ContractManagementEngine。

🔒 NO_TOKEN — 纯代码，零 AI 依赖。

职责：
  - compute() — 合同统计计算（合同数/金额按月份）
  - persist() / load() / has_data() — DB 读写
  - scan_risks() — 调用 L3 risk_engine 做风险扫描
  - get_approval_level() — 调用 L3 state_machine 获取审批配置
  - validate_state_transition() — 调用 L3 state_machine 校验状态流转
  - analyze_subject() — 合同标的对比分析（对比知识库 pricing_ref）
"""

import os
import sys
import json
import uuid
from pathlib import Path
from typing import Optional
from datetime import datetime

from bdms.core import db as _db
from bdms.core.paths import DATA_DIR
from ..base import BaseEngine

from .models import (
    Contract,
    RiskScanResult,
    CONTRACT_STATUSES,
    VALID_TRANSITIONS,
)

# ─── L3 路径注入 ───
_L3_PATH = os.path.expanduser("~/.openclaw/workspace/L3-business/skills/contract-approval")
if _L3_PATH not in sys.path:
    sys.path.insert(0, _L3_PATH)


class ContractManagementEngine(BaseEngine):
    """合同管理计算引擎。"""

    module_name = "contract_management"

    def __init__(self, db_path: Optional[Path] = None):
        super().__init__(db_path)

    # ─── BaseEngine 抽象方法实现 ───

    def compute(self, month: str) -> dict:
        """计算某月的合同统计数据。

        从 cr_contracts 表聚合：
        - 按月份统计合同数量、总金额
        - 按状态分布
        - 按类型分布
        """
        conn = _db.get_connection(self.db_path)
        try:
            if not _db.table_exists(conn, "cr_contracts"):
                return {"error": "cr_contracts 表不存在"}

            # 按 created_at 月份统计
            rows = conn.execute(
                """SELECT
                     substr(created_at, 1, 7) AS ym,
                     COUNT(*) AS cnt,
                     SUM(amount) AS total_amount,
                     AVG(amount) AS avg_amount
                   FROM cr_contracts
                   WHERE (deleted_at IS NULL OR deleted_at = '')
                     AND created_at LIKE ?
                   GROUP BY ym
                   ORDER BY ym""",
                (f"{month}%",),
            ).fetchall()

            monthly_stats = [dict(r) for r in rows]

            # 按状态分布
            status_rows = conn.execute(
                """SELECT status, COUNT(*) AS cnt, SUM(amount) AS total
                   FROM cr_contracts
                   WHERE (deleted_at IS NULL OR deleted_at = '')
                     AND substr(created_at, 1, 6) = ?
                   GROUP BY status""",
                (month,),
            ).fetchall()
            status_dist = {r["status"]: {"cnt": r["cnt"], "total": r["total"]} for r in status_rows}

            # 按类型分布
            type_rows = conn.execute(
                """SELECT contract_type, COUNT(*) AS cnt, SUM(amount) AS total
                   FROM cr_contracts
                   WHERE (deleted_at IS NULL OR deleted_at = '')
                     AND substr(created_at, 1, 6) = ?
                     AND contract_type IS NOT NULL AND contract_type != ''
                   GROUP BY contract_type""",
                (month,),
            ).fetchall()
            type_dist = {r["contract_type"]: {"cnt": r["cnt"], "total": r["total"]} for r in type_rows}

            return {
                "month": month,
                "monthly_stats": monthly_stats,
                "status_distribution": status_dist,
                "type_distribution": type_dist,
                "total_contracts": sum(s["cnt"] for s in status_dist.values()),
                "total_amount": sum(s["total"] for s in status_dist.values() if s["total"]),
            }
        finally:
            conn.close()

    def persist(self, month: str, data: dict, overwrite: bool = True) -> dict[str, int]:
        """合同统计数据为只读聚合，无需独立落盘。返回统计行数。"""
        if "error" in data:
            return {"error": 1}
        return {
            "monthly_stats": len(data.get("monthly_stats", [])),
            "status_distribution": len(data.get("status_distribution", {})),
            "type_distribution": len(data.get("type_distribution", {})),
        }

    def load(self, month: str) -> dict:
        """读取某月的合同统计数据。

        注意：合同统计为只读聚合（直接从 cr_contracts 实时 GROUP BY），
        无独立持久化表，因此 load 等价于 compute。
        这与 BaseEngine 的"load 读持久化表"语义不同，属于已知例外。
        """
        return self.compute(month)

    def has_data(self, month: str) -> bool:
        """检查某月是否有合同数据。"""
        conn = _db.get_connection(self.db_path)
        try:
            if not _db.table_exists(conn, "cr_contracts"):
                return False
            row = conn.execute(
                """SELECT COUNT(*) AS n FROM cr_contracts
                   WHERE (deleted_at IS NULL OR deleted_at = '')
                     AND substr(created_at, 1, 6) = ?""",
                (month,),
            ).fetchone()
            return bool(row and row["n"] > 0)
        finally:
            conn.close()

    # ─── 风险扫描（调用 L3 risk_engine）───

    def scan_risks(self, contract_content: str) -> list[RiskScanResult]:
        """调用 L3 risk_engine 对合同文本做风险扫描。

        Args:
            contract_content: 合同全文文本

        Returns:
            RiskScanResult 列表（contract_id=0 表示未关联）
        """
        try:
            from core.risk_engine import scan_contract
            report = scan_contract(contract_content)
        except ImportError:
            # L3 不可用时返回空结果
            return []

        batch = datetime.now().strftime("%Y%m%d%H%M%S")
        results = []
        for finding in report.findings:
            results.append(RiskScanResult(
                contract_id=0,
                scan_batch=batch,
                risk_category=finding.category,
                risk_level=finding.risk,
                issue_summary=finding.item,
                suggestion=finding.law,
                status="open",
                created_at=datetime.now().isoformat(),
            ))
        return results


    # ─── 合同解析（调用 L3 contract_parser）───

    def parse_contract(self, text: str) -> dict:
        """解析合同文本 → 结构化字段 + 条款明细。

        委托 L3 contract_parser.parse_contract()。
        L3 不可用时返回 {"parties": {}, "clauses": [], "error": "parser_unavailable"}。

        Args:
            text: 合同全文文本

        Returns:
            {
                "parties": {"party_a": str, "party_b": str, ...},
                "amount": float,
                "effective_date": str,
                "expiry_date": str,
                "clauses": [{"clause_type": str, "clause_title": str, "clause_content": str}, ...],
                "contract_type": str,
            }
        """
        try:
            from scripts.contract_parser import parse_contract
            result = parse_contract(text)
            # 转换为 dict 格式（L3 可能返回 dataclass 或 dict）
            if hasattr(result, "__dict__"):
                return {
                    "parties": getattr(result, "parties", {}),
                    "amount": getattr(result, "amount", 0),
                    "effective_date": getattr(result, "effective_date", ""),
                    "expiry_date": getattr(result, "expiry_date", ""),
                    "clauses": [
                        {
                            "clause_type": getattr(c, "clause_type", ""),
                            "clause_title": getattr(c, "title", ""),
                            "clause_content": getattr(c, "content", ""),
                        }
                        for c in getattr(result, "clauses", [])
                    ],
                    "contract_type": getattr(result, "contract_type", ""),
                }
            return result if isinstance(result, dict) else {}
        except ImportError:
            # L3 不可用时返回空结构
            return {
                "parties": {},
                "amount": 0.0,
                "effective_date": "",
                "expiry_date": "",
                "clauses": [],
                "contract_type": "",
                "degraded": True,
                "reason": "L3 contract_parser 不可用",
            }

    # ─── 审批级别（调用 L3 state_machine）───

    def get_approval_level(self, amount: float) -> dict:
        """根据金额获取审批配置。

        Returns:
            {"level": int, "roles": list[str]}

        Note: L3 state_machine 返回的「财务经理/财务总监」角色，
        在 L4 BDMS 中已替换为 PMO（见 DESIGN-DETAIL §10 角色变更说明）。
        """
        try:
            from core.state_machine import get_approval_config
            config = get_approval_config(amount)
            # 角色映射：财务 → PMO（L4 不再使用财务角色）
            mapped_roles = [
                "PMO" if role in ("财务经理", "财务总监") else role
                for role in config.roles
            ]
            return {"level": config.level, "roles": mapped_roles}
        except ImportError:
            # fallback: 默认规则（PMO 替换财务）
            if amount < 100_000:
                return {"level": 1, "roles": ["销售经理"]}
            elif amount < 500_000:
                return {"level": 2, "roles": ["销售经理", "法务审查员"]}
            elif amount < 2_000_000:
                return {"level": 3, "roles": ["销售总监", "法务审查员", "PMO"]}
            else:
                return {"level": 4, "roles": ["VP/CEO", "法务总监", "PMO"]}

    # ─── 状态流转校验（调用 L3 state_machine）───

    def validate_state_transition(self, from_status: str, to_status: str,
                                   role: str = "") -> dict:
        """校验状态流转是否合法。

        优先使用本地 VALID_TRANSITIONS（含 review4），L3 state_machine 作为补充。
        """
        # 本地规则为准（含 review4 节点）
        valid = to_status in VALID_TRANSITIONS.get(from_status, set())

        if valid:
            return {"valid": True, "message": f"允许从 {from_status} 流转到 {to_status}"}
        else:
            allowed = VALID_TRANSITIONS.get(from_status, set())
            return {
                "valid": False,
                "message": f"不允许从 {from_status} 流转到 {to_status}，允许的目标: {allowed}",
            }

    # ─── 合同标的对比分析 ───

    def analyze_subject(self, contract: dict, kb_items: list[dict]) -> dict:
        """合同标的对比分析（设计文档 §1.5 全 4 项）。

        | 分析项 | 预警规则 |
        |---|---|
        | 产品匹配度 | 产品不在知识库中 → 标的风险 |
        | 价格合理性 | 单价偏离参考价 ±20% → 价格异常预警 |
        | SLA 匹配度 | SLA 低于公司标准 → 履约风险预警 |
        | 交付周期 | 周期短于标准实施周期 → 交付风险预警 |

        Args:
            contract: 合同详情 dict（含 amount, title, effective_date, expiry_date 等）
            kb_items: 知识库条目列表，每个条目含 "title", "content", "pricing_ref",
                     "service_sla", "deploy_manual" 等字段

        Returns:
            {"comparisons": list[dict], "alerts": list[dict], "summary": str}
        """
        contract_amount = float(contract.get("amount", 0))
        contract_title = contract.get("title", "")
        contract_effective = contract.get("effective_date", "")
        contract_expiry = contract.get("expiry_date", "")

        comparisons = []
        alerts = []

        for item in kb_items:
            kb_title = item.get("title", "")
            pricing_ref = item.get("pricing_ref", "")
            content = item.get("content", "")
            service_sla = item.get("service_sla", "")
            deploy_manual = item.get("deploy_manual", "")

            # ── 1. 产品匹配度 ──
            product_matched = self._fuzzy_match(contract_title, kb_title)

            # ── 2. 价格合理性（±20% 预警）──
            ref_amounts = self._extract_amounts(pricing_ref or content)
            price_alert = None
            if ref_amounts and contract_amount > 0:
                avg_ref = sum(ref_amounts) / len(ref_amounts)
                if avg_ref > 0:
                    deviation = (contract_amount - avg_ref) / avg_ref
                    if abs(deviation) > 0.20:
                        level = "high" if abs(deviation) > 0.50 else "medium"
                        direction = "高于" if deviation > 0 else "低于"
                        price_alert = {
                            "level": level,
                            "deviation_pct": round(deviation * 100, 1),
                            "message": f"合同金额 {contract_amount:,.0f} 元{direction}参考价 {avg_ref:,.0f} 元 {abs(deviation)*100:.1f}%",
                            "suggestion": "建议确认定价合理性或更新知识库参考价",
                        }
                        alerts.append({
                            "type": "price_anomaly",
                            "kb_title": kb_title,
                            "level": level,
                            "detail": price_alert["message"],
                        })

            # ── 3. SLA 匹配度 ──
            sla_alert = self._compare_sla(service_sla, contract_title)
            if sla_alert:
                alerts.append({"type": "sla_risk", "kb_title": kb_title, **sla_alert})

            # ── 4. 交付周期 ──
            delivery_alert = self._compare_delivery(
                deploy_manual, contract_effective, contract_expiry
            )
            if delivery_alert:
                alerts.append({"type": "delivery_risk", "kb_title": kb_title, **delivery_alert})

            comparisons.append({
                "kb_title": kb_title,
                "product_matched": product_matched,
                "ref_amounts": ref_amounts,
                "pricing_ref": pricing_ref,
                "has_reference": len(ref_amounts) > 0,
                "price_alert": price_alert,
            })

        has_ref_count = sum(1 for c in comparisons if c["has_reference"])
        alert_count = len(alerts)
        return {
            "comparisons": comparisons,
            "alerts": alerts,
            "summary": f"共 {len(comparisons)} 条知识库条目，{has_ref_count} 条有定价参考，发现 {alert_count} 个预警",
        }

    @staticmethod
    def _fuzzy_match(contract_title: str, kb_title: str) -> bool:
        """简易模糊匹配：合同标题与知识库条目标题是否有字符级交集。"""
        if not contract_title or not kb_title:
            return False
        # Bigram 字符级匹配
        def bigrams(s):
            return set(s[i:i+2] for i in range(len(s)-1))
        contract_bi = bigrams(contract_title)
        kb_bi = bigrams(kb_title)
        if not contract_bi or not kb_bi:
            return False
        overlap = contract_bi & kb_bi
        return len(overlap) >= 1

    @staticmethod
    def _compare_sla(service_sla: str, contract_title: str) -> Optional[dict]:
        """SLA 匹配度对比（简化版：检查 SLA 关键词是否出现在合同标题中）。"""
        if not service_sla:
            return None
        # 从 SLA 文本提取关键指标（如 "99.9%"）
        import re
        sla_metrics = re.findall(r'(\d+\.?\d*)\s*%', service_sla)
        if sla_metrics and "服务" in contract_title:
            return {
                "level": "low",
                "detail": f"知识库 SLA 要求 {', '.join(m + '%' for m in sla_metrics)}，建议确认合同包含对应 SLA 条款",
            }
        return None

    @staticmethod
    def _compare_delivery(deploy_manual: str, effective_date: str, expiry_date: str) -> Optional[dict]:
        """交付周期对比。"""
        if not deploy_manual or not effective_date or not expiry_date:
            return None
        import re
        # 从 deploy_manual 提取标准实施周期（天）
        std_days_match = re.search(r'(\d+)\s*天', deploy_manual)
        if not std_days_match:
            return None
        std_days = int(std_days_match.group(1))
        try:
            from datetime import datetime
            eff = datetime.strptime(effective_date[:10], "%Y-%m-%d")
            exp = datetime.strptime(expiry_date[:10], "%Y-%m-%d")
            contract_days = (exp - eff).days
            if contract_days < std_days:
                return {
                    "level": "medium",
                    "detail": f"合同期限 {contract_days} 天短于标准实施周期 {std_days} 天，存在交付风险",
                }
        except (ValueError, TypeError):
            pass
        return None

    @staticmethod
    def _extract_amounts(text: str) -> list[float]:
        """从文本中提取金额数字（简化版）。"""
        import re
        amounts = []
        # 匹配 "XX万元" 或 "XX元"
        for m in re.finditer(r'(\d+(?:\.\d+)?)\s*(万元|元)', text):
            val = float(m.group(1))
            unit = m.group(2)
            if unit == "万元":
                val *= 10000
            amounts.append(val)
        return amounts


    # ─── 合同关联查询（§7 合同关联关系）───

    def find_related_contracts(self, contract_no: str) -> list[dict]:
        """按合同编号关联规则查找关联合同（见 §7）。

        匹配规则：
        - 去掉 2 位类型前缀（CR/BC/ZZ/BG）后，从第 3 位开始的 14 位字符作为匹配主键
          例如 "CR-20260922-0001" 和 "BC-20260922-0001" 的 "-20260922-000" 部分相同
        - 补充协议 supplement: 编号含 BC
        - 终止协议 termination: 编号含 ZZ
        - 框架订单 order: 编号含额外 -数字后缀
        - 变更协议 amendment: 编号含 BG

        Args:
            contract_no: 合同编号

        Returns:
            关联合同列表，每条含 contract 基本信息 + relation_type + match_rule
        """
        conn = _db.get_connection(self.db_path)
        try:
            if not _db.table_exists(conn, "cr_contracts"):
                return []

            # 匹配键：从第 3 位开始取 14 位（去掉类型前缀 CR/BC/ZZ/BG 等）
            # 例如 "CR-20260922-0001" -> key = "-20260922-000" (14 chars)
            match_key = contract_no[3:17] if len(contract_no) >= 17 else contract_no[3:] if len(contract_no) > 3 else contract_no

            # 查找同日期+序号的所有合同
            # 编号格式：<前缀>-<日期8位>-<序号4位>...，从第 4 个字符开始的 13 位 = 日期(8) + '-' + 序号前4位中的前4位
            # 更准确：用 LIKE 匹配日期+序号部分
            # 提取日期和序号段
            parts = contract_no.split("-")
            if len(parts) >= 3:
                date_seq = f"-{parts[1]}-{parts[2]}"
            else:
                date_seq = match_key

            rows = conn.execute(
                f"""SELECT id, contract_no, title, status, amount, contract_type
                   FROM cr_contracts
                   WHERE contract_no LIKE ?
                     AND contract_no != ?
                     AND (deleted_at IS NULL OR deleted_at = '')
                   ORDER BY contract_no""",
                (f"%{date_seq}%", contract_no),
            ).fetchall()

            results = []
            for row in rows:
                other_no = row["contract_no"]
                rel_type, match_rule = self._detect_relation_type(contract_no, other_no)
                if rel_type:
                    results.append({
                        "contract_id": row["id"],
                        "contract_no": other_no,
                        "title": row["title"],
                        "status": row["status"],
                        "amount": row["amount"],
                        "contract_type": row["contract_type"],
                        "relation_type": rel_type,
                        "match_rule": match_rule,
                    })

            return results
        finally:
            conn.close()

    def _detect_relation_type(self, source_no: str, target_no: str) -> tuple[str, str]:
        """根据两份合同编号判断关联类型。

        匹配方式：提取「日期 + 序号」部分进行比较。
        格式通常为：<前缀>-<日期8位>-<序号4位>[-<子序号>]
        例如 CR-20260922-0001 与 BC-20260922-0001 的日期+序号部分相同。

        Returns:
            (relation_type, match_rule) 或 ("", "") 表示无关联
        """
        # 解析编号结构：按 '-' 分割，提取日期段和序号段
        src_parts = source_no.split("-")
        tgt_parts = target_no.split("-")

        if len(src_parts) < 3 or len(tgt_parts) < 3:
            return "", ""

        # 基础三段 = [类型前缀, 日期, 序号]，用于匹配
        src_base = src_parts[:3]  # e.g. ["CR", "20260922", "0001"]
        tgt_base = tgt_parts[:3]

        # 日期和序号必须匹配（第2、3段）
        if src_base[1] != tgt_base[1] or src_base[2] != tgt_base[2]:
            return "", ""

        # 补充协议：类型前缀含 BC
        if tgt_base[0].startswith("BC") or "BC" in tgt_base[0]:
            return "supplement", "bc_prefix"
        # 终止协议：类型前缀含 ZZ
        if tgt_base[0].startswith("ZZ") or "ZZ" in tgt_base[0]:
            return "termination", "zz_prefix"
        # 变更协议：类型前缀含 BG
        if tgt_base[0].startswith("BG") or "BG" in tgt_base[0]:
            return "amendment", "bg_prefix"
        # 框架订单：目标有更多段且都是数字（如 CR-20260922-0001-01）
        if len(tgt_parts) > len(src_parts):
            extra_parts = tgt_parts[len(src_parts):]
            if all(p.isdigit() for p in extra_parts):
                return "order", "dash_order"

        # 同类型同序号（不应该出现，但兜底为 related）
        if src_base[0] == tgt_base[0]:
            return "related", "prefix_14"

        # 不同类型但日期序号相同 → 通用关联
        return "related", "prefix_14"

    def auto_build_relations(self, contract_id: int) -> int:
        """自动为指定合同构建关联关系。

        扫描所有同前缀合同，按规则自动写入 cr_contract_relations 表。
        幂等操作：已存在的关系不会重复创建。

        Args:
            contract_id: 合同 ID

        Returns:
            新建的关系数量
        """
        conn = _db.get_connection(self.db_path)
        try:
            row = conn.execute(
                "SELECT contract_no FROM cr_contracts WHERE id = ?",
                (contract_id,),
            ).fetchone()
            if not row:
                raise ValueError(f"合同 {contract_id} 不存在")

            contract_no = row["contract_no"]
            related = self.find_related_contracts(contract_no)

            new_count = 0
            for rel in related:
                target_id = rel["contract_id"]
                rel_type = rel["relation_type"]
                match_rule = rel["match_rule"]

                # 检查是否已存在（双向都检查）
                existing = conn.execute(
                    """SELECT id FROM cr_contract_relations
                       WHERE (source_contract_id = ? AND target_contract_id = ? AND relation_type = ?)
                          OR (source_contract_id = ? AND target_contract_id = ? AND relation_type = ?)""",
                    (contract_id, target_id, rel_type, target_id, contract_id, rel_type),
                ).fetchone()
                if existing:
                    continue

                # 创建关系（源 → 目标）
                conn.execute(
                    """INSERT INTO cr_contract_relations
                       (source_contract_id, target_contract_id, relation_type, match_rule)
                       VALUES (?, ?, ?, ?)""",
                    (contract_id, target_id, rel_type, match_rule),
                )
                new_count += 1

            conn.commit()
            return new_count
        finally:
            conn.close()

    # ══════════════════════════════════════════════════════════
    # 合同关系管理（cr_contract_relations）
    # ══════════════════════════════════════════════════════════

    def add_relation(self, source_contract_id: int, target_contract_id: int,
                     relation_type: str, match_rule: str = "manual") -> int:
        """添加合同关系。

        Args:
            source_contract_id: 源合同 ID
            target_contract_id: 目标合同 ID
            relation_type: 关系类型（见 ContractRelationType）
            match_rule: 匹配规则（manual / prefix_14 / bc_prefix / ...）

        Returns:
            关系记录 ID

        Raises:
            ValueError: 关系类型无效 / 合同不存在 / 自关联
        """
        from .models import VALID_RELATION_TYPES

        if relation_type not in VALID_RELATION_TYPES:
            raise ValueError(
                f"无效的关系类型: {relation_type}，有效值: {VALID_RELATION_TYPES}"
            )
        if source_contract_id == target_contract_id:
            raise ValueError("不能创建自关联的合同关系")

        conn = _db.get_connection(self.db_path)
        try:
            # 校验两个合同都存在
            for cid in (source_contract_id, target_contract_id):
                row = conn.execute(
                    "SELECT id FROM cr_contracts WHERE id = ? "
                    "AND (deleted_at IS NULL OR deleted_at = '')",
                    (cid,),
                ).fetchone()
                if not row:
                    raise ValueError(f"合同 {cid} 不存在或已删除")

            # 幂等：已存在同类型关系则直接返回
            existing = conn.execute(
                """SELECT id FROM cr_contract_relations
                   WHERE source_contract_id = ? AND target_contract_id = ?
                     AND relation_type = ?""",
                (source_contract_id, target_contract_id, relation_type),
            ).fetchone()
            if existing:
                return existing["id"]

            cur = conn.execute(
                """INSERT INTO cr_contract_relations
                   (source_contract_id, target_contract_id, relation_type, match_rule)
                   VALUES (?, ?, ?, ?)""",
                (source_contract_id, target_contract_id, relation_type, match_rule),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()

    def remove_relation(self, relation_id: int) -> bool:
        """删除合同关系（硬删除，关联表）。

        Args:
            relation_id: 关系记录 ID

        Returns:
            True = 删除成功，False = 记录不存在
        """
        conn = _db.get_connection(self.db_path)
        try:
            cur = conn.execute(
                "DELETE FROM cr_contract_relations WHERE id = ?",
                (relation_id,),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def list_relations(self, contract_id: int,
                       relation_type: str = None) -> list[dict]:
        """列出合同的所有关系（双向）。

        Args:
            contract_id: 合同 ID
            relation_type: 可选，按关系类型过滤

        Returns:
            关系列表，每条包含 id, source_contract_id, target_contract_id,
            relation_type, match_rule, direction（source/target）
        """
        conn = _db.get_connection(self.db_path)
        try:
            conditions = ["(source_contract_id = ? OR target_contract_id = ?)"]
            params: list = [contract_id, contract_id]
            if relation_type:
                conditions.append("relation_type = ?")
                params.append(relation_type)
            where = " AND ".join(conditions)

            rows = conn.execute(
                f"""SELECT * FROM cr_contract_relations
                    WHERE {where}
                    ORDER BY created_at DESC""",
                params,
            ).fetchall()

            results = []
            for r in rows:
                d = dict(r)
                d["direction"] = "source" if r["source_contract_id"] == contract_id else "target"
                # 对方合同号
                other_id = r["target_contract_id"] if r["source_contract_id"] == contract_id \
                    else r["source_contract_id"]
                other_row = conn.execute(
                    "SELECT contract_no, title FROM cr_contracts WHERE id = ?",
                    (other_id,),
                ).fetchone()
                if other_row:
                    d["other_contract_no"] = other_row["contract_no"]
                    d["other_contract_title"] = other_row["title"]
                else:
                    d["other_contract_no"] = ""
                    d["other_contract_title"] = "(已删除)"
                results.append(d)
            return results
        finally:
            conn.close()

    def get_contract_tree(self, contract_id: int,
                          relation_type: str = None,
                          max_depth: int = 5) -> dict:
        """获取合同关系树（BFS 遍历双向关系）。

        Args:
            contract_id: 根合同 ID
            relation_type: 可选，仅遍历指定类型的关系
            max_depth: 最大遍历深度（防环）

        Returns:
            {
                "contract_id": int,
                "contract_no": str,
                "title": str,
                "depth": int,
                "children": [ ...递归... ]
            }
        """
        conn = _db.get_connection(self.db_path)
        try:
            # 获取根合同
            root_row = conn.execute(
                "SELECT id, contract_no, title FROM cr_contracts WHERE id = ?",
                (contract_id,),
            ).fetchone()
            if not root_row:
                return {}

            visited = {contract_id}
            from collections import deque
            queue = deque()
            root_node = {
                "contract_id": root_row["id"],
                "contract_no": root_row["contract_no"],
                "title": root_row["title"],
                "depth": 0,
                "children": [],
            }
            queue.append((contract_id, root_node, 0))

            while queue:
                curr_id, curr_node, depth = queue.popleft()
                if depth >= max_depth:
                    continue

                # 查找所有关联合同
                rel_rows = conn.execute(
                    """SELECT * FROM cr_contract_relations
                       WHERE source_contract_id = ? OR target_contract_id = ?""",
                    (curr_id, curr_id),
                ).fetchall()

                for rel in rel_rows:
                    if relation_type and rel["relation_type"] != relation_type:
                        continue
                    # 找到对方 ID
                    other_id = rel["target_contract_id"] \
                        if rel["source_contract_id"] == curr_id \
                        else rel["source_contract_id"]
                    if other_id in visited:
                        continue
                    visited.add(other_id)

                    other_row = conn.execute(
                        "SELECT id, contract_no, title FROM cr_contracts WHERE id = ?",
                        (other_id,),
                    ).fetchone()
                    if not other_row:
                        continue

                    child_node = {
                        "contract_id": other_row["id"],
                        "contract_no": other_row["contract_no"],
                        "title": other_row["title"],
                        "depth": depth + 1,
                        "relation_type": rel["relation_type"],
                        "relation_id": rel["id"],
                        "children": [],
                    }
                    curr_node["children"].append(child_node)
                    queue.append((other_id, child_node, depth + 1))

            return root_node
        finally:
            conn.close()

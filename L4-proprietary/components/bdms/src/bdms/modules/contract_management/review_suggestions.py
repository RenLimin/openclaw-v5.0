"""审核建议生成器 — ReviewSuggestionGenerator（场景 A）。

🔒 NO_TOKEN — 纯代码，零 AI 依赖。

基于风险扫描结果 + 条款解析结果，生成结构化的审核建议 JSON。
对齐 DESIGN-DETAIL §2.2 输出格式。
"""

import re
from typing import Optional


class ReviewSuggestionGenerator:
    """审核建议生成器。

    输入：合同详情 dict + 风险扫描结果 list + 条款明细 list
    输出：结构化审核建议 JSON（含 suggestions / auto_fill_fields / overall_risk）
    """

    # 风险等级权重
    RISK_WEIGHT = {
        "high": 3,
        "medium": 2,
        "low": 1,
    }

    def generate(self, contract: dict, risk_results: list[dict],
                 clauses: list[dict] = None) -> dict:
        """生成审核建议。

        Args:
            contract: 合同详情 dict
            risk_results: 风险扫描结果列表（每条含 risk_category, risk_level, issue_summary, suggestion）
            clauses: 条款明细列表（可选，每条含 clause_type, clause_title, clause_content）

        Returns:
            对齐 §2.2 格式的 dict:
            {
                "contract_no": str,
                "overall_risk": "high"|"medium"|"low",
                "suggestions": [
                    {
                        "clause_type": str,
                        "current_text": str,
                        "suggested_text": str,
                        "risk_level": str,
                        "law_ref": str,
                        "reason": str,
                    },
                    ...
                ],
                "auto_fill_fields": {
                    "party_a": str,
                    "amount": float,
                    "effective_date": str,
                    ...
                }
            }
        """
        clauses = clauses or []
        contract_no = contract.get("contract_no", "")
        amount = contract.get("amount", 0)

        # 综合风险评级
        overall_risk = self._compute_overall_risk(risk_results)

        # 生成建议
        suggestions = []
        for risk in risk_results:
            suggestion = self._risk_to_suggestion(risk, clauses, contract)
            if suggestion:
                suggestions.append(suggestion)

        # 自动填充字段（从合同详情中提取可确认的字段）
        auto_fill = self._extract_auto_fill(contract, clauses)

        return {
            "contract_no": contract_no,
            "overall_risk": overall_risk,
            "suggestions": suggestions,
            "auto_fill_fields": auto_fill,
        }

    def _compute_overall_risk(self, risk_results: list[dict]) -> str:
        """综合风险评级。

        规则：
        - 有 1 个 high → overall = high
        - 有 ≥3 个 medium → overall = high
        - 有 1~2 个 medium → overall = medium
        - 只有 low → overall = low
        - 无风险 → overall = low
        """
        if not risk_results:
            return "low"

        high_count = sum(1 for r in risk_results if r.get("risk_level") == "high")
        medium_count = sum(1 for r in risk_results if r.get("risk_level") == "medium")

        if high_count >= 1 or medium_count >= 3:
            return "high"
        elif medium_count >= 1:
            return "medium"
        else:
            return "low"

    def _risk_to_suggestion(self, risk: dict, clauses: list[dict],
                            contract: dict) -> Optional[dict]:
        """将单条风险扫描结果转换为审核建议。"""
        category = risk.get("risk_category", "")
        level = risk.get("risk_level", "low")
        issue = risk.get("issue_summary", "")
        suggestion_text = risk.get("suggestion", "")

        # 查找对应条款的当前文本
        current_text = ""
        clause_type = self._category_to_clause_type(category)
        for clause in clauses:
            if clause.get("clause_type") == clause_type:
                current_text = clause.get("clause_content", "")
                break

        # 生成建议修改文本（基于风险项生成模板化建议）
        suggested_text = self._generate_suggested_text(category, issue, contract)

        return {
            "clause_type": clause_type,
            "current_text": current_text,
            "suggested_text": suggested_text,
            "risk_level": level,
            "law_ref": suggestion_text,  # 法条参考
            "reason": issue,
        }

    def _category_to_clause_type(self, category: str) -> str:
        """风险类别 → 条款类型映射。"""
        mapping = {
            "主体信息": "parties",
            "合同标的": "subject",
            "金额与支付": "payment",
            "履行期限": "performance_period",
            "验收标准": "acceptance",
            "违约责任": "liability",
            "争议解决": "dispute_resolution",
            "知识产权": "ip_rights",
            "保密条款": "confidentiality",
            "不可抗力": "force_majeure",
            "合同解除": "termination",
            "格式条款": "standard_clause",
        }
        return mapping.get(category, category)

    def _generate_suggested_text(self, category: str, issue: str,
                                  contract: dict) -> str:
        """生成建议修改文本（模板化）。"""
        category = category or "其他"

        templates = {
            "主体信息": "建议明确甲乙双方完整名称、统一社会信用代码、注册地址、法定代表人及联系方式。",
            "合同标的": "建议明确合同标的的具体内容、规格、数量、质量标准及交付方式。",
            "金额与支付": f"建议明确合同总金额 {contract.get('amount', 0):,.2f} 元（含税），以及付款进度、支付方式、发票类型等。",
            "履行期限": "建议明确合同履行期限、里程碑节点及各阶段交付物。",
            "验收标准": "建议明确验收标准、验收流程、验收期限及不合格处理方式。",
            "违约责任": "建议明确违约责任的具体情形、违约金计算方式及上限。",
            "争议解决": "建议明确争议解决方式（诉讼/仲裁）及管辖法院/仲裁机构。",
            "知识产权": "建议明确知识产权归属、使用范围、许可方式及侵权责任。",
            "保密条款": "建议明确保密范围、保密期限、保密义务及泄密责任。",
            "不可抗力": "建议明确不可抗力的定义、通知义务、后果处理及合同解除条件。",
            "合同解除": "建议明确合同解除的条件、程序及解除后的处理方式。",
            "格式条款": "建议对格式条款进行合理提示，确保对方知悉并理解。",
        }
        return templates.get(category, f"建议审查并完善「{category}」相关条款。")

    def _extract_auto_fill(self, contract: dict, clauses: list[dict]) -> dict:
        """从合同中提取可自动填充的字段。"""
        auto_fill = {}

        # 从合同主表提取
        if contract.get("party_a"):
            auto_fill["party_a"] = contract["party_a"]
        if contract.get("party_b"):
            auto_fill["party_b"] = contract["party_b"]
        if contract.get("amount"):
            auto_fill["amount"] = contract["amount"]
        if contract.get("effective_date"):
            auto_fill["effective_date"] = contract["effective_date"]
        if contract.get("expiry_date"):
            auto_fill["expiry_date"] = contract["expiry_date"]
        if contract.get("title"):
            auto_fill["title"] = contract["title"]
        if contract.get("contract_type"):
            auto_fill["contract_type"] = contract["contract_type"]

        # 从条款中补充提取
        for clause in clauses:
            ctype = clause.get("clause_type", "")
            ctitle = clause.get("clause_title", "")
            # 提取付款方式
            if ctype == "payment" or "付款" in ctitle:
                content = clause.get("clause_content", "")
                auto_fill["payment_terms"] = content[:200] if content else ""

        return auto_fill

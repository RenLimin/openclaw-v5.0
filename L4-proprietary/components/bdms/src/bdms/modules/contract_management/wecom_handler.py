"""WeCom 消息处理器 — WecomContractHandler（场景 C）。

🔒 NO_TOKEN — 纯代码，零 AI 依赖。

接收 WeCom 消息回调，解析指令，调用 Service 执行，返回响应。
对齐 DESIGN-DETAIL §2.4 + §5.3。
"""

import re
from typing import Optional

from .errors import WecomParseError


class WecomContractHandler:
    """WeCom 合同管理消息处理器。

    支持指令：
    - "审批 [合同编号]" → 返回审核建议
    - "解析 [合同编号]" → 返回结构化结果
    - "查询 [关键词]" → 返回合同列表
    - "审批通过 [合同编号]" → 执行 approve
    - "驳回 [合同编号] [原因]" → 执行 reject

    注意：实际的 WeCom API 调用（消息发送）由 integration 模块的 I-04 连接器负责，
    本类只处理消息解析和业务逻辑调用。
    """

    # 指令正则模式
    PATTERNS = [
        # 注意：长指令必须排在短指令前面，避免短指令先匹配
        ("approve_pass", re.compile(r'^审批通过\s*(.+)$')),
        ("approve_review", re.compile(r'^审批\s*(.+)$')),
        ("reject", re.compile(r'^驳回\s*(\S+)(?:\s*(.+))?$')),
        ("parse", re.compile(r'^解析\s*(.+)$')),
        ("query", re.compile(r'^查询\s*(.+)$')),
        ("help", re.compile(r'^(帮助|help|\?|？)$', re.IGNORECASE)),
    ]

    def __init__(self, service=None):
        """初始化。

        Args:
            service: ContractManagementService 实例（可选，延迟注入）
        """
        self._service = service

    def set_service(self, service) -> None:
        """设置 Service 实例（依赖注入）。"""
        self._service = service

    @property
    def service(self):
        if self._service is None:
            raise RuntimeError("WecomContractHandler: service 未设置，请先调用 set_service()")
        return self._service

    # ══════════════════════════════════════════════════════════
    # 消息入口
    # ══════════════════════════════════════════════════════════

    def handle_message(self, message: dict) -> dict:
        """处理 WeCom 消息。

        Args:
            message: WeCom 消息 dict，至少包含 "content"（文本内容），
                     可选 "from_user"（发送人）、"msg_type"（消息类型）

        Returns:
            {
                "success": bool,
                "action": str,           # 执行的动作
                "result": dict|list,     # 执行结果
                "reply_text": str,       # 推荐回复文本
                "error": str,            # 错误信息（失败时）
            }

        Raises:
            WecomParseError: 消息解析失败
        """
        content = message.get("content", "").strip()
        from_user = message.get("from_user", "")
        msg_type = message.get("msg_type", "text")

        if not content:
            raise WecomParseError("消息内容为空")

        if msg_type != "text":
            raise WecomParseError(f"不支持的消息类型: {msg_type}，仅支持文本消息")

        # 匹配指令
        action, params = self._parse_command(content)

        # 执行
        try:
            if action == "help":
                return self._handle_help()
            elif action == "approve_review":
                return self._handle_approve_review(params, from_user)
            elif action == "parse":
                return self._handle_parse(params, from_user)
            elif action == "query":
                return self._handle_query(params, from_user)
            elif action == "approve_pass":
                return self._handle_approve_pass(params, from_user)
            elif action == "reject":
                return self._handle_reject(params, from_user)
            else:
                raise WecomParseError(f"无法识别的指令: {content}")
        except WecomParseError:
            raise
        except Exception as e:
            return {
                "success": False,
                "action": action,
                "result": {},
                "reply_text": f"执行失败: {e}",
                "error": str(e),
            }

    # ══════════════════════════════════════════════════════════
    # 指令解析
    # ══════════════════════════════════════════════════════════

    def _parse_command(self, content: str) -> tuple[str, dict]:
        """解析指令文本。按 PATTERNS 顺序匹配，长指令优先。

        Returns:
            (action, params)
        """
        for action, pattern in self.PATTERNS:
            m = pattern.match(content)
            if m:
                if action == "help":
                    return "help", {}
                elif action == "reject":
                    return "reject", {
                        "contract_no": m.group(1).strip(),
                        "reason": (m.group(2) or "").strip(),
                    }
                else:
                    return action, {"param": m.group(1).strip()}

        # 无法识别
        raise WecomParseError(f"无法识别的指令: {content}\n请输入「帮助」查看可用指令")

    # ══════════════════════════════════════════════════════════
    # 各指令处理器
    # ══════════════════════════════════════════════════════════

    def _handle_help(self) -> dict:
        """帮助指令。"""
        help_text = """📋 合同管理可用指令：

  审批 [合同编号]    — 获取合同审核建议
  解析 [合同编号]    — 解析合同结构
  查询 [关键词]      — 查询合同列表
  审批通过 [合同编号] — 通过审批
  驳回 [合同编号] [原因] — 驳回审批
  帮助 / help       — 显示此帮助

示例：
  审批 CR-20260922-0001
  查询 梆梆安全
  驳回 CR-20260922-0001 价格条款有问题"""

        return {
            "success": True,
            "action": "help",
            "result": {},
            "reply_text": help_text,
            "error": "",
        }

    def _handle_approve_review(self, params: dict, from_user: str) -> dict:
        """审批 [合同编号] → 获取审核建议。"""
        contract_no = params["param"]

        # 查找合同
        result = self.service.list_contracts(
            filters={"keyword": contract_no},
            page_size=5,
            mask=False,
        )

        if result["total"] == 0:
            return {
                "success": False,
                "action": "approve_review",
                "result": {},
                "reply_text": f"未找到合同编号为「{contract_no}」的合同",
                "error": "contract_not_found",
            }

        contract = result["items"][0]
        cid = contract["id"]

        # 生成审核建议
        suggestions = self.service.generate_review_suggestions(cid)

        reply_text = self._format_review_suggestions(contract, suggestions)

        return {
            "success": True,
            "action": "approve_review",
            "result": {
                "contract_id": cid,
                "contract_no": contract_no,
                "suggestions": suggestions,
            },
            "reply_text": reply_text,
            "error": "",
        }

    def _handle_parse(self, params: dict, from_user: str) -> dict:
        """解析 [合同编号] → 结构化结果。"""
        contract_no = params["param"]

        result = self.service.list_contracts(
            filters={"keyword": contract_no},
            page_size=5,
            mask=False,
        )

        if result["total"] == 0:
            return {
                "success": False,
                "action": "parse",
                "result": {},
                "reply_text": f"未找到合同编号为「{contract_no}」的合同",
                "error": "contract_not_found",
            }

        contract = result["items"][0]

        reply_text = self._format_contract_info(contract)

        return {
            "success": True,
            "action": "parse",
            "result": {"contract": contract},
            "reply_text": reply_text,
            "error": "",
        }

    def _handle_query(self, params: dict, from_user: str) -> dict:
        """查询 [关键词] → 合同列表。"""
        keyword = params["param"]

        result = self.service.list_contracts(
            filters={"keyword": keyword},
            page_size=10,
            mask=True,
        )

        if result["total"] == 0:
            return {
                "success": True,
                "action": "query",
                "result": {"items": [], "total": 0},
                "reply_text": f"未找到包含「{keyword}」的合同",
                "error": "",
            }

        reply_lines = [f"🔍 共找到 {result['total']} 份合同（显示前 {len(result['items'])} 条）：", ""]
        for i, item in enumerate(result["items"], 1):
            status_label = {
                "draft": "起草",
                "review1": "一级审批",
                "review2": "二级审批",
                "review3": "三级审批",
                "review4": "四级审批",
                "approved": "审批通过",
                "signed": "已签署",
                "archived": "已归档",
            }.get(item.get("status", ""), item.get("status", ""))
            reply_lines.append(
                f"{i}. {item['contract_no']} - {item['title']}\n   状态: {status_label} | 金额: {item.get('amount_display', item.get('amount', 0))}"
            )

        return {
            "success": True,
            "action": "query",
            "result": {"items": result["items"], "total": result["total"]},
            "reply_text": "\n".join(reply_lines),
            "error": "",
        }

    def _handle_approve_pass(self, params: dict, from_user: str) -> dict:
        """审批通过 [合同编号] → 执行 approve。"""
        contract_no = params["param"]

        result = self.service.list_contracts(
            filters={"keyword": contract_no},
            page_size=5,
            mask=False,
        )

        if result["total"] == 0:
            return {
                "success": False,
                "action": "approve_pass",
                "result": {},
                "reply_text": f"未找到合同编号为「{contract_no}」的合同",
                "error": "contract_not_found",
            }

        contract = result["items"][0]
        cid = contract["id"]

        try:
            approve_result = self.service.approve(cid, operator=from_user, role="wecom")
            return {
                "success": True,
                "action": "approve_pass",
                "result": approve_result,
                "reply_text": f"✅ 合同 {contract_no} 审批通过\n"
                              f"   状态: {approve_result['from_status']} → {approve_result['to_status']}",
                "error": "",
            }
        except Exception as e:
            return {
                "success": False,
                "action": "approve_pass",
                "result": {},
                "reply_text": f"❌ 审批失败: {e}",
                "error": str(e),
            }

    def _handle_reject(self, params: dict, from_user: str) -> dict:
        """驳回 [合同编号] [原因] → 执行 reject。"""
        contract_no = params["contract_no"]
        reason = params["reason"]

        result = self.service.list_contracts(
            filters={"keyword": contract_no},
            page_size=5,
            mask=False,
        )

        if result["total"] == 0:
            return {
                "success": False,
                "action": "reject",
                "result": {},
                "reply_text": f"未找到合同编号为「{contract_no}」的合同",
                "error": "contract_not_found",
            }

        contract = result["items"][0]
        cid = contract["id"]

        try:
            reject_result = self.service.reject(cid, operator=from_user,
                                                 role="wecom", comment=reason)
            return {
                "success": True,
                "action": "reject",
                "result": reject_result,
                "reply_text": f"❌ 合同 {contract_no} 已驳回\n"
                              f"   状态: {reject_result['from_status']} → {reject_result['to_status']}\n"
                              f"   原因: {reason}",
                "error": "",
            }
        except Exception as e:
            return {
                "success": False,
                "action": "reject",
                "result": {},
                "reply_text": f"驳回失败: {e}",
                "error": str(e),
            }

    # ══════════════════════════════════════════════════════════
    # 通知发送（模板方法，实际发送由 integration 负责）
    # ══════════════════════════════════════════════════════════

    def send_approval_notification(self, contract_id: int, next_approver: str) -> dict:
        """审批节点变更通知（模板方法）。

        注意：实际的 WeCom 消息发送由 integration 模块的 I-04 连接器负责。
        本方法生成通知内容模板。

        Returns:
            {"template": str, "target": str, "contract_id": int}
        """
        contract = self.service.get_contract(contract_id)
        if not contract:
            return {"template": "", "target": next_approver, "contract_id": contract_id}

        template = (
            f"📋 待审批合同通知\n"
            f"合同编号: {contract['contract_no']}\n"
            f"合同名称: {contract['title']}\n"
            f"金额: {contract['amount']:,.2f} 元\n"
            f"当前状态: {contract['status']}\n"
            f"请及时处理审批。"
        )

        return {
            "template": template,
            "target": next_approver,
            "contract_id": contract_id,
        }

    def send_risk_alert(self, contract_id: int, risk_summary: str) -> dict:
        """高风险预警通知（模板方法）。

        Returns:
            {"template": str, "contract_id": int}
        """
        contract = self.service.get_contract(contract_id)
        if not contract:
            return {"template": "", "contract_id": contract_id}

        template = (
            f"⚠️ 合同高风险预警\n"
            f"合同编号: {contract['contract_no']}\n"
            f"合同名称: {contract['title']}\n"
            f"风险摘要: {risk_summary}\n"
            f"请法务人员及时审查。"
        )

        return {
            "template": template,
            "contract_id": contract_id,
        }

    # ══════════════════════════════════════════════════════════
    # 格式化辅助
    # ══════════════════════════════════════════════════════════

    def _format_review_suggestions(self, contract: dict, suggestions: dict) -> str:
        """格式化审核建议为可读文本。"""
        overall = suggestions.get("overall_risk", "low")
        overall_label = {"high": "🔴 高", "medium": "🟡 中", "low": "🟢 低"}.get(overall, overall)

        lines = [
            f"📋 合同审核建议 — {contract['contract_no']}",
            f"合同名称: {contract['title']}",
            f"综合风险: {overall_label}",
            "",
        ]

        sugg_list = suggestions.get("suggestions", [])
        if sugg_list:
            lines.append(f"风险项 ({len(sugg_list)} 条):")
            for i, s in enumerate(sugg_list[:10], 1):
                level = s.get("risk_level", "low")
                level_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(level, "•")
                lines.append(f"  {i}. {level_icon} [{s.get('clause_type', '')}] {s.get('reason', '')}")
            if len(sugg_list) > 10:
                lines.append(f"  ... 还有 {len(sugg_list) - 10} 条")
        else:
            lines.append("✅ 未发现自动扫描风险项")

        lines.append("")
        lines.append("回复「审批通过 [合同编号]」或「驳回 [合同编号] [原因]」进行操作")

        return "\n".join(lines)

    def _format_contract_info(self, contract: dict) -> str:
        """格式化合同信息为可读文本。"""
        status_label = {
            "draft": "起草", "review1": "一级审批", "review2": "二级审批",
            "review3": "三级审批", "review4": "四级审批", "approved": "审批通过",
            "signed": "已签署", "archived": "已归档",
        }.get(contract.get("status", ""), contract.get("status", ""))

        lines = [
            f"📄 合同详情 — {contract['contract_no']}",
            f"名称: {contract.get('title', '')}",
            f"类型: {contract.get('contract_type', '')}",
            f"甲方: {contract.get('party_a', '')}",
            f"乙方: {contract.get('party_b', '')}",
            f"金额: {contract.get('amount', 0):,.2f} 元",
            f"生效日期: {contract.get('effective_date', '')}",
            f"到期日期: {contract.get('expiry_date', '')}",
            f"状态: {status_label}",
            f"审批级别: {contract.get('approval_level', 1)} 级",
        ]

        return "\n".join(lines)

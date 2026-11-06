"""OaWritebackConnector — 泛微 OA 外部写连接器（P4.3，详设 §4）。

核心语义（Rex 已拍板）：**外部写不可物理补偿**。
- apply 成功后 OA 流程已流转，任何补偿都不得反向改 OA；
- compensate 恒抛 CompensationUnavailable，由 SagaOrchestrator 记入
  report.compensation_unavailable、置 reconciliation_required，
  生成人工冲销工单；结果标 externally_committed，绝不宣称"已回滚"。

P4.2（真实写端点契约）未闭合前：
- dry_run=True（默认）：只经 ctx.mark_success 落审计，不发任何 HTTP；
- dry_run=False：直接拒绝（RuntimeError），禁止臆造写端点。

target 解析复用 connector.py 的两路径模式：
- 多步 Saga：ctx.payloads[step_name]（编排器 apply 前写入）；
- 单连接器路径：构造注入 target。
"""
from __future__ import annotations

import os
import sys
from datetime import datetime
from typing import Any, Dict, Optional


def _ensure_paths() -> None:
    here = os.path.dirname(os.path.abspath(__file__))          # .../ontology_bridge
    comp = os.path.dirname(os.path.dirname(here))              # .../bangcle-contract
    l4_components = os.path.dirname(comp)                      # .../components
    root = os.path.abspath(os.path.join(l4_components, "..", ".."))  # workspace root
    paths = [
        comp,
        os.path.join(root, "L2-infra", "components", "ai-knowledge-base"),
    ]
    for p in paths:
        if os.path.isdir(p) and p not in sys.path:
            sys.path.insert(0, p)


_ensure_paths()

from ai_kb.ontology import (  # noqa: E402
    CompensationUnavailable,
    SagaContext,
    WritebackConnector,
)


def _now() -> str:
    return datetime.now().isoformat()


class OaWritebackConnector(WritebackConnector):
    """OA 外部写连接器：dry-run 审计 / 真实写冻结 / 补偿恒不可用。"""

    name = "oa_writeback"

    def __init__(
        self,
        *,
        step_name: str = "oa_writeback",
        dry_run: bool = True,
        target: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.step_name = step_name
        self.dry_run = dry_run
        self.target = target or {}

    # --- target 解析（与 ContractWritebackConnector 同模式）---
    def _resolve_target(self, ctx: SagaContext) -> Dict[str, Any]:
        payload = ctx.payloads.get(self.step_name)
        if isinstance(payload, dict) and payload:
            return payload
        if self.target:
            return self.target
        raise ValueError(
            "OaWritebackConnector: no target payload "
            "(multi-step saga needs payloads[%s]; single path needs target=)"
            % self.step_name
        )

    def apply(self, ctx: SagaContext) -> None:
        target = self._resolve_target(ctx)
        if not self.dry_run:
            # P4.2 抓包契约 + Rex 二次授权 + 测试单据白名单到位前，禁止真实写。
            raise RuntimeError(
                "P4.2 写端点契约未闭合，禁止真实写回 "
                "(需测试流程单据 + Rex 二次授权 + 增量文档 p4-write-v1.1)"
            )
        # dry-run：只落审计（经 ctx），绝不发起任何 HTTP 请求。
        ctx.mark_success(self.name, {
            "dry_run": True,
            "requestid": target.get("requestid"),
            "action": target.get("action"),
            "comment": target.get("comment"),
            "recorded_at": _now(),
            "note": "P4.2 未闭合：仅审计，未向 OA 发起写请求",
        })

    def compensate(self, ctx: SagaContext) -> None:
        # 恒抛：OA 外部写不可物理回滚，需人工冲销工单。
        raise CompensationUnavailable(
            "OA 外部写不可物理回滚，需人工冲销工单"
        )


__all__ = ["OaWritebackConnector"]

#!/usr/bin/env python3
"""
Bangcle 产品专家 Agent - E2E 验证脚本
验证: 创建实例 → 导入知识 → 查询带来源 → 反馈 → MCP → 统计 全链路
"""
import os
import sys
import tempfile

SB = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, SB)

from ai_kb.db import AIKB
from ai_kb.ingestion import IngestionPipeline
from ai_kb.api import AIKBService
from mcp.server import KBMCPHandler
from ai_kb.template import TemplateManager


PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name} {detail}")


def main():
    print("=== Bangcle 产品专家 Agent E2E 验证 ===")

    # 1. 创建临时实例（product-kb 模板）
    print("\n[1] 实例化（product-kb 模板）")
    tmp = tempfile.mkdtemp(prefix="bangcle-e2e-")
    db_path = os.path.join(tmp, "bangcle.db")
    kb = AIKB(db_path)
    kb.init_db()
    tm = TemplateManager(kb)
    domain_id = tm.create_instance_from_template(
        "product-kb", "bangcle-products", "Bangcle产品知识库"
    )
    check("模板实例化成功", domain_id > 0, f"domain_id={domain_id}")

    # 2. 导入产品知识
    print("\n[2] 导入产品知识")
    pipe = IngestionPipeline(kb)
    kb_dir = os.path.join(os.path.dirname(__file__), "..", "knowledge")
    doc_count = 0
    for fname in sorted(os.listdir(kb_dir)):
        if fname.endswith(".md"):
            result = pipe.ingest_single_file(domain_id, os.path.join(kb_dir, fname))
            check(f"导入 {fname}", result.success, result.error or "")
            if result.success:
                doc_count += 1
    check("导入 3 篇文档", doc_count == 3, f"doc_count={doc_count}")

    # 3. 查询带来源
    print("\n[3] 查询（带来源引用）")
    service = AIKBService(db_path, "bangcle-products")
    resp = service.query("APP加固有什么功能", top_k=5, format="markdown")
    check("查询返回来源", resp.get("source_count", 0) >= 1, f"source_count={resp.get('source_count')}")
    check("来源含实体名", resp["sources"][0].get("entity_name") if resp["sources"] else False, str(resp.get("sources", []))[:100])
    check("markdown 含来源引用", "来源引用" in resp.get("markdown", ""), resp.get("markdown", "")[:50])

    # 4. 跨产品查询
    resp2 = service.query("渠道监测能做什么", top_k=5, format="json")
    check("渠道监测查询命中", resp2.get("source_count", 0) >= 1, f"source_count={resp2.get('source_count')}")

    # 5. 反馈提交
    print("\n[4] 反馈提交")
    fb = service.add_feedback(
        query_text="APP加固有什么功能",
        feedback_type="useful",
        user_id="e2e-user",
        entity_id=resp["sources"][0].get("entity_id") if resp["sources"] else None,
    )
    check("反馈提交成功", fb.get("status") == "success" and fb.get("feedback_id", 0) > 0, str(fb))

    # 6. 统计
    stats = service.stats()
    check("统计实体数", stats.get("entities", 0) >= 3, str(stats))
    check("统计文档数", stats.get("documents", 0) == 3, str(stats))

    # 7. MCP 工具
    print("\n[5] MCP 工具验证")
    handler = KBMCPHandler(db_path, "bangcle-products")
    tools = handler.list_tools()
    tool_names = {t["name"] for t in tools}
    check("MCP 工具 >= 9", len(tools) >= 9, f"count={len(tools)}")
    check("含 kb_query", "kb_query" in tool_names)
    check("含 kb_add_feedback", "kb_add_feedback" in tool_names)
    check("含 kb_stats", "kb_stats" in tool_names)

    mcp_resp = handler.call_tool("kb_query", {"question": "威胁情报有什么来源", "top_k": 3, "format": "json"})
    check("MCP kb_query 命中", mcp_resp.get("source_count", 0) >= 1, str(mcp_resp)[:150])

    # 8. 低评分识别（质量巡检）
    print("\n[6] 质量体系验证")
    low = service.list_low_score_knowledge(threshold=1)
    check("低评分列表可调用", isinstance(low, list))

    service.close()
    kb.close()
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)

    print("\n" + "=" * 40)
    print(f"结果: {PASS} 通过 / {FAIL} 失败")
    print("=" * 40)
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

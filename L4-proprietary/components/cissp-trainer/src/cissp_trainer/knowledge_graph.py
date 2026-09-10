"""
知识图谱服务

基于邻接表 + SQLAlchemy，实现：
  - 知识点依赖查询（前置/后继）
  - 相关知识点查询
  - 学习路径推荐（"你掌握了 A，可以学 B 了"）
  - 薄弱点传播分析（一个点弱会影响哪些后续点）
  - Mermaid / 文本可视化
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import or_
from sqlalchemy.orm import Session

from .models import KnowledgePoint, KnowledgeEdge, DOMAIN_NAMES


EdgeType = Literal["prerequisite", "related", "part_of"]


@dataclass
class GraphNode:
    """图谱节点（便于计算）"""
    kp_id: int
    name: str
    domain: int
    mastery: float


@dataclass
class PropagationResult:
    """薄弱点传播结果"""
    source_kp: str
    affected_kps: list[dict]  # [{name, domain, mastery, distance, impact}]
    total_affected: int


# ── 边管理 ────────────────────────────────────────────────

def add_edge(
    session: Session,
    source_name: str,
    target_name: str,
    domain: int,
    edge_type: EdgeType = "prerequisite",
    weight: float = 1.0,
    description: str = "",
) -> KnowledgeEdge | None:
    """
    添加一条知识点关联边

    参数：
      source_name: 源知识点名称（前置）
      target_name: 目标知识点名称（后继）
      domain: 领域 ID（1-8）
      edge_type: 边类型
      weight: 关联强度 0-1
      description: 描述
    """
    # 确保两个知识点都存在
    src = _get_or_create_kp(session, source_name, domain)
    tgt = _get_or_create_kp(session, target_name, domain)

    # 检查是否已存在
    existing = (
        session.query(KnowledgeEdge)
        .filter(
            KnowledgeEdge.source_kp_id == src.id,
            KnowledgeEdge.target_kp_id == tgt.id,
            KnowledgeEdge.edge_type == edge_type,
        )
        .first()
    )
    if existing:
        existing.weight = max(existing.weight, weight)
        if description and not existing.description:
            existing.description = description
        return existing

    edge = KnowledgeEdge(
        source_kp_id=src.id,
        target_kp_id=tgt.id,
        edge_type=edge_type,
        weight=weight,
        description=description,
    )
    session.add(edge)
    session.flush()
    return edge


def _get_or_create_kp(session: Session, name: str, domain: int) -> KnowledgePoint:
    kp = (
        session.query(KnowledgePoint)
        .filter(KnowledgePoint.name == name, KnowledgePoint.domain == domain)
        .first()
    )
    if kp:
        return kp
    kp = KnowledgePoint(name=name, domain=domain, mastery_level=0.0)
    session.add(kp)
    session.flush()
    return kp


def remove_edge(session: Session, source_name: str, target_name: str,
                domain: int, edge_type: EdgeType = "prerequisite") -> bool:
    """删除一条边"""
    src = session.query(KnowledgePoint).filter_by(name=source_name, domain=domain).first()
    tgt = session.query(KnowledgePoint).filter_by(name=target_name, domain=domain).first()
    if not src or not tgt:
        return False
    edge = (
        session.query(KnowledgeEdge)
        .filter_by(source_kp_id=src.id, target_kp_id=tgt.id, edge_type=edge_type)
        .first()
    )
    if not edge:
        return False
    session.delete(edge)
    session.flush()
    return True


# ── 查询：前置 / 后继 ─────────────────────────────────────

def get_prerequisites(session: Session, kp_name: str, domain: int | None = None,
                      depth: int = 3) -> list[dict]:
    """
    查询一个知识点的所有前置知识点（向上递归）

    返回按层级排序的列表：[{name, domain, mastery, depth}]
    """
    start = _find_kp(session, kp_name, domain)
    if not start:
        return []

    visited = {}  # kp_id -> depth
    queue = deque([(start.id, 0)])

    while queue:
        kp_id, d = queue.popleft()
        if d >= depth:
            continue
        # 找所有入边的源（前置）
        edges = (
            session.query(KnowledgeEdge)
            .filter(
                KnowledgeEdge.target_kp_id == kp_id,
                KnowledgeEdge.edge_type == "prerequisite",
            )
            .all()
        )
        for e in edges:
            if e.source_kp_id not in visited:
                visited[e.source_kp_id] = d + 1
                queue.append((e.source_kp_id, d + 1))

    # 取回知识点信息
    result = []
    for kp_id, d in sorted(visited.items(), key=lambda x: x[1]):
        kp = session.get(KnowledgePoint, kp_id)
        if kp:
            result.append({
                "name": kp.name,
                "domain": kp.domain,
                "mastery": kp.mastery_level,
                "depth": d,
            })
    return result


def get_successors(session: Session, kp_name: str, domain: int | None = None,
                   depth: int = 3) -> list[dict]:
    """
    查询一个知识点的所有后继知识点（向下递归）
    """
    start = _find_kp(session, kp_name, domain)
    if not start:
        return []

    visited = {}
    queue = deque([(start.id, 0)])

    while queue:
        kp_id, d = queue.popleft()
        if d >= depth:
            continue
        edges = (
            session.query(KnowledgeEdge)
            .filter(
                KnowledgeEdge.source_kp_id == kp_id,
                KnowledgeEdge.edge_type == "prerequisite",
            )
            .all()
        )
        for e in edges:
            if e.target_kp_id not in visited:
                visited[e.target_kp_id] = d + 1
                queue.append((e.target_kp_id, d + 1))

    result = []
    for kp_id, d in sorted(visited.items(), key=lambda x: x[1]):
        kp = session.get(KnowledgePoint, kp_id)
        if kp:
            result.append({
                "name": kp.name,
                "domain": kp.domain,
                "mastery": kp.mastery_level,
                "depth": d,
            })
    return result


def get_related(session: Session, kp_name: str, domain: int | None = None) -> list[dict]:
    """查询相关知识点（related 类型 + part_of 类型，双向）"""
    start = _find_kp(session, kp_name, domain)
    if not start:
        return []

    # related + part_of，双向
    edges = (
        session.query(KnowledgeEdge)
        .filter(
            or_(KnowledgeEdge.source_kp_id == start.id,
                KnowledgeEdge.target_kp_id == start.id),
            KnowledgeEdge.edge_type.in_(["related", "part_of"]),
        )
        .all()
    )

    related_ids = set()
    for e in edges:
        if e.source_kp_id == start.id:
            related_ids.add(e.target_kp_id)
        else:
            related_ids.add(e.source_kp_id)

    result = []
    for kp_id in related_ids:
        kp = session.get(KnowledgePoint, kp_id)
        if kp:
            result.append({
                "name": kp.name,
                "domain": kp.domain,
                "mastery": kp.mastery_level,
                "edge_type": _find_edge_type(edges, start.id, kp_id),
            })
    return result


def _find_edge_type(edges: list[KnowledgeEdge], from_id: int, to_id: int) -> str:
    for e in edges:
        if e.source_kp_id == from_id and e.target_kp_id == to_id:
            return e.edge_type
        if e.target_kp_id == from_id and e.source_kp_id == to_id:
            return e.edge_type
    return "related"


def _find_kp(session: Session, name: str, domain: int | None) -> KnowledgePoint | None:
    """找知识点。domain 为 None 时按名字模糊匹配第一个"""
    if domain:
        return session.query(KnowledgePoint).filter_by(name=name, domain=domain).first()
    return session.query(KnowledgePoint).filter_by(name=name).first()


# ── 学习建议 ──────────────────────────────────────────────

def suggest_next_kps(session: Session, kp_name: str,
                     domain: int | None = None, top_n: int = 5) -> list[dict]:
    """
    学习建议：掌握了 A 之后，可以学哪些后继知识点？

    规则：
      1. 找到 A 的直接后继（深度 1）
      2. 检查后继的所有前置是否已掌握（掌握度 >= 0.7）
      3. 返回"前置已全部掌握"的后继点，按掌握度升序（最应该学的在前）
    """
    direct_successors = get_successors(session, kp_name, domain, depth=1)
    if not direct_successors:
        return []

    result = []
    for succ in direct_successors:
        # 检查这个后继点的所有前置
        prereqs = get_prerequisites(session, succ["name"], succ["domain"], depth=1)
        all_mastered = all(p["mastery"] >= 0.7 for p in prereqs)
        if all_mastered and succ["mastery"] < 0.7:
            result.append(succ)

    # 按掌握度升序（越低越该学）
    result.sort(key=lambda x: x["mastery"])
    return result[:top_n]


# ── 薄弱点传播分析 ─────────────────────────────────────────

def analyze_weak_propagation(session: Session, kp_name: str,
                             domain: int | None = None,
                             max_depth: int = 5) -> PropagationResult:
    """
    薄弱点传播分析：如果某个知识点薄弱，会影响哪些后续知识点？

    影响度 = 源点薄弱程度 × 路径权重 × (1 / 距离)
    - 源点薄弱程度 = 1 - mastery
    - 距离越远影响越小
    """
    start = _find_kp(session, kp_name, domain)
    if not start:
        return PropagationResult(source_kp=kp_name, affected_kps=[], total_affected=0)

    source_weakness = 1.0 - start.mastery_level

    # BFS 遍历所有后继
    # kp_id -> {distance, max_weight_path_product}
    affected = {}
    queue = deque([(start.id, 0, 1.0)])  # (kp_id, distance, weight_product)

    while queue:
        kp_id, dist, wprod = queue.popleft()
        if dist >= max_depth:
            continue

        edges = (
            session.query(KnowledgeEdge)
            .filter(
                KnowledgeEdge.source_kp_id == kp_id,
                KnowledgeEdge.edge_type == "prerequisite",
            )
            .all()
        )
        for e in edges:
            new_wprod = wprod * e.weight
            new_dist = dist + 1
            tgt_id = e.target_kp_id
            if tgt_id == start.id:
                continue
            if tgt_id not in affected or new_wprod > affected[tgt_id]["weight_product"]:
                affected[tgt_id] = {
                    "distance": new_dist,
                    "weight_product": new_wprod,
                }
                queue.append((tgt_id, new_dist, new_wprod))

    # 计算影响度
    affected_list = []
    for kp_id, info in affected.items():
        kp = session.get(KnowledgePoint, kp_id)
        if not kp:
            continue
        # impact = 薄弱程度 × 权重积 × (1 / 距离)
        impact = source_weakness * info["weight_product"] * (1.0 / info["distance"])
        impact = round(impact, 4)
        affected_list.append({
            "name": kp.name,
            "domain": kp.domain,
            "mastery": kp.mastery_level,
            "distance": info["distance"],
            "impact": impact,
        })

    # 按影响度降序
    affected_list.sort(key=lambda x: -x["impact"])

    return PropagationResult(
        source_kp=start.name,
        affected_kps=affected_list,
        total_affected=len(affected_list),
    )


# ── 领域图谱构建 ───────────────────────────────────────────

def build_domain_graph(session: Session, domain: int) -> dict:
    """
    构建某个领域的完整知识图谱

    返回：
      {
        "domain": 1,
        "domain_name": "安全与风险管理",
        "nodes": [{id, name, mastery, ...}],
        "edges": [{source, target, type, weight}],
      }
    """
    kps = session.query(KnowledgePoint).filter_by(domain=domain).all()
    kp_ids = {kp.id for kp in kps}

    # 获取这个领域内的所有边
    edges = (
        session.query(KnowledgeEdge)
        .filter(
            KnowledgeEdge.source_kp_id.in_(kp_ids),
            KnowledgeEdge.target_kp_id.in_(kp_ids),
        )
        .all()
    )

    nodes = []
    for kp in kps:
        nodes.append({
            "id": kp.id,
            "name": kp.name,
            "mastery": kp.mastery_level,
            "total_questions": kp.total_questions,
            "review_count": kp.review_count,
        })

    edge_list = []
    id_to_name = {kp.id: kp.name for kp in kps}
    for e in edges:
        edge_list.append({
            "source": id_to_name.get(e.source_kp_id, f"kp_{e.source_kp_id}"),
            "target": id_to_name.get(e.target_kp_id, f"kp_{e.target_kp_id}"),
            "type": e.edge_type,
            "weight": e.weight,
        })

    return {
        "domain": domain,
        "domain_name": DOMAIN_NAMES.get(domain, f"域{domain}"),
        "nodes": nodes,
        "edges": edge_list,
    }


# ── 可视化输出 ─────────────────────────────────────────────

def to_mermaid(session: Session, domain: int, direction: str = "TD") -> str:
    """
    生成 Mermaid 流程图表示领域知识图谱

    参数：
      domain: 领域 ID
      direction: TD / LR / BT / RL
    """
    graph = build_domain_graph(session, domain)
    lines = [f"flowchart {direction}"]

    # 节点
    for node in graph["nodes"]:
        # 掌握度不同颜色
        mastery = node["mastery"]
        if mastery >= 0.8:
            style = ":::mastered"
        elif mastery >= 0.5:
            style = ":::learning"
        elif mastery > 0:
            style = ":::weak"
        else:
            style = ":::notstarted"

        safe_name = _safe_mermaid_id(node["name"])
        lines.append(f"    {safe_name}[\"{node['name']}\"]{style}")

    # 边
    for edge in graph["edges"]:
        src = _safe_mermaid_id(edge["source"])
        tgt = _safe_mermaid_id(edge["target"])
        if edge["type"] == "prerequisite":
            arrow = "-->"
        elif edge["type"] == "related":
            arrow = "-.->"
        else:
            arrow = "-->"
        lines.append(f"    {src} {arrow} {tgt}")

    # 样式定义
    lines.extend([
        "",
        "    classDef mastered fill:#22c55e,stroke:#16a34a,color:white",
        "    classDef learning fill:#3b82f6,stroke:#2563eb,color:white",
        "    classDef weak fill:#f59e0b,stroke:#d97706,color:white",
        "    classDef notstarted fill:#9ca3af,stroke:#6b7280,color:white",
    ])

    return "\n".join(lines)


def _safe_mermaid_id(name: str) -> str:
    """将中文/特殊字符转成安全的 mermaid 节点 ID"""
    # 用中文的 hash 编码，保证唯一性且可读
    import hashlib
    h = hashlib.md5(name.encode("utf-8")).hexdigest()[:8]
    return f"n{h}"


def to_text_tree(session: Session, domain: int, max_depth: int = 5) -> str:
    """
    生成纯文本树状知识结构图（基于前置依赖）

    从根节点（没有前置的点）出发，向下展示层级
    """
    graph = build_domain_graph(session, domain)
    if not graph["nodes"]:
        return f"[域{domain} {graph['domain_name']}] 暂无知识点数据"

    # 构建邻接表
    name_to_node = {n["name"]: n for n in graph["nodes"]}
    adj = defaultdict(list)  # source -> [target, ...]
    in_degree = defaultdict(int)

    for e in graph["edges"]:
        if e["type"] == "prerequisite":
            adj[e["source"]].append(e["target"])
            in_degree[e["target"]] += 1

    # 根节点：入度为 0 的点
    roots = [n["name"] for n in graph["nodes"] if in_degree.get(n["name"], 0) == 0]

    if not roots:
        # 没有边，按字母序展示所有节点
        lines = [f"📂 {graph['domain_name']}（{len(graph['nodes'])} 个知识点，无层级关系）"]
        for n in sorted(graph["nodes"], key=lambda x: x["name"]):
            bar = _mastery_bar(n["mastery"])
            lines.append(f"  • {n['name']} {bar} {n['mastery']*100:.0f}%")
        return "\n".join(lines)

    # DFS 构建树
    lines = [f"🌳 {graph['domain_name']}（{len(graph['nodes'])} 个知识点）"]
    visited = set()

    def dfs(name: str, prefix: str, depth: int):
        if depth > max_depth or name in visited:
            return
        visited.add(name)
        node = name_to_node.get(name, {"mastery": 0.0})
        bar = _mastery_bar(node["mastery"])
        connector = "└── " if not adj.get(name) else "├── "
        lines.append(f"{prefix}{connector}{name} {bar} {node['mastery']*100:.0f}%")
        children = sorted(adj.get(name, []))
        new_prefix = prefix + "    "
        for i, child in enumerate(children):
            if i == len(children) - 1:
                dfs(child, new_prefix, depth + 1)
            else:
                dfs(child, new_prefix, depth + 1)

    for root in sorted(roots):
        dfs(root, "", 0)

    # 没被访问到的（孤岛）
    unvisited = [n["name"] for n in graph["nodes"] if n["name"] not in visited]
    if unvisited:
        lines.append("")
        lines.append(f"  （{len(unvisited)} 个独立知识点）")
        for name in sorted(unvisited):
            node = name_to_node[name]
            bar = _mastery_bar(node["mastery"])
            lines.append(f"    • {name} {bar} {node['mastery']*100:.0f}%")

    return "\n".join(lines)


def _mastery_bar(mastery: float, length: int = 10) -> str:
    """生成掌握度进度条"""
    filled = int(mastery * length)
    return "█" * filled + "░" * (length - filled)


def mastery_heatmap(session: Session) -> str:
    """
    生成全领域知识点掌握度热力图（文本版）

    按领域分组，按掌握度排序，用颜色块表示
    """
    lines = ["🔥 CISSP 知识点掌握热力图", "=" * 60]

    for domain_id in range(1, 9):
        kps = (
            session.query(KnowledgePoint)
            .filter_by(domain=domain_id)
            .order_by(KnowledgePoint.mastery_level.desc())
            .all()
        )
        if not kps:
            continue

        domain_name = DOMAIN_NAMES.get(domain_id, f"域{domain_id}")
        avg_mastery = sum(kp.mastery_level for kp in kps) / len(kps) if kps else 0

        lines.append(f"\n📚 域{domain_id} {domain_name}（平均 {avg_mastery*100:.0f}%）")

        # 用符号表示掌握度
        symbols = []
        for kp in kps:
            m = kp.mastery_level
            if m >= 0.9:
                s = "🟩"  # 深绿-精通
            elif m >= 0.7:
                s = "🟢"  # 绿-掌握
            elif m >= 0.5:
                s = "🟡"  # 黄-学习中
            elif m >= 0.3:
                s = "🟠"  # 橙-薄弱
            elif m > 0:
                s = "🔴"  # 红-很差
            else:
                s = "⬜"  # 白-未学
            symbols.append(s)

        # 每行 20 个
        row_size = 20
        for i in range(0, len(symbols), row_size):
            row = "".join(symbols[i:i+row_size])
            lines.append(f"  {row}")

        lines.append(f"  共 {len(kps)} 个知识点")

    return "\n".join(lines)


# ── 批量导入预设图谱 ───────────────────────────────────────

def import_preset_graph(session: Session, preset_data: list[dict]) -> dict:
    """
    导入预设知识图谱数据

    preset_data 格式：
    [
      {
        "domain": 1,
        "edges": [
          {"source": "安全基础", "target": "CIA三元组", "type": "prerequisite", "weight": 1.0},
          ...
        ]
      },
      ...
    ]
    """
    added = 0
    skipped = 0
    errors = []

    for domain_entry in preset_data:
        domain = domain_entry.get("domain")
        if not domain or domain < 1 or domain > 8:
            errors.append(f"无效领域: {domain}")
            continue
        for edge_data in domain_entry.get("edges", []):
            try:
                source = edge_data["source"]
                target = edge_data["target"]
                edge_type = edge_data.get("type", "prerequisite")
                weight = edge_data.get("weight", 1.0)
                desc = edge_data.get("description", "")
                add_edge(session, source, target, domain, edge_type, weight, desc)
                added += 1
            except Exception as e:
                errors.append(f"领域{domain} 边 {edge_data}: {e}")

    return {"added": added, "skipped": skipped, "errors": errors}

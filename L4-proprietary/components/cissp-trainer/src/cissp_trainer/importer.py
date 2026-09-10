"""
题库导入器

支持格式：
  - YAML（推荐，便于人工维护）
  - JSON（兼容现有 cissp-learning 格式）
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy.orm import Session

from .models import Question, KnowledgePoint, DOMAIN_NAMES


# ── YAML 格式 ─────────────────────────────────────────────
#
# questions:
#   - id: "domain1-001"          # 可选，外部 ID
#     domain: 1
#     difficulty: 2              # 1-5
#     question_type: single      # single / multiple / truefalse
#     stem: "题干..."
#     options:
#       A: "选项A"
#       B: "选项B"
#       C: "选项C"
#       D: "选项D"
#     correct_answer: "A"
#     explanation: "解析..."
#     tags: ["机密性", "安全模型"]   # 知识点标签
#     source: "CISSP OSG 第8版"
#     main_topic: "1.2"

def load_yaml_questions(file_path: str | Path) -> list[dict]:
    """从 YAML 文件加载题目（返回 dict 列表）"""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"YAML file not found: {path}")

    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if isinstance(data, dict) and "questions" in data:
        return data["questions"]
    elif isinstance(data, list):
        return data
    else:
        raise ValueError(f"Invalid YAML format in {path}: expected list or dict with 'questions' key")


def load_json_questions(file_path: str | Path) -> list[dict]:
    """从 JSON 文件加载题目（兼容 cissp-learning 格式）"""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"JSON file not found: {path}")

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        return data
    elif isinstance(data, dict) and "questions" in data:
        return data["questions"]
    else:
        raise ValueError(f"Invalid JSON format in {path}")


def import_questions(
    session: Session,
    questions_data: list[dict],
    source: str = "imported",
    skip_existing: bool = True,
) -> dict:
    """
    将题目数据导入数据库

    参数：
      session: 数据库 session
      questions_data: 题目 dict 列表
      source: 默认来源标识
      skip_existing: 如果 external_id 已存在是否跳过

    返回：统计 dict
    """
    added = 0
    updated = 0
    skipped = 0
    errors = []

    for idx, qdata in enumerate(questions_data):
        try:
            q = _dict_to_question(qdata, default_source=source)
        except Exception as e:
            errors.append(f"第 {idx+1} 题: {e}")
            continue

        # 检查是否已存在
        existing = None
        if q.external_id:
            existing = (
                session.query(Question)
                .filter(Question.external_id == q.external_id)
                .first()
            )

        if existing:
            if skip_existing:
                skipped += 1
                continue
            # 更新
            existing.domain = q.domain
            existing.difficulty = q.difficulty
            existing.question_type = q.question_type
            existing.stem = q.stem
            existing.options = q.options
            existing.correct_answer = q.correct_answer
            existing.explanation = q.explanation
            existing.tags = q.tags
            existing.source = q.source
            existing.main_topic = q.main_topic
            updated += 1
        else:
            session.add(q)
            added += 1

        # 同步知识点（如果有 tags）
        if q.tags:
            for tag in q.tags:
                _ensure_knowledge_point(session, tag, q.domain)

    session.flush()

    return {
        "added": added,
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
        "total_processed": len(questions_data),
    }


def _dict_to_question(qdata: dict, default_source: str = "imported") -> Question:
    """将 dict 转换为 Question 对象，兼容多种字段命名"""
    # 字段映射（多种命名 → 标准字段）
    field_map = {
        "stem": ["stem", "question", "题干", "题目"],
        "correct_answer": ["correct_answer", "answer", "正确答案", "答案"],
        "explanation": ["explanation", "解析", "explain"],
        "external_id": ["id", "external_id", "externalId", "qid"],
        "question_type": ["question_type", "type", "题型"],
        "difficulty": ["difficulty", "难度", "level"],
        "domain": ["domain", "domain_id", "领域", "域"],
        "options": ["options", "choices", "选项"],
        "tags": ["tags", "knowledge_points", "知识点", "标签"],
        "source": ["source", "来源"],
        "main_topic": ["main_topic", "topic", "主项"],
    }

    def find_field(target: str) -> Any:
        for alias in field_map[target]:
            if alias in qdata and qdata[alias] is not None:
                return qdata[alias]
        return None

    stem = find_field("stem")
    if not stem:
        raise ValueError("缺少题干 (stem/question)")

    options = find_field("options") or {}
    correct_answer = find_field("correct_answer")
    if not correct_answer:
        raise ValueError("缺少正确答案")

    domain = find_field("domain")
    if domain is None:
        raise ValueError("缺少领域 (domain)")
    domain = int(domain)
    if domain < 1 or domain > 8:
        raise ValueError(f"领域 {domain} 无效（应为 1-8）")

    difficulty = find_field("difficulty") or 3
    difficulty = int(difficulty)
    if difficulty < 1 or difficulty > 5:
        raise ValueError(f"难度 {difficulty} 无效（应为 1-5）")

    qtype = (find_field("question_type") or "single").lower()
    if qtype not in ("single", "multiple", "truefalse"):
        raise ValueError(f"题型 {qtype} 无效")

    tags = find_field("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]

    external_id = find_field("external_id")
    if isinstance(external_id, int):
        external_id = str(external_id)

    return Question(
        external_id=external_id,
        domain=domain,
        difficulty=difficulty,
        question_type=qtype,
        stem=str(stem),
        options=options,
        correct_answer=str(correct_answer).strip().upper(),
        explanation=str(find_field("explanation") or ""),
        tags=tags,
        source=str(find_field("source") or default_source),
        main_topic=str(find_field("main_topic") or ""),
    )


def _ensure_knowledge_point(session: Session, name: str, domain: int) -> KnowledgePoint:
    """确保知识点存在，不存在则创建"""
    kp = (
        session.query(KnowledgePoint)
        .filter(
            KnowledgePoint.name == name,
            KnowledgePoint.domain == domain,
        )
        .first()
    )
    if kp:
        # 相关题目数 +1
        kp.total_questions += 1
        return kp

    kp = KnowledgePoint(
        name=name,
        domain=domain,
        mastery_level=0.0,
        total_questions=1,
    )
    session.add(kp)
    session.flush()
    return kp


def import_from_file(
    session: Session,
    file_path: str | Path,
    source: str = "imported",
    skip_existing: bool = True,
) -> dict:
    """根据文件扩展名自动选择格式导入"""
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix in (".yaml", ".yml"):
        qs = load_yaml_questions(path)
    elif suffix == ".json":
        qs = load_json_questions(path)
    else:
        raise ValueError(f"不支持的文件格式: {suffix}（支持 .yaml/.yml/.json）")

    return import_questions(session, qs, source=source, skip_existing=skip_existing)


# ── 知识图谱导入 ──────────────────────────────────────────

def import_knowledge_graph_from_file(
    session: Session,
    file_path: str | Path,
) -> dict:
    """
    从 YAML 文件导入知识图谱（知识点之间的关系边）

    格式：
    - domain: 1
      edges:
        - source: "安全基础"
          target: "CIA三元组"
          type: prerequisite
          weight: 1.0
    """
    import yaml as _yaml
    from .knowledge_graph import add_edge

    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"知识图谱文件不存在: {path}")

    with open(path, encoding="utf-8") as f:
        data = _yaml.safe_load(f)

    if not isinstance(data, list):
        raise ValueError("知识图谱文件格式错误：顶层应为列表")

    added = 0
    errors = []

    for entry in data:
        domain = entry.get("domain")
        if not domain or not isinstance(domain, int):
            errors.append(f"无效领域: {entry}")
            continue
        edges = entry.get("edges", [])
        for edge_data in edges:
            try:
                src = edge_data["source"]
                tgt = edge_data["target"]
                etype = edge_data.get("type", "prerequisite")
                weight = float(edge_data.get("weight", 1.0))
                desc = edge_data.get("description", "")
                add_edge(session, src, tgt, domain, etype, weight, desc)
                added += 1
            except Exception as e:
                errors.append(f"领域{domain} 边 {edge_data}: {e}")

    session.flush()
    return {"added": added, "errors": errors, "total_entries": len(data)}

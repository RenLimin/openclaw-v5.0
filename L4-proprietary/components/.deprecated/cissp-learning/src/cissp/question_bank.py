"""
题库管理器

功能：
  - 从 JSON/Excel 导入题目
  - 按域/主项分类
  - 生成模拟卷（随机抽取，按权重分配题数）
  - 错题记录（JSON 存储）
  - 答题练习（CLI 交互）
"""

import json
import random
import os
from datetime import date
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
QUESTIONS_PATH = DATA_DIR / "questions.json"
MISTAKES_PATH = DATA_DIR / "mistakes.json"
PROGRESS_PATH = DATA_DIR / "progress.json"


def load_questions():
    """加载所有题目"""
    with open(QUESTIONS_PATH, encoding="utf-8") as f:
        return json.load(f)


def load_mistakes():
    """加载错题本"""
    if not MISTAKES_PATH.exists():
        return {"mistakes": [], "stats": {"total_mistakes": 0, "by_domain": {}, "by_main_topic": {}}}
    with open(MISTAKES_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_mistakes(data):
    """保存错题本"""
    with open(MISTAKES_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_questions_by_domain(domain_id):
    """按域筛选题目"""
    questions = load_questions()
    return [q for q in questions if q.get("domain") == domain_id]


def get_questions_by_main_topic(main_topic_id):
    """按主项筛选题目"""
    questions = load_questions()
    return [q for q in questions if q.get("main_topic") == main_topic_id]


def generate_quiz(count=10, domain=None, main_topic=None, weight_by_domain=True):
    """
    生成模拟卷/练习题

    参数：
      count: 题目数量
      domain: 指定域 ID（可选）
      main_topic: 指定主项 ID（可选）
      weight_by_domain: 是否按域权重分配题数（默认 True）

    返回：题目列表
    """
    questions = load_questions()

    # 筛选
    if main_topic:
        pool = [q for q in questions if q.get("main_topic") == main_topic]
    elif domain:
        pool = [q for q in questions if q.get("domain") == domain]
    else:
        pool = questions

    if not pool:
        return []

    if not weight_by_domain or domain or main_topic:
        # 简单随机抽取
        count = min(count, len(pool))
        return random.sample(pool, count)

    # 按域权重分配题数
    from .planner import load_domains
    domains = load_domains()
    domain_pool = {}
    for q in pool:
        d = q.get("domain")
        if d is not None:
            domain_pool.setdefault(d, []).append(q)

    total_weight = sum(d["weight"] for d in domains if d["id"] in domain_pool)
    result = []
    remaining = count

    for d in sorted(domains, key=lambda x: x["weight"], reverse=True):
        if d["id"] not in domain_pool:
            continue
        d_count = max(1, round(count * d["weight"] / total_weight))
        d_count = min(d_count, remaining, len(domain_pool[d["id"]]))
        result.extend(random.sample(domain_pool[d["id"]], d_count))
        remaining -= d_count
        if remaining <= 0:
            break

    # 不够的话从剩余题库补
    if remaining > 0:
        used_ids = {q["id"] for q in result}
        leftover = [q for q in pool if q["id"] not in used_ids]
        if leftover:
            add_count = min(remaining, len(leftover))
            result.extend(random.sample(leftover, add_count))

    random.shuffle(result)
    return result


def record_mistake(question_id, user_answer, notes=""):
    """记录错题"""
    mistakes = load_mistakes()
    questions = load_questions()
    q = next((x for x in questions if x["id"] == question_id), None)
    if not q:
        return False

    # 查找是否已有该错题
    existing = None
    for m in mistakes["mistakes"]:
        if m["question_id"] == question_id:
            existing = m
            break

    if existing:
        existing["wrong_count"] += 1
        existing["last_wrong_at"] = date.today().isoformat()
        existing["user_answer"] = user_answer
        if notes:
            existing["notes"] = notes
    else:
        mistakes["mistakes"].append({
            "question_id": question_id,
            "question": q["question"],
            "correct_answer": q["answer"],
            "wrong_count": 1,
            "last_wrong_at": date.today().isoformat(),
            "user_answer": user_answer,
            "notes": notes,
            "domain": q.get("domain"),
            "main_topic": q.get("main_topic")
        })

    # 更新统计
    mistakes["stats"]["total_mistakes"] = len(mistakes["mistakes"])
    by_domain = mistakes["stats"].setdefault("by_domain", {})
    d = str(q.get("domain", "unknown"))
    by_domain[d] = by_domain.get(d, 0) + 1

    save_mistakes(mistakes)
    return True


def get_mistakes_by_domain(domain_id=None):
    """获取错题列表"""
    mistakes = load_mistakes()
    if domain_id is None:
        return mistakes["mistakes"]
    return [m for m in mistakes["mistakes"] if m.get("domain") == domain_id]


def import_questions(source_data, source_name="custom"):
    """
    导入题目（追加到题库）

    source_data 格式：[ {question, options, answer, explanation, domain?, main_topic?} ]
    """
    questions = load_questions()
    existing_ids = {q["id"] for q in questions}

    added = 0
    for i, item in enumerate(source_data):
        new_id = f"{source_name}-{len(questions) + i + 1}"
        if new_id in existing_ids:
            continue
        q = {
            "id": new_id,
            "question": item.get("question", ""),
            "options": item.get("options", {}),
            "answer": item.get("answer", ""),
            "explanation": item.get("explanation", ""),
            "source": source_name,
            "domain": item.get("domain"),
            "main_topic": item.get("main_topic")
        }
        questions.append(q)
        added += 1

    with open(QUESTIONS_PATH, "w", encoding="utf-8") as f:
        json.dump(questions, f, ensure_ascii=False, indent=2)

    return added


def get_stats():
    """获取题库统计"""
    questions = load_questions()
    stats = {
        "total": len(questions),
        "by_domain": {},
        "by_source": {}
    }
    for q in questions:
        d = str(q.get("domain", "unknown"))
        stats["by_domain"][d] = stats["by_domain"].get(d, 0) + 1
        s = q.get("source", "unknown")
        stats["by_source"][s] = stats["by_source"].get(s, 0) + 1
    return stats


if __name__ == "__main__":
    stats = get_stats()
    print(f"题库总题数: {stats['total']}")
    print("按域分布:")
    for d in sorted(stats["by_domain"].keys(), key=lambda x: int(x) if x.isdigit() else 99):
        print(f"  域{d}: {stats['by_domain'][d]} 题")
    print("\n按来源:")
    for s, c in stats["by_source"].items():
        print(f"  {s}: {c} 题")

"""
速记卡生成器 — Flash Card Q&A 格式

输入：知识点列表（来自 domains 或自定义）
输出：Q&A 格式速记卡，支持按域/主项筛选

格式：
  Q: <问题>
  A: <答案>
  ---
  Q: <问题>
  ...

使用场景：
  - Anki 导入
  - 自测背诵
  - 通勤/碎片时间复习
"""

import json
import random
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def load_domains():
    with open(DATA_DIR / "domains.json", encoding="utf-8") as f:
        return json.load(f)["domains"]


def load_questions():
    with open(DATA_DIR / "questions.json", encoding="utf-8") as f:
        return json.load(f)


# 内置速记卡模板：基于 CISSP 核心知识点生成 Q&A
# 这里从 domains 的子项自动生成，也可从题库抽取
def generate_from_domains(domain_id=None, main_topic_id=None):
    """从 8 域考点结构生成速记卡"""
    domains = load_domains()
    cards = []

    for d in domains:
        if domain_id and d["id"] != domain_id:
            continue
        for m in d["main_topics"]:
            if main_topic_id and m["id"] != main_topic_id:
                continue
            # 每个子项生成一张卡
            for sub in m["sub_topics"]:
                cards.append({
                    "id": f"fc-{m['id']}-{hash(sub) % 10000:04d}",
                    "domain_id": d["id"],
                    "domain_name": d["name"],
                    "main_topic": m["name"],
                    "question": f"在 {d['name']} 中，{sub} 的核心要点是什么？",
                    "answer": f"考点：{sub}\n所属主项：{m['name']}\n所属域：{d['name']}\n\n（请结合 OSG 官方教材复习完整内容）",
                    "type": "concept"
                })
            # 主项级卡片
            cards.append({
                "id": f"fc-main-{m['id']}",
                "domain_id": d["id"],
                "domain_name": d["name"],
                "main_topic": m["name"],
                "question": f"{m['name']} 包含哪些关键子项？",
                "answer": "\n".join(f"  - {s}" for s in m["sub_topics"]) if m["sub_topics"] else "（暂无子项数据）",
                "type": "outline"
            })

    return cards


def generate_from_questions(domain_id=None, count=20):
    """从题库抽取题目作为速记卡（问题=正面，答案+解析=反面）"""
    questions = load_questions()

    if domain_id:
        questions = [q for q in questions if q.get("domain") == domain_id]

    count = min(count, len(questions))
    selected = random.sample(questions, count) if questions else []

    cards = []
    for q in selected:
        options_text = "\n".join(f"  {k}. {v}" for k, v in q["options"].items())
        cards.append({
            "id": f"fc-q-{q['id']}",
            "domain_id": q.get("domain"),
            "domain_name": "",
            "main_topic": q.get("main_topic", ""),
            "question": q["question"],
            "answer": f"正确答案：{q['answer']}\n\n选项：\n{options_text}\n\n解析：\n{q.get('explanation', '无')}",
            "type": "question"
        })

    return cards


def generate_flashcards(domain_id=None, count=30, mix=True):
    """
    生成速记卡（混合概念卡 + 题目卡）

    参数：
      domain_id: 指定域（None = 全部）
      count: 卡片数量
      mix: 是否混合概念卡和题目卡
    """
    if mix:
        concept_count = count // 2
        question_count = count - concept_count
        concept_cards = generate_from_domains(domain_id=domain_id)
        question_cards = generate_from_questions(domain_id=domain_id, count=question_count)
        # 随机抽取概念卡
        if len(concept_cards) > concept_count:
            concept_cards = random.sample(concept_cards, concept_count)
        cards = concept_cards + question_cards
    else:
        cards = generate_from_domains(domain_id=domain_id)
        if len(cards) > count:
            cards = random.sample(cards, count)

    random.shuffle(cards)
    return cards[:count]


def format_flashcards(cards, format="text"):
    """
    格式化速记卡输出

    format: "text"（默认，适合打印）| "anki"（TSV 格式，Anki 导入）| "json"
    """
    if format == "json":
        return json.dumps(cards, ensure_ascii=False, indent=2)

    if format == "anki":
        # Anki 导入格式：正面\t反面\t标签
        lines = ["正面\t反面\t标签"]
        for c in cards:
            tags = f"CISSP domain-{c.get('domain_id', '?')} {c.get('type', '')}"
            # 转义 tab 和换行
            q = c["question"].replace("\t", " ").replace("\n", "<br>")
            a = c["answer"].replace("\t", " ").replace("\n", "<br>")
            lines.append(f"{q}\t{a}\t{tags}")
        return "\n".join(lines)

    # text 格式：Q: ... / A: ... / ---
    lines = []
    for i, c in enumerate(cards, 1):
        domain_info = f"[域{c.get('domain_id', '?')} · {c.get('main_topic', '?')}]"
        lines.append(f"--- Card {i} {domain_info} ---")
        lines.append(f"Q: {c['question']}")
        lines.append("")
        lines.append(f"A: {c['answer']}")
        lines.append("")
        lines.append("")
    return "\n".join(lines)


def interactive_flashcards(cards):
    """交互式速记卡练习（CLI）"""
    import sys
    correct = 0
    wrong = 0

    print(f"\n📇 速记卡练习（共 {len(cards)} 张）")
    print("   回车显示答案 → y=记住了 n=没记住 q=退出\n")

    for i, c in enumerate(cards, 1):
        print(f"--- [{i}/{len(cards)}] ---")
        print(f"Q: {c['question']}")
        try:
            resp = input("\n[回车看答案 / q 退出] ").strip().lower()
        except EOFError:
            break
        if resp == "q":
            break

        print(f"\nA: {c['answer']}\n")
        try:
            resp2 = input("记住了吗？(y/n) ").strip().lower()
        except EOFError:
            break
        if resp2 == "y":
            correct += 1
        elif resp2 == "n":
            wrong += 1

    total = correct + wrong
    print(f"\n📊 练习完成：{correct} 记住 / {wrong} 没记住 / 共 {total} 张")
    if total > 0:
        print(f"    正确率: {correct/total*100:.1f}%")


if __name__ == "__main__":
    cards = generate_flashcards(domain_id=1, count=5)
    print(format_flashcards(cards))

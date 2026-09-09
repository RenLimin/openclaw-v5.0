"""
pytest 配置与 fixture
"""

import sys
import pytest
from pathlib import Path

# 将 src 加入路径
SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from cissp_trainer.database import init_db, get_engine
from cissp_trainer.models import Base, Question, KnowledgePoint
from cissp_trainer.importer import import_questions


@pytest.fixture
def db_session(tmp_path):
    """创建临时测试数据库，返回 session"""
    from sqlalchemy.orm import sessionmaker

    db_path = tmp_path / "test.db"
    engine = init_db(db_path=db_path, drop_first=True)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)
    session = SessionLocal()

    yield session

    session.close()
    engine.dispose()


@pytest.fixture
def seed_questions(db_session):
    """导入一批测试题"""
    sample_qs = [
        # 域1 - 5题
        {
            "id": "test-d1-001", "domain": 1, "difficulty": 2, "question_type": "single",
            "stem": "CIA 三元组是什么？",
            "options": {"A": "机密性完整性可用性", "B": "保密性真实性", "C": "可靠性", "D": "可审计性"},
            "correct_answer": "A", "explanation": "CIA = Confidentiality, Integrity, Availability",
            "tags": ["CIA三元组", "安全基础"], "source": "test"
        },
        {
            "id": "test-d1-002", "domain": 1, "difficulty": 3, "question_type": "single",
            "stem": "外包属于哪种风险处置？",
            "options": {"A": "规避", "B": "转移", "C": "缓解", "D": "接受"},
            "correct_answer": "B", "explanation": "外包将风险转移给第三方",
            "tags": ["风险管理", "风险处置"], "source": "test"
        },
        {
            "id": "test-d1-003", "domain": 1, "difficulty": 4, "question_type": "single",
            "stem": "风险胃口指的是？",
            "options": {"A": "风险总量", "B": "容忍度", "C": "残余风险", "D": "风险评估"},
            "correct_answer": "A", "explanation": "风险胃口是组织愿意承受的风险总量",
            "tags": ["风险管理", "风险胃口"], "source": "test"
        },
        {
            "id": "test-d1-004", "domain": 1, "difficulty": 1, "question_type": "truefalse",
            "stem": "安全策略由 IT 部门批准。",
            "options": {"A": "正确", "B": "错误"},
            "correct_answer": "B", "explanation": "安全策略由高层管理批准",
            "tags": ["安全策略", "治理"], "source": "test"
        },
        {
            "id": "test-d1-005", "domain": 1, "difficulty": 3, "question_type": "multiple",
            "stem": "以下哪些是职业道德规范内容？",
            "options": {"A": "保护社会", "B": "行事端正", "C": "最低成本", "D": "个人发展"},
            "correct_answer": "A,B", "explanation": "ISC2 职业道德前两条",
            "tags": ["职业道德"], "source": "test"
        },
        # 域2 - 3题
        {
            "id": "test-d2-001", "domain": 2, "difficulty": 2, "question_type": "single",
            "stem": "数据分类的目的？",
            "options": {"A": "合规", "B": "确定价值分配保护", "C": "省钱", "D": "检索"},
            "correct_answer": "B", "explanation": "按价值分级保护",
            "tags": ["数据分类", "资产管理"], "source": "test"
        },
        {
            "id": "test-d2-002", "domain": 2, "difficulty": 4, "question_type": "single",
            "stem": "SSD 最有效的销毁方式？",
            "options": {"A": "格式化", "B": "覆写", "C": "物理粉碎", "D": "删分区"},
            "correct_answer": "C", "explanation": "SSD 磨损均衡导致覆写不可靠",
            "tags": ["数据销毁", "SSD"], "source": "test"
        },
        {
            "id": "test-d2-003", "domain": 2, "difficulty": 2, "question_type": "single",
            "stem": "谁对数据保护负最终责任？",
            "options": {"A": "管理员", "B": "所有者", "C": "安全员", "D": "IT经理"},
            "correct_answer": "B", "explanation": "数据所有者负最终责任",
            "tags": ["数据角色", "数据所有者"], "source": "test"
        },
        # 域3 - 3题
        {
            "id": "test-d3-001", "domain": 3, "difficulty": 3, "question_type": "single",
            "stem": "Bell-LaPadula 保护什么？",
            "options": {"A": "完整性", "B": "可用性", "C": "机密性", "D": "不可否认"},
            "correct_answer": "C", "explanation": "Bell-LaPadula 是机密性模型",
            "tags": ["安全模型", "Bell-LaPadula", "机密性"], "source": "test"
        },
        {
            "id": "test-d3-002", "domain": 3, "difficulty": 3, "question_type": "single",
            "stem": "Biba 模型保护什么？",
            "options": {"A": "机密性", "B": "完整性", "C": "可用性", "D": "审计"},
            "correct_answer": "B", "explanation": "Biba 是完整性模型",
            "tags": ["安全模型", "Biba", "完整性"], "source": "test"
        },
        {
            "id": "test-d3-003", "domain": 3, "difficulty": 2, "question_type": "single",
            "stem": "以下哪个是非对称加密？",
            "options": {"A": "AES", "B": "DES", "C": "RSA", "D": "Blowfish"},
            "correct_answer": "C", "explanation": "RSA 是非对称",
            "tags": ["加密算法", "非对称加密", "RSA"], "source": "test"
        },
        # 域4 - 2题
        {
            "id": "test-d4-001", "domain": 4, "difficulty": 3, "question_type": "single",
            "stem": "SYN 洪水攻击利用什么？",
            "options": {"A": "ICMP", "B": "TCP三次握手", "C": "UDP", "D": "DNS"},
            "correct_answer": "B", "explanation": "利用 TCP 三次握手漏洞",
            "tags": ["网络攻击", "SYN洪水", "DoS"], "source": "test"
        },
        {
            "id": "test-d4-002", "domain": 4, "difficulty": 3, "question_type": "single",
            "stem": "IPSec 在哪一层工作？",
            "options": {"A": "应用层", "B": "传输层", "C": "网络层", "D": "链路层"},
            "correct_answer": "C", "explanation": "IPSec 在网络层",
            "tags": ["IPSec", "VPN"], "source": "test"
        },
        # 域5 - 2题
        {
            "id": "test-d5-001", "domain": 5, "difficulty": 2, "question_type": "single",
            "stem": "RBAC 适合什么场景？",
            "options": {"A": "研究环境", "B": "职责明确的大型组织", "C": "军事", "D": "临时团队"},
            "correct_answer": "B", "explanation": "RBAC 基于角色，适合大型组织",
            "tags": ["RBAC", "访问控制"], "source": "test"
        },
        {
            "id": "test-d5-002", "domain": 5, "difficulty": 3, "question_type": "single",
            "stem": "职责分离的目的？",
            "options": {"A": "提高效率", "B": "防止单人舞弊", "C": "减少培训", "D": "简化权限"},
            "correct_answer": "B", "explanation": "防止单人独立完成欺诈操作",
            "tags": ["职责分离", "安全原则"], "source": "test"
        },
        # 域6 - 2题
        {
            "id": "test-d6-001", "domain": 6, "difficulty": 3, "question_type": "single",
            "stem": "漏洞评估与渗透测试的区别？",
            "options": {"A": "工具vs手动", "B": "识别vs验证利用", "C": "内部vs外包", "D": "没区别"},
            "correct_answer": "B", "explanation": "漏洞评估只识别，渗透测试验证可利用性",
            "tags": ["漏洞评估", "渗透测试"], "source": "test"
        },
        {
            "id": "test-d6-002", "domain": 6, "difficulty": 4, "question_type": "single",
            "stem": "MTTD 衡量什么？",
            "options": {"A": "响应时间", "B": "检测能力", "C": "故障间隔", "D": "恢复点"},
            "correct_answer": "B", "explanation": "MTTD = Mean Time To Detect",
            "tags": ["安全指标", "MTTD"], "source": "test"
        },
        # 域7 - 2题
        {
            "id": "test-d7-001", "domain": 7, "difficulty": 2, "question_type": "single",
            "stem": "SIEM 的主要功能？",
            "options": {"A": "防入侵", "B": "集中收集关联分析日志", "C": "加密流量", "D": "身份管理"},
            "correct_answer": "B", "explanation": "SIEM 是安全信息与事件管理",
            "tags": ["SIEM", "安全运营"], "source": "test"
        },
        {
            "id": "test-d7-002", "domain": 7, "difficulty": 4, "question_type": "single",
            "stem": "RTO 和 RPO 分别是？",
            "options": {"A": "数据丢失量/停机时间", "B": "停机时间/数据丢失量", "C": "成本/人力", "D": "优先级/难度"},
            "correct_answer": "B", "explanation": "RTO = 恢复时间目标, RPO = 恢复点目标",
            "tags": ["RTO", "RPO", "灾难恢复"], "source": "test"
        },
        # 域8 - 2题
        {
            "id": "test-d8-001", "domain": 8, "difficulty": 3, "question_type": "single",
            "stem": "SQL 注入最有效的防御？",
            "options": {"A": "过滤单引号", "B": "存储过程", "C": "参数化查询", "D": "限权限"},
            "correct_answer": "C", "explanation": "参数化查询将结构与数据分离",
            "tags": ["SQL注入", "安全编码"], "source": "test"
        },
        {
            "id": "test-d8-002", "domain": 8, "difficulty": 2, "question_type": "single",
            "stem": "威胁建模应该在哪个阶段？",
            "options": {"A": "编码", "B": "测试", "C": "设计", "D": "部署"},
            "correct_answer": "C", "explanation": "设计阶段尽早进行威胁建模",
            "tags": ["威胁建模", "S-SDLC"], "source": "test"
        },
    ]

    result = import_questions(db_session, sample_qs, source="test")
    db_session.commit()
    assert result["added"] == len(sample_qs)
    return result["added"]

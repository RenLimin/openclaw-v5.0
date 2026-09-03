#!/usr/bin/env python3
"""
合同审核标准库
组件: SCA-001 (L4)
功能: 基于《民法典》等现行法律法规，形成统一的审核标准
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AuditCriterion:
    """审核标准项"""
    id: str                     # 编号（如 "1.1"）
    category: str               # 条款类别
    item: str                   # 检查项名称
    law_article: str            # 法条依据
    risk_level: str             # 风险等级：high / medium / low
    standard: str               # 审核标准描述
    pass_condition: str          # 通过条件
    fail_condition: str          # 不通过条件
    suggestion_template: str     # 修改建议模板
    reference_law: str = ""      # 参考法条全文


# ============================================================
# 审核标准库（基于《民法典》合同编 + 司法解释 + 行业规范）
# ============================================================

AUDIT_CRITERIA = [
    # ==================== 一、主体信息 ====================
    AuditCriterion(
        id="1.1", category="主体信息",
        item="双方当事人名称完整且与营业执照一致",
        law_article="§470",
        risk_level="high",
        standard="合同双方当事人的名称应当完整、准确，与营业执照/法人登记证书一致",
        pass_condition="双方名称完整，含'有限公司'等组织形式后缀",
        fail_condition="名称缺失、简称、或与营业执照不一致",
        suggestion_template="建议将'{current}'修正为营业执照上的完整名称",
        reference_law="《民法典》第470条：合同的内容由当事人约定，一般包括下列条款：（一）当事人的名称或者姓名和住所...",
    ),
    AuditCriterion(
        id="1.2", category="主体信息",
        item="双方地址完整（省市区街道门牌）",
        law_article="§470",
        risk_level="medium",
        standard="合同应载明双方当事人的法定地址，用于法律文书送达",
        pass_condition="地址含省、市、区/县、街道/路、门牌号",
        fail_condition="地址缺失或仅到市级",
        suggestion_template="建议补充详细地址：省+市+区/县+街道/路+门牌号",
        reference_law="《民法典》第470条",
    ),
    AuditCriterion(
        id="1.3", category="主体信息",
        item="双方联系电话/邮箱明确",
        law_article="—",
        risk_level="low",
        standard="合同应载明双方的联系电话或邮箱，用于日常沟通和通知送达",
        pass_condition="至少各有一个电话或邮箱",
        fail_condition="联系方式全部缺失",
        suggestion_template="建议补充联系电话和邮箱",
    ),
    AuditCriterion(
        id="1.4", category="主体信息",
        item="统一社会信用代码",
        law_article="—",
        risk_level="low",
        standard="合同应载明对方的统一社会信用代码，用于核实主体身份",
        pass_condition="载明18位统一社会信用代码",
        fail_condition="未载明",
        suggestion_template="建议补充对方的统一社会信用代码",
    ),
    AuditCriterion(
        id="1.5", category="主体信息",
        item="签约人持有有效授权",
        law_article="§490",
        risk_level="high",
        standard="签约人应为法定代表人或持有有效授权委托书的委托代理人",
        pass_condition="载明法定代表人或授权签署人姓名",
        fail_condition="签约人身份不明或授权缺失",
        suggestion_template="建议补充授权委托书，明确授权范围和期限",
        reference_law="《民法典》第490条：当事人采用合同书形式订立合同的，自当事人均签名、盖章或者按指印时合同成立。",
    ),

    # ==================== 二、合同标的 ====================
    AuditCriterion(
        id="2.1", category="合同标的",
        item="服务内容描述清晰、可衡量",
        law_article="§470",
        risk_level="high",
        standard="合同标的（服务内容）应明确、具体、可衡量，避免模糊表述",
        pass_condition="服务内容有具体描述，可判断交付标准",
        fail_condition="服务内容模糊（如'提供技术支持'而无具体内容）",
        suggestion_template="建议将服务内容细化为：1）...；2）...；3）...，并明确每项的具体标准",
        reference_law="《民法典》第470条",
    ),
    AuditCriterion(
        id="2.2", category="合同标的",
        item="服务方式明确",
        law_article="—",
        risk_level="medium",
        standard="服务方式（远程/上门/混合）应明确约定",
        pass_condition="载明具体服务方式",
        fail_condition="服务方式未约定",
        suggestion_template="建议明确服务方式：远程/上门/混合，以及具体流程",
    ),
    AuditCriterion(
        id="2.3", category="合同标的",
        item="交付物清单完整",
        law_article="§470",
        risk_level="high",
        standard="合同应列明所有交付物，包括文档、软件、报告等",
        pass_condition="有明确的交付物清单",
        fail_condition="未列明交付物或交付物不明确",
        suggestion_template="建议补充交付物清单：1）...；2）...；3）...",
    ),
    AuditCriterion(
        id="2.4", category="合同标的",
        item="服务期限/起止日期明确",
        law_article="§511",
        risk_level="medium",
        standard="合同应载明服务期限或起止日期",
        pass_condition="有明确的起止日期",
        fail_condition="期限缺失或表述矛盾",
        suggestion_template="建议明确服务期限：自YYYY年MM月DD日至YYYY年MM月DD日",
        reference_law="《民法典》第511条：当事人就有关合同内容约定不明确，依据前条规定仍不能确定的，适用下列规定：（四）履行期限不明确的，债务人可以随时履行，债权人也可以随时请求履行，但是应当给对方必要的准备时间。",
    ),

    # ==================== 三、价款与报酬 ====================
    AuditCriterion(
        id="3.1", category="价款与报酬",
        item="合同金额大小写一致",
        law_article="—",
        risk_level="high",
        standard="合同金额应同时载明大小写，且两者一致",
        pass_condition="大小写金额同时载明且一致",
        fail_condition="仅有小写无大写，或大小写不一致",
        suggestion_template="建议补充大写金额：{amount_cn}",
    ),
    AuditCriterion(
        id="3.2", category="价款与报酬",
        item="税率明确",
        law_article="—",
        risk_level="high",
        standard="合同应载明适用税率（增值税6%/13%等）",
        pass_condition="税率明确载明",
        fail_condition="税率缺失或表述模糊",
        suggestion_template="建议明确税率：增值税X%",
    ),
    AuditCriterion(
        id="3.3", category="价款与报酬",
        item="价款含税/不含税明确",
        law_article="—",
        risk_level="medium",
        standard="合同应明确价款是否含税",
        pass_condition="载明'含税'或'不含税'",
        fail_condition="未说明是否含税",
        suggestion_template="建议明确：本合同价款为含税/不含税价格",
    ),

    # ==================== 四、付款条件 ====================
    AuditCriterion(
        id="4.1", category="付款条件",
        item="付款时间/节点明确",
        law_article="§510",
        risk_level="high",
        standard="付款时间应明确约定，与项目里程碑或交付节点挂钩",
        pass_condition="有明确的付款时间和条件",
        fail_condition="付款时间缺失或表述模糊",
        suggestion_template="建议明确付款节点：合同签订后X日/验收合格后X日/...",
        reference_law="《民法典》第510条",
    ),
    AuditCriterion(
        id="4.2", category="付款条件",
        item="支付方式明确",
        law_article="§510",
        risk_level="medium",
        standard="支付方式（银行转账/支票/承兑汇票等）应明确",
        pass_condition="载明具体支付方式",
        fail_condition="支付方式未约定",
        suggestion_template="建议明确支付方式：银行转账",
    ),
    AuditCriterion(
        id="4.3", category="付款条件",
        item="发票要求明确（类型/税率/时间）",
        law_article="—",
        risk_level="medium",
        standard="合同应载明发票类型（增值税专用/普通）、税率、开具时间",
        pass_condition="发票类型、税率、开具时间均已载明",
        fail_condition="发票要求缺失",
        suggestion_template="建议明确：乙方须出具增值税专用发票（税率X%），于收到款项后X日内开具",
    ),

    # ==================== 五、验收标准 ====================
    AuditCriterion(
        id="5.1", category="验收标准",
        item="验收标准可量化",
        law_article="§509",
        risk_level="high",
        standard="验收标准应具体、可量化，避免主观判断",
        pass_condition="有明确的、可量化的验收标准",
        fail_condition="验收标准模糊（如'满意'、'合格'而无具体指标）",
        suggestion_template="建议将验收标准量化：1）功能指标：...；2）性能指标：...；3）文档指标：...",
        reference_law="《民法典》第509条",
    ),
    AuditCriterion(
        id="5.2", category="验收标准",
        item="验收流程明确（谁验收/怎么验收）",
        law_article="—",
        risk_level="high",
        standard="应明确验收人、验收方式、验收期限",
        pass_condition="验收人、方式、期限均已载明",
        fail_condition="验收流程缺失",
        suggestion_template="建议明确验收流程：由甲方/双方在X日内按照X标准进行验收",
    ),
    AuditCriterion(
        id="5.3", category="验收标准",
        item="不合格处理方式（返工/扣款/拒收）",
        law_article="—",
        risk_level="high",
        standard="应约定验收不合格时的处理方式：返工、扣款、拒收等",
        pass_condition="载明不合格的处理方式",
        fail_condition="未约定不合格处理方式",
        suggestion_template="建议补充：验收不合格的，乙方应在X日内免费返工/整改，直至验收合格",
    ),

    # ==================== 六、违约责任 ====================
    AuditCriterion(
        id="6.1", category="违约责任",
        item="双方违约责任对等",
        law_article="§577",
        risk_level="high",
        standard="双方违约责任应基本对等，不应存在明显不对等的情形",
        pass_condition="双方违约责任结构对等、比例相当",
        fail_condition="一方违约责任明显重于另一方",
        suggestion_template="建议对等化修改：将甲方的违约金比例调整为与乙方一致（X%）",
        reference_law="《民法典》第577条：当事人一方不履行合同义务或者履行合同义务不符合约定的，应当承担继续履行、采取补救措施或者赔偿损失等违约责任。",
    ),
    AuditCriterion(
        id="6.2", category="违约责任",
        item="违约金比例合理（不超过实际损失30%）",
        law_article="§585",
        risk_level="high",
        standard="违约金不应超过实际损失的30%。日违约金一般不超过0.3%（年化109.5%）",
        pass_condition="违约金比例合理，日违约金≤0.3%或总额≤10%",
        fail_condition="日违约金>0.5%（年化>182.5%）或总额>30%",
        suggestion_template="建议将日违约金从{X}%降至0.3%以下，或约定违约金上限为合同总额的10%",
        reference_law="《民法典》第585条：约定的违约金低于造成的损失的，人民法院或者仲裁机构可以根据当事人的请求予以增加；约定的违约金过分高于造成的损失的，人民法院或者仲裁机构可以根据当事人的请求予以适当减少。《合同法司法解释二》第29条：超过造成损失的30%认定为'过分高于'。",
    ),
    AuditCriterion(
        id="6.3", category="违约责任",
        item="违约金上限明确",
        law_article="—",
        risk_level="medium",
        standard="建议约定违约金上限（如合同总额的5%-10%）",
        pass_condition="载明违约金上限",
        fail_condition="未约定上限",
        suggestion_template="建议补充：违约金累计不超过合同总额的X%",
    ),
    AuditCriterion(
        id="6.4", category="违约责任",
        item="继续履行的可能性",
        law_article="§577",
        risk_level="medium",
        standard="违约条款应保留继续履行的选项",
        pass_condition="载明继续履行的权利",
        fail_condition="未提及继续履行",
        suggestion_template="建议补充：违约方支付违约金后，守约方仍有权要求继续履行合同",
    ),

    # ==================== 七、争议解决 ====================
    AuditCriterion(
        id="7.1", category="争议解决",
        item="管辖法院/仲裁机构明确",
        law_article="§507",
        risk_level="high",
        standard="应明确约定争议解决机构和地点",
        pass_condition="载明具体的管辖法院或仲裁机构",
        fail_condition="争议解决条款缺失",
        suggestion_template="建议明确：依法向甲方所在地人民法院起诉",
        reference_law="《民法典》第507条",
    ),
    AuditCriterion(
        id="7.2", category="争议解决",
        item="争议解决方式唯一（诉讼或仲裁二选一）",
        law_article="—",
        risk_level="medium",
        standard="诉讼和仲裁只能选择一种，同时约定会导致仲裁条款无效",
        pass_condition="仅约定一种方式",
        fail_condition="同时约定诉讼和仲裁",
        suggestion_template="建议选择一种：诉讼（向X人民法院起诉）或仲裁（提交X仲裁委员会仲裁）",
    ),

    # ==================== 八、知识产权 ====================
    AuditCriterion(
        id="8.1", category="知识产权",
        item="服务成果知识产权归属明确",
        law_article="§847",
        risk_level="medium",
        standard="应明确约定服务过程中产生的新技术成果的知识产权归属",
        pass_condition="载明知识产权归属",
        fail_condition="知识产权归属未约定",
        suggestion_template="建议明确：乙方在服务过程中产生的新技术成果/知识产权归甲方/乙方所有",
        reference_law="《民法典》第847条：职务技术成果的使用权、转让权属于法人或者非法人组织的，法人或者非法人组织可以就该项职务技术成果订立技术合同。",
    ),
    AuditCriterion(
        id="8.2", category="知识产权",
        item="背景知识产权归属不变",
        law_article="—",
        risk_level="low",
        standard="双方各自在合同签订前拥有知识产权应保持不变",
        pass_condition="载明背景知识产权归属不变",
        fail_condition="未提及背景知识产权",
        suggestion_template="建议补充：双方在合同签订前拥有的知识产权仍归各自所有",
    ),

    # ==================== 九、保密条款 ====================
    AuditCriterion(
        id="9.1", category="保密条款",
        item="保密信息定义明确",
        law_article="§501",
        risk_level="medium",
        standard="应明确界定保密信息的范围和类型",
        pass_condition="有保密信息的定义和范围",
        fail_condition="保密信息范围模糊",
        suggestion_template="建议明确保密信息的范围：商务信息、财务信息、技术信息、用户资料等",
        reference_law="《民法典》第501条：当事人不得泄露或者不正当地使用在合同订立过程中知悉的商业秘密或者其他应当保密的信息。",
    ),
    AuditCriterion(
        id="9.2", category="保密条款",
        item="保密期限明确",
        law_article="—",
        risk_level="medium",
        standard="应明确保密义务的期限，通常延续至合同终止后一定期限",
        pass_condition="载明保密期限（含合同终止后）",
        fail_condition="保密期限缺失",
        suggestion_template="建议明确：保密义务在合同终止后X年内继续有效",
    ),
    AuditCriterion(
        id="9.3", category="保密条款",
        item="违反保密义务的违约责任",
        law_article="—",
        risk_level="medium",
        standard="应约定违反保密义务的赔偿责任",
        pass_condition="载明违反保密义务的赔偿",
        fail_condition="未约定保密违约责任",
        suggestion_template="建议补充：违反保密义务的一方应赔偿对方因此遭受的一切损失",
    ),

    # ==================== 十、不可抗力 ====================
    AuditCriterion(
        id="10.1", category="不可抗力",
        item="不可抗力定义明确",
        law_article="§180",
        risk_level="low",
        standard="应定义不可抗力的范围和类型",
        pass_condition="有不可抗力的定义",
        fail_condition="仅提及'不可抗力'但无定义",
        suggestion_template="建议补充不可抗力的定义：不能预见、不能避免且不能克服的客观情况（如自然灾害、战争、政府行为等）",
        reference_law="《民法典》第180条：因不可抗力不能履行民事义务的，不承担民事责任。法律另有规定的，依照其规定。不可抗力是不能预见、不能避免且不能克服的客观情况。",
    ),
    AuditCriterion(
        id="10.2", category="不可抗力",
        item="通知义务和期限明确",
        law_article="§590",
        risk_level="low",
        standard="应约定不可抗力发生后的通知义务和期限",
        pass_condition="载明通知期限和方式",
        fail_condition="未约定通知义务",
        suggestion_template="建议补充：不可抗力发生后X日内书面通知对方，并提供相关证明",
        reference_law="《民法典》第590条：当事人一方因不可抗力不能履行合同的，应当及时通知对方，以减轻可能给对方造成的损失，并应当在合理期限内提供证明。",
    ),
    AuditCriterion(
        id="10.3", category="不可抗力",
        item="不可抗力后果处理",
        law_article="—",
        risk_level="low",
        standard="应约定不可抗力的后果：延期履行、部分免责、解除合同等",
        pass_condition="载明不可抗力的后果处理",
        fail_condition="未约定后果处理",
        suggestion_template="建议补充：因不可抗力导致合同无法履行的，双方可协商延期履行或解除合同，互不承担违约责任",
    ),

    # ==================== 十一、合同解除 ====================
    AuditCriterion(
        id="11.1", category="合同解除",
        item="解除条件明确",
        law_article="§563",
        risk_level="medium",
        standard="应明确约定合同解除的条件",
        pass_condition="载明解除条件",
        fail_condition="解除条件缺失",
        suggestion_template="建议明确解除条件：1）不可抗力；2）一方根本违约；3）双方协商一致",
        reference_law="《民法典》第563条：有下列情形之一的，当事人可以解除合同：（一）因不可抗力致使不能实现合同目的；（二）在履行期限届满前，当事人一方明确表示或者以自己的行为表明不履行主要债务...",
    ),
    AuditCriterion(
        id="11.2", category="合同解除",
        item="解除后结算和清理条款",
        law_article="—",
        risk_level="medium",
        standard="应约定合同解除后的结算和清理方式",
        pass_condition="载明解除后的结算方式",
        fail_condition="未约定结算清理",
        suggestion_template="建议补充：合同解除后X日内，双方就已履行部分进行结算",
    ),

    # ==================== 十二、合同变更 ====================
    AuditCriterion(
        id="12.1", category="合同变更",
        item="合同变更需双方书面同意",
        law_article="§543",
        risk_level="medium",
        standard="合同变更应经双方协商一致并以书面形式确认",
        pass_condition="载明变更条件和形式",
        fail_condition="未约定变更程序",
        suggestion_template="建议明确：本合同的任何变更须经双方协商一致并以书面形式确认",
        reference_law="《民法典》第543条：当事人协商一致，可以变更合同。",
    ),

    # ==================== 十三、格式条款 ====================
    AuditCriterion(
        id="13.1", category="格式条款",
        item="无不合理加重对方责任的格式条款",
        law_article="§496",
        risk_level="medium",
        standard="格式条款提供方不得不合理地加重对方责任",
        pass_condition="无加重对方责任的条款",
        fail_condition="存在加重对方责任的格式条款",
        suggestion_template="建议修改该条款，或按照§496条要求以合理方式提示对方注意",
        reference_law="《民法典》第496条：提供格式条款的一方未履行提示或者说明义务，致使对方没有注意或者理解与其有重大利害关系的条款的，对方可以主张该条款不成为合同的内容。",
    ),
    AuditCriterion(
        id="13.2", category="格式条款",
        item="无排除对方主要权利的格式条款",
        law_article="§497",
        risk_level="medium",
        standard="格式条款不得排除对方主要权利",
        pass_condition="无排除对方主要权利的条款",
        fail_condition="存在排除对方主要权利的格式条款",
        suggestion_template="建议删除或修改该条款，否则可能被认定为无效",
        reference_law="《民法典》第497条：提供格式条款一方不合理地免除或者减轻其责任、加重对方责任、限制对方主要权利的，该格式条款无效。",
    ),

    # ==================== 十四、合同生效 ====================
    AuditCriterion(
        id="14.1", category="合同生效",
        item="合同生效条件明确",
        law_article="§490",
        risk_level="medium",
        standard="应明确约定合同生效条件",
        pass_condition="载明生效条件（如签字盖章后生效）",
        fail_condition="生效条件缺失",
        suggestion_template="建议明确：本合同经双方签字盖章后生效",
        reference_law="《民法典》第490条",
    ),
    AuditCriterion(
        id="14.2", category="合同生效",
        item="合同份数约定明确",
        law_article="—",
        risk_level="low",
        standard="应约定合同正本/副本数量及持有人",
        pass_condition="载明合同份数和持有人",
        fail_condition="未约定合同份数",
        suggestion_template="建议明确：本合同一式X份，甲方持X份，乙方持X份",
    ),

    # ==================== 十五、项目联系人 ====================
    AuditCriterion(
        id="15.1", category="项目联系人",
        item="双方项目联系人明确",
        law_article="—",
        risk_level="low",
        standard="应明确双方的项目联系人及其联系方式",
        pass_condition="双方联系人均已载明",
        fail_condition="联系人缺失",
        suggestion_template="建议补充项目联系人的姓名、电话、邮箱",
    ),

    # ==================== 十六、质保条款 ====================
    AuditCriterion(
        id="16.1", category="质保条款",
        item="质量保证期明确",
        law_article="§509",
        risk_level="medium",
        standard="应明确质量保证期的期限",
        pass_condition="载明质保期（如1年）",
        fail_condition="质保期缺失",
        suggestion_template="建议明确：质量保证期为交付验收合格后X个月",
    ),
    AuditCriterion(
        id="16.2", category="质保条款",
        item="质保范围和响应时间",
        law_article="—",
        risk_level="medium",
        standard="应明确质保范围和响应时间",
        pass_condition="载明质保范围和响应时间",
        fail_condition="质保范围或响应时间缺失",
        suggestion_template="建议明确：质保期内，乙方应在收到甲方通知后X小时内响应",
    ),

    # ==================== 十七、授权签署 ====================
    AuditCriterion(
        id="17.1", category="授权签署",
        item="双方授权签署人明确",
        law_article="§490",
        risk_level="high",
        standard="应明确双方的授权签署人",
        pass_condition="双方签署人均已载明",
        fail_condition="签署人缺失",
        suggestion_template="建议补充授权签署人姓名及授权范围",
        reference_law="《民法典》第490条",
    ),
]


def get_criterion_by_id(criterion_id: str) -> Optional[AuditCriterion]:
    """根据 ID 获取审核标准"""
    for c in AUDIT_CRITERIA:
        if c.id == criterion_id:
            return c
    return None


def get_criteria_by_category(category: str) -> list:
    """根据类别获取审核标准"""
    return [c for c in AUDIT_CRITERIA if c.category == category]


def get_all_categories() -> list:
    """获取所有条款类别"""
    return list(dict.fromkeys(c.category for c in AUDIT_CRITERIA))


if __name__ == "__main__":
    print(f"审核标准库：共 {len(AUDIT_CRITERIA)} 项标准")
    print(f"条款类别：{len(get_all_categories())} 个")
    for cat in get_all_categories():
        items = get_criteria_by_category(cat)
        print(f"  {cat}：{len(items)} 项")

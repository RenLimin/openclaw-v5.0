---
title: 服务合同通用框架
description: 通用服务合同模板，适合咨询服务、技术服务、运维服务等
author: L3 Office 通用模板
created: 2026-09-08
updated: 2026-09-08
tags: [合同, 服务, 框架]
variables:
  - name: contract_title
    type: string
    description: 合同完整标题
    required: true
  - name: contract_number
    type: string
    description: 合同编号
    required: true
  - name: party_a_name
    type: string
    description: 甲方（客户）全称
    required: true
  - name: party_a_address
    type: string
    description: 甲方地址
    required: true
  - name: party_a_contact
    type: string
    description: 甲方联系人及电话
    required: true
  - name: party_b_name
    type: string
    description: 乙方（服务商）全称
    required: true
  - name: party_b_address
    type: string
    description: 乙方地址
    required: true
  - name: party_b_contact
    type: string
    description: 乙方联系人及电话
    required: true
  - name: signing_date
    type: date
    description: 签署日期
    required: true
  - name: service_description
    type: markdown
    description: 服务内容描述
    required: true
  - name: total_amount
    type: number
    description: 合同总金额（元）
    required: true
  - name: payment_schedule
    type: table
    description: 支付计划表格（节点/比例/金额/到期日）
    required: true
  - name: service_period
    type: string
    description: 服务周期（开始日期~结束日期）
    required: true
  - name: acceptance_criteria
    type: markdown
    description: 验收标准
    required: true
  - name: other_terms
    type: markdown
    description: 其他特殊条款
    required: false
---

# {{ contract_title }}

**合同编号:** {{ contract_number }}

**签署日期:** {{ signing_date }}

---

## 甲方（客户）

- **名称:** {{ party_a_name }}
- **地址:** {{ party_a_address }}
- **联系人:** {{ party_a_contact }}

## 乙方（服务商）

- **名称:** {{ party_b_name }}
- **地址:** {{ party_b_address }}
- **联系人:** {{ party_b_contact }}

---

## 第一条 鉴于

1.1 甲方需要乙方提供 {{ service_description }} 服务，乙方具备相应资质和能力，双方经协商一致，签订本合同。

## 第二条 服务内容

{{ service_description }}

## 第三条 合同金额

总金额：人民币 **{{ total_amount }} 元**（大写：）

## 第四条 支付方式

| 支付节点 | 比例 | 金额 | 到期日 |
|----------|------|------|--------|
{% for row in payment_schedule %}
| {{ row.node }} | {{ row.ratio }} | {{ row.amount }} | {{ row.due_date }} |
{% endfor %}

## 第五条 服务周期

服务周期：{{ service_period }}

## 第六条 验收标准

{{ acceptance_criteria }}

## 第七条 双方权利与义务

### 7.1 甲方权利义务
1. 按合同约定支付服务费用
2. 提供必要的配合和资料
3. 按时组织验收

### 7.2 乙方权利义务
1. 按合同约定提供符合质量标准的服务
2. 遵守甲方合理的管理制度
3. 对服务过程中获悉的甲方信息保密
4. 提供售后服务和问题响应

## 第八条 违约责任

8.1 任何一方违约，应向对方支付合同总金额 **X%** 的违约金。
8.2 乙方服务质量不符合要求，应在约定时间内整改，整改仍不合格的，甲方有权解除合同并要求退款赔偿。

## 第九条 保密

双方应对本合同内容及在合作中获悉的对方商业秘密保密，未经允许不得向第三方泄露。本条款在合同终止后仍然有效。

## 第十条 不可抗力

因不可抗力导致不能履行合同，受不可抗力影响一方应及时通知对方，并在合理期限内提供证明，根据不可抗力影响，部分或全部免除责任。

## 第十一条 争议解决

因本合同引起的或与本合同有关的任何争议，双方应友好协商解决，协商不成的，提交 **[甲方/乙方/合同签订地]** 人民法院诉讼解决（或：提交 XX 仲裁委员会仲裁）。

## 第十二条 其他条款

12.1 本合同自双方签字盖章之日起生效。
12.2 本合同一式 **X** 份，甲方执 **X** 份，乙方执 **X** 份，具有同等法律效力。
12.3 本合同附件是本合同不可分割的一部分，与本合同具有同等法律效力。

{% if other_terms %}
## 第十三条 其他特殊条款

{{ other_terms }}
{% endif %}

---

<div style="page-break-after: always;"></div>

## 签署页

| 甲方（客户） | 乙方（服务商） |
|--------------|--------------|
| （盖章） | （盖章） |
| **法定代表人/授权代表（签字）：** | **法定代表人/授权代表（签字）：** |
| 日期： | 日期： |

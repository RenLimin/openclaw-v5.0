---
title: 销售合同通用框架
description: 通用销售合同模板，包含完整合同结构和标准条款框架
author: L3 Office 通用模板
created: 2026-09-08
updated: 2026-09-08
tags: [合同, 销售, 框架]
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
    description: 甲方（买方）全称
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
    description: 乙方（卖方）全称
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
  - name: product_description
    type: markdown
    description: 产品/货物描述清单
    required: true
  - name: total_amount
    type: number
    description: 合同总金额（元）
    required: true
  - name: payment_schedule
    type: table
    description: 支付计划表格（节点/比例/金额/到期日）
    required: true
  - name: delivery_date
    type: date
    description: 交付日期
    required: true
  - name: delivery_location
    type: string
    description: 交付地点
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

## 甲方（买方）

- **名称:** {{ party_a_name }}
- **地址:** {{ party_a_address }}
- **联系人:** {{ party_a_contact }}

## 乙方（卖方）

- **名称:** {{ party_b_name }}
- **地址:** {{ party_b_address }}
- **联系人:** {{ party_b_contact }}

---

## 第一条 鉴于

1.1 甲方同意向乙方购买，乙方同意向甲方出售下述产品/货物，双方经协商一致，签订本合同。

## 第二条 产品/货物描述

{{ product_description }}

## 第三条 合同金额

总金额：人民币 **{{ total_amount }} 元**（大写：）

## 第四条 支付方式

| 支付节点 | 比例 | 金额 | 到期日 |
|----------|------|------|--------|
{% for row in payment_schedule %}
| {{ row.node }} | {{ row.ratio }} | {{ row.amount }} | {{ row.due_date }} |
{% endfor %}

## 第五条 交付与验收

- **交付日期：** {{ delivery_date }}
- **交付地点：** {{ delivery_location }}
- **验收标准：** {{ acceptance_criteria }}

## 第六条 双方权利与义务

### 6.1 甲方权利义务
1. 按合同约定支付货款
2. 按时组织验收
3. 接收符合合同约定的产品

### 6.2 乙方权利义务
1. 按合同约定时间交付符合质量标准的产品
2. 提供必要的安装指导和培训
3. 按约定提供售后服务

## 第七条 违约责任

7.1 任何一方违约，应向对方支付合同总金额 **X%** 的违约金。
7.2 逾期交付/逾期支付超过 **X** 日，对方有权解除合同，并要求赔偿损失。

## 第八条 保密

双方应对本合同内容及在合作中获悉的对方商业秘密保密，未经允许不得向第三方泄露。本条款在合同终止后仍然有效。

## 第九条 不可抗力

因不可抗力导致不能履行合同，受不可抗力影响一方应及时通知对方，并在合理期限内提供证明，根据不可抗力影响，部分或全部免除责任。

## 第十条 争议解决

因本合同引起的或与本合同有关的任何争议，双方应友好协商解决，协商不成的，提交 **[甲方/乙方/合同签订地]** 人民法院诉讼解决（或：提交 XX 仲裁委员会仲裁）。

## 第十一条 其他条款

11.1 本合同自双方签字盖章之日起生效。
11.2 本合同一式 **X** 份，甲方执 **X** 份，乙方执 **X** 份，具有同等法律效力。
11.3 本合同附件是本合同不可分割的一部分，与本合同具有同等法律效力。

{% if other_terms %}
## 第十二条 其他特殊条款

{{ other_terms }}
{% endif %}

---

<div style="page-break-after: always;"></div>

## 签署页

| 甲方（买方） | 乙方（卖方） |
|--------------|--------------|
| （盖章） | （盖章） |
| **法定代表人/授权代表（签字）：** | **法定代表人/授权代表（签字）：** |
| 日期： | 日期： |

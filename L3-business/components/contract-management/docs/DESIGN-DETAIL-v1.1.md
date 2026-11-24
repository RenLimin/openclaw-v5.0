# L3 通用合同管理专家 — 详细设计变更 (DESIGN-DETAIL v1.1)

| 版本 | v1.1 |
|---|---|
| 日期 | 2026-11-24 |
| 上位文档 | `DESIGN-DETAIL-v1.0.md`（模块清单/数据模型契约不变） |

## 1. 变更范围

仅 `contract_management/contract_parser.py` 的 `_extract_party_info` 及其私有辅助
函数；公开 API（`parse_contract` / `ParsedContract` / `CLAUSE_CATEGORIES`）**签名与
结构冻结不变**（AC-1）。

## 2. v1.0 缺陷复盘

`_extract_party_info(text, label)` 对每个字段执行 `re.search(全文)` 取**首个匹配**，
且甲乙方共用同一规则 ⇒ 同一物理位置的信息被复制给两方。触发条件：
① 双列表格中同名字段两列（地址/电话/邮编）；② 单列字段位于一方语境
（如「2.3 乙方指定账户信息」下的开户行/账号）。真实样本 886377 复现。

## 3. v1.1 归属算法

```
输入：全文 lines[]，本方别名集 A（甲方|需方 或 乙方|供方），他方别名集 B
1. name：先取签字页 `^甲方：公司$`；否则 `公司（以下简称"甲方"）`。
2. 双列表格行（含 | 且解析出 [label, value] 单元）：
   - `需方/供方` 行 → 名称（与 1 互为补充）；
   - 同名字段两列 → 由最近「需方/供方」标签行推断列序后按列分配。
3. 单值字段：候选行到本方提及行的最近距离 d_self；到他方最近距离 d_other；
   采纳条件：d_self 存在 且 (d_other 不存在 或 d_self < d_other) 且 d_self ≤ 8。
   —— 并列（d_self == d_other）一律不归属：缺失优于错误。
4. 值卫生：地址含「电子邮箱」或长度>60 → 丢弃；邮箱正则只取 ASCII 本地部分
   （剥离「向huijuan.lin@…」类中文前缀）。
```

## 4. 与既有契约的对齐

| 契约 | 处理 |
|---|---|
| `ParsedContract.party_a/party_b: dict` 字段 | 保留；新增可选键 `contact`（向后兼容，不影响序列化消费方） |
| L3 零副作用（AC-2） | 仍纯 stdlib + re，无 os/sys/subprocess |
| L3 不引用 L4/专有名词（AC-3） | 保持；样例只用通用占位文本 |
| skill 副本 | `skills/contract-approval/scripts/contract_parser.py` 同步同算法（除组件头注释与 `__main__` 外 diff≈0） |

## 5. 不做的事

- 不引入 NER/LLM（违反 L3 约束）；
- 不因抽取失败抛异常（返回部分 dict，缺失优于错误）。

## 6. 变更历史

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-11-24 | v1.1 | 主体抽取按方归属重写（真实样本 886377 驱动） |

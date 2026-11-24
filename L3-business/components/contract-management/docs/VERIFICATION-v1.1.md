# L3 通用合同管理专家 — 测试方案增补 (VERIFICATION v1.1)

| 版本 | v1.1 |
|---|---|
| 日期 | 2026-11-24 |
| 上位文档 | `VERIFICATION-v1.0.md`（AC-1～AC-8 不变） |

## v1.1 增补验收标准

| # | 标准 | 验证手段 | 结果 |
|---|---|---|---|
| AC-9a | 双列表格甲乙方地址/电话互不相同且分属正确 | `tests/test_party_extraction.py::test_table_columns_attributed_by_column_not_global_first` | ✅ |
| AC-9b | 单列字段按最近标签距离归属 | `::test_single_column_nearest_distance` | ✅ |
| AC-9c | 单地址贴近甲方时乙方缺失而非复制 | `::test_missing_beats_wrong` | ✅ |
| AC-9d | 真实样本 886377：地址不同、银行仅属乙方、邮箱无前缀 | `::test_real_sample_886377_no_mixing` | ✅ |
| AC-9e | `parse_contract(text)` 签名不变 | `::test_backward_compatible_signature` | ✅ |
| AC-9f | 原 AC-1～AC-8 无回归 | `pytest tests/` → **124 passed**（原 115 + 新增 9） | ✅ |
| AC-9g | docx 提取文本（无管道表格）版式同样按列归属 | `::test_docx_style_no_pipe_columns` | ✅ |
| AC-9h | 正文散行不得被误当表格行切分 | `::test_plain_body_line_not_treated_as_table` | ✅ |

## 实测记录（2026-11-24）

```text
$ python3 -m pytest tests/ -q          # 组件
124 passed in 0.23s
$ cd ../../../skills/contract-approval/scripts && python3 -m pytest tests/ -q
14 passed in 0.01s
```

真实样本 886377 修复前后对照：

| 字段 | v1.0（缺陷） | v1.1（修复后） |
|---|---|---|
| party_a.address | 全包装产品：…中山南路599号…（串用/脏值） | 上海市黄浦区中山南路599号恒信大厦2楼 |
| party_b.address | 同上（复制） | 北京市海淀区学院路30号科大天工大厦A座20层1至3室 |
| party_a.bank | 上海银行北京海淀支行（错配） | （空，不伪造） |
| party_b.bank | 同左 | 上海银行股份有限公司北京海淀支行 |
| email | 向huijuan.lin@bangcle.com（带前缀） | 未误配（ASCII 清洗后仍不归属甲方语境） |

## 运行方式

```bash
cd L3-business/components/contract-management && python3 -m pytest tests/ -q
cd L3-business/skills/contract-approval/scripts && python3 -m pytest tests/ -q
```

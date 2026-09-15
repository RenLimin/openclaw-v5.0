# 模块3：交付管理基础数据

## 职责
管理 `md_reference` 表中的「图例」等基础字典数据，供报表自动生成/计算时引用。

## 源文件结构探测结论（2026-09-15 实测）

源文件：`/Users/bangcle/Bangcle Workspace/01. Management/2026/2026团队报告/202606/2026年计划确收&实际确收对比表202601-06-0724 - 差异分析.xlsx`

「图例」sheet 名义 **506 行 × 16 列**，但：

- **有效数据只有 34 行**（第 2-35 行），第 36 行起全空（Excel 残留空行）
- 第 1 行是**分组标题行**，不是宽表头
- `merged_cells` 为空；16 列被 4 个**无标题空列**（第 4/8/11/14 列）切成 **8 个图例块**

⚠️ 因此**不能**直接用 `detect_header_row`（它面向"宽表头"场景：非空单元格多、唯一列名占比高）。本模块改为**显式按列区间解析**，再用 `HeaderMapper` 做标题名校验（标题缺失时告警而非静默跳过）。

| 块 | 列区间 | 标题 | data_type | 条目数 |
|---|---|---|---|---|
| 1 | 1-3 | 项目经理 / 部门 / 备注 | `project_manager` | 34 |
| — | 2 | （部门列去重提取） | `dept` | 5 |
| 2 | 5 | 偏差-状态/趋势 | `legend` | 7 |
| 3 | 6-7 | 偏差-原因类别 + 说明 | `deviation_reason` | 11 |
| 4 | 9 | 滞后验收原因 | `delay_accept_reason` | 5 |
| 5 | 10 | 滞后验收处置措施 | `delay_accept_action` | 5 |
| 6 | 12 | 预算执行进度 | `abnormal_type` | 7 |
| 7 | 13 | 预算执行进度类别 | `abnormal_category` | **4**（源 7 行，去重后 4） |
| 8 | 15 | 团队 | `team` | 5 |
| 9 | 16 | 产线 | `product` | 10 |

**合计 93 条互异条目。**

数据事实（非缺陷）：
- `abnormal_category` 列有 7 行非空值，但只有 4 个互异值（`异常中` 重复 4 次）→ 去重后 4 条
- `dept` 类型在源 sheet 无独立图例块，从第 2 列（项目经理的部门归属）去重提取

## code 生成规则
`make_code(label)`：ASCII 字母数字 → 小写；中文/混合 → `u<码点十六进制>`。
**同一 label 永远得到同一 code**，因此重复导入幂等、可复现，不依赖行号。

## API

```python
from bdms.modules.master_data import MasterDataService
svc = MasterDataService()               # 默认主库
svc.ensure_schema()                     # 幂等建表

# 导入（真实源文件）
svc.import_legend_from_excel(month="202606")           # 自动定位源文件
svc.import_legend_from_excel(path=Path("x.xlsx"), overwrite=False)

# 查询
svc.list_types()                        # 类型 + 条目数
svc.list_items("legend", include_disabled=False, keyword=None)
svc.get_item("legend", code)
svc.get_labels("product")               # 报表引用字典

# CRUD（软删除 enabled=0）
svc.create_item("dept", "新部门", extra={"k": "v"})
svc.update_item("dept", code, label="改名")
svc.delete_item("dept", code)           # soft
svc.delete_item("dept", code, hard=True)
svc.restore_item("dept", code)
```

## 测试
```bash
cd L4-proprietary/components/bdms && export PYTHONPATH=src
python3 -m pytest tests/test_master_data.py -v
```

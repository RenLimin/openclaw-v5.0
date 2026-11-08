# 受众适配与脱敏参考

> 本文件定义内部版/对外版的切换规则与脱敏词表。
> 脱敏在成文**最后一步**强制执行，对外版 `grep` 必须为 0。

---

## 1. 受众定义

| 受众 | 用途 | 脱敏 | 可见内容 |
|---|---|---|---|
| `internal` | 公司管理层/销售负责人 | 否 | 全部溯源链、对账附录、内部系统名 |
| `external` | 甲方（客户） | **是** | 仅交付事实、官方合同名、正式产品名 |

## 2. 脱敏词表（external 版 grep 必须为 0）

| 内部词 | 替换为 |
|---|---|
| ONES | 项目管理系统 |
| OA | 办公系统 |
| BDMS | 合同管理系统 |
| GraphQL | 接口 |
| harbor | 镜像仓库 |
| SSXM | 项目 |
| 内部任务号 | 任务编号 |
| 回款 | 付款 |
| 结算 | 费用 |
| 验收条款 | 验收约定 |

- 合同/项目一律使用**官方正式名**。
- 非官方合同名（自行概括）禁止出现在对外版。

## 3. 合同名规则

| 场景 | 规则 |
|---|---|
| 台账有官方名 | 使用 `officialName` |
| 台账无官方名 | 用 `projectName` 兜底，`nameSource=project_fallback` |
| 审计可见 | `nameSource` 字段仅内部版可见 |

## 4. 价值论述标注

- 基于真实交付的价值提炼，明确标注 **"基于事实的推断"**。
- 措辞可配置：保留 / 降级（更保守）。
- 禁止编造客户满意度、商业价值等无源结论。

## 5. 切换开关

```bash
# 内部版
python3 scripts/render_report.py --audience internal < stage4.json

# 对外版（自动脱敏）
python3 scripts/render_report.py --audience external < stage4.json
```

- `audience` 作为显式开关传入，默认 `internal`。
- 对外版渲染完成后，`audit_provenance.py` 强制校验脱敏词表。

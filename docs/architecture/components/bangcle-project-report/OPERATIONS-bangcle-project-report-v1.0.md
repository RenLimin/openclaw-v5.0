# OPERATIONS — Bangcle 项目汇报材料生成技能 v1.0（待评审）

- 技能：`bangcle-project-report`（L3）· 经 L4 PJME-001 路由
- 环境：macOS / Linux；Python 3.10+；python-docx；ONES 浏览器登录态

---

## 1. 前置条件

1. 浏览器已登录 `ones.bangcle.com`（同域有 `localStorage['ct']`）。
2. Python 依赖：`python-docx`（docx 导出）；其余用标准库。
3. 技能已在 `openclaw.json → skills.load.extraDirs` 覆盖 L3 目录（已配置，无需改动）。

## 2. 标准操作流程

### 2.1 通过专家入口（推荐）

向 PJME-001 或直接对助手说：

> "用 bangcle-project-report 生成 **中国建设银行 / 2026 年度 / 对外版** 项目汇报材料。"

技能将按 S1→S8 执行，完成后给出 md 路径与审计结论。

### 2.2 手动逐段（排障/复算用）

所有脚本 JSON 经 stdin/stdout：

```bash
cd L3-business/skills/bangcle-project-report

# 1) 取数（产出 /tmp/stage1.json）
echo '{"customer":"中国建设银行股份有限公司",
       "period":{"start":"2026-01-01","end":"2026-12-31"},
       "audience":"external"}' \
 | python3 scripts/fetch_project_tasks.py > /tmp/stage1.json

# 2) 清洗分类
python3 scripts/normalize_and_classify.py < /tmp/stage1.json > /tmp/stage2.json

# 3) 汇总明细（含对账，失败 exit 2）
python3 scripts/aggregate.py < /tmp/stage2.json > /tmp/stage3.json

# 4) 目标矩阵
python3 scripts/build_goal_matrix.py < /tmp/stage3.json > /tmp/stage4.json

# 5) 渲染 + 脱敏 + 导出 docx
python3 scripts/render_report.py --audience external --docx < /tmp/stage4.json

# 6) 溯源审计（fail-closed）
python3 scripts/audit_provenance.py --report <产出md>
```

## 3. 产物位置

| 产物 | 位置 |
|---|---|
| 汇报 MD / docx | `analysis_output/ccb_delivery/`（或对应客户目录） |
| 原始数据 | `analysis_output/ones_raw/` |
| 完整性/审计 | 随原始数据同目录，控制台摘要 |

## 4. 故障排查

| 现象 | 原因 | 处理 |
|---|---|---|
| 取数 exit 2 / hitCap | 分页未取全或触顶 | 重跑；检查 pageSize；确认末页非满页 |
| 限流 801 | 接口频控 | 指数退避自动重试；连续 3 次失败停手，稍后再跑 |
| 合同编号为空 | Project 字段未取到/快照过期 | 实时重取 `Project._7KF6tXvk`；勿用旧快照判无 |
| 审计 BLOCK | 存在无源数字/名词/未脱敏词 | 按 missing 清单逐项修正后重跑 |
| 产品方向【缺失】 | 映射表未覆盖新名词 | 补 references 映射，不临时手填 |
| docx 乱码/缺表 | python-docx 结构异常 | 重导出；核对标题=7、明细行=113 |
| 浏览器取 token 失败 | 登录态失效 | 重新登录 ONES 后再执行 |

## 5. 安全与红线

- 凭据/license 内容绝不写入产物；脱敏在成文末步强制执行。
- 对外版零内部系统名/编号/商务条款；名称取官方名。
- 本技能**不自动外发**；任何邮件/群发须人工确认。
- 不改动既有 PM 技能与全局配置。

## 6. 升级与回归

- 新增能力：设计文档升版 + 黄金基准回放（113/104/9）必须仍通过。
- 映射/词表变更后，重跑 VERIFICATION 全套 T1–T10。

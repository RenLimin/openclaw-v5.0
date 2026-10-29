# OPERATIONS — BDMS 人工数据校准与填写 v1.0 操作手册

> 状态：**待 Rex 审核** | 作者：Jerry 🦞 | 日期：2026-10-28
> 依据：`PRD / OUTLINE / DETAILED / VERIFICATION` v1.0（均通过）
> 配套：总手册 `OPERATIONS-v2.1.md`；本手册仅覆盖「人工校准」新功能。
> 本文通过后才进入 IMPLEMENTATION-PLAN。

---

## 1. 安装与启用

校准功能随 BDMS 服务启动自动启用，无需独立安装。

### 1.1 前置条件
- 已完成 `OPERATIONS-v2.1.md §1` 的环境安装与 DB 初始化。
- BDMS 服务可正常启动（launchd 或手动 uvicorn）。

### 1.2 数据库升级（自动）
新版本首次启动时，`init_db()` 会幂等创建两张新表：
- `dr_calibration`（校准覆盖层）
- `dr_calibration_history`（撤销/修改留痕）

旧库无需手工迁移；`CREATE TABLE IF NOT EXISTS` 与部分唯一索引重复执行安全。

手动确认表已建好：
```bash
sqlite3 data/bdms.db ".tables" | tr ' ' '\n' | grep dr_calibration
# 预期输出：
# dr_calibration
# dr_calibration_history
```

### 1.3 启动 / 重启服务
```bash
# launchd（生产守护）
launchctl kickstart -k gui/$(id -u)/com.bdms.server

# 或手动（调试）
cd <bdms 目录>
PYTHONPATH=src python3 -m uvicorn bdms.web.main --host 127.0.0.1 --port 8000
```

### 1.4 健康检查
```bash
curl -s http://localhost:8000/api/health
# → {"status":"ok"}
```

---

## 2. 操作指南

### 2.1 场景一：在问题清单校准一条错误（最常用）

1. 浏览器打开 `http://localhost:8000`，进入「报告生成」页。
2. 选目标月份，切到「**问题清单**」Tab。
3. 用状态（待处理）/严重度（错误/警告）筛选定位问题。
4. 点该问题行的「**校准**」按钮，弹出对话框：
   - 上方只读显示：月份 / Sheet / 行号 / 列名 / 规则说明 / **原始值**。
5. 在「校准值」输入正确值：
   - 日期列 → 日期选择器；数值列 → 数字框；枚举列 → 下拉；文本 → 普通输入。
6. 在「校准原因」填原因（必填，可下拉选常用项或自定义）。
7. 点「保存」：
   - 成功 → toast「校准成功」，对话框关闭；
   - 该问题若已合规，状态自动变「已修正」，顶部待处理数下降。

> 小批量（受影响 ≤ 200 行）即时完成；超出则显示进度条，完成后自动刷新。

### 2.2 场景二：补填空值（必填缺失）

- 与 2.1 相同路径。原始值显示为空的问题，直接在「校准值」填入合法值并填原因保存。
- 保存后对应「必填为空」规则问题消失（转 confirmed）。

### 2.3 场景三：在数据浏览里直接校准

1. 切到「**数据浏览**」Tab。
2. Sheet 下拉现在显示当月**全部 Sheet（15 个）**，选目标 Sheet。
3. 点「**进入编辑**」。
4. 点要修改的单元格 → 弹出同一校准对话框 → 填值+原因 → 保存。
5. 已校准单元格显示标记（角标/底色）；悬停看校准摘要。

### 2.4 场景四：查看校准记录（审计）

- 方式 A：点已校准单元格 →「查看校准记录」。
- 方式 B：问题清单某条 →「查看校准」。
- 弹窗展示：原始值、校准值、操作人、校准时间、校准原因；若被修改过，还能看到上一条校准值快照。

### 2.5 场景五：撤销 / 修改校准

- **撤销**：校准记录中「撤销」→ 确认。该单元格恢复原值并重校验，若仍违规则问题重新出现。
- **修改**：再次对该单元格发起校准填新值；旧校准值自动入历史快照。

### 2.6 场景六：导出含校准数据的月报

```bash
curl -s -OJ http://localhost:8000/api/report/export/202610
```
- 各 Sheet 已校准单元格输出**校准后值**，并带批注（原值→新值 / 操作人 / 时间）。
- 若该月有校准，末尾追加「**校准台账**」Sheet；无校准则不生成该 Sheet。

界面操作：报告页「导出月报」按钮，浏览器下载后用 Excel/WPS 打开核对。

### 2.7 场景七：月报锁定与解锁

- 月报「审核通过」后校准自动锁定，防止审计后被改。
- 如需继续校准：先「驳回」月报（填驳回原因）→ 解锁 → 校准 → 重新提交审核。

---

## 3. CLI / API 速查（进阶）

| 操作 | 端点 |
|---|---|
| 提交/修改校准 | `POST /api/report/calibrations/{month}` |
| 撤销校准 | `POST /api/report/calibrations/{month}/revoke` |
| 查询校准记录 | `GET /api/report/calibrations/{month}` |
| 校准总览 | `GET /api/report/calibrations/{month}/overview` |
| 动态 Sheet 列表 | `GET /api/report/sheets/{month}` |
| 校准台账 JSON | `GET /api/report/calibration-ledger/{month}` |
| 导出 Excel | `GET /api/report/export/{month}` |

示例（提交校准）：
```bash
curl -s -X POST http://localhost:8000/api/report/calibrations/202610 \
  -H 'Content-Type: application/json' \
  -d '{"sheet":"签约","row_index":12,"column_name":"签约日期",
       "corrected_value":"2026-06-03","reason":"按合同实际签署日修正",
       "operator":"gateway-owner"}'
```

---

## 4. 故障排查

### 4.1 保存校准被拒：提示类型/枚举非法
- 原因：输入值与列类型不符，或枚举值不在允许集合。
- 处理：按控件提示改为合法格式；枚举只能选下拉内值。允许集合来自主数据 legend，需调整集合应到「基础数据」配置。

### 4.2 保存被拒：月报已锁定（LOCKED）
- 原因：该月报已 approve。
- 处理：先驳回月报再校准（见 2.7）。

### 4.3 提交返回 409 CALIBRATION_BUSY
- 原因：该月大批量重校验 job 进行中。
- 处理：等进度条完成后再提交（系统不允许同月并发校准写）。

### 4.4 校准后单元格没变化 / 显示的还是旧值
排查顺序：
```bash
# 1. 校准是否生效
sqlite3 data/bdms.db \
 "SELECT status,corrected_value FROM dr_calibration WHERE month='202610';"
# 2. 服务是否为新版本（重启过）
launchctl kickstart -k gui/$(id -u)/com.bdms.server
# 3. 行号/列名是否对得上（重新生成月报会使旧校准失效）
```

### 4.5 重新生成月报后校准不见了（预期行为）
- regenerate 会重写原始数据、可能改变行号；系统在重生成前已二次确认并把旧校准置 revoked。
- 这是设计内的审计保护，不是数据丢失；旧记录在 `dr_calibration_history` 可查。

### 4.6 怀疑原始数据被改动
```bash
# 校准功能任何操作都不应改 dr_sheet_row。
# 若发现异常，立即停止使用并排查是否误调了已废弃的 apply_manual_fixes。
grep -rn "apply_manual_fixes\|apply_fixes" src/
# 新版本应为 0 处。
```

---

## 5. FAQ

| 问题 | 回答 |
|---|---|
| 校准会改掉原始导入的数据吗？ | 不会。原始 `dr_sheet_row` 只读，校准存在独立覆盖层。 |
| 能批量粘贴一堆校准吗？ | v1.0 不支持，列入 v1.1。当前逐条或小数组提交。 |
| 撤销后还能再校准吗？ | 能。撤销释放该单元格，可重新发起。 |
| 导出给外部的是哪个值？ | 校准后值；并附校准台账，可解释每一处改动。 |
| 谁能校准？ | v1.0 本地单人模式默认 `gateway-owner`；操作人随每条记录留痕。 |
| 校准需要审批吗？ | 校准本身即生效仅留痕；月报级仍有 approve/reject 审核门。 |

---

## 6. 变更历史

- 2026-10-28 v1.0：Jerry 初稿。覆盖启用升级、7 个操作场景、API 速查、6 类故障排查与 FAQ。

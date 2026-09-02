# CONTEXT.md — BDMS 交付月报生成任务

> 本文件是任务现场的核心上下文。会话 reset 后读取本文件即可恢复任务。

## 一、任务目标
Rex 要求 202606 交付月报与手工报表**完全一致**，逐项核对所有 Sheet。

## 二、当前进度（2026-09-02 23:20）

### 已完成
1. **ONES 浏览器自动化导出全链路打通**：签约 16,612 + POC 5,030 + 异常 362 行
2. **月报 15 Sheet 生成**：确收/验收/异常项目 3 Sheet 完全匹配参考报表
3. **Commit**: `91b0241`

### 进行中
4. 剩余 Sheet 数据核对与修复（对比手工报表逐项差异）

### 待办
5. 全量生成验证 + 最终 commit

## 三、关键路径

- 数据源：ONES CSV（`~/.openclaw/data/ones_exports/`）+ BDMS（`revenue_vouchers`/`acceptance_vouchers`）
- 生成脚本：`scripts/l4/delivery_center/`（main.py / pipeline.py / generators/）
- 组件文档：`docs/architecture/components/l4-delivery-center/DESIGN.md`
- 上次 commit：`91b0241`

## 四、阻塞点
- `coding-plan` provider 401 Unauthorized（API Key 过期，未达 3 次失败阈值）— 影响模型调度，不影响本地生成

## 五、验证方式
- 与手工报表（Excel）逐 Sheet 对比
- 确认所有 15 个 Sheet 数据一致

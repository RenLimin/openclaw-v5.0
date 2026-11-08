# IMPLEMENTATION-PLAN — 实时动态确认收入预估（Revenue Forecast）v1.0

| 项 | 值 |
|---|---|
| 所属 | BDMS / revenue_forecast |
| 版本 | v1.0 |
| 日期 | 2026-11-08 |
| 前置 | PRD/OUTLINE/DETAIL/VERIFICATION/OPERATIONS v1.0 |

---

## 0. 版本定位

在已交付 BDMS 上**增量新增**一个模块 `revenue_forecast`：
- 基于上一账期**收入预算执行表**（财报）计算，呈现**锁定 / 动态**双口径 + 实际发生；
- 为 Part B（ONES 实时动态）预留接口与 UI 位置，本版不接入。

原则：最小侵入，沿用 Base 层与既有模块模式，不改现有业务逻辑，不新增第三方依赖。

---

## 1. 复用资产

| 资产 | 复用点 |
|---|---|
| `modules/base.py` BaseEngine/BaseService/BaseExporter | service/exporter 基类 |
| `db.py` 连接 / init_db / job 表 | 异步 job、进度 |
| 集中 API（`web/main.py`）+ 侧栏 | 挂路由 + 导航项 |
| revenue 模块结构 | engine/service/exporter 组织参照 |
| openpyxl（已在用） | 财报解析/导出 |

---

## 2. Phase 拆分

### Phase 1：数据解析与分类（纯内核）
- `report_parser.py`：两 Sheet → ObligationRow；col2/7/8/33/34、col15–26/27/32–40/42；恒等式校验；
- `classifier.py`：十类 + 优先级，关键词/年份配置常量；
- 单测：parser + classifier 全分支。
- **门**：parser/classifier 全绿。

### Phase 2：双口径引擎
- `engine.py`：锁定（col27/逐月）、动态（col42/分类/pipeline）、实际、gap；纯函数；
- 单测：黄金数字（1.38 / 1.71 / .94 / +.33）+ 幂等 ×3。
- **门**：黄金锚点全部命中。

### Phase 3：持久化
- `repository.py`：4 表 DDL、事务、版本切换、同期幂等重建、分页/过滤/汇总查询；
- 单测：建表/两期切换/重算/分页。
- **门**：repository 全绿。

### Phase 4：服务 + API
- `service.py`：上传 job（解析→关联→计算→落库）、进度写 job 表、读模型；失败保留上版；
- 8 个 `/api/forecast/*` 端点接入；
- 真实 HTTP 集成测试全端点。
- **门**：8 端点真实 HTTP 全过。

### Phase 5：Web UI
- `/forecast` 页面：上传+进度条、概览双卡+差异、锁定/动态月度图、明细分页+下钻、Part B 状态；
- 侧栏「确认收入管理」加入口；
- Playwright E2E（slow）六路径。
- **门**：E2E 通过。

### Phase 6：导出 + 回归 + 验收
- `exporter.py`：多 sheet；导出可被 openpyxl 重开且数字一致；
- 全量回归（排除 visual/slow）：不破坏 367 passed 基线；
- 7 步法独立审计；VERIFICATION 记录；Rex 人工验收。
- **门**：全绿 + Rex 验收。

---

## 3. 文件清单

```
modules/revenue_forecast/
  __init__.py
  report_parser.py
  classifier.py
  engine.py
  repository.py
  service.py
  exporter.py
  providers/__init__.py
  providers/base.py
  providers/null_provider.py
tests/  新增 test_forecast_*.py
web/templates/forecast.html（+静态 js/css 按需）
web/main.py 挂路由；侧栏加导航
```

---

## 4. 依赖关系

```
P1 parser/classifier → P2 engine → P3 repository → P4 service/API → P5 UI → P6 导出/回归
providers（占位，无依赖，P4 起被状态查询引用）
```

---

## 5. 里程碑与验收

| 里程碑 | 判据 |
|---|---|
| 内核完成 | P1/P2 黄金数字单测全绿 |
| 后端完成 | P3/P4 真实 HTTP 全过 |
| 前端完成 | P5 E2E 六路径 |
| 交付 | P6 全量回归 + 7 步法 + Rex 人工验收 |

每 Phase 三道门：自测 → VERIFICATION 对应项 → Rex 验收节点（P6 总验收，过程门由自测+文档证据构成）。

---

## 6. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 财报列被财务调整 | 列映射集中可配 + 恒等式启动校验，差异入报告 |
| 主会话上下文膨胀影响长构建 | 开发构建隔离到独立子会话，结果回传本会话 |
| IN_PIPELINE 月份误摊 | 动态归 pipeline，锁定月份仅作下钻对照，不伪造 |
| 破坏现有功能 | 最小侵入 + 全量回归门禁 |
| Part B 提前耦合 | 仅接口 + not_configured，不引调用链 |

---

## 7. 执行方式

- 开发构建设独立子会话（isolated）执行，严格按 Phase 顺序；每 Phase 输出测试证据到文件；
- 子会话产出回传，主会话按 7 步法独立审计后再提交 git（只暂存本任务文件）。

---

*v1.0 交付 Part A 双口径；Part B（ONES 实时）仅预留。*

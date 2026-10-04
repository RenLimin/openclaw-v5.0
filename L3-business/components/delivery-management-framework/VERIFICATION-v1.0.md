# delivery-management-framework — 测试方案 (VERIFICATION)

> 版本: v1.0 · 日期: 2026-09-28

## 1. 测试范围

- BaseModel CRUD
- 模块注册引擎
- 事件总线
- 状态机
- RACI 引擎
- CLI 命令

## 2. 测试用例

| # | 场景 | 输入 | 预期结果 |
|---|---|---|---|
| TC01 | BaseModel CRUD | 模型对象 | CRUD 正确 |
| TC02 | 模块注册 | 模块定义 | 注册成功 |
| TC03 | 事件发布/订阅 | 事件 | 订阅者收到 |
| TC04 | 状态机流转 | 状态+事件 | 转移正确 |
| TC05 | RACI 分配 | 角色分配 | 分配正确 |
| TC06 | CLI 入口 | 命令 | 正确分发 |

## 3. 人工操作手册（附录）

### 使用步骤

1. 创建项目: `python3 dms_cli.py project create`
2. 添加成员: `python3 dms_cli.py member add`
3. 跟踪进度: `python3 dms_cli.py work_item list`

### 验证清单

- [ ] 项目 CRUD 正常
- [ ] 事件订阅者正常
- [ ] 状态机转移正确
- [ ] RACI 查询正确

## 4. 实测结果

- BaseModel: ✅
- 模块注册: ✅
- 事件总线: ✅
- 状态机: ✅
- RACI: ✅

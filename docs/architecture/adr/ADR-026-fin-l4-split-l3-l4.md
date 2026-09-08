# ADR-026: 个人理财引擎 L3/L4 分层拆分方案

状态：Accepted
创建日期：2026-09-08
作者：Jerry/Rex

## 问题陈述

原个人理财引擎全部代码放在 L4-proprietary/fin-l4，不符合 L0-L4 分层架构规范：
- L3 是通用业务组件，可复用
- L4 是专有业务定制，依赖 L3
- 当前全部放 L4 无法复用通用理财能力，违反分层契约

## 决策结果

将理财引擎拆分为 L3 通用能力层 + L4 专有定制层

### 拆分方案

#### 目录结构

```
L3-business/components/finance-engine/
├── __init__.py
├── core/                 # 通用核心模块
│   ├── __init__.py
│   ├── db/               # 数据库抽象
│   ├── external/         # 外部数据源接口（汇率、行情、利率）
│   ├── security/         # 安全能力（审计、备份、加密）
│   └── services/         # 通用服务基类
├── fin001_account/       # 账户/交易/预算服务
├── fin002_loan/          # 贷款计算服务
├── fin003_insurance/     # 保险计算服务
├── fin004_rate/          # 汇率利率服务
├── fin005_portfolio/     # 投资组合服务
└── fin006_advisor/       # 理财建议服务

L4-proprietary/components/fin-l4/
├── __init__.py
├── cli.py                # CLI入口保留
├── config.py             # 配置保留
├── web/                  # Web入口保留
├── integration/          # 业务集成保留
├── load_demo_data.py     # 演示数据保留
└── run_web.py            # Web启动保留
```

### 接口契约

1. **L3 层只放通用逻辑**：每个模块暴露抽象接口，不包含业务定制配置
2. **L4 层做业务定制**：继承 L3 接口，实现专有配置和业务逻辑
3. **导入约定**：L4 从 `L3-business.components.finance-engine` 导入模块

### 迁移步骤

1. ✅ 定义拆分方案和目录骨架（本ADR）
2. 创建 L3 各模块目录结构
3. 将 L4 通用代码迁移到对应 L3 模块
4. 更新 L4 导入语句，指向 L3
5. 修复测试文件 `sys.path`，指向 L3
6. 运行测试验证功能正常

## 权衡

- **优势**：符合分层架构，通用理财能力可复用，便于后续扩展
- **成本**：需要修改导入路径，少量代码迁移工作量不大

## 后果

- L3 `finance-engine` 成为通用理财能力组件
- L4 `fin-l4` 专注业务定制，代码更清晰
- 后续其他理财相关项目可直接复用 L3 模块

---
<!-- project: github.com/RenLimin/openclaw-v5.0 -->

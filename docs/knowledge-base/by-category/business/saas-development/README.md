# SaaS 产品开发知识库

> L3 业务知识 · SaaS (Software-as-a-Service) 产品开发与运营全流程。
>
> **适用场景**：B2B/B2C SaaS 产品从 0 到 1 构建、多租户架构设计、计费订阅系统、集成生态、客户成功体系。
> **遵循规范**：统一知识库规范（`../../../meta/specification.md`）、术语表（`../../../meta/glossary.md`）。

---

## 目录结构

| 模块 | 说明 | 文档数 |
|---|---|---|
| [01-product-management](./01-product-management/) | SaaS 产品管理：路线图、版本节奏、需求优先级 | 6 |
| [02-tenant-architecture](./02-tenant-architecture/) | 多租户架构设计：隔离模型、扩展性、性能 | 5 |
| [03-billing-subscription](./03-billing-subscription/) | 计费与订阅：定价模型、账单系统、发票税务 | 5 |
| [04-multi-tenant-data](./04-multi-tenant-data/) | 多租户数据策略：分片、迁移、数据隔离审计 | 4 |
| [05-identity-access](./05-identity-access/) | 身份与访问：SSO、RBAC/ABAC、审计 | 5 |
| [06-integration-marketplace](./06-integration-marketplace/) | 集成与应用市场：API 生态、合作伙伴、上架流程 | 4 |
| [07-operations-reliability](./07-operations-reliability/) | 运维与可靠性：SLA、监控、故障响应 | 5 |
| [08-customer-success](./08-customer-success/) | 客户成功：onboarding、续约、增购、流失预警 | 4 |
| [09-security-compliance](./09-security-compliance/) | 安全合规：SOC 2、GDPR、等保、渗透测试 | 4 |
| [10-pricing-packaging](./10-pricing-packaging/) | 定价与包装：套餐设计、PLG、价值度量 | 4 |
| **合计** | 10 个模块 | **46** |

---

## 核心原则

1. **Tenant-isolation first** — 多租户隔离是 SaaS 的生命线，任何设计都不能突破隔离边界
2. **Usage-based mindset** — 从第一天就度量使用量（metrics、feature usage），为后续定价迭代打基础
3. **API-first** — 内部即用 API，外部生态水到渠成
4. **Customer success ≠ support** — 成功是主动的（驱动价值实现），支持是被动的（解决问题）
5. **Pricing is a feature** — 定价不是财务问题，是产品问题，要持续迭代
6. **Compliance by design** — 安全合规从架构阶段嵌入，不是事后打补丁

---

## 关联维度

- 项目管理 → `../project-management/`（SaaS 研发流程是其特例）
- 合同管理 → `../contract-management/`（SaaS 合同/M SA/DPA 等）
- 财务 → `../finance/`（SaaS 收入确认、MRR/ARR 核算）
- 售后 → `../after-sales/`（客户成功与售后协同）

---

## 维护说明

- 新增文档：遵循 `meta/specification.md` 的 SOP 模板，frontmatter 必填项齐全
- 修订：每次修订更新 `updated` 和 `revision`
- 交叉引用：使用相对路径，跨维度引用写完整路径并标注维度

# AI 知识库 - 模板化与实例化详细设计 v1.0

> L2 Infrastructure Component · ai-knowledge-base
> 版本：v1.0 · 状态：Draft
> 最后更新：2026-10-18

---

## 1. 设计目标

1. **快速创建**：基于模板 5 分钟内创建一个新的知识库实例
2. **配置驱动**：通过配置文件定义知识库行为，无需改代码
3. **领域适配**：不同领域的知识库可以有不同的实体类型、分类体系、检索策略
4. **模板复用**：优秀的知识库配置可以沉淀为模板，供其他实例复用
5. **可扩展性**：支持自定义模板，支持模板继承和组合
6. **向后兼容**：已有的知识库实例可以继续使用，不受模板系统影响

---

## 2. 核心概念

### 2.1 模板 (Template)

模板是知识库实例的"配方"，定义了知识库的结构和行为规范。一个模板包含：
- 实体类型定义
- 分类体系
- 检索配置
- 权限模板
- 导入规则
- UI 配置（可选）

### 2.2 实例 (Instance)

基于模板创建的具体知识库。每个实例：
- 有独立的 domain（数据隔离）
- 有独立的数据库（或独立 schema）
- 有独立的文档存储
- 有独立的配置（可覆盖模板默认值）
- 有独立的访问权限

### 2.3 模板与实例的关系

```
Template（模板）
    │
    │  1:N 实例化
    │
    ├──→ Instance A（基于模板，自定义了部分配置）
    ├──→ Instance B（基于模板，完全使用默认配置）
    └──→ Instance C（基于模板，大幅自定义）
```

**设计原则**：
- 模板定义默认值和约束，实例可以覆盖默认值
- 模板升级时，实例可以选择是否同步升级
- 实例可以脱离模板独立存在（unbind）

---

## 3. 模板结构设计

### 3.1 模板格式

使用 YAML 格式定义模板，可读性好，支持注释。

```yaml
# 模板元信息
template:
  id: bangcle-product-kb          # 模板唯一标识
  name: "Bangcle 产品知识库"       # 模板显示名称
  version: "1.0.0"                # 模板版本
  description: "梆梆安全产品知识库模板，包含产品、解决方案、价格等知识类型"
  author: "knowledge-team"
  created_at: "2026-10-01"
  category: "business"            # 模板分类：business / tech / general / custom

# 实体类型定义
entity_types:
  - name: product
    display_name: "产品"
    icon: "📦"
    fields:
      - name: name
        type: string
        display_name: "产品名称"
        required: true
        searchable: true
      - name: product_line
        type: string
        display_name: "产品线"
        searchable: true
      - name: sku
        type: string
        display_name: "SKU编码"
        unique: true
        searchable: true
      - name: price
        type: number
        display_name: "价格"
        searchable: false
      - name: version_latest
        type: string
        display_name: "最新版本"
      - name: status
        type: enum
        values: [active, deprecated, eol]
        display_name: "产品状态"
      - name: summary
        type: text
        display_name: "产品简介"
        searchable: true
  
  - name: solution
    display_name: "解决方案"
    icon: "💡"
    fields:
      - name: name
        type: string
        display_name: "方案名称"
        required: true
        searchable: true
      - name: industry
        type: string
        display_name: "适用行业"
        searchable: true
      - name: core_capabilities
        type: list
        display_name: "核心能力"
      - name: typical_customers
        type: list
        display_name: "典型客户"

  - name: whitepaper
    display_name: "白皮书"
    icon: "📄"
    fields:
      - name: title
        type: string
        display_name: "标题"
        required: true
      - name: publish_date
        type: date
        display_name: "发布日期"
      - name: author
        type: string
        display_name: "作者"

# 分类体系（树形结构）
categories:
  - name: "移动安全"
    code: mobile-security
    children:
      - name: "APP加固"
        code: app-hardening
      - name: "源代码审计"
        code: source-audit
      - name: "移动应用安全检测"
        code: app-security-test
  - name: "终端安全"
    code: endpoint-security
    children:
      - name: "EDR"
        code: edr
      - name: "零信任终端"
        code: zero-trust-endpoint
  - name: "解决方案"
    code: solutions
    children:
      - name: "金融行业"
        code: finance
      - name: "政府行业"
        code: government
      - name: "汽车行业"
        code: automotive

# 文档导入规则
import_rules:
  # 路径匹配规则：根据文件路径自动分类
  path_mapping:
    - pattern: "移动安全/APP加固/**"
      collection: "mobile-security/app-hardening"
      entity_type: product
      doc_type: spec
    
    - pattern: "移动安全/源代码审计/**"
      collection: "mobile-security/source-audit"
      entity_type: product
      doc_type: spec
    
    - pattern: "解决方案/**"
      collection: "solutions/{industry}"
      entity_type: solution
      doc_type: solution_doc
  
  # 文件类型过滤
  allowed_formats:
    - pdf
    - docx
    - xlsx
    - pptx
    - md
    - txt
    - html
  
  # 命名规则：从文件名提取信息
  filename_pattern: 
    pattern: "{product_name}_V{version}_{date}.{ext}"
    extract_fields:
      product_name: "实体名称"
      version: "版本号"
      date: "发布日期"

# 检索配置
search:
  default_top_k: 5
  min_similarity: 0.3
  
  # 召回通道配置
  channels:
    entity:
      enabled: true
      weight: 1.3          # 产品知识库更看重实体精确匹配
      top_k: 10
    fts:
      enabled: true
      weight: 1.0
      top_k: 20
    vector:
      enabled: true
      weight: 0.9
      top_k: 20
    graph:
      enabled: true
      weight: 0.8
      max_depth: 2
      top_k: 10
  
  # 融合排序方法
  fusion_method: weighted_sum
  
  # 重排序（可选）
  rerank:
    enabled: false
    model: ""
    top_n: 20

# 权限模板
permissions:
  default_clearance: internal    # public / internal / confidential / restricted
  default_roles:
    - role: viewer
      permissions: [read]
    - role: editor
      permissions: [read, write]
    - role: admin
      permissions: [read, write, delete, manage]
  
  # 默认谁可以访问
  public_access: false

# 生命周期配置
lifecycle:
  # 知识默认有效期（天），0表示永不过期
  default_expiry_days: 365
  
  # 到期前提醒（天）
  expire_warning_days: 30
  
  # 审核流程配置
  review:
    enabled: false
    required_roles: [knowledge_manager]

# 质量配置
quality:
  # 最低质量分（低于此值的知识需要审核）
  min_quality_score: 0.5
  
  # 负面反馈阈值（达到此值自动进入审核队列）
  negative_feedback_threshold: 3

# Embedding 配置（可覆盖全局默认）
embedding:
  provider: default              # default = 使用全局配置
  model: ""
  batch_size: 32
  
# 切片配置
chunking:
  strategy: section              # section / semantic / fixed
  max_tokens: 512
  min_tokens: 50
  overlap_tokens: 64
  preserve_tables: true
  preserve_code: true

# UI 配置（可选，供前端使用）
ui:
  theme: default
  show_version: true
  show_feedback: true
  default_view: list             # list / grid / tree
```

### 3.2 模板版本管理

- 模板采用语义化版本（SemVer）：主版本.次版本.修订号
- 主版本升级：不兼容的变更（实体结构变化等）
- 次版本升级：向下兼容的新增功能
- 修订号：bug修复和小改进
- 实例绑定特定版本的模板，不会因模板升级而自动变化
- 提供升级工具，可手动升级实例到新版本模板

---

## 4. 模板引擎设计

### 4.1 核心功能

| 功能 | 描述 |
|---|---|
| 模板加载 | 从文件/数据库加载模板定义 |
| 模板验证 | 验证模板格式是否正确、字段是否合法 |
| 模板保存 | 保存模板到数据库 |
| 模板列表 | 列出所有可用模板 |
| 实例化 | 基于模板创建知识库实例 |
| 配置合并 | 模板默认值 + 实例自定义值合并 |
| 模板升级 | 实例升级到新版本模板 |

### 4.2 配置合并策略

实例创建时，配置合并规则：

```
最终配置 = 全局默认值 ⊕ 模板默认值 ⊕ 实例自定义值
```

- 后面的覆盖前面的
- 字典类型深度合并（不是整体替换）
- 列表类型默认替换（可配置为追加）
- 实例可以取消模板定义的某些功能（设为 enabled: false）

### 4.3 实例化流程

```
用户选择模板 + 输入实例基本信息
    ↓
验证模板有效性
    ↓
创建 domain 记录（分配唯一 code）
    ↓
初始化数据库（创建表结构 / schema）
    ↓
按模板预创建分类树
    ↓
按模板初始化权限配置
    ↓
应用检索配置和其他设置
    ↓
创建实例目录结构（文档存储等）
    ↓
记录模板版本绑定关系
    ↓
返回实例信息（含访问凭证）
```

### 4.4 模板继承（可选扩展）

支持模板之间的继承关系：

```yaml
template:
  id: finance-product-kb
  name: "金融行业产品知识库"
  extends: bangcle-product-kb      # 继承自产品知识库模板
  version: "1.0.0"
  
  # 只定义差异部分，其他继承父模板
  categories:
    - name: "金融行业解决方案"
      code: finance-solutions
      # ... 新增金融行业专用分类
  
  permissions:
    default_clearance: confidential  # 金融行业默认更高权限
  
  # 其他配置继承父模板
```

---

## 5. 内置模板

### 5.1 通用文档知识库 (generic-doc-kb)

最基础的模板，适合通用文档管理。

- 实体类型：Document（文档）
- 分类：用户自定义
- 检索：均衡配置（FTS + 向量各一半权重）
- 适用场景：团队文档、项目文档、知识沉淀

### 5.2 产品知识库 (product-kb)

面向产品型企业的知识库模板。

- 实体类型：Product（产品）、Solution（解决方案）、Whitepaper（白皮书）
- 分类：产品线 → 产品
- 检索：实体匹配权重更高
- 适用场景：产品团队、销售支持、售前

### 5.3 技术文档库 (tech-doc-kb)

面向技术团队的知识库模板。

- 实体类型：API、SDK、架构文档、最佳实践
- 分类：按技术栈/模块
- 检索：代码块保留、技术术语权重高
- 适用场景：研发团队、技术支持

### 5.4 培训知识库 (training-kb)

面向培训和学习的知识库模板。

- 实体类型：Course（课程）、Exam（试题）、Reference（参考资料）
- 分类：按学科/章节
- 检索：题目和答案关联检索
- 适用场景：企业培训、在线学习、考试系统

### 5.5 合同知识库 (contract-kb)

面向合同和法务的知识库模板。

- 实体类型：Contract（合同）、Clause（条款）、Template（模板）
- 分类：按合同类型/业务线
- 检索：精确匹配优先，权限控制更严格
- 适用场景：法务团队、合同管理

---

## 6. 模板市场（扩展设计）

### 6.1 模板来源

| 来源 | 说明 |
|---|---|
| 内置模板 | 系统自带的通用模板 |
| 自定义模板 | 用户自己创建的模板 |
| 共享模板 | 组织内共享的模板 |
| 市场模板 | 从模板市场下载的第三方模板（未来） |

### 6.2 模板管理

- 模板发布：将自定义模板发布为共享模板
- 模板审核：发布前需审核（可配置）
- 模板评分：用户可以给模板打分和评论
- 模板下载量统计

---

## 7. 迁移与兼容

### 7.1 已有实例迁移

对于模板系统上线前已存在的知识库实例：

1. 检测实例结构，自动匹配最接近的内置模板
2. 生成"自定义模板"，与当前实例配置一致
3. 实例绑定到该自定义模板
4. 用户可以选择保持现状，或迁移到标准模板

### 7.2 模板切换

实例可以切换到其他模板：

- 切换时只改变配置和结构定义，不改变已有数据
- 新增的字段默认空值
- 不兼容的字段保留但隐藏
- 提供数据迁移工具，可选执行

---

## 8. API 设计

### 8.1 模板管理 API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/templates` | 列出所有模板 |
| GET | `/api/v1/templates/{code}` | 获取模板详情 |
| POST | `/api/v1/templates` | 创建自定义模板 |
| PUT | `/api/v1/templates/{code}` | 更新模板 |
| DELETE | `/api/v1/templates/{code}` | 删除模板 |
| POST | `/api/v1/templates/{code}/publish` | 发布模板 |
| POST | `/api/v1/templates/{code}/validate` | 验证模板配置 |

### 8.2 实例化 API

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/templates/{code}/instantiate` | 基于模板创建实例 |
| GET | `/api/v1/instances/{code}/template` | 获取实例绑定的模板信息 |
| POST | `/api/v1/instances/{code}/template/upgrade` | 升级实例到新版本模板 |
| POST | `/api/v1/instances/{code}/template/unbind` | 解绑模板（完全自定义） |

---

## 9. 使用示例

### 9.1 CLI 创建实例

```bash
# 列出可用模板
ai-kb template list

# 基于 Bangcle 产品模板创建一个新实例
ai-kb instance create my-product-kb \
  --template bangcle-product-kb \
  --name "我的产品知识库" \
  --description "团队内部产品知识"

# 查看实例信息
ai-kb instance show my-product-kb

# 导入文档
ai-kb ingest scan my-product-kb ./docs/

# 查询
ai-kb query my-product-kb "APP加固的价格是多少"
```

### 9.2 Python SDK 创建实例

```python
from ai_kb import AIKBClient

# 基于模板创建实例
client = AIKBClient.create_instance(
    template_code="bangcle-product-kb",
    instance_code="my-product-kb",
    instance_name="我的产品知识库",
    config_overrides={
        "permissions": {"default_clearance": "confidential"},
        "search": {"default_top_k": 3}
    }
)

# 使用
result = client.query("APP加固支持哪些功能")
print(result.answer)
```


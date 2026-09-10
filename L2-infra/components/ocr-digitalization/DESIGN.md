# OCR 文档数字化组件设计

> L2 基础设施层组件，封装文档数字化能力，为 L3/L4 提供统一的高精度文本识别服务。
>
> **与 Office 文档生成对偶**：一个"读"（OCR）、一个"写"（Office 生成），共同构成文档处理基础设施。

## 1. 定位

| 维度 | 值 |
|---|---|
| 层级 | L2 基础设施层 |
| 组件 ID | OCR-001 |
| 组件名称 | 文档数字化（OCR） |
| 状态 | ✅ v2.0 (2026-09-10) — 从 skill 升级为标准 L2 组件 |
| 实现位置 | `L2-infra/components/ocr-digitalization/` |
| ADR | ADR-202609-023 |
| 调用方式 | Python API / CLI |

**历史演进**：
- v1.0 (2026-09-02)：以 skill 形态实现，双引擎 + 优化管线
- v2.0 (2026-09-10)：升级为标准 L2 组件，规范化 API，新增质量评分、多后端自动发现、批量处理等能力

## 2. 设计约束

1. **文件进文件出**。输入：PDF/图片路径；输出：纯文本 + Markdown + JSON。无外部服务、无状态。
2. **完整适配 OpenClaw**。脚本可被 skill、automation（cron/heartbeat）、agent 直接调用，不依赖特定运行时。
3. **避免耦合**。组件只依赖文件系统 + OCR 引擎库；不感知 L3/L4 业务语义。L4 通过 CLI 或 API 调用。
4. **可回滚**。输出文本独立保存，引擎升级不破坏既有产物。
5. **多引擎不绑定**。引擎可插拔，后端不可用时自动回退。
6. **测试不依赖 OCR 引擎**。核心逻辑用 mock backend 测试，确保 CI 环境零依赖也能跑通。
7. **Skill 层向后兼容**。原 `skills/ocr-digitalization/` 保留为兼容层，旧调用方式不受影响。

## 3. 架构总览

```
┌─────────────────────────────────────────────────────────┐
│                      OCREngine                           │
│                   （统一入口类）                          │
├─────────────┬─────────────┬─────────────┬───────────────┤
│  Preprocess │   Backends  │ Postprocess │   Quality     │
│  预处理流水线 │  多后端引擎  │  后处理管线   │  质量评分系统    │
└─────────────┴─────────────┴─────────────┴───────────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │   Document 层    │
                    │  PDF/批量/多页   │
                    └──────────────────┘
                              │
                              ▼
                   ┌────────────────────┐
                   │   输出格式层        │
                   │ Text / MD / JSON   │
                   └────────────────────┘
```

### 核心设计原则

- **单一入口**：所有能力通过 `OCREngine` 类暴露，调用方只需了解一个 API
- **后端可插拔**：遵循开闭原则，新增后端只需继承 `OCRBackend` 基类并注册
- **配置驱动**：预处理、后处理行为通过配置对象控制，无需改代码
- **质量可量化**：每次识别都输出质量评分，调用方可决定是否需要人工复核
- **渐进降级**：后端一个一个试，总有能用的；预处理一步步减，总能出结果

## 4. 处理管线

```
输入（PDF / 图片）
   │
   ▼
┌─────────────────────────────────┐
│ 1. 格式分发                      │
│    PDF → 尝试原生提取 → 扫描件？  │
│    图片 → 直接进预处理           │
└─────────────────────────────────┘
   │
   ▼
┌─────────────────────────────────┐
│ 2. 图像预处理（可配置开关）      │
│    灰度化 → 去噪 → 倾斜校正      │
│    → 对比度增强 → 锐化 → 二值化   │
│    （5 种预设 + 自定义配置）      │
└─────────────────────────────────┘
   │
   ▼
┌─────────────────────────────────┐
│ 3. 多版本 × 多引擎识别            │
│    8 种预处理版本 × N 个后端     │
│    → 评分选最优（行+置信度+中文比）│
└─────────────────────────────────┘
   │
   ▼
┌─────────────────────────────────┐
│ 4. 后处理                        │
│    阅读排序 → 去重 → 分行合并    │
│    → 领域纠错 → 空行清理         │
└─────────────────────────────────┘
   │
   ▼
┌─────────────────────────────────┐
│ 5. 质量评分                      │
│    置信度 + 清晰度 + 密度 + 布局  │
│    → 综合评分 + A/B/C/D/F 评级   │
└─────────────────────────────────┘
   │
   ▼
输出（Text / Markdown / JSON）
```

## 5. 模块设计

### 5.1 types.py — 数据模型

**职责**：定义所有数据结构，提供序列化/反序列化能力。

**核心类**：
- `OCRLine`：单行结果（text / bbox / confidence / source）
- `OCRPage`：单页结果（lines / size / quality / source）
- `OCRResult`：文档结果（pages / meta / 聚合属性）
- `QualityScore`：质量评分（4 维度 + 综合 + 评级 + details）

**设计要点**：
- 全部用 dataclass，轻量直观
- to_dict / from_dict / to_json / from_json 四件套
- 属性方法（property）提供便捷访问（如 `.confidence` / `.text`）
- 嵌套结构一致序列化

### 5.2 backends/ — 后端引擎层

**职责**：封装不同 OCR 引擎的差异，提供统一接口。

**架构**：
```
OCRBackend (ABC)
├── TesseractBackend     — 系统级引擎
├── RapidOCRBackend      — ONNXRuntime，默认主引擎
├── PaddleOCRBackend     — 高精度补充
└── EasyOCRBackend       — 多语言支持
```

**后端注册表**：
- `register_backend(name)` 装饰器注册
- `get_backend_class(name)` 获取类
- `discover_backends(lang)` 自动发现可用后端（实际加载模型）
- 按 `priority` 属性排序（数值越小越优先）

**设计要点**：
- 延迟加载：实例化不加载模型，`load()` 才加载
- 静默失败：加载失败不抛异常，`available()` 返回 False
- 统一输出格式：`[(bbox, text, confidence), ...]`

### 5.3 preprocess.py — 图像预处理

**职责**：提供可配置的图像预处理流水线。

**处理步骤**（可独立开关）：
1. 放大（upscale）— 低分辨率图先放大
2. 灰度化（grayscale）— 转灰度图
3. 去噪（denoise）— 3 档强度
4. 倾斜校正（deskew）— 投影剖面法找最优角度
5. 对比度增强（contrast）
6. 锐化（sharpen）
7. 二值化（binarize / adaptive_binarize）

**5 种预设**：default / light / strong / photo / fax

**设计要点**：
- 配置驱动：`PreprocessConfig` 控制所有开关和参数
- 多版本生成：`generate_preprocess_variants()` 生成 8 种版本，供多版本投票
- 最小依赖：不依赖 OpenCV，只用 Pillow + NumPy + 可选 SciPy

### 5.4 quality.py — 质量评分

**职责**：对识别结果进行多维度质量评估。

**4 个评估维度**：

| 维度 | 计算方法 | 权重 |
|---|---|---|
| 置信度 | OCR 引擎返回的平均置信度 × 100 | 35% |
| 清晰度 | 拉普拉斯方差 → 对数映射到 0-100 | 25% |
| 文本密度 | 文本覆盖率 → 高斯评分（理想 12%） | 20% |
| 布局完整性 | 垂直覆盖 + 边距 + 行数 + 均匀度 | 20% |

**5 级评级**：A (≥90) / B (75-89) / C (60-74) / D (40-59) / F (<40)

**设计要点**：
- 无图像也能评分（给 clarity 默认值 70）
- 评分可解释：每个维度有明确含义
- details 字段记录原始指标，便于调试

### 5.5 postprocess.py — 后处理

**职责**：对 OCR 原始结果进行清洗、优化和结构化。

**处理管线**：
1. 阅读顺序排序（y 聚类分行 → x 排序）
2. 去重（同 y 坐标 + 高相似度的行合并）
3. 合并分行（启发式判断被拆分的连续文本）
4. 领域纠错（general / contract 两套规则）
5. 噪声字符清洗
6. 空行移除

**设计要点**：
- `PostprocessConfig` 控制每步开关
- 表格检测作为扩展接口（当前返回空，未来接入 PP-Structure）
- 纠错规则可扩展，支持按领域加载

### 5.6 document.py — 文档级处理

**职责**：处理多页文档和批量场景。

**功能**：
- PDF 转图片（3 种后端自动选择：PyMuPDF / pdf2image / macOS sips）
- 原生 PDF 文本提取（优先路径，100% 准确）
- 批量目录处理（递归扫描所有支持的格式）
- 多结果合并

**设计要点**：
- 原生优先策略：非扫描件不走 OCR，又快又准
- 扫描件判定：每页平均 < 50 字符视为扫描件
- PDF 后端降级链：PyMuPDF → pdf2image → sips+PyPDF2

### 5.7 engine.py — OCREngine 主类

**职责**：统一入口，组装所有模块。

**核心 API**：
- `recognize(image)` — 单图识别
- `recognize_batch(paths)` — 批量识别
- `recognize_document(path)` — 文档识别（PDF/图片）

**设计要点**：
- 延迟加载：构造函数不加载后端，第一次识别时才加载
- 多版本投票：`multi_version=True` 时生成 8 种预处理版本分别识别取最优
- 可插拔：preprocess_config / postprocess_config 注入
- 结果一致性：所有输入都返回 `OCRResult`（单图也包装成 1 页）

### 5.8 cli.py — CLI 入口

**职责**：命令行界面。

**设计要点**：
- 子命令式设计，参数清晰
- 静默模式 / 详细模式
- 异常捕获 + 友好错误信息 + 非 0 退出码
- 可作为脚本直接运行，也可 import 调用 main()

## 6. API 设计

### 6.1 核心 API

```python
from ocr_engine import OCREngine

engine = OCREngine(
    backend="auto",              # auto / tesseract / rapidocr / paddleocr / easyocr
    lang="chi_sim+eng",          # 语言代码
    multi_version=True,          # 多版本预处理投票
    quality_analysis=True,       # 质量评分
)

# 单图
result = engine.recognize("page.png", preprocess=True)

# 文档
result = engine.recognize_document("doc.pdf", dpi=300, native_first=True)

# 批量
result = engine.recognize_batch(["p1.png", "p2.png"])

# 输出
result.text                    # 纯文本
result.lines                   # 行列表
result.confidence              # 平均置信度
result.quality_score.overall   # 质量分
result.quality_score.grade     # 评级
result.to_markdown()           # Markdown
result.to_json()               # JSON
```

### 6.2 CLI

```bash
python scripts/ocr_main.py <input> [output] [options]

# 常用选项
-e, --engine      后端引擎
-l, --lang        语言
--dpi             PDF 渲染 DPI
--preset          预处理预设 (default/light/strong/photo/fax)
--correct         纠错领域 (general/contract/none)
-f, --format      输出格式 (text/markdown/json)
--batch           批量模式
--list-backends   列出可用后端
-q, --quiet       静默模式
```

## 7. 测试策略

**原则**：核心逻辑 100% 可测，不依赖实际 OCR 引擎。

**测试分层**：

| 层级 | 测试文件 | 用例数 | 依赖 |
|---|---|---|---|
| 数据模型 | test_01_types.py | ~20 | 无 |
| 后端框架 | test_02_backends.py | ~15 | mock |
| 预处理 | test_03_preprocess.py | ~20 | Pillow + NumPy |
| 质量评分 | test_04_quality.py | ~15 | 无 + 可选 SciPy |
| 后处理 | test_05_postprocess.py | ~20 | 无 |
| 引擎核心 | test_06_engine.py | ~15 | mock |
| CLI | test_07_cli.py | ~8 | mock |

**Mock Backend**：
- Session 级注册，每个测试前重置状态
- 支持配置返回结果 / 模拟加载失败
- 完全可控，测试隔离

**合成测试图片**：
- 纯白图、渐变图、带"文字"的图（用矩形模拟）、噪声图
- 完全确定，不依赖外部资源

## 8. 与 skill 层的兼容方案

**问题**：原 skill 形态（`skills/ocr-digitalization/`）已有调用方，不能直接废弃。

**方案**：保留 skill 目录，改为薄兼容层。

```
skills/ocr-digitalization/
├── SKILL.md                    # 更新：说明已升级为 L2 组件
├── checklists/ocr-quality.md   # 保留（质量检查清单）
└── scripts/
    ├── ocr_engine.py           # 兼容层：转发到 L2 组件
    └── ocr_backends.py         # 兼容层：转发到 L2 组件
```

**兼容层实现要点**：
1. 自动定位 L2 组件路径（支持多种目录布局）
2. 解决模块名冲突（兼容层自己叫 ocr_engine.py，L2 包也叫 ocr_engine）
3. 导出旧 API：`digitalize_document_v5` / `OCRResultV5` / `PageResult` 等
4. 签名/印章检测：已迁移到 contract-approval，兼容层不包含（有说明）

**迁移路径**：
- 短期：兼容层维持，旧代码不改动
- 中期：调用方逐步改为直接引用 L2 组件
- 长期：兼容层标记 deprecated，下个大版本移除

## 9. 依赖关系

### 9.1 Python 依赖

| 库 | 用途 | 必须 |
|---|---|---|
| Pillow | 图像处理 | ✅ |
| NumPy | 数组运算 | ✅ |
| PyMuPDF | PDF 渲染（推荐） | ⚠️ 可选（有降级方案） |
| SciPy | 高级图像处理（倾斜校正、自适应二值化） | ⚠️ 可选（有降级方案） |
| rapidocr-onnxruntime | 主 OCR 引擎 | ⚠️ 可选（4 种后端至少装一个） |
| pytesseract | Tesseract Python 绑定 | ⚠️ 可选 |
| paddleocr + paddlepaddle | 高精度 OCR | ⚠️ 可选 |
| easyocr | 多语言 OCR | ⚠️ 可选 |
| pdf2image | PDF 转图（备选） | ⚠️ 可选 |
| PyPDF2 | PDF 处理（备选） | ⚠️ 可选 |

### 9.2 系统依赖

| 工具 | 用途 | 平台 |
|---|---|---|
| tesseract | OCR 引擎（系统级） | 跨平台 |
| poppler | PDF→图片（pdf2image 依赖） | 跨平台 |
| sips | PDF→图片 | macOS（自带） |

**最小可用组合**：Pillow + NumPy + Tesseract（系统级）
**推荐组合**：Pillow + NumPy + PyMuPDF + RapidOCR + SciPy

## 10. 验证标准

### v2.0 升级验证清单

- ✅ L2 ocr-digitalization 组件独立目录，结构清晰
- ✅ 8 个核心模块全部实现（engine/types/backends/preprocess/quality/postprocess/document/cli）
- ✅ 多后端架构 + 自动发现 + 优先级排序
- ✅ OCREngine 统一 API 完整，类型注解齐全
- ✅ 113 个测试全部通过（mock backend，不依赖实际 OCR 引擎）
- ✅ 原 skill 层向后兼容（import 路径不报错，旧 API 可用）
- ✅ 文档齐全（README + DESIGN + 架构文档更新）
- ✅ 原有功能不丢失（预处理、多引擎、纠错、PDF 处理等）

### 功能验证标准（需真实引擎）

1. **完整覆盖**：合同扫描件 10 页，逐页识别无缺失
2. **关键字段准确**：甲方名称、金额、日期等关键信息识别正确
3. **版面可读**：段落顺序正确，无乱序
4. **纠错生效**：已知错误模式被纠正
5. **多引擎回退**：主引擎不可用时，备用引擎可完成识别
6. **质量评分合理**：高质量图片得 A/B，低质量图片得 C/D

## 11. 演进方向

| 版本 | 功能 | 优先级 |
|---|---|---|
| v2.1 | 表格结构还原（PP-Structure 接入） | 高 |
| v2.2 | 版面分析（标题/段落/列表/图片识别） | 高 |
| v2.3 | 印章遮挡文字恢复（图像修复） | 中 |
| v2.4 | 版式还原输出（HTML / 结构化 Markdown） | 中 |
| v2.5 | 手写体识别支持 | 低 |
| v3.0 | 分布式批处理 + 进度报告 | 低 |

## 12. 变更历史

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-09-02 | v1.0 | 组件创建（skill 形态），双引擎 + 优化管线 |
| 2026-09-10 | v2.0 | 升级为标准 L2 组件；规范化 API；新增质量评分/多后端发现/批量处理；113 个测试 |

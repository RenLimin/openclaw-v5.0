# ocr-digitalization — OCR 文档数字化组件

> L2 基础设施层 · 通用 OCR 能力组件
>
> **组件 ID**: OCR-001 · **状态**: ✅ 生产就绪

## 1. 定位

| 维度 | 值 |
|---|---|
| 层级 | L2 基础设施层 |
| 类型 | 基础能力组件 |
| 职责 | 图像 / PDF → 结构化文本（多后端、高质量、可配置） |
| 下游依赖 | Pillow / NumPy / OCR 引擎（RapidOCR / PaddleOCR / Tesseract / EasyOCR） |
| 上游调用方 | contract-approval（L4）、knowledge-base（L3）、ocr-digitalization skill |

## 2. 功能特性

### 核心能力
- ✅ **多后端架构**：Tesseract / RapidOCR / PaddleOCR / EasyOCR，自动发现 + 自动选优
- ✅ **预处理流水线**：灰度化 / 二值化（全局+自适应）/ 去噪 / 倾斜校正 / 对比度增强 / 锐化 / 放大
- ✅ **多版本预处理投票**：8 种预处理版本 × 多引擎，取最优结果
- ✅ **质量评分系统**：置信度 + 清晰度 + 文本密度 + 布局完整性，A/B/C/D/F 五级评级
- ✅ **后处理管线**：行排序 / 去重 / 分行合并 / 合同场景 40+ 规则纠错 / 表格结构检测
- ✅ **原生 PDF 优先**：非扫描件 PDF 直接提取文本（100% 准确，零 OCR 成本）
- ✅ **多格式输出**：纯文本 / Markdown / JSON / 行级结构化数据
- ✅ **批量处理**：单目录递归扫描，支持所有常见图片格式 + PDF
- ✅ **CLI 工具**：命令行直接调用，支持所有配置选项

### 5 种预处理预设
| 预设 | 适用场景 |
|---|---|
| `default` | 默认，通用场景 |
| `light` | 轻度处理，高清扫描件 |
| `strong` | 强力处理，低质量扫描件 / 传真 |
| `photo` | 拍照文档（手机拍摄） |
| `fax` | 传真 / 极低质量文档 |

## 3. 快速开始

### 安装依赖

```bash
# 必选依赖
pip install pillow numpy pymupdf

# 安装至少一个 OCR 引擎（推荐 RapidOCR）
pip install rapidocr-onnxruntime          # 推荐：轻量、快速、中文不错
# 或
brew install tesseract tesseract-lang    # 系统级，macOS
pip install pytesseract
# 或
pip install paddleocr paddlepaddle       # 高精度（安装较重）
# 或
pip install easyocr                      # 80+ 语言支持
```

### 命令行使用

```bash
# 最简用法
python scripts/ocr_main.py input.pdf output.md

# 指定引擎 + 语言 + DPI
python scripts/ocr_main.py scan.jpg output.md \
    --engine rapidocr \
    --lang chi_sim+eng \
    --dpi 300

# 强力预处理（低质量扫描件）
python scripts/ocr_main.py fax.pdf output.md --preset strong

# 批量处理目录
python scripts/ocr_main.py ./scans/ --batch -o ./ocr_output/

# JSON 输出
python scripts/ocr_main.py scan.jpg --json result.json

# 列出可用后端
python scripts/ocr_main.py --list-backends
```

### Python API

```python
import sys
sys.path.insert(0, "L2-infra/components/ocr-digitalization/scripts")

from ocr_engine import OCREngine

# 初始化引擎
engine = OCREngine(
    backend="auto",           # auto / tesseract / rapidocr / paddleocr / easyocr
    lang="chi_sim+eng",       # 语言
    multi_version=True,       # 多版本预处理投票（更准但更慢）
    quality_analysis=True,    # 质量评分分析
)

# 单图识别
result = engine.recognize("page.png", preprocess=True)

# PDF / 文档识别
result = engine.recognize_document("contract.pdf", dpi=300)

# 批量识别
result = engine.recognize_batch(["p1.png", "p2.png", "p3.png"])

# 访问结果
result.text                     # 纯文本全文
result.lines                    # 所有行（OCRLine 列表）
result.confidence               # 平均置信度（0-1）
result.quality_score.overall    # 综合质量分（0-100）
result.quality_score.grade      # 质量评级（A/B/C/D/F）

# 导出
result.to_text()                # 纯文本
result.to_markdown()            # Markdown
result.to_json()                # JSON
result.to_dict()                # Python dict
```

## 4. API 参考

### OCREngine

```python
class OCREngine:
    def __init__(
        self,
        backend: str = "auto",
        lang: str = "chi_sim+eng",
        preprocess_config: PreprocessConfig | None = None,
        postprocess_config: PostprocessConfig | None = None,
        multi_version: bool = True,
        quality_analysis: bool = True,
    )

    def recognize(self, image: str | Image.Image, preprocess: bool = True) -> OCRResult
    def recognize_batch(self, image_paths: list[str], preprocess: bool = True) -> OCRResult
    def recognize_document(self, doc_path: str, dpi: int = 300, native_first: bool = True, preprocess: bool = True) -> OCRResult

    @property
    def available_backends: list[str]
    def get_backend_info(self) -> list[dict]
    def load(self) -> "OCREngine"
```

### OCRResult

```python
@dataclass
class OCRResult:
    pages: list[OCRPage]
    meta: dict

    # 属性
    @property text: str               # 纯文本全文
    @property lines: list[OCRLine]    # 所有行（扁平化）
    @property confidence: float       # 平均置信度
    @property quality_score: QualityScore  # 综合质量评分
    @property total_pages: int
    @property total_lines: int
    @property total_chars: int

    # 导出
    def to_text(self) -> str
    def to_markdown(self) -> str
    def to_json(self, indent: int = 2) -> str
    def to_dict(self) -> dict
```

### OCRLine

```python
@dataclass
class OCRLine:
    text: str
    bbox: tuple[float, float, float, float]  # (x1, y1, x2, y2)
    confidence: float = 0.9
    source: str = "ocr"     # ocr / native / corrected / merged

    @property x1, y1, x2, y2: float
    @property width, height: float
```

### QualityScore

```python
@dataclass
class QualityScore:
    overall: float              # 综合得分 0-100
    confidence: float           # 置信度得分
    clarity: float              # 清晰度得分
    text_density: float         # 文本密度得分
    layout_completeness: float  # 布局完整性得分
    details: dict               # 详细指标

    @property grade: str        # A / B / C / D / F
```

## 5. 目录结构

```
ocr-digitalization/
├── scripts/
│   ├── ocr_main.py              # CLI 入口
│   └── ocr_engine/              # 核心包
│       ├── __init__.py          # 包导出
│       ├── engine.py            # OCREngine 主类
│       ├── types.py             # 数据模型
│       ├── preprocess.py        # 图像预处理
│       ├── postprocess.py       # 后处理（排序/纠错/去重/表格）
│       ├── quality.py           # 质量评分
│       ├── document.py          # 文档级处理（PDF/批量）
│       ├── cli.py               # CLI 实现
│       └── backends/            # OCR 后端引擎
│           ├── __init__.py      # 后端注册与发现
│           ├── base.py          # 抽象基类
│           ├── tesseract.py     # Tesseract 后端
│           ├── rapidocr.py      # RapidOCR 后端
│           ├── paddleocr.py     # PaddleOCR 后端
│           └── easyocr.py       # EasyOCR 后端
├── tests/                       # 测试套件（113 个用例）
│   ├── conftest.py
│   ├── test_01_types.py
│   ├── test_02_backends.py
│   ├── test_03_preprocess.py
│   ├── test_04_quality.py
│   ├── test_05_postprocess.py
│   ├── test_06_engine.py
│   └── test_07_cli.py
├── README.md                    # 本文档
└── DESIGN.md                    # 架构设计文档
```

## 6. 测试

```bash
# 运行所有测试
python3 -m pytest L2-infra/components/ocr-digitalization/tests/ -v

# 运行特定模块测试
python3 -m pytest L2-infra/components/ocr-digitalization/tests/test_03_preprocess.py -v
```

测试使用 **mock backend**，不依赖实际 OCR 引擎安装。覆盖 7 大模块、113 个用例：
- 数据模型序列化/反序列化
- 后端注册/发现/优先级
- 图像预处理（8 种操作 + 5 种预设 + 完整流水线）
- 质量评分（4 维度 + 综合评级）
- 后处理（排序/去重/纠错/合并/表格）
- 引擎核心（单图/批量/输出格式）
- CLI（帮助/错误处理/基本功能）

## 7. 后端安装指南

| 后端 | 安装方式 | 中文精度 | 速度 | 依赖大小 | 推荐度 |
|---|---|---|---|---|---|
| **RapidOCR** | `pip install rapidocr-onnxruntime` | ⭐⭐⭐⭐ | 快 (~2s/页) | 小 | ⭐⭐⭐⭐⭐ |
| **PaddleOCR** | `pip install paddleocr paddlepaddle` | ⭐⭐⭐⭐⭐ | 中 (~5s/页) | 大 | ⭐⭐⭐⭐ |
| **Tesseract** | `brew install tesseract tesseract-lang` | ⭐⭐⭐ | 中 | 系统级 | ⭐⭐⭐ |
| **EasyOCR** | `pip install easyocr` | ⭐⭐⭐⭐ | 慢 (~10s/页) | 大 | ⭐⭐⭐ |

**引擎选择建议**：
- 默认用 RapidOCR（性价比最高）
- 高精度场景用 PaddleOCR
- 不想装 Python 包用 Tesseract（系统级）
- 多语言混合场景用 EasyOCR

`backend="auto"` 时按优先级自动选择可用的后端。

## 8. 质量评分体系

| 维度 | 权重 | 说明 |
|---|---|---|
| 置信度 (confidence) | 35% | OCR 引擎返回的平均置信度 |
| 清晰度 (clarity) | 25% | 基于拉普拉斯方差的图像清晰度 |
| 文本密度 (text_density) | 20% | 文本覆盖率是否在合理范围 |
| 布局完整性 (layout_completeness) | 20% | 文本分布均匀度 + 页数合理性 |

**评级标准**:
- ✅ **A 级** (≥90): 高质量，可直接使用
- ⭕ **B 级** (75-89): 良好，关键字段可信赖
- ⚠️ **C 级** (60-74): 一般，建议人工复核关键内容
- ❌ **D 级** (40-59): 较差，建议重新扫描
- 💀 **F 级** (<40): 不可用

## 9. 与其他组件的关系

| 组件 | 关系 | 说明 |
|---|---|---|
| `contract-approval` (L4) | 上游调用方 | 合同审批的扫描件数字化环节 |
| `knowledge-base` (L3) | 上游调用方 | 扫描件资料导入知识库 |
| `office-generation` (L2) | 对偶组件 | 一个"读"（OCR）、一个"写"（Office 生成） |
| `ocr-digitalization skill` | 兼容层 | skill 形态的调用入口，底层转发到本组件 |

## 10. 演进方向

1. **表格结构还原**：接入 PP-Structure，识别表格行列并输出结构化数据
2. **版面分析**：识别标题、段落、列表、图片，还原文档结构
3. **印章遮挡恢复**：图像修复技术恢复被印章覆盖的文字
4. **版面还原输出**：HTML / Markdown 近似原文排版
5. **手写体识别**：支持手写签名 / 手写批注的识别

## 11. 相关文档

- 架构设计：[DESIGN.md](./DESIGN.md)
- ADR：[ADR-202609-023](../../docs/architecture/components/ocr-digitalization/ADR-202609-023-ocr-digitalization.md)
- 质量检查清单：[../../../../skills/ocr-digitalization/checklists/ocr-quality.md](../../../../skills/ocr-digitalization/checklists/ocr-quality.md)

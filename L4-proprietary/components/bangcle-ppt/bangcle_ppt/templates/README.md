# 模板目录索引

> 34 个预置模板（浅色 19 + 深色 15），全部基于梆梆安全官方 VI 规范设计。

## 目录结构

```
templates/
├── shared/
│   └── variables.yaml      # 共享设计变量（颜色/字体/品牌）
├── light/                  # 浅色模板（19 个）
│   ├── cover-light.yaml
│   ├── toc-light.yaml
│   ├── section-light.yaml
│   ├── section-light-02.yaml
│   ├── section-light-03.yaml
│   ├── section-light-04.yaml
│   ├── content-two-col-light.yaml
│   ├── content-three-cards-light.yaml
│   ├── timeline-three-cards-light.yaml
│   ├── data-chart-light.yaml
│   ├── timeline-vertical-light.yaml
│   ├── radial-structure-light.yaml
│   ├── phase-timeline-light.yaml
│   ├── team-cards-light.yaml
│   ├── list-light.yaml
│   ├── text-only-light.yaml
│   ├── kpi-cards-light.yaml
│   ├── table-light.yaml
│   ├── flow-light.yaml
│   ├── blank-light.yaml
│   └── closing-light.yaml
└── dark/                   # 深色模板（15 个）
    ├── cover-dark.yaml
    ├── toc-dark.yaml
    ├── section-dark.yaml
    ├── section-dark-02.yaml
    ├── node-graph-dark.yaml
    ├── four-cards-dark.yaml
    ├── list-image-dark.yaml
    ├── honeycomb-dark.yaml
    ├── pyramid-compare-dark.yaml
    ├── phase-timeline-dark.yaml
    ├── text-only-dark.yaml
    ├── table-dark.yaml
    ├── kpi-cards-light.yaml  # 复用浅色渲染器
    ├── blank-dark.yaml       # 复用浅色渲染器
    └── closing-dark.yaml
```

## 浅色模板索引

| 文件名 | page_type | 类型 | 说明 |
|--------|-----------|------|------|
| `cover-light.yaml` | `cover-light` | 封面 | 左侧竖条 + 汇报人信息 |
| `toc-light.yaml` | `toc-light` | 目录 | 2×2 卡片式目录 |
| `section-light.yaml` | `section-light` | 章节 | 第一章过渡页 |
| `section-light-02.yaml` | `section-light` | 章节 | 第二章过渡页 |
| `section-light-03.yaml` | `section-light` | 章节 | 第三章过渡页 |
| `section-light-04.yaml` | `section-light` | 章节 | 第四章过渡页 |
| `content-two-col-light.yaml` | `content-two-col-light` | 内容 | 左文右图 + 4 要点 |
| `content-three-cards-light.yaml` | `content-three-cards-light` | 内容 | 横幅图 + 三浮动卡片 |
| `timeline-three-cards-light.yaml` | `timeline-three-cards-light` | 时间轴 | 横向时间轴 + 三卡片 |
| `data-chart-light.yaml` | `data-chart-light` | 数据 | 4 KPI + 图表 + 说明 |
| `timeline-vertical-light.yaml` | `timeline-vertical-light` | 时间轴 | 纵向时间线 + 右侧配图 |
| `radial-structure-light.yaml` | `radial-structure-light` | 架构 | 中心圆 + 放射 6 节点 |
| `phase-timeline-light.yaml` | `phase-timeline-light` | 时间轴 | 上下交错 6 阶段 |
| `team-cards-light.yaml` | `team-cards-light` | 团队 | 4 列人物介绍卡片 |
| `list-light.yaml` | `list-light` | 内容 | 编号/要点列表 |
| `text-only-light.yaml` | `text-only-light` | 内容 | 大段文字/引文 |
| `kpi-cards-light.yaml` | `kpi-cards-light` | 数据 | 4 个 KPI 大卡片 |
| `table-light.yaml` | `table-light` | 数据 | 数据表格 |
| `flow-light.yaml` | `flow-light` | 流程 | 5 步流程图 |
| `blank-light.yaml` | `blank-light` | 通用 | 自由排版空白页 |
| `closing-light.yaml` | `closing-light` | 结尾 | 谢谢观看 + 二维码 |

## 深色模板索引

| 文件名 | page_type | 类型 | 说明 |
|--------|-----------|------|------|
| `cover-dark.yaml` | `cover-dark` | 封面 | 大标题 + 分割线 |
| `toc-dark.yaml` | `toc-dark` | 目录 | 圆形数字编号列表 |
| `section-dark.yaml` | `section-dark` | 章节 | 第一章（大数字） |
| `section-dark-02.yaml` | `section-dark` | 章节 | 第二章 |
| `node-graph-dark.yaml` | `node-graph-dark` | 架构 | 中心 + 4 节点关系图 |
| `four-cards-dark.yaml` | `four-cards-dark` | 内容 | 4 卡片 + 数据区 |
| `list-image-dark.yaml` | `list-image-dark` | 内容 | 左图 + 右特性列表 |
| `honeycomb-dark.yaml` | `honeycomb-dark` | 架构 | 蜂巢/六边形矩阵 |
| `pyramid-compare-dark.yaml` | `pyramid-compare-dark` | 架构 | 金字塔 + 对比卡片 |
| `phase-timeline-dark.yaml` | `phase-timeline-dark` | 时间轴 | 6 阶段路线图（深色） |
| `text-only-dark.yaml` | `text-only-light` | 内容 | 纯文字说明 |
| `table-dark.yaml` | `table-light` | 数据 | 数据表格 |
| `kpi-cards-light.yaml` | `kpi-cards-light` | 数据 | KPI 指标卡片 |
| `blank-dark.yaml` | `blank-light` | 通用 | 自由排版 |
| `closing-dark.yaml` | `closing-dark` | 结尾 | 谢谢观看 |

## 模板 YAML 格式

每个模板文件包含三部分：

```yaml
meta:           # 元数据
  name: 模板名称
  page_type: cover-light    # 对应渲染器类型
  theme: light              # light / dark
  description: 模板说明
  version: "1.0.0"
  category: 分类

layout:       # 布局配置（与 page_type 对应的 Layout Schema 一致）
  show_logo: true
  # ... 更多布局选项

data:         # 示例数据（用于预览/测试）
  title: 示例标题
  presenter: 张三
  # ... 更多内容数据
```

## 自定义模板

1. 复制现有模板 YAML 作为起点
2. 修改 `meta` 元数据
3. 调整 `layout` 布局选项
4. 填入 `data` 默认数据
5. 保存到对应主题目录下
6. 运行测试校验：`python -m pytest tests/test_templates.py`

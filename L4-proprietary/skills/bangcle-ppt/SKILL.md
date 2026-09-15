---
name: bangcle-ppt
description: "Bangcle PPT 模板系统，提供梆梆安全官方 VI 规范的 PPT 生成能力"
homepage:
metadata:
  {
    "openclaw":
      {
        "emoji": "📊",
        "os": ["darwin", "linux"],
        "requires": { "components": ["pptxgenjs-pro (L2)"], "npm": ["pptx-automizer", "pptxgenjs"] },
        "layer": "L4",
        "component_id": "CPT-012",
      },
  }
---

# Bangcle PPT 模板系统

梆梆安全官方 PPT 设计系统，基于 `pptx-automizer` 和 `pptxgenjs` 提供符合 Bangcle VI 规范的 PPT 生成能力。

## 设计规范

完整设计规范文档: `docs/architecture/components/bangcle-ppt-template/DESIGN.md`

### 快速参考

**主色**: `#2D74BB`（梆梆蓝）
**背景**: 浅色 `#FFFFFF` / 深色 `#00122B`
**字体**: 思源黑体 Heavy/Medium， fallback Microsoft YaHei
**画布尺寸**: 13.33" × 7.5"（16:9）

## 使用方式

### 1. 基于现有模板修改（推荐）

使用 `pptx-automizer` 对现有 PPT 进行批量修改、布局调整、元素删除等操作。示例脚本:

```javascript
const { Automizer, modify } = require('pptx-automizer');
const path = require('path');

const automizer = new Automizer({
  templateDir: './templates',
  outputDir: './output',
  removeExistingSlides: true,
});

let pres = automizer.loadRoot('input.pptx').load('input.pptx', 'src');

// 添加并修改幻灯片
pres.addSlide('src', 1); // 保留第1页原样
pres.addSlide('src', 2, (slide) => {
  // 修改元素位置和大小
  slide.modifyElement({ name: 'Shape 49', nameIdx: 0 }, [
    modify.setPosition({ left: 600000, top: 1800000, width: 1600000, height: 4500000 })
  ]);
  // 删除不需要的元素
  slide.removeElement('图片 1');
  console.log('✅ 第2页修改完成');
});

pres.write('output.pptx').then(summary => {
  console.log('\n✅ 已保存:', JSON.stringify(summary));
});
```

### 2. 从零生成新 PPT

使用 `pptxgenjs` 配合本组件提供的设计常量和页面模板生成全新 PPT。

```javascript
const pptxgen = require('pptxgenjs');
const { colors, fonts, sizes } = require('./src/design-constants');

let pres = new pptxgen();
pres.layout = pptxgen.layout['16x9'];

// 添加封面页
const slide = pres.addSlide();
slide.background = { color: colors.bg.light };
// 添加主标题
slide.addText("项目汇报", {
  x: sizes.titleLeft, y: sizes.titleTop,
  w: 8, h: 0.8,
  fontFace: fonts.family,
  fontSize: fonts.size.h1,
  color: colors.title.light,
  bold: fonts.weight.heavy
});

pres.writeFile("output.pptx");
```

## 目录结构

```
skills/bangcle-ppt/
├── SKILL.md          # 本文件
├── src/
│   └── design-constants.js # 色彩、字体、尺寸常量
├── scripts/          # 常用自动化脚本
└── templates/        # 模板占位
```

## 依赖

- L2 组件: `pptxgenjs-pro` (CPT-004)
- npm 包: `pptx-automizer`, `pptxgenjs`

## 示例

已有的自动化修改示例: `L4-proprietary/components/bangcle-ppt/pptx-automizer/build_final.cjs`

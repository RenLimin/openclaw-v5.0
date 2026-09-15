const { Automizer, modify } = require('pptx-automizer');
const path = require('path');
const os = require('os');

const srcDir = path.join(os.homedir(), 'Downloads/XSZS2608190616-WXB北京分中心');
const srcFile = '北京分中心二期项目启动会v1.1.pptx';
const outFile = '北京分中心二期项目启动会v1.2.pptx';

const automizer = new Automizer({
  templateDir: srcDir,
  outputDir: srcDir,
  removeExistingSlides: true,
  verbosity: 0,
  continueOnError: true,
});

let pres = automizer.loadRoot(srcFile).load(srcFile, 'src');

// ============================================================
// 第1页：保持原样（封面）
// ============================================================
pres.addSlide('src', 1);

// ============================================================
// 第2页：项目一期/二期 纵向三栏 → 横向三栏
// ============================================================
pres.addSlide('src', 2, (slide) => {
  // --- 项目一期 (nameIdx=0) ---
  // Shape 49(合同金额白色条): (669290,1828800,1243330,4572000) → 加宽
  slide.modifyElement({ name: 'Shape 49', nameIdx: 0 }, [modify.setPosition({ left: 600000, top: 1800000, width: 1600000, height: 4500000 })]);
  // Shape 60(交付内容白色条): (2054860,1839596,1676400,4572000)
  slide.modifyElement({ name: 'Shape 60', nameIdx: 0 }, [modify.setPosition({ left: 2350000, top: 1800000, width: 1600000, height: 4500000 })]);
  // Shape 73(项目目标白色条): (3888740,1828800,1567180,4572000)
  slide.modifyElement({ name: 'Shape 73', nameIdx: 0 }, [modify.setPosition({ left: 4100000, top: 1800000, width: 1600000, height: 4500000 })]);
  
  // TextBox 0(合同金额内容): (784860,2522854,1127760,3234690)
  slide.modifyElement({ name: 'TextBox', nameIdx: 0 }, [modify.setPosition({ left: 650000, top: 2000000, width: 1500000, height: 3000000 })]);
  // TextBox 1(交付内容): (2077720,2260600,1468120,3054350)
  slide.modifyElement({ name: 'TextBox', nameIdx: 1 }, [modify.setPosition({ left: 2400000, top: 2000000, width: 1500000, height: 3000000 })]);
  // TextBox 2(项目目标): (3881120,2260600,1473200,1270000)
  slide.modifyElement({ name: 'TextBox', nameIdx: 2 }, [modify.setPosition({ left: 4150000, top: 2000000, width: 1500000, height: 1200000 })]);
  
  // --- 项目二期 (nameIdx=1) ---
  // Shape 49(合同金额): (6565900,1899285,1143000,1828800)
  slide.modifyElement({ name: 'Shape 49', nameIdx: 1 }, [modify.setPosition({ left: 6500000, top: 1850000, width: 1600000, height: 4500000 })]);
  // Shape 60(交付内容): (7835900,1899285,1676400,1828800)
  slide.modifyElement({ name: 'Shape 60', nameIdx: 1 }, [modify.setPosition({ left: 8250000, top: 1850000, width: 1600000, height: 4500000 })]);
  // Shape 73(项目目标): (9639300,1899285,1676400,1828800)
  slide.modifyElement({ name: 'Shape 73', nameIdx: 1 }, [modify.setPosition({ left: 10000000, top: 1850000, width: 1600000, height: 4500000 })]);
  
  // TextBox 3(二期合同金额): (6667500,2331085,939800,1270000)
  slide.modifyElement({ name: 'TextBox', nameIdx: 3 }, [modify.setPosition({ left: 6550000, top: 2000000, width: 1500000, height: 1200000 })]);
  // TextBox 4(二期交付内容): (7937500,2331085,1473200,1270000)
  slide.modifyElement({ name: 'TextBox', nameIdx: 4 }, [modify.setPosition({ left: 8300000, top: 2000000, width: 1500000, height: 1200000 })]);
  // TextBox 5(二期项目目标): (9740900,2331085,1473200,1270000)
  slide.modifyElement({ name: 'TextBox', nameIdx: 5 }, [modify.setPosition({ left: 10050000, top: 2000000, width: 1500000, height: 1200000 })]);
  
  // 标签也加宽
  // Text 52(合同金额标签) nameIdx=0: (1010920,2006599,901700,197485)
  slide.modifyElement({ name: 'Text 52', nameIdx: 0 }, [modify.setPosition({ left: 1010920, top: 2006599, width: 1400000, height: 197485 })]);
  // Text 63(交付内容标签) nameIdx=0: (2319020,2006600,1270000,177800)
  slide.modifyElement({ name: 'Text 63', nameIdx: 0 }, [modify.setPosition({ left: 2500000, top: 2006600, width: 1400000, height: 177800 })]);
  // Text 76(项目目标标签) nameIdx=0: (4122420,2006600,1270000,177800)
  slide.modifyElement({ name: 'Text 76', nameIdx: 0 }, [modify.setPosition({ left: 4200000, top: 2006600, width: 1400000, height: 177800 })]);
  // 二期标签
  slide.modifyElement({ name: 'Text 52', nameIdx: 1 }, [modify.setPosition({ left: 6900000, top: 2077085, width: 1400000, height: 177800 })]);
  slide.modifyElement({ name: 'Text 63', nameIdx: 1 }, [modify.setPosition({ left: 8400000, top: 2077085, width: 1400000, height: 177800 })]);
  slide.modifyElement({ name: 'Text 76', nameIdx: 1 }, [modify.setPosition({ left: 10100000, top: 2077085, width: 1400000, height: 177800 })]);
  
  console.log('✅ 第2页：纵向→横向');
});

// ============================================================
// 第3页：删除图片，保留标题
// ============================================================
pres.addSlide('src', 3, (slide) => {
  slide.removeElement('图片 1');
  console.log('✅ 第3页：图片已删除');
});

// ============================================================
// 第4页：核心需求 — 8条目拉大
// ============================================================
pres.addSlide('src', 4, (slide) => {
  // 8个条目，每个由 Shape N(背景) + Shape N+1(左色条) + emoji + 标题 + 描述 组成
  // 行1: Shape 8/9, 14/15 (y=2571115, h=554355)
  // 行2: Shape 20/21, 26/27 (y=3216910)
  // 行3: Shape 32/33, 38/39 (y=3862705)
  // 行4: Shape 44/45, 50/51 (y=4508500)
  
  const items = [
    { bg: 8, bar: 9, top: 2571115 },
    { bg: 14, bar: 15, top: 2571115 },
    { bg: 20, bar: 21, top: 3216910 },
    { bg: 26, bar: 27, top: 3216910 },
    { bg: 32, bar: 33, top: 3862705 },
    { bg: 38, bar: 39, top: 3862705 },
    { bg: 44, bar: 45, top: 4508500 },
    { bg: 50, bar: 51, top: 4508500 },
  ];
  
  for (const item of items) {
    // 背景卡片：从 2720340 加宽到 5600000，高度从 554355 加到 700000
    slide.modifyElement(`Shape ${item.bg}`, [modify.setPosition({ left: 400000, top: item.top - 50000, width: 5600000, height: 700000 })]);
    // 左侧色条高度同步
    slide.modifyElement(`Shape ${item.bar}`, [modify.setPosition({ left: 400000, top: item.top - 50000, width: 45720, height: 700000 })]);
  }
  
  // 文字加宽：Text 12,18,24,30,36,42,48,54 (标题) 和 Text 13,19,25,31,37,43,49,55 (描述)
  const textTitles = [12, 18, 24, 30, 36, 42, 48, 54];
  const textDescs = [13, 19, 25, 31, 37, 43, 49, 55];
  for (const t of textTitles) {
    try {
      slide.modifyElement(`Text ${t}`, [modify.setPosition({ left: 1313815, width: 4000000 })]);
    } catch(e) {}
  }
  for (const t of textDescs) {
    try {
      slide.modifyElement(`Text ${t}`, [modify.setPosition({ left: 1313815, width: 4000000 })]);
    } catch(e) {}
  }
  
  console.log('✅ 第4页：布局拉大');
});

// ============================================================
// 第5页：重点问题 — 三栏拉大
// ============================================================
pres.addSlide('src', 5, (slide) => {
  // 三个卡片：Shape 3(左), Shape 19(中), Shape 32(右)
  // 每个 3454400 宽 → 加宽到 3700000
  slide.modifyElement('Shape 3', [modify.setPosition({ left: 400000, top: 1767840, width: 3700000, height: 3627120 })]);
  slide.modifyElement('Shape 4', [modify.setPosition({ left: 400000, top: 1767840, width: 3700000, height: 670560 })]);
  slide.modifyElement('Shape 19', [modify.setPosition({ left: 4000000, top: 1767840, width: 3700000, height: 3627120 })]);
  slide.modifyElement('Shape 20', [modify.setPosition({ left: 4000000, top: 1767840, width: 3700000, height: 670560 })]);
  slide.modifyElement('Shape 32', [modify.setPosition({ left: 7600000, top: 1767840, width: 3700000, height: 3627120 })]);
  slide.modifyElement('Shape 33', [modify.setPosition({ left: 7600000, top: 1767840, width: 3700000, height: 670560 })]);
  
  console.log('✅ 第5页：三栏拉大');
});

// ============================================================
// 第6页：业务重点 — 两栏拉大
// ============================================================
pres.addSlide('src', 6, (slide) => {
  // 两个卡片：Shape 3(左), Shape 20(右)
  slide.modifyElement('Shape 3', [modify.setPosition({ left: 400000, top: 1767840, width: 5600000, height: 3627120 })]);
  slide.modifyElement('Shape 4', [modify.setPosition({ left: 400000, top: 1767840, width: 121920, height: 3627120 })]);
  slide.modifyElement('Shape 20', [modify.setPosition({ left: 6100000, top: 1767840, width: 5600000, height: 3627120 })]);
  slide.modifyElement('Shape 21', [modify.setPosition({ left: 6100000, top: 1767840, width: 121920, height: 3627120 })]);
  
  console.log('✅ 第6页：两栏拉大');
});

// ============================================================
// 第7页：删除（不添加）
// ============================================================

// ============================================================
// 第8页：整体方案 — 建设路径移到最后
// ============================================================
pres.addSlide('src', 8, (slide) => {
  // 当前布局：2x2 网格
  // 左上(建设思路): Shape 6(328183,1611014,4561744,1526051)
  // 右上(智能监测): Shape 45(5026008,1221297,6834412,2075758)
  // 左下(建设路径): Shape 19(332285,3235521,4553540,2243950)
  // 右下(人工驻场): Shape 89(5026008,3403714,6834412,2075758)
  // 底部(服务价值): Shape 117(328183,5582029,11535634,1214277)
  
  // 新布局：全宽竖排
  // 1. 建设思路 — 全宽
  slide.modifyElement('Shape 6', [modify.setPosition({ left: 400000, top: 1300000, width: 11000000, height: 1200000 })]);
  // 2. 智能监测平台 — 全宽
  slide.modifyElement('Shape 45', [modify.setPosition({ left: 400000, top: 2600000, width: 11000000, height: 1800000 })]);
  // 3. 人工驻场 — 全宽
  slide.modifyElement('Shape 89', [modify.setPosition({ left: 400000, top: 4500000, width: 11000000, height: 1200000 })]);
  // 4. 建设路径 — 移到最后（在人工驻场下方）
  slide.modifyElement('Shape 19', [modify.setPosition({ left: 400000, top: 5800000, width: 11000000, height: 800000 })]);
  // 5. 服务价值 — 保持底部
  slide.modifyElement('Shape 117', [modify.setPosition({ left: 400000, top: 6700000, width: 11000000, height: 1000000 })]);
  
  console.log('✅ 第8页：建设路径移后');
});

// ============================================================
// 第9页：保持原样
// ============================================================
pres.addSlide('src', 9);

pres.write(outFile).then(summary => {
  console.log('\n✅ 已保存:', JSON.stringify(summary));
}).catch(err => {
  console.error('❌ 错误:', err.message);
});

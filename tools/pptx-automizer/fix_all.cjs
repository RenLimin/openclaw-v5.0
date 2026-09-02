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

let pres = automizer
  .loadRoot(srcFile)
  .load(srcFile, 'src');

// === 第1页：保持原样 ===
pres.addSlide('src', 1);

// === 第2页：纵向改横向 ===
pres.addSlide('src', 2, (slide) => {
  // 项目一期：3个竖长条改横向
  // Shape 49(合同金额): 原始(669290,1828800,1243330,4572000)
  slide.modifyElement({ name: 'Shape 49', nameIdx: 0 }, [
    modify.setPosition({ left: 600000, top: 1800000, width: 1600000, height: 4500000 })
  ]);
  // Shape 60(交付内容): 原始(2054860,1839596,1676400,4572000)
  slide.modifyElement({ name: 'Shape 60', nameIdx: 0 }, [
    modify.setPosition({ left: 2350000, top: 1800000, width: 1600000, height: 4500000 })
  ]);
  // Shape 73(项目目标): 原始(3888740,1828800,1567180,4572000)
  slide.modifyElement({ name: 'Shape 73', nameIdx: 0 }, [
    modify.setPosition({ left: 4100000, top: 1800000, width: 1600000, height: 4500000 })
  ]);
  
  // 一期 TextBox
  slide.modifyElement({ name: 'TextBox', nameIdx: 0 }, [
    modify.setPosition({ left: 650000, top: 2000000, width: 1500000, height: 3000000 })
  ]);
  slide.modifyElement({ name: 'TextBox', nameIdx: 1 }, [
    modify.setPosition({ left: 2400000, top: 2000000, width: 1500000, height: 3000000 })
  ]);
  slide.modifyElement({ name: 'TextBox', nameIdx: 2 }, [
    modify.setPosition({ left: 4150000, top: 2000000, width: 1500000, height: 3000000 })
  ]);
  
  // 项目二期：Shape 49/60/73 nameIdx=1
  // Shape 49: 原始(6565900,1899285,1143000,1828800)
  slide.modifyElement({ name: 'Shape 49', nameIdx: 1 }, [
    modify.setPosition({ left: 6500000, top: 1850000, width: 1600000, height: 4500000 })
  ]);
  // Shape 60: 原始(7835900,1899285,1676400,1828800)
  slide.modifyElement({ name: 'Shape 60', nameIdx: 1 }, [
    modify.setPosition({ left: 8250000, top: 1850000, width: 1600000, height: 4500000 })
  ]);
  // Shape 73: 原始(9639300,1899285,1676400,1828800)
  slide.modifyElement({ name: 'Shape 73', nameIdx: 1 }, [
    modify.setPosition({ left: 10000000, top: 1850000, width: 1600000, height: 4500000 })
  ]);
  
  // 二期 TextBox nameIdx=3,4,5
  slide.modifyElement({ name: 'TextBox', nameIdx: 3 }, [
    modify.setPosition({ left: 6550000, top: 2000000, width: 1500000, height: 3000000 })
  ]);
  slide.modifyElement({ name: 'TextBox', nameIdx: 4 }, [
    modify.setPosition({ left: 8300000, top: 2000000, width: 1500000, height: 3000000 })
  ]);
  slide.modifyElement({ name: 'TextBox', nameIdx: 5 }, [
    modify.setPosition({ left: 10050000, top: 2000000, width: 1500000, height: 3000000 })
  ]);
  
  console.log('✅ 第2页：纵向改横向完成');
});

// === 第3页：删除图片，保留标题 ===
pres.addSlide('src', 3, (slide) => {
  // 删除图片（Picture 1），保留标题和装饰条
  slide.removeElement('图片 1');
  console.log('✅ 第3页：图片已删除');
});

// === 第4页：调整布局比例 ===
pres.addSlide('src', 4, (slide) => {
  // 当前：8个条目分两列四行，每个较窄
  // 增大每个条目的高度和宽度
  // 条目是 Shape 8/9, 14/15, 20/21, 26/27, 32/33, 38/39, 44/45, 50/51
  // 每个条目卡片高度从 554355 增大到 700000
  for (let i = 0; i < 4; i++) {
    const base = 8 + i * 6; // 8, 14, 20, 26, 32, 38, 44, 50
    for (let j = 0; j < 2; j++) {
      const idx = base + j * 6;
      try {
        slide.modifyElement(`Shape ${idx}`, [
          modify.setPosition({ left: j === 0 ? 400000 : 6000000, top: 2200000 + i * 900000, width: 5600000, height: 800000 })
        ]);
      } catch(e) {}
    }
  }
  console.log('✅ 第4页：布局调整完成');
});

// === 第5页：参照第4页 ===
pres.addSlide('src', 5);

// === 第6页：参照第4页 ===
pres.addSlide('src', 6);

// === 第7页：删除 ===
// 不添加第7页

// === 第8页：重新排版 ===
pres.addSlide('src', 8);

// === 第9页：保持原样 ===
pres.addSlide('src', 9);

pres.write(outFile).then(summary => {
  console.log('\n✅ 已保存:', JSON.stringify(summary));
}).catch(err => {
  console.error('❌ 错误:', err.message);
});

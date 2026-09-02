const { Automizer, modify } = require('pptx-automizer');
const path = require('path');
const os = require('os');

const srcDir = path.join(os.homedir(), 'Downloads/XSZS2608190616-WXB北京分中心');
const out = path.join(srcDir, '北京分中心二期项目启动会v1.2.pptx');

const automizer = new Automizer({
  templateDir: srcDir,
  outputDir: srcDir,
  removeExistingSlides: true,
  verbosity: 0,
  continueOnError: true,
});

let pres = automizer
  .loadRoot('北京分中心二期项目启动会v1.1.pptx')
  .load('北京分中心二期项目启动会v1.1.pptx', 'src');

// 项目一期：3个白色竖长条改成横向
// Shape 49: 合同金额 1243330x4572000 -> 改为 1243330x1200000 (压矮)
// Shape 60: 交付内容 1676400x4572000 -> 改为 1676400x1200000
// Shape 73: 项目目标 1567180x4572000 -> 改为 1567180x1200000
// 然后调整位置使其横向排列

// 用 modify.setPosition 来改位置和大小
// setPosition({left, top, width, height})

pres.addSlide('src', 2, (slide) => {
  // 合同金额 - 改高度从 4572000 到 1200000
  slide.modifyElement('Shape 49', [
    modify.setPosition({ left: 669290, top: 1828800, width: 1243330, height: 1200000 })
  ]);
  // 交付内容 - 改高度 + 调整位置到合同金额右边
  slide.modifyElement('Shape 60', [
    modify.setPosition({ left: 2054860, top: 1828800, width: 1676400, height: 1200000 })
  ]);
  // 项目目标 - 改高度 + 调整位置
  slide.modifyElement('Shape 73', [
    modify.setPosition({ left: 3888740, top: 1828800, width: 1567180, height: 1200000 })
  ]);
  
  // 同步调整 TextBox 大小
  // TextBox 1 (合同金额内容) @ (784860, 2522854) size=(1127760, 3234690)
  slide.modifyElement('TextBox 1', [
    modify.setPosition({ left: 784860, top: 2000000, width: 1127760, height: 1000000 })
  ]);
  // TextBox 2 (交付内容) @ (2077720, 2260600) size=(1468120, 3054350)
  slide.modifyElement('TextBox 2', [
    modify.setPosition({ left: 2100000, top: 2000000, width: 1600000, height: 1000000 })
  ]);
  // TextBox 3 (项目目标) @ (3881120, 2260600) size=(1473200, 1270000)
  slide.modifyElement('TextBox 3', [
    modify.setPosition({ left: 3900000, top: 2000000, width: 1500000, height: 1000000 })
  ]);
  
  console.log('✅ 第2页修改完成');
});

// 其他页原样复制
for (let i = 1; i <= 9; i++) {
  if (i !== 2) {
    pres.addSlide('src', i);
  }
}

pres.write('北京分中心二期项目启动会v1.2.pptx').then(summary => {
  console.log('\n✅ 已保存:', JSON.stringify(summary));
}).catch(err => {
  console.error('❌ 错误:', err.message);
});

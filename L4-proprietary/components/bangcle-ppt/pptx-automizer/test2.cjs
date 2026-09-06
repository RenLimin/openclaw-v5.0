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
});

let pres = automizer
  .loadRoot('北京分中心二期项目启动会v1.1.pptx')
  .load('北京分中心二期项目启动会v1.1.pptx', 'src');

// 遍历第2页所有形状，打印名称和尺寸
pres.addSlide('src', 2, (slide) => {
  // 用 slide 的 getElements 或直接访问 XML 来枚举形状
  const xml = slide.sourceArchive;
  console.log('Slide 2 loaded');
  
  // 尝试 modifyElement 来改形状
  // 先试试改 TextBox 的宽度
  try {
    slide.modifyElement('TextBox 1', [modify.setWidth(1600000)]);
    console.log('✅ 修改了 TextBox 1');
  } catch(e) {
    console.log('❌ TextBox 1:', e.message);
  }
});

pres.addSlide('src', 1)
  .addSlide('src', 3)
  .addSlide('src', 4)
  .addSlide('src', 5)
  .addSlide('src', 6)
  .addSlide('src', 7)
  .addSlide('src', 8)
  .addSlide('src', 9);

pres.write('北京分中心二期项目启动会v1.2.pptx').then(summary => {
  console.log('\n✅ 已保存:', JSON.stringify(summary));
}).catch(err => {
  console.error('❌ 错误:', err.message);
});

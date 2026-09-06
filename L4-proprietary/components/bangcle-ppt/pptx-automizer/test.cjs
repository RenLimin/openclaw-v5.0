const { Automizer } = require('pptx-automizer');
const path = require('path');
const os = require('os');

const srcDir = path.join(os.homedir(), 'Downloads/XSZS2608190616-WXB北京分中心');
const src = path.join(srcDir, '北京分中心二期项目启动会v1.1.pptx');
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

// 先遍历所有页看看信息
pres.addSlide('src', 1)
  .addSlide('src', 2, (slide) => {
    console.log('\n=== 第2页 ===');
    const shapes = slide.targetSlide.shapes;
    console.log('shapes:', shapes.length);
    for (const s of shapes) {
      const t = s.text ? ` '${s.text.substring(0,50)}'` : '';
      console.log(`  ${s.name}: pos=(${s.left},${s.top}) size=(${s.width},${s.height})${t}`);
    }
  })
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

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

// 先遍历所有页，打印形状信息用于分析
for (let i = 1; i <= 9; i++) {
  pres.addSlide('src', i, (slide) => {
    const shapes = slide.targetSlide.shapes;
    console.log(`\n=== Slide ${i} (${shapes.length} shapes) ===`);
    for (const s of shapes) {
      const t = s.text ? ` '${s.text.substring(0,40)}'` : '';
      console.log(`  ${s.name}: pos=(${s.left},${s.top}) size=(${s.width},${s.height})${t}`);
    }
  });
}

pres.write(outFile).then(summary => {
  console.log('\n✅ 已保存:', JSON.stringify(summary));
}).catch(err => {
  console.error('❌ 错误:', err.message);
});

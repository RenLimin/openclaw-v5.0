import Automizer from 'pptx-automizer';
import path from 'path';
import os from 'os';

const src = path.join(os.homedir(), 'Downloads/XSZS2608190616-WXB北京分中心/北京分中心二期项目启动会v1.1.pptx');
const out = path.join(os.homedir(), 'Downloads/XSZS2608190616-WXB北京分中心/北京分中心二期项目启动会v1.2.pptx');

const automizer = new Automizer();

const pres = automizer.loadRoot(src);

pres.addSlide(src, 2, (slide) => {
  const shapes = slide.targetSlide.shapes;
  console.log(`\n第2页 shapes: ${shapes.length}`);
  for (const s of shapes) {
    console.log(`  ${s.name}: pos=(${s.left},${s.top}) size=(${s.width},${s.height})`);
    if (s.text) {
      console.log(`    text: '${s.text.substring(0, 60)}'`);
    }
  }
});

await pres.write(out);
console.log('\n✅ 已保存');

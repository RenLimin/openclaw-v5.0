const { Automizer, modify } = require('pptx-automizer');
const path = require('path');
const os = require('os');

const srcDir = path.join(os.homedir(), 'Downloads/XSZS2608190616-WXB北京分中心');
const out = path.join(srcDir, '北京分中心二期项目启动会v1.2.pptx');

const automizer = new Automizer({
  templateDir: srcDir,
  outputDir: srcDir,
  removeExistingSlides: false,  // 保留所有原始幻灯片
  verbosity: 0,
  continueOnError: true,
});

let pres = automizer
  .loadRoot('北京分中心二期项目启动会v1.1.pptx')
  .load('北京分中心二期项目启动会v1.1.pptx', 'src');

// 遍历所有幻灯片并修改第2页
for (let i = 1; i <= 9; i++) {
  pres.addSlide('src', i, (slide) => {
    if (i === 2) {
      // 项目一期：3个白色竖长条改成横向
      slide.modifyElement('Shape 49', [
        modify.setPosition({ left: 669290, top: 1828800, width: 1500000, height: 1200000 })
      ]);
      slide.modifyElement('Shape 60', [
        modify.setPosition({ left: 2300000, top: 1828800, width: 1500000, height: 1200000 })
      ]);
      slide.modifyElement('Shape 73', [
        modify.setPosition({ left: 4000000, top: 1828800, width: 1500000, height: 1200000 })
      ]);
      
      // 同步调整 TextBox
      slide.modifyElement('TextBox 1', [
        modify.setPosition({ left: 784860, top: 2000000, width: 1300000, height: 900000 })
      ]);
      slide.modifyElement('TextBox 2', [
        modify.setPosition({ left: 2400000, top: 2000000, width: 1300000, height: 900000 })
      ]);
      slide.modifyElement('TextBox 3', [
        modify.setPosition({ left: 4100000, top: 2000000, width: 1300000, height: 900000 })
      ]);
      
      console.log('✅ 第2页修改完成');
    }
  });
}

pres.write('北京分中心二期项目启动会v1.2.pptx').then(summary => {
  console.log('✅ 已保存:', JSON.stringify(summary));
}).catch(err => {
  console.error('❌ 错误:', err.message);
});

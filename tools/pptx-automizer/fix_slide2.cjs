const { Automizer, modify } = require('pptx-automizer');
const path = require('path');
const os = require('os');

const srcDir = path.join(os.homedir(), 'Downloads/XSZS2608190616-WXB北京分中心');
const outFile = '北京分中心二期项目启动会v1.2.pptx';

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

for (let i = 1; i <= 9; i++) {
  pres.addSlide('src', i, (slide) => {
    if (i === 2) {
      // === 项目一期（nameIdx=0） ===
      // Shape 49(合同金额), Shape 60(交付内容), Shape 73(项目目标) — 竖长条改横向
      slide.modifyElement({ name: 'Shape 49', nameIdx: 0 }, [
        modify.setPosition({ left: 600000, top: 1800000, width: 1600000, height: 1300000 })
      ]);
      slide.modifyElement({ name: 'Shape 60', nameIdx: 0 }, [
        modify.setPosition({ left: 2350000, top: 1800000, width: 1600000, height: 1300000 })
      ]);
      slide.modifyElement({ name: 'Shape 73', nameIdx: 0 }, [
        modify.setPosition({ left: 4100000, top: 1800000, width: 1600000, height: 1300000 })
      ]);
      
      // TextBox 1(合同金额内容), TextBox 2(交付内容), TextBox 3(项目目标)
      slide.modifyElement({ name: 'TextBox', nameIdx: 0 }, [
        modify.setPosition({ left: 650000, top: 2000000, width: 1500000, height: 1000000 })
      ]);
      slide.modifyElement({ name: 'TextBox', nameIdx: 1 }, [
        modify.setPosition({ left: 2400000, top: 2000000, width: 1500000, height: 1000000 })
      ]);
      slide.modifyElement({ name: 'TextBox', nameIdx: 2 }, [
        modify.setPosition({ left: 4150000, top: 2000000, width: 1500000, height: 1000000 })
      ]);
      
      // === 项目二期（nameIdx=1） ===
      slide.modifyElement({ name: 'Shape 49', nameIdx: 1 }, [
        modify.setPosition({ left: 6500000, top: 1800000, width: 1600000, height: 1300000 })
      ]);
      slide.modifyElement({ name: 'Shape 60', nameIdx: 1 }, [
        modify.setPosition({ left: 8250000, top: 1800000, width: 1600000, height: 1300000 })
      ]);
      slide.modifyElement({ name: 'Shape 73', nameIdx: 1 }, [
        modify.setPosition({ left: 10000000, top: 1800000, width: 1600000, height: 1300000 })
      ]);
      
      // TextBox 3(二期合同金额), TextBox 4(交付内容), TextBox 5(项目目标)
      slide.modifyElement({ name: 'TextBox', nameIdx: 3 }, [
        modify.setPosition({ left: 6550000, top: 2000000, width: 1500000, height: 1000000 })
      ]);
      slide.modifyElement({ name: 'TextBox', nameIdx: 4 }, [
        modify.setPosition({ left: 8300000, top: 2000000, width: 1500000, height: 1000000 })
      ]);
      slide.modifyElement({ name: 'TextBox', nameIdx: 5 }, [
        modify.setPosition({ left: 10050000, top: 2000000, width: 1500000, height: 1000000 })
      ]);
      
      console.log('✅ 第2页修改完成');
    }
  });
}

pres.write(outFile).then(summary => {
  console.log('✅ 已保存:', JSON.stringify(summary));
}).catch(err => {
  console.error('❌ 错误:', err.message);
});

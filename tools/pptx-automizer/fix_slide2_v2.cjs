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
      // 白色长条：只改位置和宽度，保持原始高度不变
      // 原始：Shape 49(669290,1828800,1243330,4572000), Shape 60(2054860,1839596,1676400,4572000), Shape 73(3888740,1828800,1567180,4572000)
      // 改后：三栏横向排列，每个变宽，高度保持 4572000
      slide.modifyElement({ name: 'Shape 49', nameIdx: 0 }, [
        modify.setPosition({ left: 600000, top: 1828800, width: 1600000, height: 4572000 })
      ]);
      slide.modifyElement({ name: 'Shape 60', nameIdx: 0 }, [
        modify.setPosition({ left: 2350000, top: 1828800, width: 1600000, height: 4572000 })
      ]);
      slide.modifyElement({ name: 'Shape 73', nameIdx: 0 }, [
        modify.setPosition({ left: 4100000, top: 1828800, width: 1600000, height: 4572000 })
      ]);
      
      // TextBox：只改 left 和 width，保持原始 top 和 height
      // TextBox 1(合同金额): 原始(784860,2522854,1127760,3234690)
      slide.modifyElement({ name: 'TextBox', nameIdx: 0 }, [
        modify.setPosition({ left: 650000, top: 2522854, width: 1500000, height: 3234690 })
      ]);
      // TextBox 2(交付内容): 原始(2077720,2260600,1468120,3054350)
      slide.modifyElement({ name: 'TextBox', nameIdx: 1 }, [
        modify.setPosition({ left: 2400000, top: 2260600, width: 1500000, height: 3054350 })
      ]);
      // TextBox 3(项目目标): 原始(3881120,2260600,1473200,1270000)
      slide.modifyElement({ name: 'TextBox', nameIdx: 2 }, [
        modify.setPosition({ left: 4150000, top: 2260600, width: 1500000, height: 1270000 })
      ]);
      
      // === 项目二期（nameIdx=1） ===
      // 原始：Shape 49(6565900,1899285,1143000,1828800), Shape 60(7835900,1899285,1676400,1828800), Shape 73(9639300,1899285,1676400,1828800)
      slide.modifyElement({ name: 'Shape 49', nameIdx: 1 }, [
        modify.setPosition({ left: 6500000, top: 1899285, width: 1600000, height: 1828800 })
      ]);
      slide.modifyElement({ name: 'Shape 60', nameIdx: 1 }, [
        modify.setPosition({ left: 8250000, top: 1899285, width: 1600000, height: 1828800 })
      ]);
      slide.modifyElement({ name: 'Shape 73', nameIdx: 1 }, [
        modify.setPosition({ left: 10000000, top: 1899285, width: 1600000, height: 1828800 })
      ]);
      
      // TextBox 4(二期合同金额): 原始(6667500,2331085,939800,1270000)
      slide.modifyElement({ name: 'TextBox', nameIdx: 3 }, [
        modify.setPosition({ left: 6550000, top: 2331085, width: 1500000, height: 1270000 })
      ]);
      // TextBox 5(二期交付内容): 原始(7937500,2331085,1473200,1270000)
      slide.modifyElement({ name: 'TextBox', nameIdx: 4 }, [
        modify.setPosition({ left: 8300000, top: 2331085, width: 1500000, height: 1270000 })
      ]);
      // TextBox 6(二期项目目标): 原始(9740900,2331085,1473200,1270000)
      slide.modifyElement({ name: 'TextBox', nameIdx: 5 }, [
        modify.setPosition({ left: 10050000, top: 2331085, width: 1500000, height: 1270000 })
      ]);
      
      console.log('✅ 第2页修改完成（保留原始高度）');
    }
  });
}

pres.write(outFile).then(summary => {
  console.log('✅ 已保存:', JSON.stringify(summary));
}).catch(err => {
  console.error('❌ 错误:', err.message);
});

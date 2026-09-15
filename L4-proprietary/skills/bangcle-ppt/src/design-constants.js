/**
 * Bangcle PPT 设计系统常量
 * 从官方模板提取的标准化设计常量
 * 组件 ID: CPT-012
 */

// 色彩体系
exports.colors = {
  // VI 标准色
  primary: '#2D74BB',        // C-01 主色（梆梆蓝）
  lightBlue: '#3FA1DA',      // C-02 浅蓝
  cyan: '#27AABF',           // C-03 青色
  green: '#33ADA0',          // C-04 青绿
  gold: '#EFBA20',           // C-05 金色
  darkBlue: '#00122B',       // C-06 深藏青
  darkGray: '#595757',       // C-07 深灰

  // 辅助色
  veryLightBlue: '#BEE3FA',
  lightGray: '#E7E6E6',
  brightBlue: '#649CEF',
  mediumBlue: '#5B9BD5',
  pureBlue: '#0081FF',
  grayBlue: '#387BBE',
  darkGrayBlue: '#4073B5',
  goldBrown: '#DCBA84',
  mediumGray: '#BFBFBF',

  // 文字色（浅色模板）
  text: {
    lightTitle: '#2D74BB',
    lightSubtitle: '#387BBE',
    lightBody: '#595757',
    lightCaption: '#A7A7A7',
    lightAccent: '#2D74BB',
  },

  // 文字色（深色模板）
  textDark: {
    darkTitle: '#FFFFFF',
    darkSubtitle: '#FFFFFF',
    darkBody: '#FFFFFF',
    darkCaption: '#BEE3FA',
    darkAccent: '#EFBA20',
  },

  // 背景色
  bg: {
    light: '#FFFFFF',
    dark: '#00122B',
  },

  // 边框
  border: {
    lightCard: '#E7E6E6',
    darkCard: '#2D74BB',
  }
};

// 字体系统
exports.fonts = {
  family: 'Source Han Sans',
  fallback: 'Microsoft YaHei',
  weight: {
    heavy: 900,
    medium: 500,
  },
  // 字号层级（浅色模板，单位 pt）
  size: {
    h0: 138,      // 封面大标题 / 巨大编号
    h1: 36,       // 页面主标题
    h2: 32,       // 章节副标题
    h3: 28,       // 目录标题
    h4: 24,       // 内容小标题 / 目录项标题
    h5: 20,       // 卡片标题
    body: 14,     // 正文
    bodySm: 12,   // 小字正文
    caption: 11,  // 辅助文字
    enSub: 14,    // 英文副标题
    number: 28,   // 编号数字
  },
  // 字号层级（深色模板，单位 pt）
  sizeDark: {
    h1: 28,
    h3: 20,
    h5: 18,
    body: 12,
  }
};

// 尺寸常量（单位 英寸，pptxgenjs 使用英寸）
exports.sizes = {
  slide: {
    width: 13.333,
    height: 7.5,
  },
  margin: {
    titleLeft: 0.54,      // 标题左距
    titleTop: 0.47,       // 标题顶距
  },
  logo: {
    width: 1.34,
    height: 0.49,
  },
  card: {
    standardWidth: 3.18,
    standardHeight: 2.9,
    twoColumnWidth: 5.57,
  },
  // 换算成 EMU（pptx-automizer 使用 EMU）
  emu: {
    slideWidth: 12192000,
    slideHeight: 6858000,
    titleLeft: 493776,
    titleTop: 429004,
    logoWidth: 1222310,
    logoHeight: 446726,
    cardStandardWidth: 2895600,
    cardStandardHeight: 2641680,
  }
};

// 页面类型
exports.pageTypes = [
  'cover-light',      // 浅色封面页
  'toc-light',        // 浅色目录页
  'section-light',    // 浅色章节过渡页
  'content-two-col',  // 左文右图内容页
  'content-three-cards', // 三卡片+横幅图
  'timeline-three-cards', // 时间轴+三卡片
  'data-chart',       // 图表+数据卡片页
  'timeline-vertical', // 纵向时间轴
  'cover-dark',       // 深色封面页
  'toc-dark',         // 深色目录页
  'section-dark',     // 深色章节过渡页
  'closing-qrcode',   // 二维码结尾页
];

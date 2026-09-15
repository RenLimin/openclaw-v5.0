/* BDMS 前端公共脚本 */
window.bdmsFmt = {
  wan: v => (v == null) ? '-' : (v / 10000).toLocaleString('zh-CN', {maximumFractionDigits: 2}) + ' 万',
  pct: v => (v == null) ? '-' : (v * 100).toFixed(2) + '%',
  monthLabel: m => m ? `${String(m).slice(0,4)}年${String(m).slice(4)}月` : '-',
};
console.debug('BDMS UI loaded');

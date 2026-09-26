async function loadMonths() {
  const r = await fetch('/api/report/months');
  const d = await r.json();
  const months = d.months || [];
  document.getElementById('months-list').innerHTML = months.length
    ? '<div class="table-wrapper"><table class="table"><thead><tr><th>月份</th><th>操作</th></tr></thead><tbody>'
      + months.map(m => {
          const mm = m.month || m;
          return `<tr><td><strong>${mm.slice(0,4)}年${mm.slice(4)}月</strong></td>
            <td><a class="btn btn-sm btn-success" href="/api/report/export/${mm}">下载 Excel</a></td></tr>`;
        }).join('') + '</tbody></table></div>'
    : '<p style="color:var(--c-muted);">尚无已生成月份</p>';
}

async function doGenerate() {
  const monthRaw = document.getElementById('gen-month').value.trim();
  // <input type="month"> 返回 YYYY-MM，后端需要 YYYYMM，去掉横杠
  const month = monthRaw.replace('-', '');
  const mode = document.getElementById('gen-mode').value;
  const st = document.getElementById('gen-status');
  st.textContent = `生成中（${mode}）...`;
  try {
    const r = await fetch('/api/report/generate', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({month, mode})
    });
    const d = await r.json();
    if (!r.ok) { st.textContent = `⚠️ ${d.error}`; return; }
    st.innerHTML = `✅ <strong>${d.action}</strong> 完成，合计 <strong>${d.total_rows}</strong> 行`;
    let h = '<div class="table-wrapper"><table class="table"><thead><tr><th>Sheet</th><th>行数</th></tr></thead><tbody>';
    for (const [k, v] of Object.entries(d.sheets || {})) h += `<tr><td>${k}</td><td>${v}</td></tr>`;
    h += '</tbody></table></div>';
    document.getElementById('sheet-detail').innerHTML = h;
    loadMonths();
  } catch (e) { st.textContent = `失败: ${e}`; }
}

function doExport() {
  const monthRaw = document.getElementById('gen-month').value.trim();
  // <input type="month"> 返回 YYYY-MM，后端需要 YYYYMM，去掉横杠
  const month = monthRaw.replace('-', '');
  if (!month || month.length !== 6) {
    alert('请选择有效的月份');
    return;
  }
  window.location.href = `/api/report/export/${month}`;
}

document.addEventListener('DOMContentLoaded', function() {
  loadMonths().catch(function(e) {
    console.error('loadMonths 失败:', e);
    document.getElementById('months-list').innerHTML = '<p style="color:var(--c-muted);">加载失败，请刷新页面重试</p>';
  });
});

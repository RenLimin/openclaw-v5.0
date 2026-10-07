/**
 * BDMS Dashboard v2.1 — 前端交互逻辑
 * 对齐 DESIGN-DETAIL-DASHBOARD-v2.1.md §15
 */
'use strict';

// ─── 状态 ───
let currentMonth = null;
let currentView = 'default';
let kpiCache = {};

// ─── 初始化 ───
document.addEventListener('DOMContentLoaded', async () => {
    await initMonthSelector();
    await loadDashboard();
    bindEvents();
});

// ─── 月份选择器 ───
async function initMonthSelector() {
    const resp = await fetch('/api/report/months');
    const data = await resp.json();
    const select = document.getElementById('month-select');
    if (!select) return;

    select.innerHTML = '';
    (data.months || []).forEach(m => {
        const opt = document.createElement('option');
        opt.value = m;
        opt.textContent = `${m.slice(0, 4)}-${m.slice(4)}`;
        select.appendChild(opt);
    });

    if (data.months && data.months.length > 0) {
        currentMonth = data.months[data.months.length - 1];
        select.value = currentMonth;
    }
}

// ─── 加载驾驶舱 ───
async function loadDashboard(month = currentMonth, refresh = false) {
    if (!month) return;
    currentMonth = month;

    // KPI 汇总
    const kpiResp = await fetch(`/api/dashboard/summary?month=${month}&refresh=${refresh}`);
    const kpiData = await kpiResp.json();
    kpiCache = kpiData;
    renderKPIs(kpiData);

    // 趋势
    const trendResp = await fetch(`/api/dashboard/trend/delivery_count?month=${month}&range=12`);
    const trendData = await trendResp.json();
    renderTrendChart('delivery-trend-chart', trendData, '交付项目数');

    // 下钻默认加载
    await loadDrillDown(month, 'dept_stats');
}

// ─── 渲染 KPI 卡片 ───
function renderKPIs(data) {
    const grid = document.getElementById('kpi-grid');
    if (!grid) return;

    const kpis = [
        { key: 'contract_count', label: '合同数量', unit: '个' },
        { key: 'contract_amount', label: '合同金额', unit: '万元' },
        { key: 'project_executing', label: '在建项目', unit: '个' },
        { key: 'delivery_count', label: '交付项目', unit: '个' },
        { key: 'delivery_ontime_rate', label: '交付及时率', unit: '%', pct: true },
        { key: 'acceptance_count', label: '验收项目', unit: '个' },
        { key: 'revenue_amount', label: '确收金额', unit: '万元' },
        { key: 'revenue_rate', label: '确收率', unit: '%', pct: true },
        { key: 'after_sales_tickets', label: '售后工单', unit: '个' },
        { key: 'project_cost', label: '项目成本', unit: '万元' },
        { key: 'risk_open', label: '风险项目', unit: '个' },
        { key: 'profit_margin', label: '毛利率', unit: '%', pct: true },
    ];

    grid.innerHTML = '';
    kpis.forEach(kpi => {
        const val = data[kpi.key] ?? 0;
        const displayVal = kpi.pct ? (val * 100).toFixed(1) : (kpi.key.includes('amount') || kpi.key.includes('cost') ? (val / 10000).toFixed(0) : val);
        const color = getKPIColor(kpi.key, val);

        const card = document.createElement('div');
        card.className = 'kpi-card';
        card.style.cssText = `background:${color};color:#fff;padding:1rem;border-radius:8px;text-align:center;cursor:pointer;`;
        card.innerHTML = `<div style="font-size:0.85rem;opacity:0.9;">${kpi.label}</div><div style="font-size:1.8rem;font-weight:bold;margin:0.3rem 0;">${displayVal}<span style="font-size:0.7rem;margin-left:2px;">${kpi.unit}</span></div>`;
        card.onclick = () => loadDrillDown(currentMonth, kpi.key);
        grid.appendChild(card);
    });
}

function getKPIColor(key, val) {
    if (key === 'delivery_ontime_rate' || key === 'revenue_rate') {
        if (val >= 0.9) return '#27ae60';
        if (val >= 0.8) return '#f39c12';
        return '#e74c3c';
    }
    if (key === 'risk_open') {
        if (val <= 2) return '#27ae60';
        if (val <= 5) return '#f39c12';
        return '#e74c3c';
    }
    if (key === 'profit_margin') {
        if (val >= 0.2) return '#27ae60';
        if (val >= 0.1) return '#f39c12';
        return '#e74c3c';
    }
    return '#3498db';
}

// ─── 趋势图 ───
function renderTrendChart(canvasId, data, label) {
    const ctx = document.getElementById(canvasId);
    if (!ctx || typeof Chart === 'undefined') return;

    if (ctx._chart) ctx._chart.destroy();

    ctx._chart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: data.map(d => d.month),
            datasets: [{
                label: label,
                data: data.map(d => d.value),
                borderColor: '#3498db',
                backgroundColor: 'rgba(52,152,219,0.1)',
                fill: true,
                tension: 0.3,
            }]
        },
        options: {
            responsive: true,
            plugins: { legend: { display: true } },
            scales: { y: { beginAtZero: true } }
        }
    });
}

// ─── 下钻 ───
async function loadDrillDown(month, metric, dimension = null, value = null) {
    if (!month || !metric) return;

    let url = `/api/dashboard/drill-down?month=${month}&metric=${metric}`;
    if (dimension) url += `&dimension=${dimension}`;
    if (value) url += `&value=${encodeURIComponent(value)}`;

    const resp = await fetch(url);
    const data = await resp.json();
    renderDrillDownTable(data);
}

function renderDrillDownTable(data) {
    const container = document.getElementById('drilldown-table-container');
    if (!container) return;

    if (!data.items || data.items.length === 0) {
        container.innerHTML = '<p style="padding:1rem;color:#888;">无数据</p>';
        return;
    }

    const columns = Object.keys(data.items[0]);
    let html = '<table style="width:100%;border-collapse:collapse;"><thead><tr>';
    columns.forEach(c => { html += `<th style="padding:0.5rem;border-bottom:2px solid #3498db;text-align:left;">${c}</th>`; });
    html += '</tr></thead><tbody>';

    data.items.forEach(row => {
        html += '<tr>';
        columns.forEach(c => {
            const val = row[c] ?? '';
            html += `<td style="padding:0.4rem;border-bottom:1px solid #eee;">${val}</td>`;
        });
        html += '</tr>';
    });
    html += '</tbody></table>';
    container.innerHTML = html;
}

// ─── 字段编辑 ───
async function editField(table, recordId, field, value) {
    const resp = await fetch('/api/dashboard/edit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ table, record_id: recordId, field, value })
    });
    const result = await resp.json();
    if (result.success) {
        await loadDashboard(currentMonth);
    } else {
        alert('编辑失败: ' + (result.error || '未知错误'));
    }
}

// ─── 视图管理 ───
async function loadViews() {
    const resp = await fetch('/api/dashboard/views');
    const data = await resp.json();
    const container = document.getElementById('view-list');
    if (!container) return;

    container.innerHTML = '';
    (data.views || []).forEach(v => {
        const div = document.createElement('div');
        div.style.cssText = 'padding:0.5rem;border-bottom:1px solid #eee;cursor:pointer;';
        div.innerHTML = `<strong>${v.view_name}</strong>${v.is_default ? ' ⭐' : ''}`;
        div.onclick = () => switchView(v.view_id);
        container.appendChild(div);
    });
}

async function switchView(viewId) {
    await loadDashboard(currentMonth);
}

// ─── 事件绑定 ───
function bindEvents() {
    const monthSelect = document.getElementById('month-select');
    if (monthSelect) monthSelect.onchange = (e) => loadDashboard(e.target.value);

    const refreshBtn = document.getElementById('refresh-btn');
    if (refreshBtn) refreshBtn.onclick = () => loadDashboard(currentMonth, true);
}

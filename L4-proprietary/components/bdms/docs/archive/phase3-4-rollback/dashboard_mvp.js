// MVP Dashboard JS
let charts = {};

async function loadMVP() {
    const month = document.getElementById('month-select')?.value || '2026-09';
    const status = document.getElementById('load-status');
    status.textContent = '加载中...';

    try {
        const res = await fetch(`/api/dashboard/mvp/${month}`);
        const data = await res.json();
        const kpis = data.kpis || {};

        // 更新 KPI 卡片
        document.getElementById('kpi-contract-count').textContent = kpis.contract_count || 0;
        document.getElementById('kpi-contract-amount').textContent = ((kpis.contract_amount || 0) / 10000).toFixed(1);
        document.getElementById('kpi-project-count').textContent = kpis.project_count || 0;
        document.getElementById('kpi-active-projects').textContent = kpis.active_project_count || 0;
        document.getElementById('kpi-delivering-projects').textContent = kpis.delivering_project_count || 0;
        document.getElementById('kpi-completed-projects').textContent = kpis.completed_project_count || 0;
        document.getElementById('kpi-risk-count').textContent = kpis.risk_count || 0;
        document.getElementById('kpi-high-risk-count').textContent = kpis.high_risk_count || 0;

        status.textContent = data._cached ? '（缓存）' : '（实时）';
    } catch (e) {
        status.textContent = '加载失败: ' + e.message;
    }
}

async function refreshMVP() {
    const month = document.getElementById('month-select')?.value || '2026-09';
    const status = document.getElementById('load-status');
    status.textContent = '刷新中...';

    try {
        await fetch('/api/dashboard/mvp/refresh', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ month }),
        });
        await loadMVP();
        status.textContent = '（已刷新）';
    } catch (e) {
        status.textContent = '刷新失败: ' + e.message;
    }
}

document.addEventListener('DOMContentLoaded', () => loadMVP());

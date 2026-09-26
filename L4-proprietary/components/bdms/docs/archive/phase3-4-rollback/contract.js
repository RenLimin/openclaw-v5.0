// 合同管理页面 JS
let currentPage = 1;

async function loadContracts(page = 1) {
    currentPage = page;
    const status = document.getElementById('filter-status')?.value || '';
    const keyword = document.getElementById('filter-keyword')?.value || '';
    const params = new URLSearchParams({ page, page_size: 20 });
    if (status) params.set('status', status);
    if (keyword) params.set('keyword', keyword);

    try {
        const res = await fetch(`/api/contract/list?${params}`);
        const data = await res.json();
        renderContractList(data.items || []);
        renderPagination(data.total || 0, page);
    } catch (e) {
        document.getElementById('contract-tbody').innerHTML =
            `<tr><td colspan="6" style="padding:2rem;text-align:center;color:var(--c-danger);">加载失败: ${e.message}</td></tr>`;
    }
}

function renderContractList(items) {
    const tbody = document.getElementById('contract-tbody');
    if (!items.length) {
        tbody.innerHTML = '<tr><td colspan="6" style="padding:2rem;text-align:center;color:var(--c-muted);">暂无合同数据</td></tr>';
        return;
    }
    const statusMap = {
        draft: { label: '起草', color: 'gray' },
        review1: { label: '一级审批', color: 'blue' },
        review2: { label: '二级审批', color: 'blue' },
        review3: { label: '三级审批', color: 'blue' },
        review4: { label: '四级审批', color: 'blue' },
        approved: { label: '审批通过', color: 'green' },
        signed: { label: '已签署', color: 'purple' },
        archived: { label: '已归档', color: 'gray' },
        rejected: { label: '已驳回', color: 'red' },
    };
    tbody.innerHTML = items.map(c => {
        const st = statusMap[c.status] || { label: c.status, color: 'gray' };
        const amount = (c.amount / 10000).toFixed(1);
        return `<tr style="border-bottom:1px solid var(--c-border);">
            <td style="padding:0.75rem;">${c.contract_no || '-'}</td>
            <td style="padding:0.75rem;">${c.title || '-'}</td>
            <td style="padding:0.75rem;">${c.contract_type || '-'}</td>
            <td style="padding:0.75rem;text-align:right;">${amount} 万</td>
            <td style="padding:0.75rem;text-align:center;"><span class="badge badge-${st.color}">${st.label}</span></td>
            <td style="padding:0.75rem;text-align:center;"><button class="btn btn-sm btn-secondary" onclick="showContractDetail(${c.id})">查看</button></td>
        </tr>`;
    }).join('');
}

function renderPagination(total, page) {
    const totalPages = Math.ceil(total / 20);
    const pag = document.getElementById('contract-pagination');
    if (totalPages <= 1) { pag.innerHTML = ''; return; }
    let html = '';
    if (page > 1) html += `<button class="btn btn-sm" onclick="loadContracts(${page - 1})">&lt;</button>`;
    html += `<span style="padding:0.5rem;">${page} / ${totalPages}</span>`;
    if (page < totalPages) html += `<button class="btn btn-sm" onclick="loadContracts(${page + 1})">&gt;</button>`;
    pag.innerHTML = html;
}

async function showContractDetail(id) {
    try {
        const res = await fetch(`/api/contract/${id}`);
        const data = await res.json();
        const panel = document.getElementById('contract-detail-panel');
        const content = document.getElementById('contract-detail-content');
        content.innerHTML = `
            <div style="display:grid;gap:1rem;">
                <div><strong>合同编号：</strong>${data.contract_no || '-'}</div>
                <div><strong>标题：</strong>${data.title || '-'}</div>
                <div><strong>类型：</strong>${data.contract_type || '-'}</div>
                <div><strong>金额：</strong>${((data.amount || 0) / 10000).toFixed(1)} 万</div>
                <div><strong>状态：</strong>${data.status || '-'}</div>
                <div><strong>生效日期：</strong>${data.effective_date || '-'}</div>
                <div><strong>到期日期：</strong>${data.expiry_date || '-'}</div>
                <div><strong>创建时间：</strong>${data.created_at || '-'}</div>
            </div>
        `;
        panel.style.display = 'block';
    } catch (e) {
        alert('加载详情失败: ' + e.message);
    }
}

function closeDetailPanel() {
    document.getElementById('contract-detail-panel').style.display = 'none';
}

function exportContracts() {
    alert('导出功能开发中');
}

// 页面加载时自动加载
document.addEventListener('DOMContentLoaded', () => loadContracts());

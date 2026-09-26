// 项目管理页面 JS
let currentPage = 1;

async function loadProjects(page = 1) {
    currentPage = page;
    const status = document.getElementById('filter-status')?.value || '';
    const pm = document.getElementById('filter-pm')?.value || '';
    const keyword = document.getElementById('filter-keyword')?.value || '';
    const params = new URLSearchParams({ page, page_size: 20 });
    if (status) params.set('status', status);
    if (pm) params.set('pm', pm);
    if (keyword) params.set('keyword', keyword);

    try {
        const res = await fetch(`/api/project/list?${params}`);
        const data = await res.json();
        renderProjectList(data.items || []);
        renderPagination(data.total || 0, page);
    } catch (e) {
        document.getElementById('project-tbody').innerHTML =
            `<tr><td colspan="7" style="padding:2rem;text-align:center;color:var(--c-danger);">加载失败: ${e.message}</td></tr>`;
    }
}

function renderProjectList(items) {
    const tbody = document.getElementById('project-tbody');
    if (!items.length) {
        tbody.innerHTML = '<tr><td colspan="7" style="padding:2rem;text-align:center;color:var(--c-muted);">暂无项目数据</td></tr>';
        return;
    }
    const statusMap = {
        initiating: { label: '立项中', color: 'gray' },
        planning: { label: '规划中', color: 'blue' },
        executing: { label: '执行中', color: 'blue' },
        delivering: { label: '交付中', color: 'yellow' },
        accepting: { label: '验收中', color: 'green' },
        closing: { label: '结项中', color: 'green' },
        closed: { label: '已结项', color: 'gray' },
        cancelled: { label: '已取消', color: 'red' },
    };
    tbody.innerHTML = items.map(p => {
        const st = statusMap[p.status] || { label: p.status, color: 'gray' };
        const progress = p.progress_pct || 0;
        return `<tr style="border-bottom:1px solid var(--c-border);">
            <td style="padding:0.75rem;">${p.project_no || '-'}</td>
            <td style="padding:0.75rem;">${p.project_name || '-'}</td>
            <td style="padding:0.75rem;">${p.pm || '-'}</td>
            <td style="padding:0.75rem;text-align:center;"><span class="badge badge-${st.color}">${st.label}</span></td>
            <td style="padding:0.75rem;">
                <div style="background:var(--c-surface-2);border-radius:4px;height:8px;width:100px;">
                    <div style="background:var(--c-primary);border-radius:4px;height:8px;width:${progress}%;"></div>
                </div>
            </td>
            <td style="padding:0.75rem;text-align:center;">${p.risk_count || 0}</td>
            <td style="padding:0.75rem;text-align:center;"><button class="btn btn-sm btn-secondary" onclick="showProjectDetail(${p.id})">查看</button></td>
        </tr>`;
    }).join('');
}

function renderPagination(total, page) {
    const totalPages = Math.ceil(total / 20);
    const pag = document.getElementById('project-pagination');
    if (totalPages <= 1) { pag.innerHTML = ''; return; }
    let html = '';
    if (page > 1) html += `<button class="btn btn-sm" onclick="loadProjects(${page - 1})">&lt;</button>`;
    html += `<span style="padding:0.5rem;">${page} / ${totalPages}</span>`;
    if (page < totalPages) html += `<button class="btn btn-sm" onclick="loadProjects(${page + 1})">&gt;</button>`;
    pag.innerHTML = html;
}

async function showProjectDetail(id) {
    try {
        const res = await fetch(`/api/project/${id}`);
        const data = await res.json();
        const modal = document.getElementById('project-detail-modal');
        const body = document.getElementById('modal-body');
        const p = data.project || {};
        body.innerHTML = `
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:1rem;">
                <div><strong>项目编号：</strong>${p.project_no || '-'}</div>
                <div><strong>名称：</strong>${p.project_name || '-'}</div>
                <div><strong>PM：</strong>${p.pm || '-'}</div>
                <div><strong>状态：</strong>${p.status || '-'}</div>
                <div><strong>预算：</strong>${((p.budget || 0) / 10000).toFixed(1)} 万</div>
                <div><strong>开始日期：</strong>${p.start_date || '-'}</div>
            </div>
            <h4 style="margin-top:1.5rem;">阶段</h4>
            <div>${(data.phases || []).map(ph =>
                `<div style="display:flex;justify-content:space-between;padding:0.5rem 0;border-bottom:1px solid var(--c-border);">
                    <span>${ph.phase_name}</span><span style="color:var(--c-muted);">${ph.status || 'pending'}</span>
                </div>`
            ).join('') || '<span style="color:var(--c-muted);">暂无阶段</span>'}
            <h4 style="margin-top:1.5rem;">团队</h4>
            <div>${(data.team_members || []).map(m =>
                `<div style="display:flex;justify-content:space-between;padding:0.5rem 0;border-bottom:1px solid var(--c-border);">
                    <span>${m.member_name}</span><span style="color:var(--c-muted);">${m.role || ''}</span>
                </div>`
            ).join('') || '<span style="color:var(--c-muted);">暂无成员</span>'}
        `;
        modal.style.display = 'flex';
    } catch (e) {
        alert('加载详情失败: ' + e.message);
    }
}

function closeProjectModal() {
    document.getElementById('project-detail-modal').style.display = 'none';
}

document.addEventListener('DOMContentLoaded', () => loadProjects());

/* ============================================================
   table.js — 数据表格组件
   组件：web-common (L2) · v2.0 · ADR-033
   功能：列排序 / 固定表头 / 行选中 / 展开行 / 空状态
   用法：
     <div class="table-wrapper" data-table data-sortable>
       <table class="table">
         <thead>
           <tr>
             <th data-sort="name">名称 <span class="sort-indicator"></span></th>
             <th data-sort="amount" data-sort-type="number">金额</th>
           </tr>
         </thead>
         <tbody>
           <tr data-row><td>...</td></tr>
         </tbody>
       </table>
     </div>
   JS API:
     Table.initAll() — 初始化所有表格
   事件：排序触发 'table:sort'（detail: {key, direction}）
   ============================================================ */
(function () {
  'use strict';

  const SELECTOR = '[data-table]';

  class Table {
    constructor(wrapper) {
      this.wrapper = wrapper;
      this.table = wrapper.querySelector('table');
      if (!this.table) return;
      this.tbody = this.table.querySelector('tbody');
      this._bindEvents();
      this._initStickyHeader();
    }

    _bindEvents() {
      // 排序
      if (this.wrapper.dataset.sortable !== undefined) {
        this.table.querySelectorAll('th[data-sort]').forEach((th) => {
          th.style.cursor = 'pointer';
          th.addEventListener('click', () => this._sort(th));
        });
      }

      // 行选中（data-selectable 表格）
      if (this.wrapper.dataset.selectable !== undefined && this.tbody) {
        this.tbody.querySelectorAll('tr[data-row]').forEach((row) => {
          row.addEventListener('click', () => {
            const selected = row.classList.toggle('selected');
            row.setAttribute('aria-selected', selected ? 'true' : 'false');
            this.wrapper.dispatchEvent(new CustomEvent('table:select', {
              detail: { row, selected },
              bubbles: true,
            }));
          });
        });
      }

      // 展开行（data-expandable 表格，行内含 .row-expander）
      if (this.wrapper.dataset.expandable !== undefined && this.tbody) {
        this.tbody.querySelectorAll('.row-expander').forEach((btn) => {
          btn.addEventListener('click', () => {
            const row = btn.closest('tr');
            const detail = row.nextElementSibling;
            const expanded = row.classList.toggle('expanded');
            btn.setAttribute('aria-expanded', expanded ? 'true' : 'false');
            if (detail && detail.classList.contains('row-detail')) {
              detail.hidden = !expanded;
            }
          });
        });
      }
    }

    _initStickyHeader() {
      if (this.wrapper.dataset.stickyHeader !== undefined) {
        this.wrapper.style.maxHeight = this.wrapper.dataset.maxHeight || '400px';
        this.wrapper.style.overflowY = 'auto';
        const thead = this.table.querySelector('thead');
        if (thead) thead.style.position = 'sticky';
        if (thead) thead.style.top = '0';
        if (thead) thead.style.zIndex = '1';
      }
    }

    _sort(th) {
      const key = th.dataset.sort;
      const type = th.dataset.sortType || 'string';
      const current = th.dataset.direction || '';
      const direction = current === 'asc' ? 'desc' : 'asc';
      th.dataset.direction = direction;

      // 清除其他 th 的排序状态
      this.table.querySelectorAll('th[data-sort]').forEach((other) => {
        if (other !== th) {
          delete other.dataset.direction;
          const ind = other.querySelector('.sort-indicator');
          if (ind) ind.textContent = '';
        }
      });

      // 指示器
      const indicator = th.querySelector('.sort-indicator') || (() => {
        const span = document.createElement('span');
        span.className = 'sort-indicator';
        th.appendChild(span);
        return span;
      })();
      indicator.textContent = direction === 'asc' ? ' ↑' : ' ↓';

      // 排序行
      if (this.tbody) {
        const rows = Array.from(this.tbody.querySelectorAll('tr[data-row]'));
        rows.sort((a, b) => {
          const av = a.querySelector(`td:nth-child(${this._colIndex(th)})`)?.textContent.trim() || '';
          const bv = b.querySelector(`td:nth-child(${this._colIndex(th)})`)?.textContent.trim() || '';
          if (type === 'number') return direction === 'asc' ? Number(av) - Number(bv) : Number(bv) - Number(av);
          return direction === 'asc' ? av.localeCompare(bv, 'zh-CN') : bv.localeCompare(av, 'zh-CN');
        });
        rows.forEach((row) => this.tbody.appendChild(row));
      }

      this.wrapper.dispatchEvent(new CustomEvent('table:sort', {
        detail: { key, direction },
        bubbles: true,
      }));
    }

    _colIndex(th) {
      const theadRow = th.closest('tr');
      return Array.from(theadRow.children).indexOf(th) + 1;
    }

    static initAll() {
      document.querySelectorAll(SELECTOR).forEach((el) => {
        if (!el.__table) el.__table = new Table(el);
      });
    }
  }

  window.Table = Table;
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', Table.initAll);
  } else {
    Table.initAll();
  }
})();

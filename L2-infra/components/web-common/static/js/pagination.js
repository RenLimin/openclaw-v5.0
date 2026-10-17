/* ============================================================
   pagination.js — 分页组件
   组件：web-common (L2) · v2.0 · ADR-033
   功能：页码跳转 / 上一页下一页 / 每页大小选择 / 自动生成页码
   用法：
     <nav class="pagination" data-pagination
          data-total="100" data-page-size="10" data-current="1">
       <button class="btn btn-sm" data-page-prev>上一页</button>
       <span class="page-numbers" data-page-numbers></span>
       <button class="btn btn-sm" data-page-next>下一页</button>
       <select data-page-size-select>
         <option value="10">10/页</option>
         <option value="20">20/页</option>
         <option value="50">50/页</option>
       </select>
     </nav>
   JS API:
     Pagination.initAll() — 初始化所有分页
   事件：翻页触发 'pagination:change'（detail: {page, pageSize}）
   ============================================================ */
(function () {
  'use strict';

  const SELECTOR = '[data-pagination]';

  class Pagination {
    constructor(el) {
      this.el = el;
      this.current = parseInt(el.dataset.current || '1', 10);
      this.pageSize = parseInt(el.dataset.pageSize || '10', 10);
      this.total = parseInt(el.dataset.total || '0', 10);
      this.maxButtons = parseInt(el.dataset.maxButtons || '5', 10);
      this._bindEvents();
      this.render();
    }

    get totalPages() {
      return Math.max(1, Math.ceil(this.total / this.pageSize));
    }

    _bindEvents() {
      const prev = this.el.querySelector('[data-page-prev]');
      const next = this.el.querySelector('[data-page-next]');
      const sizeSelect = this.el.querySelector('[data-page-size-select]');
      if (prev) prev.addEventListener('click', () => this.go(this.current - 1));
      if (next) next.addEventListener('click', () => this.go(this.current + 1));
      if (sizeSelect) {
        sizeSelect.value = String(this.pageSize);
        sizeSelect.addEventListener('change', () => {
          this.pageSize = parseInt(sizeSelect.value, 10);
          this.current = 1;
          this.render();
          this._emit();
        });
      }
    }

    _pageNumbers() {
      const total = this.totalPages;
      const current = this.current;
      const max = this.maxButtons;
      let start = Math.max(1, current - Math.floor(max / 2));
      let end = Math.min(total, start + max - 1);
      start = Math.max(1, end - max + 1);

      const pages = [];
      if (start > 1) pages.push({ page: 1, type: 'page' });
      if (start > 2) pages.push({ page: '…', type: 'ellipsis' });
      for (let i = start; i <= end; i++) pages.push({ page: i, type: 'page' });
      if (end < total - 1) pages.push({ page: '…', type: 'ellipsis' });
      if (end < total) pages.push({ page: total, type: 'page' });
      return pages;
    }

    render() {
      const container = this.el.querySelector('[data-page-numbers]');
      if (container) {
        container.innerHTML = '';
        this._pageNumbers().forEach((item) => {
          if (item.type === 'ellipsis') {
            const span = document.createElement('span');
            span.className = 'page-ellipsis';
            span.textContent = '…';
            container.appendChild(span);
          } else {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'page-btn' + (item.page === this.current ? ' active' : '');
            btn.textContent = item.page;
            if (item.page === this.current) {
              btn.setAttribute('aria-current', 'page');
              btn.disabled = true;
            } else {
              btn.addEventListener('click', () => this.go(item.page));
            }
            container.appendChild(btn);
          }
        });
      }

      // 更新上一页/下一页状态
      const prev = this.el.querySelector('[data-page-prev]');
      const next = this.el.querySelector('[data-page-next]');
      if (prev) prev.disabled = this.current <= 1;
      if (next) next.disabled = this.current >= this.totalPages;

      // 更新信息文本
      const info = this.el.querySelector('[data-page-info]');
      if (info) {
        const start = this.total === 0 ? 0 : (this.current - 1) * this.pageSize + 1;
        const end = Math.min(this.total, this.current * this.pageSize);
        info.textContent = `${start}-${end} / ${this.total} 条`;
      }
    }

    go(page) {
      if (page < 1 || page > this.totalPages || page === this.current) return;
      this.current = page;
      this.render();
      this._emit();
    }

    _emit() {
      this.el.dispatchEvent(new CustomEvent('pagination:change', {
        detail: { page: this.current, pageSize: this.pageSize },
        bubbles: true,
      }));
    }

    static initAll() {
      document.querySelectorAll(SELECTOR).forEach((el) => {
        if (!el.__pagination) el.__pagination = new Pagination(el);
      });
    }
  }

  window.Pagination = Pagination;
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', Pagination.initAll);
  } else {
    Pagination.initAll();
  }
})();

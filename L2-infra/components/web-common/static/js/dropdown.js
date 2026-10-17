/* ============================================================
   dropdown.js — 下拉菜单组件
   组件：web-common (L2) · v2.0 · ADR-033
   功能：点击展开 / 点击外部关闭 / 分组 / 搜索过滤 / 键盘导航
   用法：
     <div class="dropdown" data-dropdown>
       <button class="dropdown-trigger btn" data-dropdown-toggle>菜单</button>
       <div class="dropdown-menu" data-dropdown-menu>
         <div class="dropdown-item" data-value="a">选项 A</div>
         <div class="dropdown-item" data-value="b">选项 B</div>
       </div>
     </div>
   JS API:
     Dropdown.init(el)            — 初始化单个下拉
     Dropdown.initAll()           — 初始化页面所有下拉（DOMContentLoaded 自动调用）
     Dropdown.toggle(el)          — 切换展开/收起
     Dropdown.closeAll()          — 关闭所有下拉
   事件：选择后触发 'dropdown:select'（detail: {value, text, el}）
   ============================================================ */
(function () {
  'use strict';

  const SELECTOR = '[data-dropdown]';
  const TOGGLE_SELECTOR = '[data-dropdown-toggle]';
  const MENU_SELECTOR = '[data-dropdown-menu]';
  const ITEM_SELECTOR = '[data-dropdown-item], .dropdown-item';

  class Dropdown {
    constructor(el) {
      this.el = el;
      this.toggle = el.querySelector(TOGGLE_SELECTOR);
      this.menu = el.querySelector(MENU_SELECTOR);
      if (!this.toggle || !this.menu) return;

      this.isOpen = false;
      // 初始化 ARIA
      this.toggle.setAttribute('aria-haspopup', 'true');
      this.toggle.setAttribute('aria-expanded', 'false');
      this._bindEvents();
    }

    _bindEvents() {
      // 点击触发器切换
      this.toggle.addEventListener('click', (e) => {
        e.stopPropagation();
        this.isOpen ? this.close() : this.open();
      });

      // 点击菜单项
      this.menu.addEventListener('click', (e) => {
        const item = e.target.closest(ITEM_SELECTOR);
        if (!item) return;
        const value = item.dataset.value || item.textContent.trim();
        const detail = { value, text: item.textContent.trim(), el: item };
        this.el.dispatchEvent(new CustomEvent('dropdown:select', { detail, bubbles: true }));
        if (item.dataset.keepOpen !== 'true') this.close();
      });

      // 键盘导航
      this.toggle.addEventListener('keydown', (e) => {
        if (e.key === 'ArrowDown' || e.key === 'ArrowUp' || e.key === 'Enter' || e.key === ' ') {
          if (e.key === 'Enter' || e.key === ' ') {
            // 让按钮原生行为处理展开
            return;
          }
          e.preventDefault();
          this.open();
          this._focusFirstItem();
        }
      });

      this.menu.addEventListener('keydown', (e) => {
        const items = this._visibleItems();
        if (!items.length) return;
        const idx = items.indexOf(document.activeElement);
        if (e.key === 'ArrowDown') {
          e.preventDefault();
          items[(idx + 1) % items.length].focus();
        } else if (e.key === 'ArrowUp') {
          e.preventDefault();
          items[(idx - 1 + items.length) % items.length].focus();
        } else if (e.key === 'Escape') {
          this.close();
          this.toggle.focus();
        }
      });

      // 搜索过滤（菜单内有输入框时）
      const searchInput = this.menu.querySelector('[data-dropdown-search]');
      if (searchInput) {
        searchInput.addEventListener('input', () => this._filter(searchInput.value));
      }
    }

    open() {
      Dropdown.closeAll();
      this.menu.classList.add('open');
      this.el.classList.add('open');
      this.toggle.setAttribute('aria-expanded', 'true');
      this.isOpen = true;
    }

    close() {
      this.menu.classList.remove('open');
      this.el.classList.remove('open');
      this.toggle.setAttribute('aria-expanded', 'false');
      this.isOpen = false;
    }

    _focusFirstItem() {
      const items = this._visibleItems();
      if (items.length) items[0].focus();
    }

    _visibleItems() {
      return Array.from(this.menu.querySelectorAll(ITEM_SELECTOR)).filter(
        (el) => el.style.display !== 'none' && !el.hasAttribute('hidden')
      );
    }

    _filter(query) {
      const q = query.trim().toLowerCase();
      this.menu.querySelectorAll(ITEM_SELECTOR).forEach((item) => {
        const text = item.textContent.trim().toLowerCase();
        item.style.display = !q || text.includes(q) ? '' : 'none';
      });
    }

    static closeAll() {
      document.querySelectorAll(SELECTOR).forEach((el) => {
        const menu = el.querySelector(MENU_SELECTOR);
        if (menu) menu.classList.remove('open');
        el.classList.remove('open');
        const toggle = el.querySelector(TOGGLE_SELECTOR);
        if (toggle) toggle.setAttribute('aria-expanded', 'false');
      });
    }

    static init(el) {
      if (el.__dropdown) return el.__dropdown;
      el.__dropdown = new Dropdown(el);
      return el.__dropdown;
    }

    static initAll() {
      document.querySelectorAll(SELECTOR).forEach((el) => Dropdown.init(el));
    }
  }

  // 点击外部关闭
  document.addEventListener('click', (e) => {
    if (!e.target.closest(SELECTOR)) Dropdown.closeAll();
  });

  // Esc 关闭
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') Dropdown.closeAll();
  });

  window.Dropdown = Dropdown;
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', Dropdown.initAll);
  } else {
    Dropdown.initAll();
  }
})();

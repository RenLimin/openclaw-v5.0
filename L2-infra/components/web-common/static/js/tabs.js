/* ============================================================
   tabs.js — 标签页组件
   组件：web-common (L2) · v2.0 · ADR-033
   功能：切换激活态 / 键盘方向键导航 / 保存历史位置（hash 或 localStorage）
   用法：
     <div class="tabs" data-tabs>
       <div class="tabs-nav" role="tablist">
         <button class="tabs-tab active" role="tab" data-tab="tab1">标签 1</button>
         <button class="tabs-tab" role="tab" data-tab="tab2">标签 2</button>
       </div>
       <div class="tabs-panels">
         <div class="tabs-panel active" role="tabpanel" data-panel="tab1">内容 1</div>
         <div class="tabs-panel" role="tabpanel" data-panel="tab2">内容 2</div>
       </div>
     </div>
   JS API:
     Tabs.initAll() — 初始化所有 tabs
   事件：切换后触发 'tabs:change'（detail: {tab, panel}）
   ============================================================ */
(function () {
  'use strict';

  const SELECTOR = '[data-tabs]';

  class Tabs {
    constructor(el) {
      this.el = el;
      this.tabs = Array.from(el.querySelectorAll('[data-tab]'));
      this.panels = Array.from(el.querySelectorAll('[data-panel]'));
      if (!this.tabs.length) return;
      this._bindEvents();
      this._restore();
    }

    _bindEvents() {
      this.tabs.forEach((tab) => {
        tab.addEventListener('click', () => this.activate(tab.dataset.tab));
        tab.addEventListener('keydown', (e) => {
          const idx = this.tabs.indexOf(tab);
          if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
            e.preventDefault();
            const next = e.key === 'ArrowRight'
              ? (idx + 1) % this.tabs.length
              : (idx - 1 + this.tabs.length) % this.tabs.length;
            this.activate(this.tabs[next].dataset.tab);
            this.tabs[next].focus();
          } else if (e.key === 'Home') {
            e.preventDefault();
            this.activate(this.tabs[0].dataset.tab);
            this.tabs[0].focus();
          } else if (e.key === 'End') {
            e.preventDefault();
            this.activate(this.tabs[this.tabs.length - 1].dataset.tab);
            this.tabs[this.tabs.length - 1].focus();
          }
        });
      });
    }

    activate(name) {
      this.tabs.forEach((tab) => {
        const active = tab.dataset.tab === name;
        tab.classList.toggle('active', active);
        tab.setAttribute('aria-selected', active ? 'true' : 'false');
        if (active) tab.setAttribute('tabindex', '0');
        else tab.setAttribute('tabindex', '-1');
      });
      this.panels.forEach((panel) => {
        const active = panel.dataset.panel === name;
        panel.classList.toggle('active', active);
        panel.hidden = !active;
      });
      this._save(name);
      this.el.dispatchEvent(new CustomEvent('tabs:change', {
        detail: { tab: name },
        bubbles: true
      }));
    }

    _save(name) {
      try {
        const key = this.el.dataset.tabsKey || '__tabs_active';
        if (this.el.dataset.tabsHash === 'true') {
          if (location.hash !== `#${name}`) history.replaceState(null, '', `#${name}`);
        } else {
          localStorage.setItem(key, name);
        }
      } catch (e) { /* 隐私模式忽略 */ }
    }

    _restore() {
      let name = null;
      try {
        const key = this.el.dataset.tabsKey || '__tabs_active';
        name = this.el.dataset.tabsHash === 'true'
          ? (location.hash || '').slice(1)
          : localStorage.getItem(key);
      } catch (e) { /* ignore */ }
      if (!name || !this.tabs.some((t) => t.dataset.tab === name)) {
        name = (this.el.dataset.defaultTab) || this.tabs[0].dataset.tab;
      }
      this.activate(name);
    }

    static initAll() {
      document.querySelectorAll(SELECTOR).forEach((el) => {
        if (!el.__tabs) el.__tabs = new Tabs(el);
      });
    }
  }

  window.Tabs = Tabs;
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', Tabs.initAll);
  } else {
    Tabs.initAll();
  }
})();

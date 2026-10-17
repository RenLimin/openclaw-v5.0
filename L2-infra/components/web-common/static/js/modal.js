/* ============================================================
   modal.js — 模态弹窗组件
   组件：web-common (L2) · v2.0 · ADR-033
   功能：打开/关闭 / 蒙层点击关闭 / Esc 关闭 / 焦点管理 / 滚动锁定
   用法：
     <div class="modal-overlay" id="myModal" data-modal>
       <div class="modal-content" role="dialog" aria-modal="true">
         <div class="modal-header">...</div>
         <div class="modal-body">...</div>
         <div class="modal-footer">...</div>
       </div>
     </div>
   JS API:
     Modal.open(id)     — 打开弹窗
     Modal.close(id)    — 关闭弹窗
     Modal.closeTop()   — 关闭最上层弹窗
   ============================================================ */
(function () {
  'use strict';

  class Modal {
    constructor(el) {
      this.el = el;
      this._lastFocused = null;
      this._bindEvents();
    }

    _bindEvents() {
      // 蒙层点击关闭（点击背景而非内容）
      this.el.addEventListener('click', (e) => {
        if (e.target === this.el) this.close();
      });

      // 关闭按钮
      this.el.querySelectorAll('[data-modal-close], .modal-close, .modal-header .close').forEach((btn) => {
        btn.addEventListener('click', () => this.close());
      });

      // Esc 关闭
      this.el.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') this.close();
      });
    }

    open() {
      this._lastFocused = document.activeElement;
      this.el.classList.add('open');
      this.el.setAttribute('aria-hidden', 'false');
      document.body.classList.add('modal-open'); // 锁定滚动
      this.el.style.display = 'flex';
      // 焦点移入
      const focusTarget = this.el.querySelector('[data-modal-focus], input, button, select, textarea, a[href]');
      if (focusTarget) focusTarget.focus();
    }

    close() {
      if (this.el.style.display === 'none') return;
      this.el.classList.remove('open');
      this.el.setAttribute('aria-hidden', 'true');
      this.el.style.display = 'none';
      // 判断是否还有其他打开的 modal
      const anyOpen = document.querySelectorAll('.modal-overlay.open').length > 0;
      if (!anyOpen) document.body.classList.remove('modal-open');
      if (this._lastFocused) this._lastFocused.focus();
    }

    static open(id) {
      const el = typeof id === 'string' ? document.getElementById(id) : id;
      if (!el) {
        console.warn(`Modal.open: #${id} 不存在`);
        return;
      }
      if (!el.__modal) el.__modal = new Modal(el);
      el.__modal.open();
    }

    static close(id) {
      const el = typeof id === 'string' ? document.getElementById(id) : id;
      if (!el || !el.__modal) return;
      el.__modal.close();
    }

    static closeTop() {
      const openModals = document.querySelectorAll('.modal-overlay.open');
      if (openModals.length) Modal.close(openModals[openModals.length - 1]);
    }

    static initAll() {
      document.querySelectorAll('[data-modal]').forEach((el) => {
        if (!el.__modal) el.__modal = new Modal(el);
      });
    }
  }

  // 全局 keydown：Esc 关闭最上层
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      const openModals = document.querySelectorAll('.modal-overlay.open');
      if (openModals.length) Modal.close(openModals[openModals.length - 1]);
    }
  });

  // 兼容旧版全局函数（macro 内联 JS 使用）
  window.openModal = Modal.open;
  window.closeModal = Modal.close;

  window.Modal = Modal;
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', Modal.initAll);
  } else {
    Modal.initAll();
  }
})();

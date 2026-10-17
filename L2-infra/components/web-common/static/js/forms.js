/* ============================================================
   forms.js — 表单校验组件
   组件：web-common (L2) · v2.0 · ADR-033
   功能：客户端校验 / 错误状态 / 实时反馈 / 提交拦截
   用法：
     <form data-validate>
       <div class="form-group">
         <label>邮箱</label>
         <input name="email" type="email" data-rules="required|email">
         <div class="form-error" data-error-for="email"></div>
       </div>
       <button type="submit">提交</button>
     </form>
   JS API:
     Forms.validate(form)   — 校验整个表单，返回 {valid, errors}
     Forms.validateField(el) — 校验单个字段
   事件：校验失败触发 'form:invalid'（detail: {form, errors}）
   ============================================================ */
(function () {
  'use strict';

  const RULES = {
    required: {
      validate: (value, el) => value !== undefined && String(value).trim() !== '',
      message: '该字段不能为空',
    },
    email: {
      validate: (value) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value),
      message: '请输入有效的邮箱地址',
    },
    url: {
      validate: (value) => !value || /^https?:\/\/\S+$/.test(value),
      message: '请输入有效的 URL',
    },
    number: {
      validate: (value) => !value || !isNaN(Number(value)),
      message: '请输入数字',
    },
    min: {
      validate: (value, el, param) => !value || Number(value) >= Number(param),
      message: (param) => `不能小于 ${param}`,
    },
    max: {
      validate: (value, el, param) => !value || Number(value) <= Number(param),
      message: (param) => `不能大于 ${param}`,
    },
    minLength: {
      validate: (value, el, param) => !value || String(value).length >= Number(param),
      message: (param) => `至少输入 ${param} 个字符`,
    },
    maxLength: {
      validate: (value, el, param) => !value || String(value).length <= Number(param),
      message: (param) => `最多输入 ${param} 个字符`,
    },
    pattern: {
      validate: (value, el, param) => !value || new RegExp(param).test(value),
      message: '格式不正确',
    },
    match: {
      validate: (value, el, param) => {
        const target = document.querySelector(param);
        return !target || value === target.value;
      },
      message: '两次输入不一致',
    },
  };

  class Forms {
    constructor(form) {
      this.form = form;
      this.fields = Array.from(form.querySelectorAll('[data-rules]'));
      this._bindEvents();
    }

    _bindEvents() {
      // 失焦时校验单个字段
      this.fields.forEach((field) => {
        field.addEventListener('blur', () => this.validateField(field));
        field.addEventListener('input', () => {
          if (field.classList.contains('is-invalid')) this.validateField(field);
        });
      });

      // 提交拦截
      this.form.addEventListener('submit', (e) => {
        const result = this.validate();
        if (!result.valid) {
          e.preventDefault();
          e.stopPropagation();
          this.form.dispatchEvent(new CustomEvent('form:invalid', {
            detail: { form: this.form, errors: result.errors },
            bubbles: true,
          }));
          // 聚焦第一个错误字段
          const firstInvalid = this.form.querySelector('.is-invalid');
          if (firstInvalid) firstInvalid.focus();
        }
      });
    }

    _parseRules(field) {
      const rulesStr = field.dataset.rules || '';
      return rulesStr.split('|').filter(Boolean).map((rule) => {
        const [name, param] = rule.split(':');
        return { name, param };
      });
    }

    validateField(field) {
      const value = field.value;
      const errors = [];
      this._parseRules(field).forEach(({ name, param }) => {
        const rule = RULES[name];
        if (!rule) return;
        if (!rule.validate(value, field, param)) {
          errors.push(typeof rule.message === 'function' ? rule.message(param) : rule.message);
        }
      });
      this._setState(field, errors);
      return errors;
    }

    validate() {
      const errors = {};
      let valid = true;
      this.fields.forEach((field) => {
        const fieldErrors = this.validateField(field);
        if (fieldErrors.length) {
          valid = false;
          errors[field.name || field.id] = fieldErrors;
        }
      });
      return { valid, errors };
    }

    _setState(field, errors) {
      const group = field.closest('.form-group');
      if (errors.length) {
        field.classList.add('is-invalid');
        field.setAttribute('aria-invalid', 'true');
        if (group) {
          const errorEl = group.querySelector('[data-error-for], .form-error');
          if (errorEl) errorEl.textContent = errors[0];
          group.classList.add('has-error');
        }
      } else {
        field.classList.remove('is-invalid');
        field.removeAttribute('aria-invalid');
        if (group) {
          const errorEl = group.querySelector('[data-error-for], .form-error');
          if (errorEl) errorEl.textContent = '';
          group.classList.remove('has-error');
        }
      }
    }

    static validate(form) {
      if (!form.__forms) form.__forms = new Forms(form);
      return form.__forms.validate();
    }

    static validateField(field) {
      const form = field.closest('[data-validate]') || field.form;
      if (!form) return [];
      if (!form.__forms) form.__forms = new Forms(form);
      return form.__forms.validateField(field);
    }

    static initAll() {
      document.querySelectorAll('[data-validate]').forEach((form) => {
        if (!form.__forms) form.__forms = new Forms(form);
      });
    }
  }

  window.Forms = Forms;
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', Forms.initAll);
  } else {
    Forms.initAll();
  }
})();

/* ============================================================
   datepicker.js — 基于 flatpickr 的日期选择器
   自动增强所有 input[type=date] / input[type=month]
   用法：
     1. 基础：<input type="date"> → 自动升级
     2. 范围：两个 input 加 data-range="from" / data-range="to"
     3. 快捷选项：data-shortcuts="true"
     4. 月份选择：<input type="month">
     5. 禁用手动改：data-static="true"
   ============================================================ */

(function () {
  'use strict';

  // 中文本地化配置（flatpickr 内置了 locale 字符串接口）
  const zhLocale = {
    weekdays: {
      shorthand: ['日', '一', '二', '三', '四', '五', '六'],
      longhand: ['星期日', '星期一', '星期二', '星期三', '星期四', '星期五', '星期六']
    },
    months: {
      shorthand: ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月'],
      longhand: ['一月', '二月', '三月', '四月', '五月', '六月', '七月', '八月', '九月', '十月', '十一月', '十二月']
    },
    rangeSeparator: ' 至 ',
    weekAbbreviation: '周',
    scrollTitle: '滚动切换',
    toggleTitle: '点击切换',
    amPM: ['上午', '下午'],
    yearAriaLabel: '年',
    monthAriaLabel: '月',
    hourAriaLabel: '时',
    minuteAriaLabel: '分',
    secondAriaLabel: '秒',
    firstDayOfWeek: 1  // 周一开始
  };

  // 快捷选项
  function getShortcuts() {
    const today = new Date();
    const toDate = (d) => d;
    return [
      {
        text: '今天',
        onClick: function () { return today; }
      },
      {
        text: '昨天',
        onClick: function () {
          const d = new Date(today);
          d.setDate(d.getDate() - 1);
          return d;
        }
      },
      {
        text: '最近7天',
        onClick: function () {
          const d = new Date(today);
          d.setDate(d.getDate() - 6);
          return [d, today];
        }
      },
      {
        text: '最近30天',
        onClick: function () {
          const d = new Date(today);
          d.setDate(d.getDate() - 29);
          return [d, today];
        }
      },
      {
        text: '本月',
        onClick: function () {
          const start = new Date(today.getFullYear(), today.getMonth(), 1);
          const end = new Date(today.getFullYear(), today.getMonth() + 1, 0);
          return [start, end];
        }
      },
      {
        text: '上月',
        onClick: function () {
          const start = new Date(today.getFullYear(), today.getMonth() - 1, 1);
          const end = new Date(today.getFullYear(), today.getMonth(), 0);
          return [start, end];
        }
      }
    ];
  }

  // 检测暗色模式
  function isDark() {
    return document.documentElement.classList.contains('dark') ||
           document.body.classList.contains('dark') ||
           (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches);
  }

  // 基础配置
  function baseConfig(el) {
    const cfg = {
      locale: zhLocale,
      dateFormat: 'Y-m-d',
      altFormat: 'Y-m-d',
      allowInput: true,
      clickOpens: true,
      wrap: false,
      static: false,
      position: 'auto',
      theme: isDark() ? 'dark' : 'light'
    };

    // data 属性配置
    if (el.dataset.static === 'true') cfg.static = true;
    if (el.dataset.allowInput === 'false') cfg.allowInput = false;
    if (el.dataset.dateFormat) cfg.dateFormat = el.dataset.dateFormat;
    if (el.dataset.minDate) cfg.minDate = el.dataset.minDate;
    if (el.dataset.maxDate) cfg.maxDate = el.dataset.maxDate;
    if (el.dataset.defaultDate) cfg.defaultDate = el.dataset.defaultDate;

    // 快捷选项
    if (el.dataset.shortcuts === 'true') {
      cfg.plugins = cfg.plugins || [];
      // shortcurts 直接写在配置里（flatpickr 支持）
    }

    return cfg;
  }

  // 初始化单个日期选择器
  function initSingle(el) {
    if (el._flatpickr) return;

    const cfg = baseConfig(el);

    // 快捷选项 — 用 onChange 不够，直接用 flatpickr 官方 shortcuts 写法
    if (el.dataset.shortcuts === 'true') {
      // 创建快捷按钮容器
      cfg.onOpen = function (selectedDates, dateStr, instance) {
        const cal = instance.calendarContainer;
        if (cal.querySelector('.dp-shortcuts')) return;

        const shortcuts = document.createElement('div');
        shortcuts.className = 'dp-shortcuts';
        shortcuts.style.cssText = 'display:flex;flex-wrap:wrap;gap:4px;padding:8px 12px;border-bottom:1px solid var(--c-border, #e5e7eb);';

        const items = getShortcuts();
        items.forEach(function (item) {
          const btn = document.createElement('button');
          btn.type = 'button';
          btn.textContent = item.text;
          btn.style.cssText = 'font-size:12px;padding:2px 8px;border:1px solid var(--c-border, #d1d5db);border-radius:4px;background:var(--c-surface, #fff);color:var(--c-text-secondary, #6b7280);cursor:pointer;';
          btn.onmouseover = function () {
            btn.style.background = 'var(--c-surface-2, #f3f4f6)';
          };
          btn.onmouseout = function () {
            btn.style.background = 'var(--c-surface, #fff)';
          };
          btn.onclick = function (e) {
            e.stopPropagation();
            const result = item.onClick();
            if (Array.isArray(result) && instance.mode === 'range') {
              instance.setDate(result);
            } else if (Array.isArray(result)) {
              instance.setDate(result[0]);
            } else {
              instance.setDate(result);
            }
          };
          shortcuts.appendChild(btn);
        });

        cal.querySelector('.flatpickr-innerContainer').before(shortcuts);
      };
    }

    flatpickr(el, cfg);
  }

  // 初始化范围选择器
  function initRange(fromEl, toEl) {
    if (fromEl._flatpickr) return;

    const cfg = baseConfig(fromEl);
    cfg.mode = 'range';
    cfg.dateFormat = 'Y-m-d';
    cfg.allowInput = true;

    // 双输入框联动的 range 模式
    // flatpickr range 模式原生支持单输入框显示 "start to end"
    // 我们用 from 输入框承载，to 输入框保持同步

    // 快捷选项（范围模式专用）
    if (fromEl.dataset.shortcuts === 'true' || toEl.dataset.shortcuts === 'true') {
      cfg.onOpen = function (selectedDates, dateStr, instance) {
        const cal = instance.calendarContainer;
        if (cal.querySelector('.dp-shortcuts')) return;

        const shortcuts = document.createElement('div');
        shortcuts.className = 'dp-shortcuts';
        shortcuts.style.cssText = 'display:flex;flex-wrap:wrap;gap:4px;padding:8px 12px;border-bottom:1px solid var(--c-border, #e5e7eb);';

        const items = getShortcuts().filter(function (item) {
          return item.onClick.length > 0 || true;
        });

        items.forEach(function (item) {
          const btn = document.createElement('button');
          btn.type = 'button';
          btn.textContent = item.text;
          btn.style.cssText = 'font-size:12px;padding:2px 8px;border:1px solid var(--c-border, #d1d5db);border-radius:4px;background:var(--c-surface, #fff);color:var(--c-text-secondary, #6b7280);cursor:pointer;';
          btn.onmouseover = function () { btn.style.background = 'var(--c-surface-2, #f3f4f6)'; };
          btn.onmouseout = function () { btn.style.background = 'var(--c-surface, #fff)'; };
          btn.onclick = function (e) {
            e.stopPropagation();
            const result = item.onClick();
            if (Array.isArray(result)) {
              instance.setDate(result);
            }
          };
          shortcuts.appendChild(btn);
        });

        cal.querySelector('.flatpickr-innerContainer').before(shortcuts);
      };
    }

    cfg.onChange = function (selectedDates, dateStr) {
      if (selectedDates.length === 2) {
        const fmt = function (d) {
          return d.getFullYear() + '-' +
            String(d.getMonth() + 1).padStart(2, '0') + '-' +
            String(d.getDate()).padStart(2, '0');
        };
        fromEl.value = fmt(selectedDates[0]);
        toEl.value = fmt(selectedDates[1]);
      } else if (selectedDates.length === 1) {
        const fmt = function (d) {
          return d.getFullYear() + '-' +
            String(d.getMonth() + 1).padStart(2, '0') + '-' +
            String(d.getDate()).padStart(2, '0');
        };
        fromEl.value = fmt(selectedDates[0]);
      }
    };

    // 初始值
    if (fromEl.value && toEl.value) {
      cfg.defaultDate = [fromEl.value, toEl.value];
    } else if (fromEl.value) {
      cfg.defaultDate = fromEl.value;
    }

    flatpickr(fromEl, cfg);

    // to 框点击也打开 from 的选择器
    toEl.addEventListener('focus', function () {
      fromEl._flatpickr.open();
    });
    toEl.addEventListener('click', function () {
      fromEl._flatpickr.open();
    });
  }

  // 初始化月份选择器
  function initMonthPicker(el) {
    if (el._flatpickr) return;

    // flatpickr 不能直接接管 type="month"，先改成 text，再用 Y-m 格式模拟
    // 这样可以彻底移除原生的 calendar picker indicator
    const originalValue = el.value;
    el.type = 'text';
    el.value = originalValue;
    el.dataset.originalType = 'month';

    const cfg = baseConfig(el);
    cfg.dateFormat = 'Y-m';
    cfg.allowInput = true;
    cfg.altInput = false;

    // 打开时直接显示月份选择视图
    cfg.onOpen = function (selectedDates, dateStr, instance) {
      // 模拟点击月份标题进入月视图
      if (!instance._monthModeInit) {
        instance._monthModeInit = true;
        // flatpickr 没有原生 month 模式，用标准日期选择 + Y-m 格式即可
        // 用户选完某一天后，实际值只保留到月
      }
    };

    // 选完后只保留年月
    cfg.onChange = function (selectedDates, dateStr, instance) {
      if (selectedDates.length > 0) {
        const d = selectedDates[0];
        const ym = d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0');
        el.value = ym;
        instance.setDate(ym, false);
      }
    };

    flatpickr(el, cfg);
  }

  // 主入口
  function initAll(root) {
    root = root || document;

    if (typeof flatpickr === 'undefined') {
      console.warn('[datepicker] flatpickr not loaded');
      return;
    }

    // 范围选择器（成对的 from/to）
    const rangeFroms = root.querySelectorAll('input[data-range="from"]');
    rangeFroms.forEach(function (fromEl) {
      const rangeId = fromEl.dataset.rangeGroup || 'default';
      const toEl = root.querySelector('input[data-range="to"][data-range-group="' + rangeId + '"]');
      if (toEl) {
        initRange(fromEl, toEl);
      } else {
        initSingle(fromEl);
      }
    });

    // 普通日期选择器（排除已被 range 处理的）
    const dateInputs = root.querySelectorAll('input[type="date"]:not([data-range="from"]):not([data-range="to"]):not([data-no-picker])');
    dateInputs.forEach(function (el) {
      if (el._flatpickr) return;
      initSingle(el);
    });

    // 月份选择器
    const monthInputs = root.querySelectorAll('input[type="month"]:not([data-no-picker])');
    monthInputs.forEach(function (el) {
      if (el._flatpickr) return;
      initMonthPicker(el);
    });
  }

  // 自动初始化
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { initAll(); });
  } else {
    initAll();
  }

  // 暴露全局方法
  window.DatePicker = {
    init: initAll,
    initSingle: initSingle,
    initRange: initRange,
    // 暴露给动态生成的内容用
    refresh: function () { initAll(); }
  };
})();

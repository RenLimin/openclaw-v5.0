/**
 * theme.js — 深浅主题切换
 *
 * 依赖全局变量 window.__WEB_COMMON_STORAGE_KEY__
 * （由 base_layout 宏在页面中注入）
 *
 * API:
 *   window.Theme.current       // 当前主题 'light' | 'dark'
 *   window.Theme.set(theme)    // 设置主题
 *   window.Theme.toggle()      // 切换主题
 *   window.Theme.onChange(cb)  // 订阅主题变化
 */
(function() {
    var STORAGE_KEY = window.__WEB_COMMON_STORAGE_KEY__ || 'web-common-theme';
    var html = document.documentElement;
    var listeners = [];

    function getSystemTheme() {
        return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }

    function getSavedTheme() {
        try {
            return localStorage.getItem(STORAGE_KEY);
        } catch (e) {
            return null;
        }
    }

    function applyTheme(theme) {
        html.setAttribute('data-theme', theme);
        // 更新按钮文本（如果存在）
        var btn = document.getElementById('themeToggle');
        if (btn) {
            btn.textContent = theme === 'dark' ? '☀️ 浅色' : '🌙 深色';
        }
        // 通知监听器
        listeners.forEach(function(cb) {
            try { cb(theme); } catch (e) { console.error('Theme listener error:', e); }
        });
    }

    function setTheme(theme) {
        if (theme !== 'light' && theme !== 'dark') return;
        applyTheme(theme);
        try {
            localStorage.setItem(STORAGE_KEY, theme);
        } catch (e) { /* ignore */ }
    }

    function toggleTheme() {
        var current = html.getAttribute('data-theme') || 'light';
        setTheme(current === 'dark' ? 'light' : 'dark');
    }

    function getCurrent() {
        return html.getAttribute('data-theme') || 'light';
    }

    function onChange(cb) {
        if (typeof cb === 'function') {
            listeners.push(cb);
        }
    }

    // 初始化：优先读取本地存储，其次跟随系统
    var saved = getSavedTheme();
    var initial = saved || getSystemTheme();
    applyTheme(initial);

    // 绑定按钮点击
    function bindButton() {
        var btn = document.getElementById('themeToggle');
        if (btn && !btn.__themeBound) {
            btn.addEventListener('click', toggleTheme);
            btn.__themeBound = true;
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', bindButton);
    } else {
        bindButton();
    }

    // 系统主题变化时跟随（仅当用户未手动设置时）
    if (window.matchMedia) {
        window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function(e) {
            if (!getSavedTheme()) {
                applyTheme(e.matches ? 'dark' : 'light');
            }
        });
    }

    // 暴露 API
    window.Theme = {
        get current() { return getCurrent(); },
        set: setTheme,
        toggle: toggleTheme,
        onChange: onChange
    };
})();

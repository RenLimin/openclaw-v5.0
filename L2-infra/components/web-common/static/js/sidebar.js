/* ============================================================
   sidebar.js — 侧边栏折叠/展开 + 拖拽调宽 + 宽度持久化
   依赖: layout.html 中的 #sidebar / #sidebarToggle / #sidebarResizer
   持久化: localStorage (key: <storage_key>:sidebar:state)
   ============================================================ */
(function() {
    'use strict';

    var STORAGE_KEY = (window.__WEB_COMMON_STORAGE_KEY__ || 'web-common') + ':sidebar';
    // 宽度可由宿主页面通过 window 全局覆盖（默认保持 200/56，向后兼容）
    var DEFAULT_WIDTH = window.__SIDEBAR_DEFAULT_WIDTH__ || 200;
    var COLLAPSED_WIDTH = window.__SIDEBAR_COLLAPSED_WIDTH__ || 56;
    var MIN_WIDTH = window.__SIDEBAR_MIN_WIDTH__ || 160;
    var MAX_WIDTH = window.__SIDEBAR_MAX_WIDTH__ || 360;

    var sidebar = document.getElementById('sidebar');
    var toggleBtn = document.getElementById('sidebarToggle');
    var resizer = document.getElementById('sidebarResizer');
    if (!sidebar) return;

    // 初始化折叠按钮 ARIA 状态
    function updateToggleAria(c) {
        if (toggleBtn) {
            toggleBtn.setAttribute('aria-expanded', c ? 'false' : 'true');
            toggleBtn.setAttribute('aria-label', c ? '展开侧边栏' : '收起侧边栏');
        }
    }

    // ---- 状态读写 ----
    function loadState() {
        try {
            return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
        } catch (e) {
            return {};
        }
    }
    function saveState(patch) {
        try {
            var s = loadState();
            Object.assign(s, patch);
            localStorage.setItem(STORAGE_KEY, JSON.stringify(s));
        } catch (e) {}
    }

    var state = loadState();
    var collapsed = state.collapsed === true;
    var savedWidth = state.width || DEFAULT_WIDTH;

    // ---- 应用宽度（通过 CSS 变量） ----
    function applyWidth(w) {
        document.documentElement.style.setProperty('--sidebar-w', w + 'px');
    }

    // ---- 折叠/展开 ----
    function setCollapsed(c) {
        collapsed = c;
        var icon = toggleBtn ? toggleBtn.querySelector('.sidebar-toggle-icon') : null;
        if (c) {
            sidebar.classList.add('collapsed');
            applyWidth(COLLAPSED_WIDTH);
            if (toggleBtn) {
                if (icon) icon.style.transform = 'rotate(90deg)';
                toggleBtn.title = '展开侧边栏';
            }
        } else {
            sidebar.classList.remove('collapsed');
            applyWidth(savedWidth);
            if (toggleBtn) {
                if (icon) icon.style.transform = '';
                toggleBtn.title = '收起侧边栏';
            }
        }
        updateToggleAria(c);
        saveState({ collapsed: c });
    }

    // 初始化
    if (collapsed) {
        sidebar.classList.add('collapsed');
        applyWidth(COLLAPSED_WIDTH);
    } else {
        applyWidth(savedWidth);
    }
    // 初始化按钮状态
    if (toggleBtn) {
        var icon = toggleBtn.querySelector('.sidebar-toggle-icon');
        if (collapsed && icon) icon.style.transform = 'rotate(90deg)';
        toggleBtn.title = collapsed ? '展开侧边栏' : '收起侧边栏';
    }
    updateToggleAria(collapsed);

    // ---- 折叠按钮点击 ----
    if (toggleBtn) {
        toggleBtn.addEventListener('click', function() {
            setCollapsed(!collapsed);
        });
    }

    // ---- 拖拽调宽 ----
    if (resizer) {
        var isDragging = false;
        var startX = 0;
        var startWidth = 0;

        function onMouseDown(e) {
            if (collapsed) return;
            isDragging = true;
            startX = e.clientX;
            startWidth = sidebar.offsetWidth;
            document.body.style.cursor = 'col-resize';
            document.body.style.userSelect = 'none';
            sidebar.style.transition = 'none';
            e.preventDefault();
        }

        function onMouseMove(e) {
            if (!isDragging) return;
            var delta = e.clientX - startX;
            var newWidth = Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, startWidth + delta));
            applyWidth(newWidth);
        }

        function onMouseUp() {
            if (!isDragging) return;
            isDragging = false;
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
            sidebar.style.transition = '';
            var w = sidebar.offsetWidth;
            savedWidth = w;
            saveState({ width: w });
        }

        resizer.addEventListener('mousedown', onMouseDown);
        document.addEventListener('mousemove', onMouseMove);
        document.addEventListener('mouseup', onMouseUp);

        // 双击 resizer 恢复默认宽度
        resizer.addEventListener('dblclick', function() {
            if (collapsed) {
                setCollapsed(false);
            } else {
                savedWidth = DEFAULT_WIDTH;
                applyWidth(DEFAULT_WIDTH);
                saveState({ width: DEFAULT_WIDTH });
            }
        });
    }
})();

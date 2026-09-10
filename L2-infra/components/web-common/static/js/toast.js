/**
 * toast.js — Toast 消息提示
 *
 * API:
 *   window.showToast(message, type, duration)
 *   window.Toast.success(msg, duration)
 *   window.Toast.error(msg, duration)
 *   window.Toast.warning(msg, duration)
 *   window.Toast.info(msg, duration)
 *
 * 依赖 DOM 元素: #toastContainer
 * （不存在时会自动创建）
 */
(function() {
    var ICONS = {
        success: '✅',
        error:   '❌',
        warning: '⚠️',
        info:    'ℹ️'
    };

    function ensureContainer() {
        var container = document.getElementById('toastContainer');
        if (!container) {
            container = document.createElement('div');
            container.id = 'toastContainer';
            container.className = 'toast-container';
            document.body.appendChild(container);
        }
        return container;
    }

    function showToast(message, type, duration) {
        type = type || 'info';
        duration = duration || 3000;

        var container = ensureContainer();
        var toast = document.createElement('div');
        toast.className = 'toast ' + type;
        toast.setAttribute('role', type === 'error' ? 'alert' : 'status');

        var icon = ICONS[type] || ICONS.info;
        toast.innerHTML = '<span>' + icon + '</span><span>' + escapeHtml(message) + '</span>';

        container.appendChild(toast);

        // 自动消失
        setTimeout(function() {
            toast.style.animation = 'fadeOut 0.3s ease-out forwards';
            setTimeout(function() {
                if (toast.parentNode) {
                    toast.parentNode.removeChild(toast);
                }
            }, 300);
        }, duration);

        return toast;
    }

    function escapeHtml(text) {
        var div = document.createElement('div');
        div.appendChild(document.createTextNode(text));
        return div.innerHTML;
    }

    // 全局函数
    window.showToast = showToast;

    // 命名空间 API
    window.Toast = {
        show: showToast,
        success: function(msg, d) { return showToast(msg, 'success', d); },
        error:   function(msg, d) { return showToast(msg, 'error', d); },
        warning: function(msg, d) { return showToast(msg, 'warning', d); },
        info:    function(msg, d) { return showToast(msg, 'info', d); }
    };
})();

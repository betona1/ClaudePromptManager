/* CPM v2 — Inline Edit + AJAX + Service Discovery */

(function() {
    'use strict';

    // CSRF token helper
    function getCookie(name) {
        let val = null;
        document.cookie.split(';').forEach(c => {
            c = c.trim();
            if (c.startsWith(name + '=')) val = decodeURIComponent(c.substring(name.length + 1));
        });
        return val;
    }

    // API fetch with CSRF
    function apiFetch(url, options = {}) {
        const defaults = {
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken'),
            },
        };
        return fetch(url, { ...defaults, ...options, headers: { ...defaults.headers, ...options.headers } });
    }

    // Flash effect
    function flash(el, color) {
        el.style.transition = 'background 0.3s';
        el.style.background = color === 'green' ? '#d1fae5' : '#fee2e2';
        setTimeout(() => { el.style.background = ''; }, 1000);
    }

    // Inline editing: double-click on .editable-cell
    document.addEventListener('dblclick', function(e) {
        const cell = e.target.closest('.editable-cell');
        if (!cell || cell.querySelector('input, textarea')) return;

        const field = cell.dataset.field;
        const id = cell.dataset.id;
        const endpoint = cell.dataset.endpoint;
        const originalText = cell.textContent.trim();
        const isMultiline = cell.dataset.multiline === 'true';

        let input;
        if (isMultiline) {
            input = document.createElement('textarea');
            input.rows = 3;
        } else {
            input = document.createElement('input');
            input.type = 'text';
        }
        input.value = originalText;
        input.className = 'inline-edit-input';
        cell.textContent = '';
        cell.appendChild(input);
        input.focus();
        input.select();

        function save() {
            const newVal = input.value.trim();
            cell.textContent = newVal || originalText;
            if (newVal === originalText) return;

            const body = {};
            body[field] = newVal;

            apiFetch(endpoint + id + '/', {
                method: 'PATCH',
                body: JSON.stringify(body),
            }).then(r => {
                if (r.ok) {
                    flash(cell, 'green');
                } else {
                    cell.textContent = originalText;
                    flash(cell, 'red');
                }
            }).catch(() => {
                cell.textContent = originalText;
                flash(cell, 'red');
            });
        }

        function cancel() {
            cell.textContent = originalText;
        }

        input.addEventListener('keydown', function(ev) {
            if (ev.key === 'Enter' && !isMultiline) { ev.preventDefault(); save(); }
            if (ev.key === 'Enter' && isMultiline && ev.ctrlKey) { ev.preventDefault(); save(); }
            if (ev.key === 'Escape') { cancel(); }
        });
        input.addEventListener('blur', save);
    });

    // Service discovery
    window.discoverServices = function(host) {
        const btn = document.getElementById('btn-discover');
        if (btn) {
            btn.disabled = true;
            btn.textContent = 'Scanning...';
        }

        apiFetch('/api/discover/', {
            method: 'POST',
            body: JSON.stringify({
                host: host || '127.0.0.1',
                port_range: [3000, 12000],
            }),
        }).then(r => r.json()).then(data => {
            alert('Scan complete: ' + data.open_count + ' open ports found on ' + data.host);
            location.reload();
        }).catch(err => {
            alert('Scan failed: ' + err);
            if (btn) { btn.disabled = false; btn.textContent = 'Auto-Discover'; }
        });
    };

})();

/* GitHub Sync — Multi-account Setup page */
(function() {
    'use strict';

    function getCookie(name) {
        var val = null;
        document.cookie.split(';').forEach(function(c) {
            c = c.trim();
            if (c.startsWith(name + '=')) val = decodeURIComponent(c.substring(name.length + 1));
        });
        return val;
    }

    function apiFetch(url, options) {
        options = options || {};
        var defaults = {
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken'),
            },
        };
        var merged = Object.assign({}, defaults, options);
        merged.headers = Object.assign({}, defaults.headers, options.headers || {});
        return fetch(url, merged);
    }

    function escHtml(s) {
        var d = document.createElement('div');
        d.textContent = s;
        return d.innerHTML;
    }

    // Elements
    var accountsList = document.getElementById('gh-accounts-list');
    var accountsEmpty = document.getElementById('gh-accounts-empty');
    var addBtn = document.getElementById('gh-add-btn');
    var addForm = document.getElementById('gh-add-form');
    var addSave = document.getElementById('gh-add-save');
    var addCancel = document.getElementById('gh-add-cancel');
    var addToken = document.getElementById('gh-add-token');
    var addUsername = document.getElementById('gh-add-username');
    var addStatus = document.getElementById('gh-add-status');

    var syncSection = document.getElementById('github-sync-section');
    var syncAccountLabel = document.getElementById('gh-sync-account-label');
    var syncStatus = document.getElementById('github-sync-status');
    var tableWrap = document.getElementById('github-sync-table-wrap');
    var tableEl = document.getElementById('github-sync-table');
    var doSyncBtn = document.getElementById('github-do-sync-btn');
    var doSyncStatus = document.getElementById('github-do-sync-status');
    var checkAll = document.getElementById('github-check-all');
    var hideMatched = document.getElementById('github-hide-matched');
    var hideForks = document.getElementById('github-hide-forks');

    if (!accountsList) return;

    var allRepos = [];
    var activeAccountId = null;

    // ── Account List ──────────────────────────────────────

    function loadAccounts() {
        apiFetch('/api/github/accounts/').then(function(r) { return r.json(); })
        .then(function(data) {
            renderAccounts(data.accounts || []);
        });
    }

    function renderAccounts(accounts) {
        if (accounts.length === 0) {
            accountsList.innerHTML = '';
            accountsEmpty.style.display = 'block';
            return;
        }
        accountsEmpty.style.display = 'none';
        var html = '';
        accounts.forEach(function(a) {
            var avatar = a.avatar_url
                ? '<img src="' + escHtml(a.avatar_url) + '&s=32" class="gh-account-avatar">'
                : '<div class="gh-account-avatar-placeholder">G</div>';
            var displayName = a.display_name ? ' <span class="text-light">(' + escHtml(a.display_name) + ')</span>' : '';
            html += '<div class="gh-account-card" data-id="' + a.id + '">'
                + '<div class="gh-account-info">'
                + avatar
                + '<span class="gh-account-name">' + escHtml(a.username) + displayName + '</span>'
                + '</div>'
                + '<div class="gh-account-actions">'
                + '<button class="btn-sm btn-blue gh-sync-btn" data-id="' + a.id + '" data-username="' + escHtml(a.username) + '">Sync</button>'
                + '<button class="gh-account-delete" data-id="' + a.id + '" data-username="' + escHtml(a.username) + '" title="삭제">&times;</button>'
                + '</div>'
                + '</div>';
        });
        accountsList.innerHTML = html;
    }

    // ── Add Account ───────────────────────────────────────

    addBtn.addEventListener('click', function() {
        addForm.style.display = addForm.style.display === 'none' ? 'block' : 'none';
        if (addForm.style.display === 'block') {
            addToken.value = '';
            addUsername.value = '';
            addStatus.style.display = 'none';
            addToken.focus();
        }
    });

    addCancel.addEventListener('click', function() {
        addForm.style.display = 'none';
    });

    addSave.addEventListener('click', function() {
        var token = addToken.value.trim();
        var username = addUsername.value.trim();
        if (!token || !username) {
            showAddStatus('Token과 Username을 입력하세요.', 'red');
            return;
        }
        addSave.disabled = true;
        addSave.textContent = '확인중...';

        apiFetch('/api/github/accounts/add/', {
            method: 'POST',
            body: JSON.stringify({ token: token, username: username }),
        }).then(function(r) { return r.json(); })
        .then(function(data) {
            addSave.disabled = false;
            addSave.textContent = '추가';
            if (data.status === 'ok') {
                addForm.style.display = 'none';
                loadAccounts();
            } else {
                showAddStatus(data.error || 'Failed', 'red');
            }
        }).catch(function(err) {
            addSave.disabled = false;
            addSave.textContent = '추가';
            showAddStatus('Error: ' + err, 'red');
        });
    });

    function showAddStatus(msg, color) {
        addStatus.style.display = 'block';
        addStatus.textContent = msg;
        addStatus.className = 'github-token-status ' + (color === 'green' ? 'status-ok' : 'status-err');
    }

    // ── Delete Account ────────────────────────────────────

    accountsList.addEventListener('click', function(e) {
        var delBtn = e.target.closest('.gh-account-delete');
        if (!delBtn) return;
        e.stopPropagation();

        var id = delBtn.dataset.id;
        var username = delBtn.dataset.username;
        var pw = prompt('"' + username + '" 계정을 삭제하시겠습니까?\n삭제 비밀번호:');
        if (pw === null || pw === '') return;

        apiFetch('/api/github/accounts/' + id + '/delete/', {
            method: 'POST',
            body: JSON.stringify({ password: pw }),
        }).then(function(r) { return r.json(); })
        .then(function(data) {
            if (data.status === 'ok') {
                // Hide sync section if deleted account was active
                if (activeAccountId == id) {
                    syncSection.style.display = 'none';
                    activeAccountId = null;
                }
                loadAccounts();
            } else {
                alert(data.error || 'Delete failed');
            }
        }).catch(function(err) { alert('Error: ' + err); });
    });

    // ── Sync Button (per account) ─────────────────────────

    accountsList.addEventListener('click', function(e) {
        var syncBtn = e.target.closest('.gh-sync-btn');
        if (!syncBtn) return;
        e.stopPropagation();

        var id = syncBtn.dataset.id;
        var username = syncBtn.dataset.username;
        activeAccountId = id;

        // Highlight active
        accountsList.querySelectorAll('.gh-account-card').forEach(function(c) {
            c.classList.toggle('gh-active', c.dataset.id === id);
        });

        syncSection.style.display = 'block';
        syncAccountLabel.textContent = username;
        syncStatus.textContent = 'Loading repos...';
        tableWrap.style.display = 'none';

        apiFetch('/api/github/repos/?account_id=' + id)
        .then(function(r) { return r.json(); })
        .then(function(data) {
            syncStatus.textContent = '';
            if (data.error) {
                syncStatus.textContent = data.error;
                return;
            }
            allRepos = data.repos || [];
            syncStatus.textContent = data.total + ' repos';
            renderTable();
            tableWrap.style.display = 'block';
        }).catch(function(err) {
            syncStatus.textContent = 'Error: ' + err;
        });
    });

    // ── Sync Table ────────────────────────────────────────

    function renderTable() {
        var hideM = hideMatched && hideMatched.checked;
        var hideF = hideForks && hideForks.checked;

        var filtered = allRepos.filter(function(r) {
            if (hideM && r.status === 'matched') return false;
            if (hideF && r.fork) return false;
            return true;
        });

        if (filtered.length === 0) {
            tableEl.innerHTML = '<div class="text-sm text-muted" style="padding: 16px; text-align: center;">표시할 레포가 없습니다.</div>';
            return;
        }

        var html = '';
        filtered.forEach(function(repo, i) {
            var statusLabel, statusClass;
            if (repo.status === 'matched') {
                statusLabel = '매칭';
                statusClass = 'sync-matched';
            } else if (repo.status === 'incomplete') {
                statusLabel = '빈필드';
                statusClass = 'sync-incomplete';
            } else {
                statusLabel = '없음';
                statusClass = 'sync-missing';
            }

            var actionLabel = '';
            if (repo.status === 'missing') actionLabel = '생성';
            else if (repo.status === 'incomplete') actionLabel = '업데이트';

            var checkable = repo.status !== 'matched';
            var checked = checkable && checkAll.checked;
            var checkboxHtml = checkable
                ? '<input type="checkbox" class="sync-check" data-idx="' + i + '"' + (checked ? ' checked' : '') + '>'
                : '<span class="text-light">-</span>';

            html += '<div class="sync-row' + (repo.fork ? ' sync-fork' : '') + '" data-status="' + repo.status + '">'
                + '<div class="sync-col-check">' + checkboxHtml + '</div>'
                + '<div class="sync-col-name">' + escHtml(repo.name) + (repo.fork ? ' <span class="sync-fork-label">fork</span>' : '') + '</div>'
                + '<div class="sync-col-desc">' + escHtml(repo.description || '') + '</div>'
                + '<div class="sync-col-status"><span class="sync-badge ' + statusClass + '">' + statusLabel + '</span></div>'
                + '<div class="sync-col-action">' + actionLabel + '</div>'
                + '</div>';
        });

        tableEl.innerHTML = html;
    }

    if (checkAll) {
        checkAll.addEventListener('change', function() {
            tableEl.querySelectorAll('.sync-check').forEach(function(cb) { cb.checked = checkAll.checked; });
        });
    }
    if (hideMatched) hideMatched.addEventListener('change', renderTable);
    if (hideForks) hideForks.addEventListener('change', renderTable);

    // ── Do Sync ───────────────────────────────────────────

    doSyncBtn.addEventListener('click', function() {
        var checked = tableEl.querySelectorAll('.sync-check:checked');
        if (checked.length === 0) {
            doSyncStatus.textContent = '선택된 항목이 없습니다.';
            return;
        }

        var hideM = hideMatched && hideMatched.checked;
        var hideF = hideForks && hideForks.checked;
        var filtered = allRepos.filter(function(r) {
            if (hideM && r.status === 'matched') return false;
            if (hideF && r.fork) return false;
            return true;
        });

        var selectedRepos = [];
        checked.forEach(function(cb) {
            var idx = parseInt(cb.dataset.idx, 10);
            if (filtered[idx]) selectedRepos.push(filtered[idx]);
        });
        if (selectedRepos.length === 0) return;

        doSyncBtn.disabled = true;
        doSyncStatus.textContent = '동기화 중...';

        apiFetch('/api/github/sync/', {
            method: 'POST',
            body: JSON.stringify({ repos: selectedRepos }),
        }).then(function(r) { return r.json(); })
        .then(function(data) {
            doSyncBtn.disabled = false;
            if (data.error) {
                doSyncStatus.textContent = data.error;
                return;
            }
            var msg = '';
            if (data.created && data.created.length) msg += data.created.length + '개 생성';
            if (data.updated && data.updated.length) msg += (msg ? ', ' : '') + data.updated.length + '개 업데이트';
            if (!msg) msg = '변경 없음';
            doSyncStatus.textContent = msg;

            // Re-fetch
            var activeBtn = accountsList.querySelector('.gh-sync-btn[data-id="' + activeAccountId + '"]');
            if (activeBtn) activeBtn.click();
        }).catch(function(err) {
            doSyncBtn.disabled = false;
            doSyncStatus.textContent = 'Error: ' + err;
        });
    });

    // ── Init ──────────────────────────────────────────────
    loadAccounts();

})();

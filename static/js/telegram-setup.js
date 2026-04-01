/* Telegram Bot Setup — Setup page */
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
    var botsList = document.getElementById('tg-bots-list');
    var botsEmpty = document.getElementById('tg-bots-empty');
    var addBtn = document.getElementById('tg-add-btn');
    var addForm = document.getElementById('tg-add-form');
    var addSave = document.getElementById('tg-add-save');
    var addCancel = document.getElementById('tg-add-cancel');
    var addToken = document.getElementById('tg-add-token');
    var addChatId = document.getElementById('tg-add-chatid');
    var addStatus = document.getElementById('tg-add-status');

    if (!botsList) return;

    // ── Bot List ──────────────────────────────────────────

    function loadBots() {
        apiFetch('/api/telegram/bots/').then(function(r) { return r.json(); })
        .then(function(data) {
            renderBots(data.bots || []);
        });
    }

    function renderBots(bots) {
        if (bots.length === 0) {
            botsList.innerHTML = '';
            botsEmpty.style.display = 'block';
            return;
        }
        botsEmpty.style.display = 'none';
        var html = '';
        bots.forEach(function(b) {
            var activeClass = b.is_active ? '' : ' tg-inactive';
            var chatIds = b.chat_ids || [];

            // Chat IDs list
            var chatIdsHtml = '';
            chatIds.forEach(function(c) {
                var labelHtml = c.label ? ' <span class="tg-chatid-label">' + escHtml(c.label) + '</span>' : '';
                var delBtn = chatIds.length > 1
                    ? '<button class="tg-chatid-del" data-chatid-pk="' + c.id + '" title="삭제">&times;</button>'
                    : '';
                chatIdsHtml += '<div class="tg-chatid-row">'
                    + '<span class="tg-chatid-val">' + escHtml(c.chat_id) + '</span>'
                    + labelHtml
                    + delBtn
                    + '</div>';
            });

            // Add chat ID inline form
            chatIdsHtml += '<div class="tg-chatid-add-row">'
                + '<input type="text" class="tg-new-chatid" placeholder="Chat ID" data-bot-id="' + b.id + '">'
                + '<input type="text" class="tg-label-input tg-new-label" placeholder="이름" data-bot-id="' + b.id + '">'
                + '<button class="tg-chatid-add-btn" data-bot-id="' + b.id + '">+</button>'
                + '</div>';

            html += '<div class="tg-bot-card' + activeClass + '" data-id="' + b.id + '">'
                + '<div class="tg-bot-top">'
                + '<div class="tg-bot-info">'
                + '<div class="tg-bot-avatar">&#129302;</div>'
                + '<div class="tg-bot-details">'
                + '<div class="tg-bot-name">' + escHtml(b.bot_name || b.bot_username) + '</div>'
                + '<div class="tg-bot-meta">@' + escHtml(b.bot_username) + '</div>'
                + '<div class="tg-bot-token">' + escHtml(b.token_masked) + '</div>'
                + '</div>'
                + '</div>'
                + '<div class="tg-bot-actions">'
                + '<button class="btn-sm btn-blue tg-test-btn" data-id="' + b.id + '" data-name="@' + escHtml(b.bot_username) + '">Test</button>'
                + '<button class="tg-bot-delete" data-id="' + b.id + '" data-name="@' + escHtml(b.bot_username) + '" title="삭제">&times;</button>'
                + '</div>'
                + '</div>'
                + '<div class="tg-chatids">'
                + '<div style="font-size:12px;color:#6b7280;margin-bottom:4px;">Chat IDs (' + chatIds.length + ')</div>'
                + chatIdsHtml
                + '</div>'
                + '</div>';
        });
        botsList.innerHTML = html;
    }

    // ── Add Bot ───────────────────────────────────────────

    addBtn.addEventListener('click', function() {
        addForm.style.display = addForm.style.display === 'none' ? 'block' : 'none';
        if (addForm.style.display === 'block') {
            addToken.value = '';
            addChatId.value = '';
            addStatus.style.display = 'none';
            addToken.focus();
        }
    });

    addCancel.addEventListener('click', function() {
        addForm.style.display = 'none';
    });

    addSave.addEventListener('click', function() {
        var token = addToken.value.trim();
        var chatId = addChatId.value.trim();
        if (!token || !chatId) {
            showAddStatus('Bot Token과 Chat ID를 입력하세요.', 'red');
            return;
        }
        addSave.disabled = true;
        addSave.textContent = '확인중...';

        apiFetch('/api/telegram/bots/add/', {
            method: 'POST',
            body: JSON.stringify({ token: token, chat_id: chatId }),
        }).then(function(r) { return r.json(); })
        .then(function(data) {
            addSave.disabled = false;
            addSave.textContent = '추가';
            if (data.status === 'ok') {
                showAddStatus('@' + data.bot_username + ' 추가 완료!', 'green');
                addForm.style.display = 'none';
                loadBots();
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

    // ── Delete Bot ────────────────────────────────────────

    botsList.addEventListener('click', function(e) {
        var delBtn = e.target.closest('.tg-bot-delete');
        if (!delBtn) return;
        e.stopPropagation();

        var id = delBtn.dataset.id;
        var name = delBtn.dataset.name;
        var pw = prompt('"' + name + '" 봇을 삭제하시겠습니까?\n삭제 비밀번호:');
        if (pw === null || pw === '') return;

        apiFetch('/api/telegram/bots/' + id + '/delete/', {
            method: 'POST',
            body: JSON.stringify({ password: pw }),
        }).then(function(r) { return r.json(); })
        .then(function(data) {
            if (data.status === 'ok') {
                loadBots();
            } else {
                alert(data.error || 'Delete failed');
            }
        }).catch(function(err) { alert('Error: ' + err); });
    });

    // ── Test Bot ──────────────────────────────────────────

    botsList.addEventListener('click', function(e) {
        var testBtn = e.target.closest('.tg-test-btn');
        if (!testBtn) return;
        e.stopPropagation();

        var id = testBtn.dataset.id;
        testBtn.disabled = true;
        testBtn.textContent = '...';

        apiFetch('/api/telegram/bots/' + id + '/test/', {
            method: 'POST',
            body: JSON.stringify({}),
        }).then(function(r) { return r.json(); })
        .then(function(data) {
            testBtn.disabled = false;
            if (data.status === 'ok') {
                var count = (data.sent_to || []).length;
                testBtn.textContent = count + '명 전송!';
                testBtn.style.background = '#22c55e';
                setTimeout(function() {
                    testBtn.textContent = 'Test';
                    testBtn.style.background = '';
                }, 2000);
            } else {
                testBtn.textContent = 'Fail';
                testBtn.style.background = '#ef4444';
                alert(data.error || 'Test failed');
                setTimeout(function() {
                    testBtn.textContent = 'Test';
                    testBtn.style.background = '';
                }, 2000);
            }
        }).catch(function(err) {
            testBtn.disabled = false;
            testBtn.textContent = 'Test';
            alert('Error: ' + err);
        });
    });

    // ── Add Chat ID ───────────────────────────────────────

    botsList.addEventListener('click', function(e) {
        var addCidBtn = e.target.closest('.tg-chatid-add-btn');
        if (!addCidBtn) return;
        e.stopPropagation();

        var botId = addCidBtn.dataset.botId;
        var card = addCidBtn.closest('.tg-bot-card');
        var chatIdInput = card.querySelector('.tg-new-chatid[data-bot-id="' + botId + '"]');
        var labelInput = card.querySelector('.tg-new-label[data-bot-id="' + botId + '"]');
        var chatId = chatIdInput.value.trim();
        var label = labelInput.value.trim();

        if (!chatId) {
            chatIdInput.style.borderColor = '#ef4444';
            setTimeout(function() { chatIdInput.style.borderColor = ''; }, 1500);
            return;
        }

        addCidBtn.disabled = true;
        addCidBtn.textContent = '...';

        apiFetch('/api/telegram/bots/' + botId + '/chat-ids/add/', {
            method: 'POST',
            body: JSON.stringify({ chat_id: chatId, label: label }),
        }).then(function(r) { return r.json(); })
        .then(function(data) {
            addCidBtn.disabled = false;
            addCidBtn.textContent = '+';
            if (data.status === 'ok') {
                loadBots();
            } else {
                alert(data.error || 'Failed');
            }
        }).catch(function(err) {
            addCidBtn.disabled = false;
            addCidBtn.textContent = '+';
            alert('Error: ' + err);
        });
    });

    // Enter key support for chat ID input
    botsList.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && e.target.classList.contains('tg-new-chatid')) {
            var botId = e.target.dataset.botId;
            var card = e.target.closest('.tg-bot-card');
            var btn = card.querySelector('.tg-chatid-add-btn[data-bot-id="' + botId + '"]');
            if (btn) btn.click();
        }
    });

    // ── Delete Chat ID ────────────────────────────────────

    botsList.addEventListener('click', function(e) {
        var delBtn = e.target.closest('.tg-chatid-del');
        if (!delBtn) return;
        e.stopPropagation();

        var pk = delBtn.dataset.chatidPk;
        if (!confirm('이 Chat ID를 삭제하시겠습니까?')) return;

        apiFetch('/api/telegram/chat-ids/' + pk + '/delete/', {
            method: 'POST',
            body: JSON.stringify({}),
        }).then(function(r) { return r.json(); })
        .then(function(data) {
            if (data.status === 'ok') {
                loadBots();
            } else {
                alert(data.error || 'Delete failed');
            }
        }).catch(function(err) { alert('Error: ' + err); });
    });

    // ── Init ──────────────────────────────────────────────
    loadBots();

})();

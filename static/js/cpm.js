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

    // Screenshot Preview Modal — left/right nav only (no autoplay)
    var galleryImages = [];
    var galleryIndex = 0;

    function showSlide(idx) {
        var modalImg = document.getElementById('screenshot-modal-img');
        if (!modalImg || !galleryImages.length) return;
        galleryIndex = idx;
        modalImg.src = galleryImages[galleryIndex];
        updateModalNav();
    }

    function nextSlide() {
        if (galleryImages.length <= 1) return;
        showSlide((galleryIndex + 1) % galleryImages.length);
    }

    function prevSlide() {
        if (galleryImages.length <= 1) return;
        showSlide((galleryIndex - 1 + galleryImages.length) % galleryImages.length);
    }

    function openGalleryModal(images, startIndex) {
        if (!images || !images.length) return;
        galleryImages = images;
        galleryIndex = startIndex || 0;
        var modal = document.getElementById('screenshot-modal');
        var modalImg = document.getElementById('screenshot-modal-img');
        if (!modal || !modalImg) return;
        modalImg.src = galleryImages[galleryIndex];
        modal.style.display = 'flex';
        document.body.style.overflow = 'hidden';
        updateModalNav();
    }

    function updateModalNav() {
        var prevBtn = document.getElementById('screenshot-modal-prev');
        var nextBtn = document.getElementById('screenshot-modal-next');
        var counter = document.getElementById('screenshot-modal-counter');
        var multi = galleryImages.length > 1;
        if (prevBtn) prevBtn.style.display = multi ? 'flex' : 'none';
        if (nextBtn) nextBtn.style.display = multi ? 'flex' : 'none';
        if (counter) {
            counter.style.display = multi ? 'block' : 'none';
            counter.textContent = (galleryIndex + 1) + ' / ' + galleryImages.length;
        }
    }

    (function() {
        var modal = document.getElementById('screenshot-modal');
        if (!modal) return;
        var modalImg = document.getElementById('screenshot-modal-img');
        var backdrop = modal.querySelector('.screenshot-modal-backdrop');
        var closeBtn = modal.querySelector('.screenshot-modal-close');
        var prevBtn = document.getElementById('screenshot-modal-prev');
        var nextBtn = document.getElementById('screenshot-modal-next');

        // Hover preview popup (lightweight, separate from full modal)
        var hoverPopup = document.createElement('div');
        hoverPopup.id = 'screenshot-hover-popup';
        hoverPopup.className = 'screenshot-hover-popup';
        hoverPopup.style.display = 'none';
        hoverPopup.innerHTML = '<img src="" alt="Preview">';
        document.body.appendChild(hoverPopup);
        var hoverImg = hoverPopup.querySelector('img');
        var hoverTimer = null;
        var hoverOpen = false;

        function showHoverPopup(src, anchorEl) {
            hoverImg.src = src;
            hoverPopup.style.display = 'block';
            // Position: try below the card, if too low then above
            var rect = anchorEl.closest('.memo-card') ? anchorEl.closest('.memo-card').getBoundingClientRect() : anchorEl.getBoundingClientRect();
            var popH = 440;
            var popW = 570;
            var top = rect.bottom + 10;
            if (top + popH > window.innerHeight) top = Math.max(10, rect.top - popH - 10);
            var left = rect.left;
            if (left + popW > window.innerWidth) left = window.innerWidth - popW - 10;
            if (left < 10) left = 10;
            hoverPopup.style.top = top + 'px';
            hoverPopup.style.left = left + 'px';
            hoverOpen = true;
        }
        function hideHoverPopup() {
            clearTimeout(hoverTimer);
            hoverPopup.style.display = 'none';
            hoverImg.src = '';
            hoverOpen = false;
        }

        prevBtn.addEventListener('click', function(e) {
            e.stopPropagation();
            prevSlide();
        });
        nextBtn.addEventListener('click', function(e) {
            e.stopPropagation();
            nextSlide();
        });

        function closeModal() {
            modal.style.display = 'none';
            modalImg.src = '';
            document.body.style.overflow = '';
            galleryImages = [];
            galleryIndex = 0;
        }

        function getMarkImages(mark) {
            var multi = mark.dataset.screenshots;
            if (multi && multi.trim()) {
                var imgs = multi.split('|').filter(function(s) { return s.trim(); });
                if (imgs.length > 0) return imgs;
            }
            var single = mark.dataset.screenshot;
            if (single && single.trim()) return [single];
            return [];
        }

        // Dashboard cards: hover → lightweight popup, click → full modal
        document.querySelectorAll('.memo-card-img-mark').forEach(function(mark) {
            mark.addEventListener('mouseenter', function(e) {
                e.stopPropagation();
                var src = mark.dataset.screenshot;
                hoverTimer = setTimeout(function() { showHoverPopup(src, mark); }, 300);
            });
            mark.addEventListener('mouseleave', function() {
                clearTimeout(hoverTimer);
                hideHoverPopup();
            });
            mark.addEventListener('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                hideHoverPopup();
                openGalleryModal(getMarkImages(mark), 0);
            });
        });

        // Close full modal: backdrop click, × button, Escape
        backdrop.addEventListener('click', closeModal);
        closeBtn.addEventListener('click', closeModal);
        document.addEventListener('keydown', function(e) {
            if (modal.style.display === 'none') return;
            if (e.key === 'Escape') closeModal();
            if (e.key === 'ArrowLeft') prevSlide();
            if (e.key === 'ArrowRight') nextSlide();
        });
    })();

    // Screenshot Gallery (project detail page)
    (function() {
        const gallery = document.getElementById('screenshot-gallery');
        if (!gallery) return;
        const projectId = gallery.dataset.projectId;
        const zone = document.getElementById('screenshot-upload-zone');
        const zoneInner = document.getElementById('upload-zone-inner');
        const progress = document.getElementById('upload-progress');
        const fileInput = document.getElementById('screenshot-file-input');
        const addBtn = document.getElementById('screenshot-add-btn');
        const countLabel = document.getElementById('screenshot-count-label');

        function getThumbCount() { return gallery.querySelectorAll('.screenshot-thumb').length; }

        function updateCountLabel() {
            if (countLabel) countLabel.textContent = '(' + getThumbCount() + '/100)';
        }

        function showProgress() { zoneInner.style.display = 'none'; progress.style.display = 'block'; }
        function hideProgress() { zoneInner.style.display = 'flex'; progress.style.display = 'none'; }

        function toggleUploadZone() {
            zone.style.display = zone.style.display === 'none' ? 'block' : 'none';
            if (zone.style.display === 'block') zoneInner.focus();
        }

        // Toggle upload zone on [+] click
        if (addBtn) addBtn.addEventListener('click', toggleUploadZone);

        function addThumb(screenshotId, url) {
            var thumb = document.createElement('div');
            thumb.className = 'screenshot-thumb';
            thumb.dataset.screenshotId = screenshotId;
            thumb.innerHTML = '<img src="' + url + '?t=' + Date.now() + '" alt="Screenshot">' +
                '<button class="screenshot-thumb-delete" title="Delete">&times;</button>';
            // Insert before [+] button
            var btn = document.getElementById('screenshot-add-btn');
            if (btn) {
                gallery.insertBefore(thumb, btn);
            } else {
                gallery.appendChild(thumb);
            }
            // Hide [+] if at 5
            if (getThumbCount() >= 100 && btn) btn.style.display = 'none';
            // Hide upload zone
            zone.style.display = 'none';
            updateCountLabel();
        }

        function uploadFile(file) {
            if (!file || !file.type.startsWith('image/')) { alert('Image file only'); return; }
            if (file.size > 10 * 1024 * 1024) { alert('Max 10MB'); return; }
            if (getThumbCount() >= 100) { alert('Maximum 100 screenshots'); return; }
            showProgress();
            var fd = new FormData();
            fd.append('file', file);
            fetch('/api/projects/' + projectId + '/screenshot/', { method: 'POST', body: fd })
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    hideProgress();
                    if (data.status === 'ok') addThumb(data.screenshot_id, data.url);
                    else alert(data.error);
                })
                .catch(function(err) { hideProgress(); alert('Upload failed: ' + err); });
        }

        function uploadBase64(dataUrl) {
            if (getThumbCount() >= 100) { alert('Maximum 100 screenshots'); return; }
            showProgress();
            fetch('/api/projects/' + projectId + '/screenshot/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ image: dataUrl }),
            })
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    hideProgress();
                    if (data.status === 'ok') addThumb(data.screenshot_id, data.url);
                    else alert(data.error);
                })
                .catch(function(err) { hideProgress(); alert('Upload failed: ' + err); });
        }

        // Delete individual screenshot
        gallery.addEventListener('click', function(e) {
            var delBtn = e.target.closest('.screenshot-thumb-delete');
            if (!delBtn) return;
            e.stopPropagation();
            if (!confirm('Delete this screenshot?')) return;
            var thumb = delBtn.closest('.screenshot-thumb');
            var ssId = thumb.dataset.screenshotId;
            fetch('/api/screenshots/' + ssId + '/delete/', { method: 'DELETE' })
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (data.status === 'ok') {
                        thumb.remove();
                        // Show [+] button if under 5
                        var btn = document.getElementById('screenshot-add-btn');
                        if (getThumbCount() < 100) {
                            if (!btn) {
                                btn = document.createElement('div');
                                btn.className = 'screenshot-add-btn';
                                btn.id = 'screenshot-add-btn';
                                btn.title = 'Add screenshot';
                                btn.textContent = '+';
                                btn.addEventListener('click', toggleUploadZone);
                                gallery.appendChild(btn);
                            }
                            btn.style.display = '';
                        }
                        updateCountLabel();
                    }
                });
        });

        // Click thumbnail image → open modal
        gallery.addEventListener('click', function(e) {
            var img = e.target.closest('.screenshot-thumb img');
            if (!img) return;
            e.preventDefault();
            // Open modal with navigation
            var thumbs = Array.from(gallery.querySelectorAll('.screenshot-thumb img'));
            var idx = thumbs.indexOf(img);
            openGalleryModal(thumbs.map(function(i) { return i.src; }), idx);
        });

        // Click to focus (for Ctrl+V)
        zoneInner.addEventListener('click', function() { zoneInner.focus(); });
        zoneInner.addEventListener('focus', function() { zoneInner.classList.add('focused'); });
        zoneInner.addEventListener('blur', function() { zoneInner.classList.remove('focused'); });

        // Drag & drop
        zoneInner.addEventListener('dragover', function(e) { e.preventDefault(); zoneInner.classList.add('dragover'); });
        zoneInner.addEventListener('dragleave', function() { zoneInner.classList.remove('dragover'); });
        zoneInner.addEventListener('drop', function(e) {
            e.preventDefault(); zoneInner.classList.remove('dragover');
            if (e.dataTransfer.files.length) uploadFile(e.dataTransfer.files[0]);
        });

        // File picker
        fileInput.addEventListener('change', function() {
            if (fileInput.files.length) { uploadFile(fileInput.files[0]); fileInput.value = ''; }
        });

        // Clipboard paste (Ctrl+V)
        document.addEventListener('paste', function(e) {
            if (!document.getElementById('screenshot-upload-zone')) return;
            var items = e.clipboardData && e.clipboardData.items;
            if (!items) return;
            for (var i = 0; i < items.length; i++) {
                if (items[i].type.startsWith('image/')) {
                    e.preventDefault();
                    var reader = new FileReader();
                    reader.onload = function(ev) { uploadBase64(ev.target.result); };
                    reader.readAsDataURL(items[i].getAsFile());
                    return;
                }
            }
        });
    })();

    // Recent preview expand/collapse
    (function() {
        var arrow = document.getElementById('recent-preview-arrow');
        var expand = document.getElementById('recent-preview-expand');
        if (!arrow || !expand) return;
        arrow.addEventListener('click', function(e) {
            e.stopPropagation();
            var isOpen = expand.classList.toggle('open');
            arrow.classList.toggle('open', isOpen);
        });
    })();

    // Heart (favorite) toggle
    document.addEventListener('click', function(e) {
        var heart = e.target.closest('.memo-card-heart');
        if (!heart) return;
        e.preventDefault();
        e.stopPropagation();
        var projectId = heart.dataset.projectId;

        apiFetch('/api/projects/' + projectId + '/favorite/', {
            method: 'POST',
            body: JSON.stringify({}),
        }).then(function(r) { return r.json(); })
        .then(function(data) {
            if (data.status === 'ok') {
                heart.classList.toggle('active', data.favorited);
                var card = heart.closest('.memo-card');
                if (card) card.dataset.favorited = data.favorited ? 'true' : 'false';
                // Re-apply filter if in fav mode
                applyProjectFilter();
            }
        });
    });

    // Project filter toggle (ALL / Favorites)
    var showAll = true; // default: show ALL
    var filterToggle = document.getElementById('project-filter-toggle');
    if (filterToggle) {
        // Check if any favorited projects exist — if yes, default to fav mode
        var hasFav = document.querySelector('.memo-card[data-favorited="true"]');
        if (hasFav) {
            showAll = false;
            filterToggle.textContent = '\u2665';
            filterToggle.classList.add('fav-mode');
            applyProjectFilter();
        }

        filterToggle.addEventListener('click', function() {
            showAll = !showAll;
            if (showAll) {
                filterToggle.textContent = 'ALL';
                filterToggle.classList.remove('fav-mode');
            } else {
                filterToggle.textContent = '\u2665';
                filterToggle.classList.add('fav-mode');
            }
            applyProjectFilter();
        });
    }

    function applyProjectFilter() {
        var cards = document.querySelectorAll('.memo-card[data-favorited]');
        cards.forEach(function(card) {
            if (showAll) {
                card.classList.remove('filtered-out');
            } else {
                var fav = card.dataset.favorited === 'true';
                card.classList.toggle('filtered-out', !fav);
            }
        });
    }

    // Project delete (password protected)
    document.addEventListener('click', function(e) {
        var del = e.target.closest('.memo-card-delete');
        if (!del) return;
        e.preventDefault();
        e.stopPropagation();
        var projectId = del.dataset.projectId;
        var projectName = del.dataset.projectName;
        var pw = prompt('Delete "' + projectName + '"?\nEnter delete password:');
        if (pw === null || pw === '') return;
        apiFetch('/api/projects/' + projectId + '/delete/', {
            method: 'POST',
            body: JSON.stringify({ password: pw }),
        }).then(function(r) { return r.json(); })
        .then(function(data) {
            if (data.status === 'ok') {
                del.closest('.memo-card').remove();
            } else {
                alert(data.error || 'Delete failed');
            }
        }).catch(function(err) { alert('Error: ' + err); });
    });

    // ── Todo Modal ────────────────────────────────────────────────
    (function() {
        var modal = document.getElementById('todo-modal');
        if (!modal) return;

        var backdrop = modal.querySelector('.todo-modal-backdrop');
        var closeBtn = document.getElementById('todo-modal-close');
        var titleEl = document.getElementById('todo-modal-title');
        var todoList = document.getElementById('todo-list');
        var deployList = document.getElementById('todo-deploy-list');
        var deployDivider = document.getElementById('todo-deploy-divider');
        var addInput = document.getElementById('todo-add-input');
        var addBtn = document.getElementById('todo-add-btn');
        var addDeployInput = document.getElementById('todo-add-deploy-input');
        var addDeployBtn = document.getElementById('todo-add-deploy-btn');
        var progressEl = document.getElementById('todo-modal-progress');
        var currentProjectId = null;

        function openModal(projectId, projectName) {
            currentProjectId = projectId;
            titleEl.textContent = projectName + ' \u2014 Goals';
            modal.style.display = 'flex';
            addInput.value = '';
            addDeployInput.value = '';
            loadTodos();
            setTimeout(function() { addInput.focus(); }, 100);
        }

        function closeModal() {
            modal.style.display = 'none';
            currentProjectId = null;
            todoList.innerHTML = '';
            deployList.innerHTML = '';
        }

        function loadTodos() {
            todoList.innerHTML = '<div class="todo-list-empty">Loading...</div>';
            deployList.innerHTML = '';
            deployDivider.style.display = 'none';

            apiFetch('/api/projects/' + currentProjectId + '/todos/')
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (data.status !== 'ok') return;
                    renderTodos(data.todos);
                    updateProgress(data.completed, data.total);
                    updateBadge(currentProjectId, data.completed, data.total);
                })
                .catch(function() {
                    todoList.innerHTML = '<div class="todo-list-empty">Failed to load</div>';
                });
        }

        function renderTodos(todos) {
            todoList.innerHTML = '';
            deployList.innerHTML = '';
            var hasTask = false;
            var hasDeploy = false;

            todos.forEach(function(todo) {
                var el = createTodoElement(todo);
                if (todo.category === 'deploy') {
                    deployList.appendChild(el);
                    hasDeploy = true;
                } else {
                    todoList.appendChild(el);
                    hasTask = true;
                }
            });

            if (!hasTask && !hasDeploy) {
                todoList.innerHTML = '<div class="todo-list-empty">No goals yet. Add your first goal above.</div>';
            }
            deployDivider.style.display = hasDeploy ? 'flex' : 'none';
        }

        function createTodoElement(todo) {
            var div = document.createElement('div');
            div.className = 'todo-item' + (todo.is_completed ? ' completed' : '');
            div.dataset.todoId = todo.id;

            var checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.className = 'todo-item-checkbox';
            checkbox.checked = todo.is_completed;

            var title = document.createElement('span');
            title.className = 'todo-item-title';
            title.textContent = todo.title;

            var dateSpan = document.createElement('span');
            dateSpan.className = 'todo-item-date';
            if (todo.completed_at) {
                var d = new Date(todo.completed_at);
                dateSpan.textContent = (d.getMonth() + 1) + '/' + d.getDate() + ' \u2713';
            }

            var delBtn = document.createElement('button');
            delBtn.className = 'todo-item-delete';
            delBtn.innerHTML = '&times;';
            delBtn.title = 'Delete';

            div.appendChild(checkbox);
            div.appendChild(title);
            div.appendChild(dateSpan);
            div.appendChild(delBtn);

            checkbox.addEventListener('change', function() {
                apiFetch('/api/todos/' + todo.id + '/', {
                    method: 'PATCH',
                    body: JSON.stringify({ is_completed: checkbox.checked }),
                }).then(function(r) { return r.json(); })
                .then(function(data) {
                    if (data.status === 'ok') loadTodos();
                });
            });

            delBtn.addEventListener('click', function(e) {
                e.stopPropagation();
                apiFetch('/api/todos/' + todo.id + '/', {
                    method: 'DELETE',
                }).then(function(r) { return r.json(); })
                .then(function(data) {
                    if (data.status === 'ok') loadTodos();
                });
            });

            return div;
        }

        function addTodo(category) {
            var input = category === 'deploy' ? addDeployInput : addInput;
            var title = input.value.trim();
            if (!title) return;

            input.disabled = true;
            apiFetch('/api/projects/' + currentProjectId + '/todos/', {
                method: 'POST',
                body: JSON.stringify({ title: title, category: category }),
            }).then(function(r) { return r.json(); })
            .then(function(data) {
                input.disabled = false;
                if (data.status === 'ok') {
                    input.value = '';
                    loadTodos();
                    input.focus();
                }
            }).catch(function() {
                input.disabled = false;
            });
        }

        function updateProgress(completed, total) {
            if (total === 0) {
                progressEl.textContent = 'No goals set';
            } else {
                progressEl.textContent = completed + ' / ' + total + ' completed';
            }
        }

        function updateBadge(projectId, completed, total) {
            var badge = document.querySelector('.memo-card-todo-badge[data-project-id="' + projectId + '"]');
            if (!badge) return;
            if (total > 0) {
                badge.innerHTML = '<span class="todo-progress">' + completed + '/' + total + '</span>';
                badge.title = 'Goals: ' + completed + '/' + total;
            } else {
                badge.innerHTML = '<span class="todo-progress-empty">\u2610</span>';
                badge.title = 'Goals: none';
            }
        }

        document.addEventListener('click', function(e) {
            var badge = e.target.closest('.memo-card-todo-badge');
            if (!badge) return;
            e.preventDefault();
            e.stopPropagation();
            openModal(badge.dataset.projectId, badge.dataset.projectName);
        });

        addBtn.addEventListener('click', function() { addTodo('task'); });
        addDeployBtn.addEventListener('click', function() { addTodo('deploy'); });

        addInput.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') { e.preventDefault(); addTodo('task'); }
        });
        addDeployInput.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') { e.preventDefault(); addTodo('deploy'); }
        });

        backdrop.addEventListener('click', closeModal);
        closeBtn.addEventListener('click', closeModal);
        document.addEventListener('keydown', function(e) {
            if (modal.style.display === 'none' || modal.style.display === '') return;
            if (e.key === 'Escape') closeModal();
        });
    })();

    // GitHub link click (inside memo-card <a>, so intercept)
    document.addEventListener('click', function(e) {
        var gh = e.target.closest('.memo-link.github');
        if (!gh) return;
        var href = gh.dataset.href;
        if (href) {
            e.preventDefault();
            e.stopPropagation();
            window.open(href, '_blank');
        }
    });

    // Project add modal
    (function() {
        var addBtn = document.getElementById('project-add-btn');
        var modal = document.getElementById('project-add-modal');
        if (!addBtn || !modal) return;

        var backdrop = modal.querySelector('.project-add-backdrop');
        var cancelBtn = document.getElementById('project-add-cancel');
        var saveBtn = document.getElementById('project-add-save');
        var errorDiv = document.getElementById('project-add-error');
        var nameInput = document.getElementById('add-project-name');
        var pathInput = document.getElementById('add-project-path');
        var descInput = document.getElementById('add-project-description');
        var githubInput = document.getElementById('add-project-github');
        var serverInput = document.getElementById('add-project-server');

        function openModal() {
            modal.style.display = 'flex';
            nameInput.value = '';
            pathInput.value = '';
            descInput.value = '';
            githubInput.value = '';
            serverInput.value = '';
            errorDiv.style.display = 'none';
            setTimeout(function() { nameInput.focus(); }, 100);
        }

        function closeModal() {
            modal.style.display = 'none';
        }

        function showError(msg) {
            errorDiv.textContent = msg;
            errorDiv.style.display = 'block';
        }

        function saveProject() {
            var name = nameInput.value.trim();
            if (!name) { showError('Project name is required'); nameInput.focus(); return; }

            saveBtn.disabled = true;
            saveBtn.textContent = 'Creating...';

            var body = { name: name };
            if (pathInput.value.trim()) body.path = pathInput.value.trim();
            if (descInput.value.trim()) body.description = descInput.value.trim();
            if (githubInput.value.trim()) body.github_url = githubInput.value.trim();
            if (serverInput.value.trim()) body.server_info = serverInput.value.trim();

            apiFetch('/api/projects/', {
                method: 'POST',
                body: JSON.stringify(body),
            }).then(function(r) {
                if (r.ok) return r.json();
                return r.json().then(function(d) { throw d; });
            }).then(function(data) {
                closeModal();
                location.reload();
            }).catch(function(err) {
                saveBtn.disabled = false;
                saveBtn.textContent = 'Create';
                if (err && err.name) {
                    showError(err.name.join ? err.name.join(', ') : String(err.name));
                } else if (err && err.detail) {
                    showError(err.detail);
                } else {
                    showError('Failed to create project');
                }
            });
        }

        addBtn.addEventListener('click', openModal);
        backdrop.addEventListener('click', closeModal);
        cancelBtn.addEventListener('click', closeModal);
        saveBtn.addEventListener('click', saveProject);

        // Enter to save, Escape to close
        modal.addEventListener('keydown', function(e) {
            if (e.key === 'Escape') closeModal();
            if (e.key === 'Enter') { e.preventDefault(); saveProject(); }
        });
    })();

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
            var msg = 'Scan complete: ' + data.open_count + ' open ports on ' + data.host;
            if (data.linked && data.linked.length > 0) {
                msg += '\n\nAuto-linked to projects:';
                data.linked.forEach(function(l) { msg += '\n  port ' + l.port + ' → ' + l.project; });
            }
            alert(msg);
            location.reload();
        }).catch(err => {
            alert('Scan failed: ' + err);
            if (btn) { btn.disabled = false; btn.textContent = 'Auto-Discover'; }
        });
    };

})();

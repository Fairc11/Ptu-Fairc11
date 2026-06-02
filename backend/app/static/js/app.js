/**
 * Ptu v1.4.1 - Desktop Application Script
 */
const Ptu = (() => {
    'use strict';

    // ── State ──────────────────────────────────────────────────────────
    const state = {
        currentTaskId: null,
        previewUrls: [],
        currentIndex: 0,
        mode: 'standard',
        loggedIn: false,
        isDesktop: !!(window.pywebview && window.pywebview.api),
        // 已登录标志，由 updateLogin 维护
        ws: null,
        loginPollTimer: null,
        profilePosts: [],
        profileUserName: '',
    };

    // ── 全局粘贴监听（自动提取 URL 到当前聚焦的输入框） ──────────────
    document.addEventListener('paste', function(e) {
        const active = document.activeElement;
        if (!active || (active.id !== 'url-input' && active.id !== 'profile-url-input')) return;
        const text = (e.clipboardData || window.clipboardData).getData('text');
        if (text) {
            e.preventDefault();
            active.value = extractUrl(text);
        }
    });

    // ── URL 提取（从分享文本中提取抖音链接） ─────────────────────────
    function extractUrl(text) {
        if (!text) return '';
        // 按优先级匹配：主页 > 短链接 > 详情页 > 分享页 > 国际版
        const patterns = [
            /https?:\/\/www\.douyin\.com\/user\/[^\s]+/,
            /https?:\/\/v\.douyin\.com\/[^\s]+/,
            /https?:\/\/www\.douyin\.com\/(note|video|share)\/[^\s]+/,
            /https?:\/\/www\.iesdouyin\.com\/[^\s]+/,
        ];
        for (const p of patterns) {
            const m = text.match(p);
            if (m) return m[0].replace(/[，。；;、)）]+$/g, '');
        }
        return text.trim();
    }

    function setInputValue(input, value) {
        input.value = value;
        input.dispatchEvent(new Event('input', {bubbles: true}));
        input.dispatchEvent(new Event('change', {bubbles: true}));
    }

    // ── CDN 代理（绕过防盗链） ─────────────────────────────────────────
    function proxyUrl(url) {
        if (!url || url.startsWith('/api/proxy/')) return url;
        const needsProxy = ['douyinpic.com', 'tos-cn-', 'zjcdn.com', 'ies-music', 'music.douyin'];
        if (needsProxy.some(d => url.includes(d))) {
            return '/api/proxy/media?url=' + encodeURIComponent(url);
        }
        return url;
    }

    // ── API Client ─────────────────────────────────────────────────────
    async function _parseError(r) {
        try {
            const e = await r.json();
            return e.detail || e.message || JSON.stringify(e);
        } catch (_) {
            const text = await r.text().catch(() => '');
            return text || `服务器错误 (${r.status})`;
        }
    }
    const api = {
        async get(url) {
            const r = await fetch(url);
            if (!r.ok) { throw new Error(await _parseError(r)); }
            return r.json();
        },
        async post(url, body) {
            const r = await fetch(url, {
                method: 'POST',
                headers: body ? {'Content-Type':'application/json'} : undefined,
                body: body ? JSON.stringify(body) : undefined,
            });
            if (!r.ok) { throw new Error(await _parseError(r)); }
            return r.json();
        },
        scrape(url) { return api.post('/api/scrape', {url}); },
        download(taskId) { return api.post(`/api/tasks/${taskId}/download`); },
        render(taskId, opts) { return api.post(`/api/tasks/${taskId}/render`, {options: opts}); },
        output(taskId) { return `/api/tasks/${taskId}/output`; },
        loginQR() { return api.post('/api/login/qrcode'); },
        loginConfirm() { return api.post('/api/login/confirm'); },
        logout() { return api.post('/api/login/logout'); },
        clearCache() { return api.post('/api/browser/clear-cache'); },
        loginStatus() { return api.get('/api/login/status'); },
        deleteTask(id) { return fetch(`/api/tasks/${id}`, {method:'DELETE'}).then(r=>r.json()); },
        batchDelete(ids) { return api.post('/api/tasks/batch-delete', {task_ids: ids}); },
        openFolder(taskId) { return api.post(`/api/tasks/${taskId}/open-folder`); },
        openLogsFolder() { return api.post('/api/logs/open-folder'); },
    };

    // ── Desktop Bridge ─────────────────────────────────────────────────
    const desktop = {
        get isAvailable() { return !!(window.pywebview && window.pywebview.api); },
        _maximized: false,
        minimize() { if (desktop.isAvailable) window.pywebview.api.minimize_window(); },
        maximize() {
            if (!desktop.isAvailable) return;
            if (desktop._maximized) {
                window.pywebview.api.restore_window();
                desktop._maximized = false;
            } else {
                window.pywebview.api.maximize_window();
                desktop._maximized = true;
            }
            desktop._updateMaxBtn();
        },
        close()   { if (desktop.isAvailable) window.pywebview.api.close_window(); },
        startDrag() { if (desktop.isAvailable) window.pywebview.api.start_titlebar_drag(); },
        openInExplorer(path) { if (desktop.isAvailable) window.pywebview.api.open_in_explorer(path); },
        notify(title, msg) { if (desktop.isAvailable) window.pywebview.api.show_notification(title, msg); },
        _updateMaxBtn() {
            const btn = document.getElementById('maximize-btn');
            if (!btn) return;
            if (desktop._maximized) {
                btn.innerHTML = '<svg viewBox="0 0 16 16"><rect x="3" y="6" width="7" height="7" rx="1" fill="none" stroke="currentColor" stroke-width="1.5"/><rect x="6" y="3" width="7" height="7" rx="1" fill="none" stroke="currentColor" stroke-width="1.5"/></svg>';
                btn.setAttribute('aria-label', '还原');
            } else {
                btn.innerHTML = '<svg viewBox="0 0 16 16"><rect x="3" y="3" width="10" height="10" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.5"/></svg>';
                btn.setAttribute('aria-label', '最大化');
            }
        },
    };

    // ── WebSocket ──────────────────────────────────────────────────────
    const ws = {
        connect(taskId) {
            if (state.ws) state.ws.close();
            const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            state.ws = new WebSocket(`${proto}//${window.location.host}/ws/${taskId}`);
            state.ws.onmessage = e => {
                const d = JSON.parse(e.data);
                const p = document.getElementById('progress-section');
                if (p) p.classList.remove('hidden');
                const m = document.getElementById('progress-message');
                if (m) m.textContent = d.message || d.stage;
                const bar = document.getElementById('progress-bar');
                if (bar) bar.style.width = (d.progress * 100) + '%';
            };
        },
        disconnect() { if (state.ws) { state.ws.close(); state.ws = null; } },
    };

    // ── Toast Notifications ────────────────────────────────────────────
    const toast = {
        _show(msg, type) {
            const container = document.getElementById('toast-container');
            if (!container) return;
            const el = document.createElement('div');
            el.className = `toast toast-${type}`;
            el.textContent = msg;
            container.appendChild(el);
            setTimeout(() => { el.classList.add('out'); setTimeout(() => el.remove(), 250); }, 3000);
        },
        success(msg) { toast._show(msg, 'success'); },
        error(msg)   {
            toast._show(msg, 'error');
            // 错误信息在日志面板也留一份
            const logEl = document.getElementById('log-content');
            if (logEl) {
                const time = new Date().toLocaleTimeString();
                logEl.textContent = (logEl.textContent || '') + `\n[${time}] ❌ ${msg}`;
            }
        },
        info(msg)    { toast._show(msg, 'info'); },
    };

    // ── Progress ───────────────────────────────────────────────────────
    const progress = {
        show(msg, pct) {
            const sec = document.getElementById('progress-section');
            if (sec) sec.classList.remove('hidden');
            const m = document.getElementById('progress-message');
            if (m) m.textContent = msg;
            const bar = document.getElementById('progress-bar');
            if (bar) bar.style.width = (pct || 0) + '%';
        },
        update(msg, pct) {
            const m = document.getElementById('progress-message');
            if (m) m.textContent = msg;
            const bar = document.getElementById('progress-bar');
            if (bar) bar.style.width = (pct || 0) + '%';
        },
        hide() {
            const sec = document.getElementById('progress-section');
            if (sec) sec.classList.add('hidden');
        },
        complete(msg) {
            progress.update(msg || '完成', 100);
            setTimeout(progress.hide, 2000);
        },
    };

    // ── Login Modal ────────────────────────────────────────────────────
    const loginModal = {
        open() {
            const modal = document.getElementById('login-modal');
            if (!modal) return;
            modal.classList.remove('hidden');
            const success = document.getElementById('qr-success');
            const img = document.getElementById('qr-image');
            const loading = document.getElementById('qr-loading');
            if (success) success.classList.add('hidden');
            if (img) img.classList.add('hidden');
            if (loading) loading.classList.remove('hidden');
            loginModal.refresh();
        },
        close() {
            const modal = document.getElementById('login-modal');
            if (modal) modal.classList.add('hidden');
            if (state.loginPollTimer) { clearInterval(state.loginPollTimer); state.loginPollTimer = null; }
        },
        refresh() {
            const loading = document.getElementById('qr-loading');
            const img = document.getElementById('qr-image');
            const success = document.getElementById('qr-success');
            const status = document.getElementById('qr-status');
            if (loading) loading.classList.remove('hidden');
            if (img) img.classList.add('hidden');
            if (success) success.classList.add('hidden');
            if (status) status.textContent = '获取二维码中...';
            if (state.loginPollTimer) { clearInterval(state.loginPollTimer); state.loginPollTimer = null; }
            api.loginQR().then(d => {
                if (d.qrcode) {
                    if (loading) loading.classList.add('hidden');
                    if (img) { img.src = 'data:image/png;base64,' + d.qrcode; img.classList.remove('hidden'); }
                    if (status) status.textContent = '请用抖音扫描二维码';
                    state.loginPollTimer = setInterval(loginModal.poll, 2000);
                } else {
                    if (loading) loading.classList.add('hidden');
                    if (status) status.textContent = '获取失败，请重试';
                }
            }).catch(e => {
                if (loading) loading.classList.add('hidden');
                if (status) status.textContent = (e.message && e.message.length < 60) ? e.message : '获取失败，请检查网络后重试';
            });
        },
        poll() {
            api.loginConfirm().then(d => {
                if (d.status === 'done') {
                    const status = document.getElementById('qr-status');
                    const img = document.getElementById('qr-image');
                    const success = document.getElementById('qr-success');
                    if (status) status.textContent = '登录成功！';
                    if (img) img.classList.add('hidden');
                    if (success) success.classList.remove('hidden');
                    if (state.loginPollTimer) { clearInterval(state.loginPollTimer); state.loginPollTimer = null; }
                    ui.updateLogin({logged_in: true});
                    setTimeout(loginModal.close, 1500);
                }
            }).catch(() => {});
        },
    };

    // ── Lightbox ───────────────────────────────────────────────────────
    const lightbox = {
        open(idx) {
            state.currentIndex = idx;
            const lb = document.getElementById('lightbox');
            if (!lb) return;
            const img = document.getElementById('lb-image');
            const vid = document.getElementById('lb-video');
            const counter = document.getElementById('lb-counter');
            if (img) { img.style.display = 'block'; img.src = proxyUrl(state.previewUrls[idx]); }
            if (vid) { vid.style.display = 'none'; vid.pause(); vid.src = ''; }
            if (counter) counter.textContent = (idx + 1) + '/' + state.previewUrls.length;
            lb.classList.remove('hidden');
        },
        openVideo(src) {
            const lb = document.getElementById('lightbox');
            if (!lb) return;
            const img = document.getElementById('lb-image');
            const vid = document.getElementById('lb-video');
            const counter = document.getElementById('lb-counter');
            if (img) img.style.display = 'none';
            if (vid) { vid.style.display = 'block'; vid.src = proxyUrl(src); vid.play(); }
            if (counter) counter.textContent = '';
            lb.classList.remove('hidden');
        },
        close() {
            const lb = document.getElementById('lightbox');
            if (lb) lb.classList.add('hidden');
            const vid = document.getElementById('lb-video');
            if (vid) { vid.pause(); vid.src = ''; }
        },
        prev() {
            if (state.previewUrls.length < 1) return;
            state.currentIndex = (state.currentIndex - 1 + state.previewUrls.length) % state.previewUrls.length;
            lightbox.open(state.currentIndex);
        },
        next() {
            if (state.previewUrls.length < 1) return;
            state.currentIndex = (state.currentIndex + 1) % state.previewUrls.length;
            lightbox.open(state.currentIndex);
        },
    };

    // ── UI Components ──────────────────────────────────────────────────
    const ui = {
        updateLogin(d) {
            state.loggedIn = d.logged_in;
            const badge = document.getElementById('login-status');
            const logoutBtn = document.getElementById('logout-btn');
            if (!badge) return;
            if (d.logged_in) {
                badge.textContent = '已登录';
                badge.className = 'status-badge status-completed';
                if (logoutBtn) logoutBtn.classList.remove('hidden');
            } else {
                badge.textContent = '点击登录';
                badge.className = 'status-badge status-pending status-clickable';
                if (logoutBtn) logoutBtn.classList.add('hidden');
            }
        },

        async _pasteToInput(inputId) {
            const input = document.getElementById(inputId);
            if (!input) return;
            input.focus();
            input.select();
            toast.info('正在读取剪贴板...');

            // 超时辅助
            const withTimeout = (promise, ms) => {
                let tid;
                const timeout = new Promise((_, reject) => {
                    tid = setTimeout(() => reject(new Error('timeout')), ms);
                });
                return Promise.race([promise, timeout]).finally(() => clearTimeout(tid));
            };

            // 通道1：pywebview 原生桥接（桌面端最可靠）
            if (window.pywebview && window.pywebview.api && window.pywebview.api.get_clipboard) {
                try {
                    const text = await withTimeout(window.pywebview.api.get_clipboard(), 5000);
                    if (text && text.length > 5) {
                        setInputValue(input, extractUrl(text));
                        toast.success('已粘贴');
                        return;
                    }
                } catch (e) { /* fall through */ }
            }

            // 通道2：浏览器 Clipboard API
            if (navigator.clipboard && navigator.clipboard.readText) {
                try {
                    const text = await withTimeout(navigator.clipboard.readText(), 5000);
                    if (text && text.length > 5) {
                        setInputValue(input, extractUrl(text));
                        toast.success('已粘贴');
                        return;
                    }
                } catch (e) { /* fall through */ }
            }

            // 都失败
            toast.info('请按 Ctrl+V 粘贴到输入框');
        },

        pasteUrl() {
            ui._pasteToInput('url-input');
        },

        pasteProfileUrl() {
            ui._pasteToInput('profile-url-input');
        },

        async scrape() {
            const input = document.getElementById('url-input');
            if (!input) return;
            let url = input.value.trim();
            const m = url.match(/https?:\/\/v\.douyin\.com\/\S+/);
            if (m) url = m[0];
            if (!url) { toast.error('请输入链接'); return; }
            progress.show('解析中...', 10);
            const errorSec = document.getElementById('error-section');
            if (errorSec) errorSec.classList.add('hidden');
            const resultSec = document.getElementById('result-section');
            if (resultSec) resultSec.classList.add('hidden');
            try {
                const data = await api.scrape(url);
                state.currentTaskId = data.task_id;
                ui.showResult(data);
                progress.hide();
                ws.connect(state.currentTaskId);
            } catch (err) {
                progress.hide();
                if (err.message.includes('登录')) {
                    toast.info('请先登录后再使用');
                    loginModal.open();
                } else {
                    toast.error(err.message);
                }
            }
        },

        showResult(data) {
            const meta = data.metadata;
            const section = document.getElementById('result-section');
            if (!section) return;
            section.classList.remove('hidden');

            document.getElementById('result-title').textContent = meta.title || '未命名';
            document.getElementById('result-author').textContent = meta.author ? '@' + meta.author : '';

            const lpData = meta.live_photo_data || [];
            const typeLabel = {'image_set':'图文笔记','video':'视频','live_photo':'实况照片','comprehensive':'综合内容'};
            const typeEl = document.getElementById('media-type');
            if (typeEl) typeEl.textContent = lpData.length > 0 ? lpData.length + ' 张实况照片' : (typeLabel[meta.media_type] || '');

            const allUrls = meta.image_urls || [];
            state.previewUrls = allUrls;
            state.currentIndex = 0;
            const gallery = document.getElementById('image-gallery');
            if (!gallery) return;
            gallery.innerHTML = '';

            const countEl = document.getElementById('image-count');
            const renderBtn = document.getElementById('render-btn');
            const downloadBtn = document.getElementById('download-btn');
            const videoLink = document.getElementById('download-video-link');

            if (meta.media_type === 'video') {
                gallery.className = 'video-cover';
                if (allUrls[0]) {
                    gallery.innerHTML = '<div class="play-overlay">&#9654;</div><img src="'+proxyUrl(allUrls[0])+'" alt="cover">';
                    gallery.onclick = () => lightbox.openVideo(proxyUrl(meta.music_url || ''));
                }
                if (countEl) countEl.textContent = '';
                if (renderBtn) renderBtn.classList.add('hidden');
                if (downloadBtn) downloadBtn.textContent = '下载视频';
            } else {
                gallery.className = 'gallery-grid';
                const maxShow = Math.min(allUrls.length, 25);
                for (let i = 0; i < maxShow; i++) {
                    const div = document.createElement('div');
                    div.className = 'gallery-item';
                    let html = '<img src="'+proxyUrl(allUrls[i])+'" loading="lazy">';
                    if (lpData.length > 0 && i < lpData.length && lpData[i].video_url) {
                        html += '<span class="vid-badge">&#9654;</span>';
                    }
                    div.innerHTML = html;
                    div.onclick = (idx => () => {
                        if (lpData.length > idx && lpData[idx].video_url) lightbox.openVideo(proxyUrl(lpData[idx].video_url));
                        else lightbox.open(idx);
                    })(i);
                    gallery.appendChild(div);
                }
                if (countEl) countEl.textContent = '共 '+allUrls.length+' 张' + (lpData.length > 0 ? '（含 '+lpData.length+' 段视频）' : '');
                if (renderBtn) renderBtn.classList.remove('hidden');
                if (downloadBtn) downloadBtn.textContent = '下载素材';
            }

            const musicInfo = document.getElementById('music-info');
            if (meta.media_type !== 'video') {
                musicInfo.classList.remove('hidden');
                if (meta.music_url) {
                    document.getElementById('music-title').textContent = '背景音乐: ' + (meta.music_title || '抖音原声');
                    const player = document.getElementById('music-player');
                    if (player) player.src = proxyUrl(meta.music_url);
                    document.getElementById('music-status').textContent = '点击播放';
                } else {
                    document.getElementById('music-title').textContent = '暂无背景音乐';
                    document.getElementById('music-status').textContent = '';
                }
            } else {
                musicInfo.classList.add('hidden');
            }

            const liveOpt = document.getElementById('live-photo-option');
            if (liveOpt) liveOpt.style.display = (meta.media_type === 'live_photo' || lpData.length > 0) ? '' : 'none';

            if (videoLink) videoLink.classList.add('hidden');
            if (downloadBtn) downloadBtn.classList.remove('hidden');
            const dlLoc = document.getElementById('download-location');
            if (dlLoc) dlLoc.classList.add('hidden');
            section.scrollIntoView({behavior:'smooth', block:'start'});
        },

        async download() {
            if (!state.currentTaskId) return;
            progress.show('下载中...', 30);
            try {
                const data = await api.download(state.currentTaskId);
                progress.hide();
                const pe = document.getElementById('download-path');
                if (pe) {
                    if (data.download_path) pe.textContent = data.download_path;
                    else if (data.files && data.files.video_path) pe.textContent = data.files.video_path.replace(/\\/g,'/');
                    else if (data.files && data.files.images_dir) pe.textContent = data.files.images_dir.replace(/\\/g,'/').replace('/images','');
                }
                const dlLoc = document.getElementById('download-location');
                if (dlLoc) dlLoc.classList.remove('hidden');
                toast.success('下载完成');
            } catch (err) {
                progress.hide();
                toast.error(err.message);
            }
        },

        openFolder() {
            if (state.currentTaskId) api.openFolder(state.currentTaskId).catch(() => {});
        },

        renderModal: {
            open() { const m = document.getElementById('render-modal'); if (m) m.classList.remove('hidden'); },
            close() { const m = document.getElementById('render-modal'); if (m) m.classList.add('hidden'); },
        },

        async startRender() {
            if (!state.currentTaskId) return;
            ui.renderModal.close();
            const opts = {
                image_duration: parseFloat(document.getElementById('image-duration').value),
                transition: document.getElementById('transition').value,
                resolution: document.getElementById('resolution').value,
                use_original_music: document.getElementById('music-choice').value === 'original',
                live_photo_mode: document.getElementById('live-photo-mode').value,
                transition_duration: 0.7,
            };
            progress.show('渲染中...', 50);
            try {
                const data = await api.render(state.currentTaskId, opts);
                const vl = document.getElementById('download-video-link');
                if (vl) { vl.href = api.output(state.currentTaskId); vl.classList.remove('hidden'); }
                const pe = document.getElementById('download-path');
                if (pe && data.output_path) pe.textContent = data.output_path.replace(/\\/g,'/');
                const dlLoc = document.getElementById('download-location');
                if (dlLoc) dlLoc.classList.remove('hidden');
                progress.complete('渲染完成');
            } catch (err) {
                progress.hide();
                toast.error(err.message);
            }
        },

        toggleMusic() {
            const player = document.getElementById('music-player');
            const icon = document.getElementById('music-play-icon');
            const status = document.getElementById('music-status');
            if (!player) return;
            if (player.paused || player.ended) {
                player.play();
                if (icon) icon.innerHTML = '<svg viewBox="0 0 24 24"><rect x="6" y="4" width="4" height="16" rx="1" fill="currentColor"/><rect x="14" y="4" width="4" height="16" rx="1" fill="currentColor"/></svg>';
                if (status) status.textContent = '播放中';
            } else {
                player.pause();
                if (icon) icon.innerHTML = '<svg viewBox="0 0 24 24"><polygon points="8,5 19,12 8,19" fill="currentColor"/></svg>';
                if (status) status.textContent = '已暂停';
            }
        },

        dismissError() { const e = document.getElementById('error-section'); if (e) e.classList.add('hidden'); },
        cancelTask() { ws.disconnect(); progress.hide(); },

        // ── Delete operations ──────────────────────────────────────────
        toggleSelectAll() {
            const checked = document.getElementById('select-all').checked;
            document.querySelectorAll('.task-checkbox').forEach(cb => cb.checked = checked);
            ui.updateBatchBtn();
        },
        updateBatchBtn() {
            const checked = document.querySelectorAll('.task-checkbox:checked').length;
            const btn = document.getElementById('batch-delete-btn');
            if (!btn) return;
            if (checked > 0) { btn.classList.remove('hidden'); btn.textContent = '删除选中(' + checked + ')'; }
            else { btn.classList.add('hidden'); }
        },
        async deleteSingle(id) {
            if (!confirm('确定删除此任务？')) return;
            try {
                await api.deleteTask(id);
                const el = document.querySelector('[data-task-id="'+id+'"]');
                if (el) el.remove();
                ui.updateTaskCount();
            } catch (e) { toast.error(e.message); }
        },
        async batchDelete() {
            const ids = [];
            document.querySelectorAll('.task-checkbox:checked').forEach(cb => {
                const el = cb.closest('[data-task-id]');
                if (el) ids.push(el.dataset.taskId);
            });
            if (!ids.length) return;
            if (!confirm('确定删除选中的 ' + ids.length + ' 个任务？')) return;
            try {
                await api.batchDelete(ids);
                ids.forEach(id => {
                    const el = document.querySelector('[data-task-id="'+id+'"]');
                    if (el) el.remove();
                });
                document.getElementById('select-all').checked = false;
                ui.updateBatchBtn();
                ui.updateTaskCount();
            } catch (e) { toast.error(e.message); }
        },
        updateTaskCount() {
            const count = document.querySelectorAll('#task-list > [data-task-id]').length;
            const span = document.getElementById('task-count');
            if (span) span.textContent = count + ' 个任务';
            const list = document.getElementById('task-list');
            if (count === 0 && list) list.innerHTML = '<p class="empty-state">暂无记录</p>';
        },
        _logPollTimer: null,
        async _pollLogs() {
            try {
                const d = await api.get('/api/logs?lines=50');
                const el = document.getElementById('log-content');
                const count = document.getElementById('log-count');
                if (el) {
                    if (d.lines && d.lines.length > 0) {
                        el.textContent = d.lines.join('\n');
                    } else {
                        el.textContent = '暂无日志';
                    }
                }
                if (count) count.textContent = (d.total || 0) + ' 条';
            } catch (e) {
                // silent - panel just won't update
            }
        },
        toggleLogPanel() {
            const panel = document.getElementById('log-panel');
            if (!panel) return;
            const isCollapsed = panel.classList.contains('collapsed');
            panel.classList.toggle('collapsed');
            if (isCollapsed) {
                // Expand: start polling
                ui._pollLogs();
                if (ui._logPollTimer) clearInterval(ui._logPollTimer);
                ui._logPollTimer = setInterval(ui._pollLogs, 5000);
            } else {
                // Collapse: stop polling
                if (ui._logPollTimer) {
                    clearInterval(ui._logPollTimer);
                    ui._logPollTimer = null;
                }
            }
        },
        switchTab(name) {
            document.querySelectorAll('.sidebar-tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-pane').forEach(t => t.classList.remove('active'));
            const tabBtn = document.querySelector(`.sidebar-tab[data-tab="${name}"]`);
            const pane = document.getElementById(`tab-${name}`);
            if (tabBtn) tabBtn.classList.add('active');
            if (pane) pane.classList.add('active');
        },

        async scrapeProfile() {
            const input = document.getElementById('profile-url-input');
            if (!input) return;
            const url = input.value.trim();
            if (!url) { toast.error('请输入主页链接'); return; }
            if (!state.loggedIn) { toast.info('请先登录后再使用'); loginModal.open(); return; }
            const progressSec = document.getElementById('profile-progress');
            const progressMsg = document.getElementById('profile-progress-msg');
            const progressBar = document.getElementById('profile-progress-bar');
            if (progressSec) progressSec.classList.remove('hidden');
            if (progressMsg) progressMsg.textContent = '正在抓取主页...';
            if (progressBar) progressBar.style.width = '20%';
            try {
                const d = await api.post('/api/profile/scrape', {url, max_posts: 500});
                if (progressBar) progressBar.style.width = '80%';
                if (progressMsg) progressMsg.textContent = '渲染结果...';
                // User info
                const userSec = document.getElementById('profile-user');
                const userName = document.getElementById('profile-user-name');
                const postCount = document.getElementById('profile-post-count');
                const avatar = document.getElementById('profile-avatar');
                if (userSec) userSec.classList.remove('hidden');
                if (userName) userName.textContent = d.user_name || '未知用户';
                if (postCount) postCount.textContent = `共 ${d.total} 个作品`;
                if (avatar && d.avatar_url) avatar.innerHTML = `<img src="/api/proxy/media?url=${encodeURIComponent(d.avatar_url)}">`;
                // 保存到 state
                state.profilePosts = d.posts || [];
                state.profileUserName = d.user_name || '';
                // Posts grid
                const grid = document.getElementById('posts-grid');
                const postsSec = document.getElementById('profile-posts');
                const batchBar = document.getElementById('profile-batch-bar');
                if (postsSec) postsSec.classList.remove('hidden');
                if (batchBar) batchBar.classList.remove('hidden');
                ui.renderProfileGrid(d.posts || []);
                if (progressSec) progressSec.classList.add('hidden');
                const totalPosts = (d.posts || []).length;
                if (totalPosts > 0) {
                    toast.success(`抓取完成，共 ${totalPosts} 个作品`);
                } else {
                    toast.error('未抓取到作品，可能被WAF拦截，请重试或检查链接');
                }
            } catch (err) {
                if (progressSec) progressSec.classList.add('hidden');
                toast.error('抓取失败: ' + err.message);
            }
        },

        renderProfileGrid(posts) {
            const grid = document.getElementById('posts-grid');
            if (!grid) return;
            grid.innerHTML = '';
            if (!posts || posts.length === 0) {
                grid.innerHTML = '<p class="empty-state">未找到作品，可能主页为空或被拦截</p>';
                return;
            }
            posts.forEach((p, idx) => {
                const div = document.createElement('div');
                div.className = 'profile-post';
                div.dataset.index = idx;
                div.style.setProperty('--stagger', `${Math.min(idx, 24) * 18}ms`);
                const hasCover = p.cover_url && p.cover_url.length > 10;
                const imgSrc = hasCover ? '/api/proxy/media?url=' + encodeURIComponent(p.cover_url) : '';
                div.innerHTML = `
                    <input type="checkbox" class="profile-post-check" data-index="${idx}" checked onchange="Ptu.ui.updateProfileSelectCount()">
                    <img src="${imgSrc}" loading="lazy" onerror="this.style.display='none'; this.nextElementSibling.style.display='flex'">
                    <div class="post-placeholder" style="display:${hasCover?'none':'flex'}">
                        <span>${p.media_type === 'video' ? '视频' : '图文'}</span>
                        <span class="post-desc">${(p.desc||'').substring(0,20) || '未知作品'}</span>
                    </div>
                    <span class="post-type">${p.media_type === 'video' ? '视频' : '图文'}</span>`;
                // 点击网格项切换 checkbox（不跳转）
                div.onclick = (e) => {
                    if (e.target.tagName === 'INPUT') return;
                    const cb = div.querySelector('.profile-post-check');
                    if (cb) { cb.checked = !cb.checked; ui.updateProfileSelectCount(); }
                };
                grid.appendChild(div);
            });
            ui.updateProfileSelectCount();
        },

        toggleProfileSelectAll() {
            const checked = document.getElementById('profile-select-all').checked;
            document.querySelectorAll('.profile-post-check').forEach(cb => cb.checked = checked);
            ui.updateProfileSelectCount();
        },

        updateProfileSelectCount() {
            const checked = document.querySelectorAll('.profile-post-check:checked').length;
            const el = document.getElementById('profile-selected-count');
            if (el) el.textContent = `${checked} 个已选`;
            const btn = document.getElementById('batch-download-btn');
            if (btn) btn.disabled = checked === 0;
        },

        async batchDownload() {
            const checks = document.querySelectorAll('.profile-post-check:checked');
            if (!checks.length) { toast.error('请先选择要下载的作品'); return; }
            const indices = [];
            checks.forEach(cb => indices.push(parseInt(cb.dataset.index)));
            const posts = indices.map(i => state.profilePosts[i]).filter(Boolean);
            if (!posts.length) { toast.error('未找到选中的作品'); return; }

            const btn = document.getElementById('batch-download-btn');
            if (btn) { btn.disabled = true; btn.textContent = '准备中...'; }

            try {
                const d = await api.post('/api/profile/batch-download', {
                    posts: posts.map(p => ({
                        aweme_id: p.aweme_id,
                        share_url: p.share_url,
                        desc: p.desc,
                        cover_url: p.cover_url,
                        media_type: p.media_type,
                        create_time: p.create_time,
                        image_urls: p.image_urls || [],
                        video_url: p.video_url || '',
                        music_url: p.music_url || '',
                        music_title: p.music_title || '',
                        live_photo_data: p.live_photo_data || [],
                    })),
                    user_name: state.profileUserName || '未知用户',
                });
                const ok = d.success || 0;
                const fail = d.total - ok;
                toast.success(`批量下载完成: ${ok} 个成功${fail ? ', ' + fail + ' 个失败' : ''}`);
                if (d.base_dir) {
                    if (desktop.isAvailable) desktop.openInExplorer(d.base_dir);
                }
            } catch (err) {
                toast.error('批量下载失败: ' + err.message);
            } finally {
                if (btn) { btn.disabled = false; btn.textContent = '批量下载'; }
            }
        },

        async exportLogs() {
            try {
                const d = await api.post('/api/logs/save');
                if (d.path) {
                    toast.success('日志已保存: ' + d.path);
                } else {
                    const a = document.createElement('a');
                    a.href = '/api/logs/export';
                    a.download = 'ptu.log';
                    a.click();
                    toast.success('日志已导出');
                }
            } catch (err) {
                try {
                    const a = document.createElement('a');
                    a.href = '/api/logs/export';
                    a.download = 'ptu.log';
                    a.click();
                    toast.success('日志已导出');
                } catch (e2) {
                    toast.error('导出失败: ' + err.message);
                }
            }
        },

        async showLogFiles() {
            const section = document.getElementById('log-files-section');
            const list = document.getElementById('log-files-list');
            if (!section || !list) return;
            section.classList.toggle('hidden');
            if (!section.classList.contains('hidden')) {
                try {
                    const d = await api.get('/api/logs/files');
                    if (d.files && d.files.length > 0) {
                        list.innerHTML = d.files.map(f =>
                            `<div class="log-file-item">
                                <span>${f.date}${f.current ? ' · 当前运行' : ''}</span>
                                <a class="log-file-size" href="/api/logs/export?file=${encodeURIComponent(f.name)}">${(f.size/1024).toFixed(0)}KB 下载</a>
                            </div>`
                        ).join('');
                    } else {
                        list.innerHTML = '<div class="log-file-item" style="color:var(--text-tertiary)">暂无历史日志</div>';
                    }
                } catch(e) {
                    list.innerHTML = '<div class="log-file-item" style="color:var(--text-tertiary)">加载失败</div>';
                }
            }
        },

        async openLogsFolder() {
            try {
                const d = await api.openLogsFolder();
                toast.success('已打开日志文件夹: ' + d.path);
            } catch (err) {
                toast.error('打开日志文件夹失败: ' + err.message);
            }
        },
    };

    // ── Init ──────────────────────────────────────────────────────────
    function init() {
        // Login status
        api.loginStatus().then(d => {
            ui.updateLogin(d);
        }).catch(() => {});

        // Event listeners
        const input = document.getElementById('url-input');
        if (input) {
            input.addEventListener('keydown', e => { if (e.key === 'Enter') ui.scrape(); });
            input.addEventListener('paste', () => {
                setTimeout(() => {
                    const v = input.value.trim();
                    const m = v.match(/https?:\/\/v\.douyin\.com\/\S+/);
                    if (m) input.value = m[0];
                }, 10);
            });
        }

        // Profile URL input handlers
        const profileInput = document.getElementById('profile-url-input');
        if (profileInput) {
            profileInput.addEventListener('keydown', e => { if (e.key === 'Enter') ui.scrapeProfile(); });
            profileInput.addEventListener('paste', () => {
                setTimeout(() => { profileInput.value = extractUrl(profileInput.value); }, 10);
            });
        }

        // Login status click → open login modal
        const loginStatus = document.getElementById('login-status');
        if (loginStatus) {
            loginStatus.addEventListener('click', () => {
                if (!state.loggedIn) loginModal.open();
            });
        }

        // History click → switch to single tab and re-view cached result
        const taskList = document.getElementById('task-list');
        if (taskList) {
            taskList.addEventListener('click', async e => {
                const item = e.target.closest('[data-task-id]');
                if (!item) return;
                // Ignore clicks on checkbox, delete button, status badge
                if (e.target.closest('.task-checkbox, .task-delete, .status-badge, .task-date')) return;
                const taskId = item.dataset.taskId;
                if (!taskId) return;
                try {
                    const task = await api.get('/api/tasks/' + taskId);
                    if (task && task.metadata) {
                        state.currentTaskId = taskId;
                        // 切换到单链接 tab（结果面板在 single tab 内）
                        ui.switchTab('single');
                        ui.showResult({task_id: taskId, metadata: task.metadata});
                    }
                } catch (err) {
                    toast.error('无法加载历史记录: ' + err.message);
                }
            });
        }

        // Logout
        const logoutBtn = document.getElementById('logout-btn');
        if (logoutBtn) {
            logoutBtn.addEventListener('click', () => {
                if (!confirm('确定退出登录？此操作将同时清除浏览器缓存。')) return;
                api.logout().then(() => {
                    ui.updateLogin({logged_in: false});
                    toast.success('已退出登录');
                }).catch(e => toast.error('退出失败: ' + e.message));
            });
        }

        // Clear cache
        const clearCacheBtn = document.getElementById('clear-cache-btn');
        if (clearCacheBtn) {
            clearCacheBtn.addEventListener('click', () => {
                if (!confirm('确定清除浏览器缓存和登录状态？')) return;
                api.clearCache().then(d => {
                    toast.success(d.message || '缓存已清除');
                    ui.updateLogin({logged_in: false});
                }).catch(e => toast.error('清理失败: ' + e.message));
            });
        }
    }

    // Auto-init
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    // ── Theme Toggle ──────────────────────────────────────────────
    function toggleTheme() {
        const body = document.body;
        const isDark = body.getAttribute('data-theme') === 'dark';
        const next = isDark ? 'light' : 'dark';
        body.setAttribute('data-theme', next);
        localStorage.setItem('ptu-theme', next);
        // 更新按钮图标
        const btn = document.querySelector('.theme-toggle');
        if (btn) btn.textContent = next === 'dark' ? '☀️' : '🌙';
    }

    // 初始化主题
    (function initTheme() {
        const saved = localStorage.getItem('ptu-theme');
        if (saved === 'dark') {
            document.body.setAttribute('data-theme', 'dark');
            const btn = document.querySelector('.theme-toggle');
            if (btn) btn.textContent = '☀️';
        }
    })();

    return {
        state,
        api,
        desktop,
        ws,
        toggleTheme,
        ui: {
            ...ui,
            loginModal,
            lightbox,
            progress,
            toast,
        },
    };
})();

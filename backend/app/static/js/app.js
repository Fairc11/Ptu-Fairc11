/**
 * Ptu v1.0.0
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
        isDesktop: false,
        // 已登录标志，由 updateLogin 维护
        ws: null,
        loginPollTimer: null,
    };

    // ── API Client ─────────────────────────────────────────────────────
    const api = {
        async get(url) {
            const r = await fetch(url);
            if (!r.ok) { const e = await r.json().catch(()=>({})); throw new Error(e.detail || `请求失败 (${r.status})`); }
            return r.json();
        },
        async post(url, body) {
            const r = await fetch(url, {
                method: 'POST',
                headers: body ? {'Content-Type':'application/json'} : undefined,
                body: body ? JSON.stringify(body) : undefined,
            });
            if (!r.ok) { const e = await r.json().catch(()=>({})); throw new Error(e.detail || `请求失败 (${r.status})`); }
            return r.json();
        },
        scrape(url) { return api.post('/api/scrape', {url}); },
        download(taskId) { return api.post(`/api/tasks/${taskId}/download`); },
        render(taskId, opts) { return api.post(`/api/tasks/${taskId}/render`, {options: opts}); },
        output(taskId) { return `/api/tasks/${taskId}/output`; },
        loginQR() { return api.post('/api/login/qrcode'); },
        loginConfirm() { return api.post('/api/login/confirm'); },
        logout() { return api.post('/api/login/logout'); },
        loginStatus() { return api.get('/api/login/status'); },
        deleteTask(id) { return fetch(`/api/tasks/${id}`, {method:'DELETE'}).then(r=>r.json()); },
        batchDelete(ids) { return api.post('/api/tasks/batch-delete', {task_ids: ids}); },
        openFolder(taskId) { return api.post(`/api/tasks/${taskId}/open-folder`); },
    };

    // ── Desktop Bridge ─────────────────────────────────────────────────
    const desktop = {
        isAvailable: false,
        minimize() {},
        maximize() {},
        close()   {},
        startDrag() {},
        openInExplorer(path) {},
        notify(title, msg) {},
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
        error(msg)   { toast._show(msg, 'error'); },
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
                } else if (status) status.textContent = '获取失败，请重试';
            }).catch(e => { if (status) status.textContent = e.message || '获取失败，请重试'; });
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
            if (img) { img.style.display = 'block'; img.src = state.previewUrls[idx]; }
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
            if (vid) { vid.style.display = 'block'; vid.src = src; vid.play(); }
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
                badge.textContent = '未登录';
                badge.className = 'status-badge status-pending';
                if (logoutBtn) logoutBtn.classList.add('hidden');
            }
        },

        pasteUrl() {
            const input = document.getElementById('url-input');
            if (!input) return;
            navigator.clipboard.readText().then(text => {
                if (text) {
                    input.value = text;
                    const m = text.match(/https?:\/\/v\.douyin\.com\/\S+/);
                    if (m) input.value = m[0];
                }
            }).catch(() => {
                input.focus();
                document.execCommand('paste');
            });
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

            const typeLabel = {'image_set':'图文笔记','video':'视频'};
            const typeEl = document.getElementById('media-type');
            if (typeEl) typeEl.textContent = typeLabel[meta.media_type] || '';

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
                    gallery.innerHTML = '<div class="play-overlay">&#9654;</div><img src="'+allUrls[0]+'" alt="cover">';
                    gallery.onclick = () => lightbox.openVideo(meta.music_url || '');
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
                    div.innerHTML = '<img src="'+allUrls[i]+'" loading="lazy">';
                    div.onclick = (idx => () => lightbox.open(idx))(i);
                    gallery.appendChild(div);
                }
                if (countEl) countEl.textContent = '共 '+allUrls.length+' 张';
                if (renderBtn) renderBtn.classList.remove('hidden');
                if (downloadBtn) downloadBtn.textContent = '下载素材';
            }

            const musicInfo = document.getElementById('music-info');
            if (meta.media_type !== 'video') {
                musicInfo.classList.remove('hidden');
                if (meta.music_url) {
                    document.getElementById('music-title').textContent = '背景音乐: ' + (meta.music_title || '抖音原声');
                    const player = document.getElementById('music-player');
                    if (player) player.src = meta.music_url;
                    document.getElementById('music-status').textContent = '点击播放';
                } else {
                    document.getElementById('music-title').textContent = '暂无背景音乐';
                    document.getElementById('music-status').textContent = '';
                }
            } else {
                musicInfo.classList.add('hidden');
            }

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

        // Logout
        const logoutBtn = document.getElementById('logout-btn');
        if (logoutBtn) {
            logoutBtn.addEventListener('click', () => {
                if (!confirm('确定退出登录？')) return;
                api.logout().then(() => ui.updateLogin({logged_in: false}));
            });
        }
    }

    // Auto-init
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    return {
        state,
        api,
        desktop,
        ws,
        ui: {
            ...ui,
            loginModal,
            lightbox,
            progress,
            toast,
        },
    };
})();

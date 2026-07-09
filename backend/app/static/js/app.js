/**
 * Ptu v1.5.0 - Desktop Application Script
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
        loginCountdownTimer: null,
        qrExpiresAt: 0,
        profilePosts: [],
        profileUserName: '',
        profileUrl: '',
        profileNextCursor: 0,
        profileHasMore: false,
        generatedVideoPath: '',
        diagnosticPath: '',
        diagnosticFolder: '',
        douyinPanelVisible: false,
        browserDockSyncTimer: null,
        browserDockObserver: null,
        titlebarDragBound: false,
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

    function normalizeDouyinUrl(url) {
        let value = (url || '').trim();
        if (!value) return 'https://www.douyin.com/';
        if (value.startsWith('www.')) value = 'https://' + value;
        try {
            const u = new URL(value);
            const allowed = ['www.douyin.com', 'douyin.com', 'v.douyin.com', 'www.iesdouyin.com', 'iesdouyin.com'];
            if (!['http:', 'https:'].includes(u.protocol) || !allowed.includes(u.hostname.toLowerCase())) {
                return 'https://www.douyin.com/';
            }
            u.protocol = 'https:';
            return u.toString();
        } catch (_) {
            return 'https://www.douyin.com/';
        }
    }

    function isCaptureReadyDouyinUrl(url) {
        try {
            const u = new URL(normalizeDouyinUrl(url));
            const path = u.pathname.toLowerCase();
            if (u.hostname.toLowerCase() === 'v.douyin.com') return true;
            if (path.startsWith('/video/') || path.startsWith('/note/') || path.startsWith('/share/')) return true;
            return path.startsWith('/user/') && !path.startsWith('/user/self');
        } catch (_) {
            return false;
        }
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
        diagnosticCreate() { return api.post('/api/logs/diagnostic/create'); },
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
        openExternalUrl(url) {
            if (!desktop.isAvailable || !window.pywebview.api.open_external_url) {
                window.open(url, '_blank', 'noopener');
                return Promise.resolve({status: 'ok', url});
            }
            return window.pywebview.api.open_external_url(url || '');
        },
        notify(title, msg) { if (desktop.isAvailable) window.pywebview.api.show_notification(title, msg); },
        _dockRect() {
            const host = document.getElementById('browser-native-host');
            if (!host) return null;
            const r = host.getBoundingClientRect();
            return {x: r.left, y: r.top, width: r.width, height: r.height};
        },
        mountDouyinPanel(visible) {
            if (!desktop.isAvailable || !window.pywebview.api.mount_douyin_panel) {
                return Promise.resolve({status: 'missing'});
            }
            return window.pywebview.api.mount_douyin_panel(desktop._dockRect(), !!visible);
        },
        resizeDouyinPanel() {
            if (!desktop.isAvailable || !window.pywebview.api.resize_douyin_panel) {
                return Promise.resolve({status: 'missing'});
            }
            return window.pywebview.api.resize_douyin_panel(desktop._dockRect());
        },
        openDouyinPanel(url) {
            if (!desktop.isAvailable || !window.pywebview.api.open_douyin_panel) {
                return Promise.resolve({status: 'missing', url: url || ''});
            }
            return window.pywebview.api.open_douyin_panel(url || '', desktop._dockRect());
        },
        getDouyinPanelUrl() {
            if (!desktop.isAvailable || !window.pywebview.api.get_douyin_panel_url) {
                return Promise.resolve({status: 'missing', url: ''});
            }
            return window.pywebview.api.get_douyin_panel_url();
        },
        syncDouyinPanelLogin(url) {
            if (!desktop.isAvailable || !window.pywebview.api.sync_douyin_panel_login) {
                return Promise.resolve({status: 'missing', url: url || ''});
            }
            return window.pywebview.api.sync_douyin_panel_login(url || '');
        },
        clearDouyinPanelLogin() {
            if (!desktop.isAvailable || !window.pywebview.api.clear_douyin_panel_login) {
                return Promise.resolve({status: 'missing'});
            }
            return window.pywebview.api.clear_douyin_panel_login();
        },
        hideDouyinPanel() {
            if (!desktop.isAvailable || !window.pywebview.api.hide_douyin_panel) {
                return Promise.resolve({status: 'missing'});
            }
            return window.pywebview.api.hide_douyin_panel();
        },
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
            const panel = document.getElementById('browser-login-panel');
            if (!panel) return;
            desktop.hideDouyinPanel();
            state.douyinPanelVisible = false;
            panel.classList.remove('hidden');
            ui._setBrowserDockState('等待扫码');
            ui._setBrowserStatus('请在右侧扫码登录。登录成功后会自动显示抖音页面。');
            const success = document.getElementById('qr-success');
            const img = document.getElementById('qr-image');
            const loading = document.getElementById('qr-loading');
            if (success) success.classList.add('hidden');
            if (img) img.classList.add('hidden');
            if (loading) loading.classList.remove('hidden');
            loginModal.refresh();
        },
        close() {
            const panel = document.getElementById('browser-login-panel');
            if (panel) panel.classList.add('hidden');
            if (state.loginPollTimer) { clearInterval(state.loginPollTimer); state.loginPollTimer = null; }
            if (state.loginCountdownTimer) { clearInterval(state.loginCountdownTimer); state.loginCountdownTimer = null; }
        },
        updateCountdown() {
            const status = document.getElementById('qr-status');
            if (!status || !state.qrExpiresAt) return;
            const left = Math.max(0, Math.ceil((state.qrExpiresAt - Date.now()) / 1000));
            if (left <= 0) {
                status.textContent = '二维码已过期，请刷新';
                if (state.loginPollTimer) { clearInterval(state.loginPollTimer); state.loginPollTimer = null; }
                if (state.loginCountdownTimer) { clearInterval(state.loginCountdownTimer); state.loginCountdownTimer = null; }
                return;
            }
            if (!status.dataset.locked) {
                status.textContent = `请用抖音扫描二维码 · ${left}s`;
            }
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
            if (status) delete status.dataset.locked;
            if (state.loginPollTimer) { clearInterval(state.loginPollTimer); state.loginPollTimer = null; }
            if (state.loginCountdownTimer) { clearInterval(state.loginCountdownTimer); state.loginCountdownTimer = null; }
            api.loginQR().then(d => {
                if (d.qrcode) {
                    if (loading) loading.classList.add('hidden');
                    if (img) { img.src = 'data:image/png;base64,' + d.qrcode; img.classList.remove('hidden'); }
                    state.qrExpiresAt = Date.now() + ((d.expires_in || 120) * 1000);
                    if (status) status.textContent = '请用抖音扫描二维码';
                    loginModal.updateCountdown();
                    state.loginCountdownTimer = setInterval(loginModal.updateCountdown, 1000);
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
                const status = document.getElementById('qr-status');
                if (d.status === 'done') {
                    const img = document.getElementById('qr-image');
                    const success = document.getElementById('qr-success');
                    if (status) status.textContent = '登录成功！';
                    if (img) img.classList.add('hidden');
                    if (success) success.classList.remove('hidden');
                    if (state.loginPollTimer) { clearInterval(state.loginPollTimer); state.loginPollTimer = null; }
                    if (state.loginCountdownTimer) { clearInterval(state.loginCountdownTimer); state.loginCountdownTimer = null; }
                    ui.updateLogin({logged_in: true});
                    ui.afterLoginSuccess();
                    setTimeout(loginModal.close, 1500);
                } else if (d.status === 'scanned') {
                    if (status) {
                        status.textContent = d.message || '已扫码，请在手机上确认登录';
                        status.dataset.locked = 'true';
                    }
                } else if (d.status === 'expired') {
                    if (status) {
                        status.textContent = d.message || '二维码已过期，请刷新';
                        status.dataset.locked = 'true';
                    }
                    if (state.loginPollTimer) { clearInterval(state.loginPollTimer); state.loginPollTimer = null; }
                    if (state.loginCountdownTimer) { clearInterval(state.loginCountdownTimer); state.loginCountdownTimer = null; }
                } else if (d.status === 'error') {
                    if (status) {
                        status.textContent = d.message || '登录状态异常，请刷新二维码';
                        status.dataset.locked = 'true';
                    }
                }
            }).catch(e => {
                const status = document.getElementById('qr-status');
                if (status) status.textContent = (e.message && e.message.length < 60) ? e.message : '网络异常，请稍后重试';
            });
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
        _isMacLike() {
            const platform = (navigator.userAgentData && navigator.userAgentData.platform) || navigator.platform || '';
            return /Mac|iPhone|iPad|iPod/.test(platform);
        },

        _pasteShortcutLabel() {
            return ui._isMacLike() ? '⌘V' : 'Ctrl+V';
        },

        bindTitlebarDrag() {
            const titlebar = document.getElementById('custom-titlebar');
            if (!titlebar || !desktop.isAvailable || state.titlebarDragBound) return;
            state.titlebarDragBound = true;
            titlebar.addEventListener('pointerdown', e => {
                if (e.button !== 0) return;
                if (e.pointerType === 'touch') return;
                if (e.target.closest('#titlebar-controls, button, input, textarea, select, a')) return;
                desktop.startDrag();
            });
        },

        _browserInputUrl() {
            const input = document.getElementById('browser-url-input');
            return normalizeDouyinUrl(input ? input.value : '');
        },

        _setBrowserStatus(message) {
            const status = document.getElementById('browser-status');
            if (status) status.textContent = message;
        },

        _setBrowserDockState(message) {
            const stateEl = document.getElementById('browser-dock-state');
            if (stateEl) stateEl.textContent = message;
        },

        _setBrowserAddress(url) {
            const safeUrl = normalizeDouyinUrl(url);
            const input = document.getElementById('browser-url-input');
            if (input) setInputValue(input, safeUrl);
            return safeUrl;
        },

        afterLoginSuccess() {
            if (!desktop.isAvailable) return;
            const home = ui._setBrowserAddress('https://www.douyin.com/');
            loginModal.close();
            desktop.mountDouyinPanel(true);
            ui._setBrowserDockState('同步登录中');
            ui._setBrowserStatus('正在把 Ptu 登录状态同步到右侧内置浏览器...');
            desktop.syncDouyinPanelLogin(home).then(d => {
                if (d.status === 'ok') {
                    state.douyinPanelVisible = true;
                    ui._setBrowserDockState('已登录');
                    ui._setBrowserStatus('右侧内置抖音浏览器已同步 Ptu 登录状态。');
                    toast.success('内置浏览器已同步登录');
                } else if (d.status === 'missing_cookies') {
                    ui._setBrowserDockState('未同步');
                    ui._setBrowserStatus('Ptu 暂未拿到可同步的登录状态，请重新扫码。');
                } else if (d.status !== 'missing') {
                    ui._setBrowserDockState('同步失败');
                    ui._setBrowserStatus('内置浏览器登录同步失败，请刷新或重新扫码。');
                }
            }).catch(() => {
                ui._setBrowserDockState('同步失败');
                ui._setBrowserStatus('内置浏览器登录同步失败，请刷新或重新扫码。');
            });
        },

        async _currentBrowserUrl() {
            if (desktop.isAvailable) {
                const d = await desktop.getDouyinPanelUrl();
                if (d && d.status === 'ok' && d.url) {
                    return ui._setBrowserAddress(d.url);
                }
            }
            return ui._browserInputUrl();
        },

        async openDouyinPanel() {
            const url = ui._browserInputUrl();
            ui._setBrowserAddress(url);
            if (desktop.isAvailable) {
                ui._setBrowserDockState('打开中');
                loginModal.close();
                await desktop.mountDouyinPanel(false);
                const d = await desktop.openDouyinPanel(url);
                if (d.status === 'ok') {
                    state.douyinPanelVisible = true;
                    ui._setBrowserDockState('浏览中');
                    ui._setBrowserStatus('抖音已在右侧内置浏览区打开。请在抖音页面里手动点分享并复制链接。');
                    toast.success('已在右侧内置浏览区打开抖音');
                } else if (d.status === 'unsupported') {
                    state.douyinPanelVisible = false;
                    await desktop.openExternalUrl(d.url || url);
                    ui._setBrowserDockState('Mac 外部浏览器');
                    ui._setBrowserStatus('Mac V1.5 版暂不支持内嵌抖音预览，已改用系统浏览器打开。复制链接后粘贴到左侧抓取框。');
                    toast.info('已在系统浏览器打开抖音');
                } else {
                    ui._setBrowserDockState('打开失败');
                    ui._setBrowserStatus('内置浏览区打开失败，可使用系统浏览器手动复制链接。');
                    toast.error('打开内置面板失败: ' + (d.message || d.status));
                }
            } else {
                ui._setBrowserDockState('网页模式');
                ui._setBrowserStatus('网页模式无法承载抖音内置预览，请在系统浏览器中打开后复制链接。');
            }
        },

        browserHome() {
            ui._setBrowserAddress('https://www.douyin.com/');
            ui.openDouyinPanel();
        },

        async hideDouyinPanel() {
            try {
                const d = await desktop.hideDouyinPanel();
                if (d.status === 'ok' || d.status === 'missing') {
                    state.douyinPanelVisible = false;
                    ui._setBrowserDockState('已隐藏');
                    ui._setBrowserStatus('已隐藏抖音预览。需要时点击“打开抖音”即可恢复。');
                }
            } catch (err) {
                toast.error('隐藏预览失败: ' + err.message);
            }
        },

        updateLogin(d) {
            state.loggedIn = d.logged_in;
            const badge = document.getElementById('login-status');
            const logoutBtn = document.getElementById('logout-btn');
            if (!badge) return;
            if (d.logged_in) {
                badge.textContent = '已登录';
                badge.className = 'status-badge status-completed';
                if (logoutBtn) { logoutBtn.classList.remove('hidden'); logoutBtn.style.display = ''; }
            } else {
                badge.textContent = '点击登录';
                if (d.status === 'expired') badge.textContent = '已过期';
                badge.className = 'status-badge status-pending status-clickable';
                if (logoutBtn) { logoutBtn.classList.add('hidden'); logoutBtn.style.display = 'none'; }
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
            toast.info(`请按 ${ui._pasteShortcutLabel()} 粘贴到输入框`);
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
            state.generatedVideoPath = '';
            const copyPathBtn = document.getElementById('copy-path-btn');
            if (copyPathBtn) copyPathBtn.classList.add('hidden');
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
                toast.success('素材已保存到本地文件夹');
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
                image_duration: 2.6,
                transition: 'fade',
                resolution: '1080x1920',
                use_original_music: true,
                live_photo_mode: 'video',
                transition_duration: 0.28,
            };
            progress.show('准备生成竖屏视频...', 35);
            try {
                const data = await api.render(state.currentTaskId, opts);
                const vl = document.getElementById('download-video-link');
                if (vl) {
                    vl.href = api.output(state.currentTaskId);
                    vl.textContent = '打开视频';
                    vl.classList.remove('hidden');
                }
                const pe = document.getElementById('download-path');
                if (pe && data.output_path) {
                    state.generatedVideoPath = data.output_path;
                    const stats = [];
                    if (data.output_file) stats.push(data.output_file);
                    if (data.visual_count !== undefined) stats.push(`素材 ${data.visual_count}`);
                    if (data.live_video_count) stats.push(`实况 ${data.live_video_count}`);
                    if (data.music_duration_seconds) stats.push(`音乐 ${Number(data.music_duration_seconds).toFixed(1)}s`);
                    if (data.cycle_count && data.cycle_count > 1) stats.push(`循环 ${data.cycle_count}`);
                    pe.textContent = '已保存到素材文件夹 · ' + data.output_path.replace(/\\/g,'/') + (stats.length ? ' · ' + stats.join(' · ') : '');
                }
                const copyPathBtn = document.getElementById('copy-path-btn');
                if (copyPathBtn) copyPathBtn.classList.remove('hidden');
                const dlLoc = document.getElementById('download-location');
                if (dlLoc) dlLoc.classList.remove('hidden');
                progress.complete('竖屏视频生成完成');
                toast.success('视频已生成，已放在素材文件夹');
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
                const d = await api.post('/api/profile/scrape', {url, max_posts: 30, max_cursor: 0});
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
                state.profileUrl = url;
                state.profileNextCursor = d.next_cursor || 0;
                state.profileHasMore = !!d.has_more;
                // Posts grid
                const grid = document.getElementById('posts-grid');
                const postsSec = document.getElementById('profile-posts');
                const batchBar = document.getElementById('profile-batch-bar');
                if (postsSec) postsSec.classList.remove('hidden');
                if (batchBar) batchBar.classList.remove('hidden');
                ui.renderProfileGrid(d.posts || []);
                ui.updateProfilePagination();
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

        async loadNextProfilePage() {
            if (!state.profileUrl || !state.profileHasMore) return;
            const btn = document.getElementById('profile-next-page-btn');
            if (btn) { btn.disabled = true; btn.textContent = '加载中...'; }
            try {
                const d = await api.post('/api/profile/scrape', {
                    url: state.profileUrl,
                    max_posts: 30,
                    max_cursor: state.profileNextCursor || 0,
                });
                const incoming = d.posts || [];
                const seen = new Set(state.profilePosts.map(p => p.aweme_id));
                incoming.forEach(p => {
                    if (!seen.has(p.aweme_id)) {
                        state.profilePosts.push(p);
                        seen.add(p.aweme_id);
                    }
                });
                state.profileNextCursor = d.next_cursor || 0;
                state.profileHasMore = !!d.has_more && incoming.length > 0;
                ui.renderProfileGrid(state.profilePosts);
                ui.updateProfilePagination();
                toast.success(`已加载 ${state.profilePosts.length} 个作品`);
            } catch (err) {
                toast.error('加载下一批失败: ' + err.message);
            } finally {
                if (btn) { btn.disabled = !state.profileHasMore; btn.textContent = '下一批 30 个'; }
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
            ui.updateProfilePagination();
        },

        updateProfilePagination() {
            const bar = document.getElementById('profile-page-bar');
            const status = document.getElementById('profile-page-status');
            const btn = document.getElementById('profile-next-page-btn');
            if (!bar || !status || !btn) return;
            if (!state.profilePosts.length) {
                bar.classList.add('hidden');
                return;
            }
            bar.classList.remove('hidden');
            status.textContent = `已加载 ${state.profilePosts.length} 个`;
            btn.disabled = !state.profileHasMore;
            btn.textContent = state.profileHasMore ? '下一批 30 个' : '没有更多了';
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
                toast.info('正在打包脱敏诊断包，请稍等...');
                if (desktop.isAvailable) {
                    const d = await api.diagnosticCreate();
                    if (d.path) {
                        state.diagnosticPath = d.path;
                        state.diagnosticFolder = d.folder || '';
                        desktop.openInExplorer(d.path);
                        const box = document.getElementById('diagnostic-result');
                        const pathEl = document.getElementById('diagnostic-path');
                        if (box) box.classList.remove('hidden');
                        if (pathEl) pathEl.textContent = d.path;
                    }
                    toast.success('诊断包已导出，已打开所在文件夹');
                } else {
                    const a = document.createElement('a');
                    a.href = '/api/logs/diagnostic';
                    a.download = 'ptu_diagnostic.zip';
                    a.click();
                    toast.success('诊断包已导出');
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

        openDiagnosticFolder() {
            if (state.diagnosticPath && desktop.isAvailable) {
                desktop.openInExplorer(state.diagnosticPath);
            } else {
                ui.openLogsFolder();
            }
        },

        async copyCurrentPath() {
            const path = state.generatedVideoPath || (document.getElementById('download-path') || {}).textContent || '';
            if (!path) return;
            try {
                if (desktop.isAvailable && window.pywebview.api.set_clipboard) {
                    await window.pywebview.api.set_clipboard(path);
                } else if (navigator.clipboard && navigator.clipboard.writeText) {
                    await navigator.clipboard.writeText(path);
                }
                toast.success('路径已复制');
            } catch (err) {
                toast.error('复制失败: ' + err.message);
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

        acceptDisclaimer() {
            const check = document.getElementById('disclaimer-check');
            if (check && !check.checked) {
                toast.info('请先勾选已阅读并同意');
                return;
            }
            localStorage.setItem('ptu-disclaimer-accepted-v1', 'yes');
            const modal = document.getElementById('disclaimer-modal');
            if (modal) modal.classList.add('hidden');
        },

        showDisclaimerIfNeeded() {
            if (localStorage.getItem('ptu-disclaimer-accepted-v1') === 'yes') return;
            const modal = document.getElementById('disclaimer-modal');
            if (modal) modal.classList.remove('hidden');
        },

        mountBrowserDock() {
            const host = document.getElementById('browser-native-host');
            if (!host || !desktop.isAvailable) return;
            let mountedOnce = false;
            const sync = () => {
                if (state.douyinPanelVisible) desktop.resizeDouyinPanel();
                else if (!mountedOnce) {
                    mountedOnce = true;
                    desktop.mountDouyinPanel(false);
                }
            };
            if (state.browserDockSyncTimer) clearInterval(state.browserDockSyncTimer);
            state.browserDockSyncTimer = setInterval(sync, 250);
            setTimeout(sync, 300);
            setTimeout(sync, 900);
            if (window.ResizeObserver) {
                if (state.browserDockObserver) state.browserDockObserver.disconnect();
                state.browserDockObserver = new ResizeObserver(sync);
                state.browserDockObserver.observe(host);
                state.browserDockObserver.observe(document.body);
            }
            window.addEventListener('resize', sync);
            if (window.visualViewport) window.visualViewport.addEventListener('resize', sync);
        },
    };

    // ── Init ──────────────────────────────────────────────────────────
    function init() {
        // Login status
        api.loginStatus().then(d => {
            ui.updateLogin(d);
        }).catch(() => {});
        ui.showDisclaimerIfNeeded();
        ui.bindTitlebarDrag();
        ui.mountBrowserDock();

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
                if (!confirm('这会清除 Ptu 保存的抖音登录状态，不会影响你的 Edge、Chrome 或系统浏览器。确定继续吗？')) return;
                api.logout().then(() => {
                    ui.updateLogin({logged_in: false});
                    desktop.clearDouyinPanelLogin();
                    toast.success('已退出登录并清除 Ptu 登录痕迹');
                }).catch(e => toast.error('退出失败: ' + e.message));
            });
        }

        // Clear cache
        const clearCacheBtn = document.getElementById('clear-cache-btn');
        if (clearCacheBtn) {
            clearCacheBtn.addEventListener('click', () => {
                if (!confirm('这会清除 Ptu 保存的抖音登录状态和内置浏览器痕迹，不会影响你的 Edge、Chrome 或系统浏览器。确定继续吗？')) return;
                api.clearCache().then(d => {
                    desktop.clearDouyinPanelLogin();
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

# Ptu 开发日志

> 从 0 到 1 构建抖音图文/视频下载工具的全过程

---

## 2026-05-10 — UI 重构为暗色主题 + 浏览器实例复用

### 变更摘要
- **UI 完整重写**: 从 Morandi 蓝渐变主题全面迁移至 Noir + Indigo 暗色设计系统
- **架构重构**: `scraper.py` 引入浏览器实例复用机制（`_get_browser` / `_close_browser_deadline`），避免每次请求都启动新浏览器
- **精简代码**: 移除冗余的 Playwright 浏览器路径（API-only 模式），`scrape()` 方法只走 API 路径，未登录时抛出 `PermissionError`
- **新增特性**: `downloader.py` 图片并行下载（`asyncio.gather`）
- **打包**: `setup_check.py` 增加 `get_chromium_path()` 工具函数，新增 `install_chromium_direct()` 支持离线下载 Chromium headless shell
- **版本**: `main.py` 升级至 1.1.0

---

## 2026-05-08 — v1.0.0 正式发布

### 新增
- **打包**: PyInstaller 单文件 exe（75MB），`releases/1.0.0/Ptu.exe`
- **setup_check.py**: 首次运行自动检测 Chromium/FFmpeg，缺失则自动下载
- **build.spec**: 完整打包所有 backend 文件，排除非必需模块
- **通知栏**: 顶部更新通知条，支持 localStorage 记住关闭状态
- **版本号**: 统一改为 v1.0.0

### 修复
- **闪退**: `build.spec` excludes 里误写了 `email` 导致 uvicorn 启动失败
- **表情包混入**: `_extract_carousel` 使用 `naturalWidth` 过滤小图（>0 && <200），排除加载后的 emoji 和头像
- **启动阻塞**: FFmpeg 缺失不再阻塞启动，仅打印提示
- **三元运算符 bug**: meta 提取 JS 中 `d?d.content:''` 被我改成 `d?d.content||''` 破坏了语法，导致整个轮播提取跳过

---

## 2026-05-10 — UI 暗色主题 + 图片并行下载

### 变更
- `app.css` — 完整暗色设计系统（Noir + Indigo），CSS 变量体系
- `scraper.py` — 浏览器实例复用（_get_browser / _close_browser_deadline），API-only 模式
- `downloader.py` — IMAGE_SET 并行下载（asyncio.gather）
- `main.py` — 版本升至 1.1.0，`open_folder` 优先使用 task.download_path

---

## 2026-05-08 — v1.0.0 正式发布

### 新增
- 打包: PyInstaller → releases/1.0.0/Ptu.exe
- setup_check.py: 自动检测 Chromium/FFmpeg
- 通知栏、版本号 v1.0.0

### 修复
- email 模块被排除导致闪退
- naturalWidth 过滤 emoji
- FFmpeg 不阻塞启动
- 三元运算符缺少冒号

---

## 2026-05-10 — 侧边栏 → 暗色主题过渡

### 问题
用户反馈侧边栏布局比例不对、SVG 图标渲染有问题。

### 修复
- 删除侧边栏复杂 SVG 图标，替换为小圆点指示器
- UI 回滚到 Morandi 蓝主题

---

## 2026-05-10 — 安装包风格 UI 重设计

### 尝试
深色侧边栏 + 白色内容区的安装包风格，类似 Windows Installer 布局。

### 结果
用户评价"比例不对"，回滚。

---

## 2026-05-10 — 背景音乐提取

### 问题
实况照片的背景音乐没有被提取。

### 调查
iOS 实况照片的背景音乐 URL 包含 `ies-music` 关键词，存放在 `douyinstatic.com` CDN。

### 修复
- `scraper.py`: 网络拦截 `ies-music` / `/music/` 响应，DOM 兜底查找 `<video>` 标签中含 `ies-music` 的源
- 音乐提取后存入 `music_url_found`，附加到 ScrapeResult
- API 路径也从 `detail.music.play_url.url_list[0]` 提取

---

## 2026-05-10 — 图片解析彻底修复

### 根因分析
通过逐层调试发现 4 个根本原因:

1. **API 路径用了错误的接口** — `aweme/v1/web/aweme/detail/` 对图文笔记返回空数据，需要同时尝试 `aweme/v1/web/note/detail/`
2. **Playwright 图片懒加载** — `img.src` 返回占位 SVG，真实 URL 在 `data-src` 属性
3. **画廊模式** — 写死坐标点击 (1700, 500)，视口变化就点不到导航箭头
4. **标准模式** — 收集了整个页面的图片，包括侧边栏无关内容

### 修复
- API 路径: 同时尝试两个端点，合并 `aweme_detail` 和 `note_detail` 的图片源
- `data-src` 支持: `getUrl()` 函数先读 `img.src`，如果是占位则读 `getAttribute('data-src')`，再检查 `backgroundImage`
- DOM 导航翻页: `document.querySelector` 查找下一张按钮并 `.click()`，找不到再 fallback 到键盘箭头
- 标准模式: 按垂直位置排序加 x 位置过滤（只取页面中间 15%~70% 宽度区域）

---

## 2026-05-08 — v1.0.0 正式发布

### 新增
- **打包**: PyInstaller 单文件 exe（75MB），releases/1.0.0/Ptu.exe
- **setup_check.py**: 首次运行自动检测 Chromium/FFmpeg，缺失则自动下载
- **build.spec**: 完整打包所有 backend 文件，排除非必需模块
- **通知栏**: 顶部更新通知条，支持 localStorage 记住关闭状态
- **版本号**: 统一改为 v1.0.0

### 修复
- **闪退**: build.spec excludes 里误写了 email 导致 uvicorn 启动失败
- **表情包混入**: _extract_carousel 使用 naturalWidth 过滤小图（>0 && <200），排除加载后的 emoji 和头像
- **启动阻塞**: FFmpeg 缺失不再阻塞启动，仅打印提示
- **三元运算符 bug**: meta 提取 JS 中 d?d.content:'' 被我改成 d?d.content||'' 破坏了语法，导致整个轮播提取跳过


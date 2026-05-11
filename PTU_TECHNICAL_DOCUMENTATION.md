# Ptu - 抖音图文/视频下载工具 · 技术文档

> 版本: 1.1.0  
> 定型日期: 2026-05-09  
> 状态: **已定型，不再修改**

---

## 目录

1. [项目概述](#1-项目概述)
2. [系统架构](#2-系统架构)
3. [模块详解](#3-模块详解)
   - 3.1 入口层 (run.py, desktop_app.py)
   - 3.2 后端 API (FastAPI)
   - 3.3 数据模型
   - 3.4 抓取服务 (scraper.py)
   - 3.5 下载服务 (downloader.py)
   - 3.6 媒体处理 (media_processor.py)
   - 3.7 登录服务 (qr_login.py)
   - 3.8 实况照片处理 (live_photo.py)
   - 3.9 环境检测 (setup_check.py)
   - 3.10 JS API 桥接 (js_api.py)
4. [前段 UI 设计](#4-前端-ui-设计)
5. [API 端点文档](#5-api-端点文档)
6. [数据流详解](#6-数据流详解)
7. [已知技术决策与权衡](#7-已知技术决策与权衡)
8. [构建与发布](#8-构建与发布)
9. [附录: 文件清单](#9-附录文件清单)

---

## 1. 项目概述

Ptu 是一个抖音图文/实况照片/视频抓取与幻灯片视频合成工具。支持三种内容类型：

| 类型 | 识别方式 | 输出 |
|------|---------|------|
| 图文笔记 (image_set) | 多张图片，无关联视频 | 下载所有图片 + 背景音乐 |
| 视频 (video) | URL 含 `/video/` 或 API 返回 aweme_type ≤ 66 | 下载视频文件 + 封面 |
| 实况照片 (live_photo) | API 返回 image_post_info.images[].video | 每张图片 + 关联视频分别保存 |

### 核心能力

- Playwright 浏览器抓取（标准模式，无需登录）
- API 直调（快速模式，需扫码登录）
- FFmpeg 幻灯片视频合成（淡入淡出 / Ken Burns 转场）
- pywebview 桌面原生窗口（无边框 + 自定义标题栏）

---

## 2. 系统架构

```
┌─────────────────────────────────────────────────┐
│                 桌面窗口 (pywebview)             │
│  ┌───────────────────────────────────────────┐  │
│  │   Jinja2 模板 (base.html + index.html)     │  │
│  │   + static/css/app.css (深色主题)           │  │
│  │   + static/js/app.js (模块化 JS)           │  │
│  └───────────────┬───────────────────────────┘  │
│                  │ HTTP/WS                       │
│  ┌───────────────▼───────────────────────────┐  │
│  │         FastAPI + Uvicorn                  │  │
│  │  /api/scrape → scraper.py                 │  │
│  │  /api/download → downloader.py            │  │
│  │  /api/render → media_processor.py         │  │
│  │  /api/login/* → qr_login.py              │  │
│  │  /ws/{id} → progress.py                  │  │
│  └───────────────┬───────────────────────────┘  │
│                  │                               │
│  ┌───────────────▼───────────────────────────┐  │
│  │   Playwright (抓取)  │  FFmpeg (渲染)     │  │
│  │   httpx (下载)       │  aria2 (未启用)    │  │
│  └───────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
```

### 启动模式

| 模式 | 命令 | 说明 |
|------|------|------|
| **桌面模式** (默认) | `双击 Ptu 桌面版.lnk` 或 `python run.py` | 启动 FastAPI + pywebview 窗口 |
| **Web 模式** | `python run.py --web` | 仅启动 FastAPI，浏览器访问 |

打包 EXE 后双击默认进桌面模式。

---

## 3. 模块详解

### 3.1 入口层

#### `run.py` — 主入口

```python
流程:
1. 释放端口 8000
2. 检测 Chromium (打包后后台线程自动安装)
3. 启动 desktop_app.py (桌面模式默认)
```

关键参数路由:
- 无参数 / `-d` → 桌面模式
- `--web` → Web 模式（仅开发用）
- `sys.frozen` 自动 → 桌面模式

#### `desktop_app.py` — pywebview 桌面窗口

特性:
- **无边框窗口** (`frameless=True`, `easy_drag=False`)
- **自定义标题栏**: 最小化/最大化/关闭按钮 (`js_api.py` 中的方法)
- **窗口拖拽**: `WM_SYSCOMMAND` + `SC_MOVE | HTCAPTION`
- **系统托盘**: 关闭按钮 → 最小化到托盘（不退出）；托盘右键菜单 "显示/退出"
- **单实例锁**: `win32event.CreateMutex("Ptu-Desktop-1.1.0")`
- **窗口位置记忆**: 关闭时保存 `x, y, w, h, maximized` 到 `.ptu_window_state.json`

窗口创建:
```python
self.window = webview.create_window(
    title="Ptu",
    url=f"http://{host}:{port}/?desktop=1",
    frameless=True, easy_drag=False,
    min_size=(860, 580),
    confirm_close=True,
    js_api=self.js_api,
)
webview.start(menu=tray_menu, storage_path=str(Path.home() / ".ptu"))
```

---

### 3.2 后端 API (FastAPI)

框架装在 `backend/app/main.py`:

```python
app = FastAPI(title="Ptu", version="1.1.0")
```

启动时:
1. 创建 `tasks_db` 父目录
2. 初始化 `TaskStore`（JSON 文件持久化）
3. 创建下载/输出目录

**静态文件**: `backend/app/static/` → 挂载到 `/static/`

**模板**: Jinja2 + `backend/app/templates/`
- `base.html` — 基础布局（splash、自定义标题栏、topbar）
- `index.html` — 主 UI（URL 输入、结果展示、历史记录、弹窗、lightbox）

---

### 3.3 数据模型 (`schemas.py`)

```python
class MediaType(str, enum.Enum):
    IMAGE_SET = "image_set"      # 图集/笔记
    VIDEO = "video"              # 普通视频
    LIVE_PHOTO = "live_photo"    # 实况照片

class LivePhotoSource(BaseModel):
    image_url: str               # 图片 CDN URL
    video_url: str               # 关联视频 URL（可为空）

class ScrapeResult(BaseModel):
    title: str
    author: str
    media_type: MediaType
    image_urls: list[str]        # 图片 URL 列表
    music_url: str | None        # VIDEO 类型时存放视频 URL
    music_title: str
    cover_url: str | None
    live_photo_data: list[LivePhotoSource]
    aweme_id: str
```

---

### 3.5 抓取服务 (`scraper.py`) ⭐ 核心

#### 三条抓取路径 (优先级顺序)

```
scrape(share_url)
  ├─ (1) 路径一: API 直调
  │    _scrape_via_api(aweme_id)
  │    → httpx GET /aweme/v1/web/aweme/detail/
  │    → 需要 sessionid/sid_tt cookie + ttwid
  │    → 最快 (~2s)，但无 cookie 时返回 None
  │    → 使用 _parse_detail_to_result() 解析
  │
  ├─ (2) 路径二: Playwright 浏览器 (重点优化)
  │    _scrape_via_playwright(url)
  │    → 持久化浏览器 (跨请求复用节省 3-5s)
  │    → 多层提取策略:
  │       a) XHR 响应拦截 (8s 超时)
  │          → 拦截 /aweme/v1/web/aweme/detail/ 等 API
  │          → 使用 _parse_detail_to_result() 解析
  │          → 最快路径，视频页命中
  │       b) 内嵌 JSON 提取 (旧版页面)
  │          → 从 RENDER_DATA / __NEXT_DATA__ / __INITIAL_STATE__ 提取
  │          → 新版 Douyin 已不内嵌数据，此路常不通
  │       c) DOM 渲染后重试
  │          → 等 img.length > 10 → 再次尝试 JSON 提取
  │       d) 轮播提取 (仅图文/实况页)
  │          → 使用 Swiper 容器定位 + 中央栏位过滤
  │       e) DOM 提取 (最后退路)
  │          → 同样使用 Swiper + 中心栏位过滤
  │    → 通常 8-15s
  │
  └─ (3) 路径三: f2 库
       _scrape_via_f2(aweme_id)
       → 需安装 f2 库
       → 极少命中
```

#### 持久化浏览器 (`_get_browser`)

```python
async def _get_browser(self):
    # 1. 检查已有 browser 是否存活
    # 2. 优先使用系统 Chrome/Edge (channel="chrome"/"msedge")
    # 3. 回退到 Playwright 内置 Chromium
    # 4. asyncio.Lock() 保证线程安全
```

节省每次 3-5s 浏览器启动时间。浏览器会在 30s 无活动后自动关闭。

#### XHR 响应拦截 (核心优化)

```python
# 在页面导航前设置拦截
xhr_detail = asyncio.get_event_loop().create_future()

async def on_xhr(resp):
    if '/aweme/v1/web/aweme/detail/' in resp.url:
        data = await resp.json()
        xhr_detail.set_result(data)

page.on("response", on_xhr)

# 导航后等待 API 响应（8s 超时）
try:
    raw_data = await asyncio.wait_for(xhr_detail, timeout=8)
    result = self._parse_detail_to_result(detail)
    return result
except:
    pass  # fall through
```

**注意**: 此拦截仅对视频页生效（视频页调用 `/aweme/v1/web/aweme/detail/` API）。图文/实况页不再调用 detail 接口，而是通过 `related/` 接口或其他方式渲染数据，因此 XHR 拦截不生效，走轮播/DOM 提取。

#### 内容图片过滤策略 (`_extract_carousel` / `_extract_from_dom`)

Douyin 页面渲染后会包含大量推荐内容的缩略图，必须精准过滤。

**两层过滤策略**:

```
策略 1: Swiper 容器定位 (优先)
  → querySelector('[class*="SwiperSlide"]')
  → 只在 swiper 容器内查找图片
  → 最准，排除所有推荐内容

策略 2: 中心栏目过滤 (回退)
  → 只统计 viewport 水平位置 20%-65% 的图片
  → 只统计 viewport 垂直位置前 60% 的图片
  → 排除 off-screen (top=0, left=0, width=0) 的图片
  → 只统计 naturalWidth > 400px 的图片
  → base URL 去重 (去掉 ? 后和 ~tplv 后的参数)
```

**为什么 carousel 提取无法获取视频 URL**: 实况视频通过 `zjcdn.com` CDN 加载，且通常是懒加载（用户点击轮播滑动后才触发）。响应拦截器虽然监听 `zjcdn.com` + `/video/` 模式，但在 carousel 路径下页面尚未触发视频加载。

#### `_parse_detail_to_result` — 统一解析器

从 `detail` dict 解析 `ScrapeResult`，供 API 路径和 XHR 拦截路径共用。

```python
def _parse_detail_to_result(self, detail, page_url=""):
    # 1. 取 title / author
    # 2. 取音乐信息 (music.play_url.url_list[0])
    # 3. 判断视频帖: detail.video 存在且无 image_post_info
    # 4. 判断图文/实况: image_post_info.images[]
    #    → 每张图检测 img.video.play_addr → 有则 LIVE_PHOTO
```

---

### 3.6 下载服务 (`downloader.py`)

```python
class DownloadManager:
    semaphore = asyncio.Semaphore(3)  # 最大并发 3
```

三种下载模式:

| 内容类型 | 下载策略 | 目录结构 |
|---------|---------|---------|
| LIVE_PHOTO | 串行下载每个 pair (图片+视频) | `live_photos/` |
| VIDEO | 单文件下载 + 封面 | `video/` + `images/cover.jpg` |
| IMAGE_SET | **并行下载所有图片** (`asyncio.gather`) | `images/` |

**并行下载优化**: IMAGE_SET 使用 `asyncio.gather` 同时下载所有图片，20 张图从串行 20s 降到 ~3s。

**HEIC/WEBP 转换**: 下载后自动检查图片格式，HEIC → JPEG (via pillow_heif)，WEBP → JPEG (via PIL)。

---

### 3.7 媒体处理 (`media_processor.py`)

基于 FFmpeg 的幻灯片视频合成。

三种转场模式:

| 模式 | FFmpeg 策略 | 适用场景 |
|------|------------|---------|
| **simple** | `-loop 1 -t duration` + concat filter | 无转场，逐图切换 |
| **xfade** | `xfade=transition=fade` | 淡入淡出，需 >1 张图 |
| **ken_burns** | `zoompan` + concat demuxer | 缩放推进效果 |

注意: `live_photo_videos` 参数虽被接收但**未被实际使用** — 实况视频尚未集成到渲染管线。

---

### 3.8 登录服务 (`qr_login.py`)

三层获取二维码策略:

```
get_qrcode()
  ├─ (1) 直接 API (httpx)
  │    → GET sso.douyin.com/get_qrcode/ 拿 cookie
  │    → GET /passport/web/get_qrcode/ 拿 QR code base64
  │    → 无需浏览器，最快
  │
  ├─ (2) Playwright + 系统 Chrome/Edge
  │    → channel="chrome" / "msedge"
  │    → 拦截 /passport/web/get_qrcode 响应
  │
  └─ (3) Playwright + 内置 Chromium
       → executable_path 指定已安装的 Chromium
```

登录状态确认:
- Playwright 模式: 检查页面 cookie 是否包含 `sessionid`/`sid_tt`
- API 模式: 尝试轮询 `sso.douyin.com/passport/web/qrcode/check`

已知问题: API 模式的 `_confirm_api` 中，httpx client 随 `async with` 退出而关闭，无法复用初始 cookie，导致部分场景下无法确认登录。

---

### 3.9 实况照片处理 (`live_photo.py`)

HEIC → JPEG 转换，利用 `pillow_heif` 库。

```python
class LivePhotoProcessor:
    def is_heic(self, path: str) -> bool
    def convert_heic_to_jpeg(self, path: str, output_dir: Path) -> str
```

---

### 3.10 环境检测 (`setup_check.py`)

启动时检测 + 后台自动安装缺失组件。

| 组件 | 检测方式 | 安装方式 |
|------|---------|---------|
| Chromium | `get_chromium_path()` | 直接下载 Playwright CDN (EXE 可用) |
| FFmpeg | 检查 PATH + 当前目录 | 下载 gyand.dev 预编译包 |

`install_chromium_direct()`: 通过 `playwright._impl._registry.ALL_BROWSERS` 或 `browsers.json` 获取 build ID，从 `playwright.azureedge.net` 下载对应版本。

---

## 4. 前端 UI 设计

### 设计系统: Noir + Indigo

深色主题，替代原 Morandi Blue 浅色主题。

| Token | Value | 用途 |
|-------|-------|------|
| `--bg-app` | `#0e0e14` | 最深背景 |
| `--bg-card` | `#1e1e2c` | 卡片背景 |
| `--accent` | `#818cf8` | Indigo 强调色 |
| `--text-primary` | `#efeff6` | 主文本 |
| `--error` | `#f87171` | 错误色 |
| `--success` | `#34d399` | 成功色 |

**无 CDN 依赖** — 所有样式内联在 `app.css`（~380行），无 Tailwind、无 Font Awesome。

### JS 模块架构 (`app.js`)

```javascript
const Ptu = (() => {
    const state = { currentTaskId, previewUrls, mode, loggedIn, isDesktop, ... };
    const api = { scrape, download, render, loginQR, ... };
    const desktop = { minimize, maximize, close, startDrag, ... };
    const ws = { connect, disconnect };
    const ui = {
        updateLogin, setMode, pasteUrl, scrape, showResult,
        download, startRender, toggleMusic, ...,
        loginModal: { open, close, refresh, poll },
        lightbox: { open, openVideo, close, prev, next },
        progress: { show, update, hide, complete },
        toast: { success, error, info },
    };
    return { state, api, desktop, ws, ui };
})();
```

### 桌面模式检测

```html
<body data-desktop="{{ 'true' if desktop_mode else '' }}">
```

CSS 中:
```css
#custom-titlebar { display: none; }
[data-desktop="true"] #custom-titlebar { display: flex; }
```

所有 `window.pywebview.api.*` 调用都有 `if (Ptu.state.isDesktop)` 守卫。

---

## 5. API 端点文档

| 方法 | 路径 | 说明 | 参数 |
|------|------|------|------|
| GET | `/` | 首页 | `?desktop=1` 启用桌面模式 |
| POST | `/api/scrape` | 抓取链接 | `{"url": "..."}` |
| GET | `/api/tasks` | 列出所有任务 | — |
| GET | `/api/tasks/{id}` | 获取单个任务 | — |
| DELETE | `/api/tasks/{id}` | 删除任务（含文件） | — |
| POST | `/api/tasks/batch-delete` | 批量删除 | `{"task_ids": [...]}` |
| POST | `/api/tasks/{id}/download` | 下载素材 | — |
| POST | `/api/tasks/{id}/render` | 渲染视频 | `{"options": {...}}` |
| GET | `/api/tasks/{id}/output` | 下载渲染视频 | — |
| POST | `/api/tasks/{id}/open-folder` | 打开文件位置 | — |
| GET | `/api/tasks/{id}/files` | 列出下载文件 | — |
| WS | `/ws/{id}` | 实时进度推送 | — |
| POST | `/api/login/qrcode` | 获取二维码 | — |
| POST | `/api/login/confirm` | 确认登录 | — |
| POST | `/api/login/logout` | 退出登录 | — |
| GET | `/api/login/status` | 登录状态 | — |

---

## 6. 数据流详解

### 6.1 完整抓取流程

```
用户粘贴链接 → 点击抓取
  │
  ▼
POST /api/scrape {"url": "https://v.douyin.com/xxx"}
  │
  ▼
DouyinScraper.scrape(url)
  │
  ├─ 1. _resolve_url() → httpx HEAD → 获得真实 URL
  │    例: https://www.douyin.com/note/7623415106386410122
  │
  ├─ 2. _extract_aweme_id(resolved_url) → regex 提取 ID
  │    例: "7623415106386410122"
  │
  ├─ 3. API 路径 (有 cookie 时)
  │    GET /aweme/v1/web/aweme/detail/?aweme_id=xxx
  │    + Cookie: sessionid=xxx; ttwid=xxx
  │    + Referer: https://www.douyin.com/
  │    → 成功: _parse_detail_to_result()
  │    → 失败: None (空响应，需要 a_bogus 签名)
  │
  └─ 4. Playwright 路径
       a) _get_browser() → 获取/复用浏览器实例
       b) 创建 context + page
       c) 注入 cookies (来自 cookies.yaml)
       d) 设置 response 拦截器 (视频 + XHR)
       e) page.goto(url, domcontentloaded)
       f) XHR 响应拦截 (8s) → _parse_detail_to_result()
       g) JSON 提取 (旧版页面结构)
       h) DOM 渲染后重试
       i) 轮播提取 (Swiper 容器 → 中心栏位过滤)
       j) DOM 提取 (最终退路)
```

### 6.2 下载流程

```
POST /api/tasks/{id}/download
  │
  ▼
DownloadManager.download_all()
  │
  ├─ metadata.live_photo_data? → 串行下载每个图片+视频对
  ├─ metadata.media_type == VIDEO? → 下载视频文件 + 封面
  └─ 否则 (IMAGE_SET) → asyncio.gather 并行下载所有图片 + 音乐
```

### 6.3 渲染流程

```
POST /api/tasks/{id}/render
  │
  ▼
MediaProcessor.render_slideshow()
  │
  ├─ 收集 images/ 目录下所有图片
  ├─ 可选: HEIC → JPEG 转换
  ├─ 查找音乐文件
  ├─ 选择 FFmpeg 命令模板:
  │   simple / xfade / ken_burns
  └─ subprocess.run(ffmpeg_cmd, timeout=300)
```

---

## 7. 已知技术决策与权衡

### 7.1 为什么不用 a_bogus 签名？

Douyin 的公开 API 需要 `a_bogus`（X-Bogus）签名参数。DouyinCrawler 项目通过注入 JS + exejs 生成签名。但我们实测下载的 `douyin.js` 签名脚本未能使 API 返回数据（返回 200 空响应），原因可能是：
- JS 脚本版本与当前 Douyin 后端不匹配
- 需要额外的参数组合和 URL 编码规范
- 当前 Playwright 路径已能满足需求（视频页 XHR 拦截成功）

**当前方案**: 有 cookie 时尝试 API 直调，无 cookie 时走 Playwright。这比维护一个可能过期的签名算法更稳健。

### 7.2 为什么新版本 Douyin 页面无法提取内嵌 JSON？

Douyin 已从传统 SSR（数据嵌入 RENDER_DATA）迁移到 CSR（客户端渲染）。新版页面：
- `RENDER_DATA` 仅有 app 配置数据（无内容）
- `__NEXT_DATA__` 不存在
- `__INITIAL_STATE__` 不存在
- 内容通过 XHR/Fetch 动态加载

这对我们的影响:
- `_extract_from_page_data` 对新版页面永久失效
- 需要 XHR 拦截或 DOM 提取作为替代

### 7.3 API 模式的 httpx client 生命周期问题

在 `QRLoginService._get_qrcode_api()` 中，httpx client 通过 `async with` 创建，退出块时自动关闭。虽然将 `self._api_client = client` 保存了引用，但 client 在 `__aexit__` 中已关闭连接，后续 `_confirm_api()` 中创建的 new client 没有初始 cookie。

**影响**: API 模式的登录确认可能失败，回退到 Playwright 模式。

### 7.4 实况视频检测限制

实况视频通过 `zjcdn.com` CDN 加载，response 拦截器监听此域名。但视频加载是懒触发的（用户滑动到对应图片后才加载），所以在 carousel 提取路径下，视频 URL 可能尚未被捕获，导致实况照片被降级为普通图集。

### 7.5 下载器 video_url vs music_url 复用

下载器中 `VIDEO` 类型从 `metadata.music_url` 读取视频 URL。这是因为 `ScrapeResult` 没有专门的 `video_url` 字段，视频 URL 被复用了 `music_url` 字段。这在下载器中表现为条件判断:
```python
if metadata.media_type == MediaType.VIDEO and metadata.music_url:
    # music_url 实际存放的是视频播放地址
```

---

## 8. 构建与发布

### 8.1 开发环境

```bash
# 依赖
pip install -r requirements.txt

# 运行 (桌面模式)
python run.py

# 运行 (web 模式)
python run.py --web
```

### 8.2 打包 EXE

```bash
pyinstaller build.spec
```

打包配置要点 (`build.spec`):
- 入口: `run.py`
- 隐藏导入: 37+ 包（含 pywebview, playwright, plyer 等）
- `console=False`: 隐藏控制台窗口
- UPX 压缩开启
- 图标: `icon.ico`

### 8.3 安装包 (Inno Setup)

```bash
# 前提: Inno Setup 已安装
iscc installer.iss
```

安装包特性:
- WebView2 Runtime 检测 + 可选下载
- 桌面快捷方式 + 开始菜单
- 卸载时清理数据目录

---

## 9. 附录: 文件清单

```
抖音/
├── run.py                              # 主入口 (桌面/Web 模式路由)
├── desktop_app.py                      # pywebview 桌面窗口管理器
├── setup_check.py                      # 环境检测 + 自动安装
├── build.spec                          # PyInstaller 打包配置
├── build_exe.bat                       # 打包脚本
├── installer.iss                       # Inno Setup 安装脚本
├── icon.ico                            # 应用图标
├── PTU_TECHNICAL_DOCUMENTATION.md      # 本文档
├── 启动桌面版.bat                       # 快速启动 bat
├── 开发模式（热重载）.bat               # 开发启动 bat
│
├── backend/
│   ├── config.yaml                     # 配置文件
│   ├── cookies.yaml                    # Cookie 存储 (登录后自动保存)
│   │
│   └── app/
│       ├── main.py                     # FastAPI 主应用
│       ├── config.py                   # 配置管理 (路径解析)
│       ├── js_api.py                   # JS 原生桥接 (15 方法)
│       │
│       ├── api/
│       │   ├── router_scraper.py       # POST /api/scrape
│       │   ├── router_download.py      # POST /api/tasks/{id}/download
│       │   ├── router_media.py         # POST /api/tasks/{id}/render
│       │   ├── router_ws.py            # WS /ws/{id}
│       │   └── router_login.py         # 登录 API
│       │
│       ├── services/
│       │   ├── scraper.py             # ⭐ 核心抓取服务 (879 行)
│       │   ├── downloader.py          # 下载管理器
│       │   ├── media_processor.py     # FFmpeg 视频合成
│       │   ├── qr_login.py            # 扫码登录
│       │   ├── live_photo.py          # HEIC 转换
│       │   ├── progress.py            # WebSocket 进度推送
│       │   ├── ttwid.py               # ttwid token 获取
│       │   └── douyin_sign.js         # (预留) a_bogus 签名脚本
│       │
│       ├── models/
│       │   ├── schemas.py             # Pydantic 数据模型
│       │   └── task_store.py          # JSON 任务持久化
│       │
│       ├── templates/
│       │   ├── base.html              # 基础布局 + splash
│       │   └── index.html             # 主 UI 页面
│       │
│       └── static/
│           ├── css/app.css            # 深色主题 (380 行)
│           └── js/app.js              # 模块化 JS (520 行)
│
├── releases/
│   └── 1.0.0/
│       └── Ptu.exe                    # 打包后的独立 exe
│
└── data/                              # 运行时生成
    ├── tasks.json                     # 任务数据库
    ├── downloads/{folder}/            # 下载文件
    │   ├── images/                    # 图片
    │   ├── music/                     # 背景音乐
    │   ├── video/                     # 视频文件
    │   └── live_photos/               # 实况照片 (图片+短视频对)
    └── output/{id}/
        └── slideshow.mp4              # 渲染输出
```

---

> 文档结束。此版本 v1.1.0 已定型，不再修改。

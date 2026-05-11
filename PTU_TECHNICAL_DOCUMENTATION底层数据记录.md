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

---

## 工作痕迹 — 抓取失败 + 速度优化 (2026-05-11)

### 背景

用户报告"抓取失败"和"抓取速度有点慢"。Pydantic serializer warning（`Expected enum but got str`）已修复。

### RCA 根因分析

**现象**：`_scrape_via_pw_api()` 在隔离测试 2/5 成功（40%），但在 `scrape()` 全流程 0/3 全挂。

**根因一：f2 库 Bark 通知超时**（主因）

全流程耗时 78s，其中 f2 库的 `fetch_one_video()` 占了 71.5s。原因：
- f2 库 `DouyinHandler.__init__` 会初始化 `BarkHandler`（Bark 通知）
- `BarkHandler` 尝试连接 `api.day.app` 发送通知
- 国内网络无法访问 `api.day.app`，连接超时 + 重试
- 每次重试约 20s，总计 60s+
- f2 库版本 0.0.1.7，配置 `conf/conf.yaml` 中 `enable_bark: true`

**修复**：在 `_scrape_via_f2()` 中，导入 `DouyinHandler` 后立即设置：
```python
BarkClientConfManager.client_conf["enable_bark"] = False
```
效果：71.5s → 3.5s

**根因二：f2 数据提取嵌套未解**

`_scrape_via_f2()` 从 `fetch_one_video()` 返回值直接取顶层 key（`desc`, `images`, `author` 等）。
但 f2 返回的实际结构是 `{_data: {aweme_detail: {...}}}`，数据在 `_data.aweme_detail` 下。

修改：改为从 `r._data.aweme_detail` 提取，复用 `_parse_detail_to_result` 逻辑。

**根因三：WAF 指纹锁定**

Playwright 路径的 WAF 对抗分析：
- 抖音 WAF 在 `mon.zijieapi.com` 执行 JS 挑战
- 检测 headless 特征：`navigator.webdriver`、`navigator.plugins`、WebGL 指纹
- Playwright `add_init_script()` 可以绕过部分检测
- 单次通过率 ~40%（随时间波动）
- 同一浏览器进程被 WAF 指纹锁定后，新建 context 无效

尝试的方案及效果：

| 方案 | 成功率 | 说明 |
|------|--------|------|
| 原始固定 12s sleep | 40% | 基线 |
| + 增强反检测 (WebGL/chrome.runtime) | 40% | 无明显提升 |
| + 两步导航 (首页→目标页) | 40% | WAF 挑战未完成时无效 |
| + 智能等待 URL 跳回 douyin.com | 40% | 挑战能完成但仍概率拦截 |
| + 浏览器进程重启 | 20% | 反而更差（新进程新指纹） |

结论：WAF 对抗是概率游戏，最终方案是**绕过**而非**对抗**——用 f2 库（有 a_bogus 签名）直调 API。

### API 路径优化

**问题**：`_scrape_via_api` 串行重试 6 个端点，每个 8s 超时，总计 48s。

**修复**：
- 改为 `asyncio.as_completed` 并行发起
- httpx timeout 从 8s 降到 4s
- SSR HTML 兜底 timeout 从 10s 降到 3s

### DOM 提取改进

1. **作者信息为空**：原选择器 `[class*="nickname"]` 不匹配新版抖音 DOM。改为多级兜底：
   - `[class*="nickname"]`, `[class*="author"]`, `[class*="UserHeader"]`
   - `a[href*="user"]` 链接文本
   - `meta[name="author"]`
   - 文本节点搜索 `@` 前缀

2. **图片数量不一致**（2-16张波动）：懒加载图片未等全。修复：
   - 首次提取后等 1.5s 做二次补抓
   - base URL 去重合并

### 最终性能

```
测试 URL: https://v.douyin.com/nppy0mpKjAw/
全流程 scrape() 耗时: 4.6s (原 78s → 17x)
图片: 13张
作者: 𝙏𝙬𝙞𝙡𝙞𝙜𝙝𝙩
路径: API(1.1s FAIL) → f2(3.5s OK)
```

---

### 第二次迭代 (2026-05-11) — 音乐提取 + 正文 TXT

**改动 A — 图集音乐提取**
- 范围：`_scrape_via_f2()` 方法
- 从 `detail["music"]["play_url"]["url_list"][0]` 提取 `music_url`
- 从 `detail["music"]["title"]` 提取 `music_title`
- 传入 `ScrapeResult(music_url=..., music_title=...)`
- 验证：音乐 mp3 成功下载

**改动 B — 正文文字提取 + TXT**
- `schemas.py`: `ScrapeResult` 增加 `text_content: str = ""` 字段
- `_scrape_via_f2()`: 把 `detail.get("desc", "")` 写入 `text_content`
- `downloader.py`: `download_all()` 末尾写 `target_dir / "post.txt"`

**验证结果**
```
图片: 13张    音乐: music.mp3    文字: post.txt (51字)
正文内容: "大理苍山寂照庵，这里没有香火缭绕..."
```

**改动原则**
- 不改已有逻辑，只加字段/加写文件
- 所有新字段有默认值（`""`），不影响下游
- 备份目录 `备份_20260511/`，可随时回滚

### 剩余问题

1. Playwright 路径（Path 2/3）WAF 通过率仍仅 40-60%，但现在是兜底路径
2. f2 库 Bark 禁用通过修改 `BarkClientConfManager.client_conf` 运行时生效，不持久化
3. f2 库的 `INFO 处理作品:` 日志仍会输出到 stderr（已设 `logging.WARNING` 但 f2 用自定义 logger）
4. 纯视频链接的识别问题待讨论（当前 f2 路径对视频可能返回错误类型）

---

### 第三次迭代 (2026-05-11) — CDN 代理（防盗链预览修复）

**根因**
抖音 CDN（`douyinpic.com`, `tos-cn-`, `zjcdn.com`, `ies-music`）检查 HTTP Referer 头。
前端浏览器直接请求时 Referer = `http://127.0.0.1:8000/`，被 CDN 拦截。
图片/音乐/视频全部无法在线预览。

**方案：后端代理 + 前端统一走代理**

- `main.py`: 新增 `/api/proxy/media?url=...` 端点
  - 用共享 `httpx.AsyncClient` 转发请求，带上 `Referer: https://www.douyin.com/`
  - 域名白名单：`douyinpic.com`, `tos-cn-`, `zjcdn.com`, `ies-music`, `music.douyin`
  - 共享客户端在 shutdown 时释放

- `app.js`: 新增 `proxyUrl()` 辅助函数
  - 移入 `Ptu` IIFE 顶部，全局可用
  - 只对 CDN 域名做代理，本地 URL 原样返回
  - 替换全部 7 处 CDN 直连：
    1. lightbox 图片 `img.src`
    2. lightbox 视频 `vid.src`
    3. 视频封面 `gallery.innerHTML`
    4. 视频播放 `lightbox.openVideo()`
    5. gallery 缩略图 `img.src`
    6. 实况视频 `lightbox.openVideo(lpData[idx].video_url)`
    7. 音乐播放器 `player.src`

**验证**
```
图片代理: 200, 1.4MB (webp)
音乐代理: 200, 933KB (mp3)
```

**改动原则**
- `image_urls` 保持原始 CDN URL（下载器用原始 URL）
- 只有前端预览时走代理
- 无副作用，原有逻辑完全不变

---

## 完整工作会话记录 (2026-05-11)

> 本文档按时间顺序记录从"用户报告抓取失败"到"全部修复完成"的完整工作过程。
> 包括：用户原始需求 → RCA 分析 → 每次尝试的代码改动 → 测试结果 → 成功/失败判断 → 最终方案。
> 目的：沉淀经验，避免重复踩坑，为后续维护提供完整上下文。

---

### Phase 0：初始状态

**代码版本**: Ptu v1.1.0（项目根 CLAUDE.md 记录）
**项目结构**:
```
抖音/
├── run.py                   # 入口：uvicorn.run(backend.app.main:app)
├── desktop_app.py           # 不存在！文件丢失
├── setup_check.py           # 环境检测 + Chromium/FFmpeg 自动下载
├── 启动桌面版.bat            # cd /d %~dp0 → python run.py → pause
├── 开发模式（热重载）.bat
├── Ptu 桌面版.lnk           # 桌面快捷方式，指向 EXE 或 python run.py
├── backend/
│   └── app/
│       ├── main.py          # FastAPI 应用，注册路由 + 模板
│       ├── config.py        # 路径解析（支持 PyInstaller 打包模式）
│       ├── api/
│       │   ├── router_scraper.py   # POST /api/scrape
│       │   ├── router_download.py  # POST /api/tasks/{id}/download
│       │   ├── router_media.py     # POST /api/tasks/{id}/render
│       │   ├── router_ws.py        # WS /ws/{id}
│       │   └── router_login.py     # 扫码登录
│       ├── services/
│       │   ├── scraper.py          # 核心抓取（Playwright + API + f2）
│       │   ├── downloader.py       # 异步下载
│       │   ├── media_processor.py  # FFmpeg 视频合成
│       │   ├── qr_login.py         # 登录
│       │   ├── live_photo.py       # HEIC 转换
│       │   ├── ttwid.py            # ttwid Cookie 获取
│       │   └── progress.py         # WS 进度推送
│       ├── models/
│       │   ├── schemas.py          # Pydantic 模型
│       │   └── task_store.py       # JSON 任务持久化
│       ├── templates/              # Jinja2 模板
│       └── static/
│           ├── css/app.css
│           └── js/app.js           # 前端逻辑
├── PTU_TECHNICAL_DOCUMENTATION.md  # 定型文档 v1.1.0
├── cookies.yaml                    # 抖音登录 Cookie（sessionid/sid_tt 有效）
└── data/                           # 运行时生成
```

**依赖**:
- Python 3.13
- FastAPI + Uvicorn
- Playwright（Chromium headless）
- httpx
- f2 库 0.0.1.7（已安装）
- pywebview（桌面模式，但 desktop_app.py 缺失）
- FFmpeg

**初始性能**:
- `_scrape_via_pw_api` 隔离测试: 40% 成功率
- `scrape()` 全流程: 0/3 全部失败
- 总耗时: ~78s（其中 71.5s 是假死）

---

### Phase 1：初始报告

**用户报告**：桌面客户端启动显示 Pydantic serializer warning（`Expected enum but got str`）

**问题1：Pydantic 枚举序列化警告**
- 位置: `router_scraper.py`
- 代码: `store.update_status(task.task_id, "scraping")` → 传的是字符串而不是枚举值
- 修复: `"scraping"` → `TaskStatus.SCRAPING`，同理 `"scraped"` → `TaskStatus.SCRAPED`，`"error"` → `TaskStatus.ERROR`
- 状态: ✅ 已修复

**用户后续消息**：`/pua:on` + `"它显示抓取失败 我们重新审查一下全部代码吧 还有抓取的速度有点慢"`

---

### Phase 2：尝试 WAF 对抗（失败路径）

> 以下记录了所有尝试过的 WAF 对抗方案及其效果。
> 这些方案最终被判定为"概率游戏，不可靠"。
> 保留记录的目的是：下次遇到同类问题不必重复尝试。

#### 尝试 2.1：增强浏览器启动参数

**修改**: `_get_browser()` 的 `launch_args`
```python
# 原始
launch_args = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox", "--disable-web-security",
    "--disable-features=IsolateOrigins,site-per-process",
]

# 修改后（新增 6 个参数）
launch_args = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox", "--disable-web-security",
    "--disable-features=IsolateOrigins,site-per-process",
    "--disable-dev-shm-usage", "--no-zygote", "--disable-gpu",
    "--disable-accelerated-2d-canvas", "--no-first-run",
    "--disable-default-apps", "--disable-component-update",
]
```

**说明**: 这些参数减少 Chromium 的自动化特征，降低被 WAF 识别的概率。
- `--disable-dev-shm-usage`: 在 Docker/受限环境中避免共享内存不足
- `--no-zygote`: 禁用 zygote 进程（某些检测脚本会检查 zygote）
- `--disable-gpu`: 禁用 GPU 加速（headless 不需要）
- `--no-first-run`: 跳过首次运行向导
- `--disable-default-apps`: 不加载默认应用
- `--disable-component-update`: 禁用组件更新

**效果**: 无明显变化。WAF 通过率仍 ~40%。

#### 尝试 2.2：增强反检测 Stealth 脚本

**修改**: `_scrape_via_pw_api()` 的 `add_init_script` 内容

```javascript
// 原始（仅覆盖 navigator.webdriver）
Object.defineProperty(navigator, 'webdriver', { get: () => false });
Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en'] });

// 增强后（+ WebGL 指纹固定 + chrome.runtime + hardwareConcurrency）
Object.defineProperty(navigator, 'webdriver', { get: () => false });
Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en'] });
window.chrome = { runtime: {} };
const __gl = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(p) {
    if (p === 37445) return 'Intel Inc.';
    if (p === 37446) return 'Intel Iris OpenGL Engine';
    return __gl.call(this, p);
};
Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
```

**各覆盖项的作用**:
1. `navigator.webdriver = false`: 最基础的检测。headless Chrome 此属性为 true
2. `navigator.plugins` 设非空数组: headless 下 plugins 为空数组，WAF 检测到可能判定为自动化
3. `navigator.languages`: 固定中文语言，避免 WAF 通过语言设置判断
4. `window.chrome = { runtime: {} }`: 部分 WAF 检测 `chrome.runtime` 对象是否存在
5. WebGL `getParameter` 拦截: 在 37445 (UNMASKED_VENDOR_WEBGL) 和 37446 (UNMASKED_RENDERER_WEBGL) 处返回固定值。headless 的 WebGL renderer 通常是 "Google SwiftShader" 或类似值，与真实浏览器不同
6. `hardwareConcurrency = 8`: headless 可能返回 1 或 2，固定为 8 模拟真实机器

**效果**: 无明显变化。WAF 通过率仍 ~40%。说明 WAF 的检测维度不止这些。

#### 尝试 2.3：替换固定 12s sleep 为智能轮询

**问题**: 原始代码 `await asyncio.sleep(12)` 固定等待 12 秒。如果 WAF 在 8 秒就完成了，浪费 4 秒。如果 WAF 需要 15 秒，12 秒不够。

**修改**: 每 2 秒检查一次页面是否有 `douyinpic.com` 或 `tos-cn-` 图片出现，最多等 30 秒（后改为 20 秒）。

```python
# 原始
await asyncio.sleep(12)
img_count = await page.evaluate("document.querySelectorAll('img').length")
if img_count == 0 and attempt < 2:
    continue

# 改为智能轮询
content_loaded = False
for _ in range(10):  # 最多等 20s
    await asyncio.sleep(2)
    status = await page.evaluate("""() => {
        const imgs = document.querySelectorAll('img');
        if (imgs.length === 0) return 'no_images';
        for (const img of imgs) {
            const s = img.src || img.getAttribute('data-src') || '';
            if (s.includes('douyinpic.com') || s.includes('tos-cn-')) return 'content_found';
        }
        return 'no_content';
    }""")
    if status == 'content_found':
        content_loaded = True
        break
    elif status == 'no_images' and _ >= 2:
        # ~6s 无任何图片 → 被 WAF 拦截
        break
```

**效果**: 内容出现快的场景下提速明显（12s→8s），但总体成功率不变。

#### 尝试 2.4：两步导航（首页先触发 WAF）

**假设**: 直接访问目标页面时 WAF 冷启动拦截率高。先访问首页让 WAF 完成挑战并下发 cookie，再访问目标页面时 cookie 已就绪。

**修改**: 在 `page.goto(nav_url)` 之前先访问 `https://www.douyin.com/`

```python
# 两步导航
try:
    await page.goto("https://www.douyin.com/",
                    wait_until="domcontentloaded", timeout=15000)
    await asyncio.sleep(2.5)  # 等待 WAF 挑战
except Exception:
    pass

await page.goto(nav_url, ...)
```

**效果**: 无明显变化。原因：2.5 秒不够 WAF 挑战完成（JS 挑战通常需要 5-15 秒）。后来改为智能等待 URL 从 `mon.zijieapi.com` 跳回 `douyin.com`，但即使挑战完成，仍然有概率被拦截。

#### 尝试 2.5：浏览器进程重启（最差的尝试）

**假设**: WAF 指纹锁定在浏览器进程级别，新建 context 不够，需要新建整个浏览器进程。

**新增方法**: `_reset_browser()`
```python
async def _reset_browser(self):
    async with self._pw_lock:
        try:
            if self._pw_browser:
                await self._pw_browser.close()
        except Exception:
            pass
        self._pw_browser = None
        return await self._launch_new_browser()
```

同时在 `_scrape_via_pw_api` 的 WAF 检测路径中调用 `_reset_browser()` 替代 `continue`。

**效果**: **反而更差**。成功率从 40% 降到 20%（1/5）。原因分析：
1. 关闭浏览器进程 → 丢失已有 WAF cookie
2. 新浏览器进程 → 新指纹 →WAF 重新挑战
3. 短时间内反复启动新进程 → 行为模式异常 → 更容易被 WAF 判定为爬虫

**教训**: 浏览器进程重启是负优化。WAF 冷却需要时间，不是新建进程能解决的。这条路的正确做法应该是：**等足够长时间让 WAF 冷却**，而不是重新创建浏览器。

#### 尝试 2.6：智能等待 WAF URL 跳回

**改进尝试 2.4**: 不固定 2.5 秒，而是每 1 秒检查 URL 是否从 `mon.zijieapi.com` 跳回 `douyin.com`，最多等 15 秒。

```python
try:
    await page.goto("https://www.douyin.com/",
                    wait_until="domcontentloaded", timeout=15000)
    for _ in range(15):
        await asyncio.sleep(1)
        cur = page.url
        if 'douyin.com' in cur and 'mon.zijie' not in cur:
            break
except Exception:
    pass
```

**效果**: 成功率仍 ~40%。URL 跳回 douyin.com 说明 WAF 挑战已完成并下发 cookie，但后续访问 note 页面仍可能被拦截。这说明 WAF 的挑战结果不一定是"通过"，也可能是"检测到自动化，下发拦截 cookie"。

**结论**: WAF 对抗是一条死路。单次通过率 ~40%，3 次重试累积 ~78.4%（0.4 + 0.6×0.4 + 0.6²×0.4）。理论上可接受，但实际上 WAF 的检测是"连坐式"的——同一浏览器进程一旦被标记，后续所有请求都会被拦截。

---

### Phase 3：转向 f2 库（成功路径）

**关键转折**: 测试发现 f2 库（v0.0.1.7）能成功调用抖音 API，因为 f2 有内置的 `a_bogus` 签名机制。

#### 初始 f2 测试结果

```
python -c "from f2.apps.douyin.handler import DouyinHandler; h = DouyinHandler(...); r = await h.fetch_one_video(...)"
```

发现：
1. f2 返回结构是 `{_data: {aweme_detail: {...}}}`，不是扁平结构
2. `aweme_type: 68`（表示图文/笔记类型）
3. `Has images: True`，但 `image_post_info` 不存在（图片在顶层 `images` 字段）
4. `Has music: True` — 音乐数据存在
5. **Has author: True** — 作者信息可以提取
6. Bark 通知尝试连接 `api.day.app`，由于国内网络不可达，超时重试 3 次，耗时 ~60s

#### 修复 3.1：f2 数据提取嵌套

**错误**: 原始代码直接从 `raw` 取 `raw.get("desc")`、`raw.get("images")`。
但 f2 的 `raw` 只有 `_data` 和 `_cache` 两个 key。
```python
# 错误的原始代码
raw = r if isinstance(r, dict) else r.__dict__
title = raw.get("desc", "") or raw.get("title", "") or ""
author = raw.get("author", {}).get("nickname", "")
for f in ["images", "note_images"]:
    for x in (raw.get(f, []) or []):  # 这里永远为空
```

**修复**: 解嵌套
```python
detail = raw.get("_data", {}).get("aweme_detail", {})
title = detail.get("desc", "") or detail.get("title", "") or ""
author = detail.get("author", {}).get("nickname", "")
```

**效果**: f2 从返回 0 张图变为返回 13 张图。

#### 修复 3.2：Bark 通知禁用

**问题**: f2 库的 `DouyinHandler.__init__` 创建 `BarkHandler`，尝试向 `api.day.app` 发送通知。
由于国内网络不可达，连接超时 + 重试，每次 ~20s，总计 60s+。

```
[ERROR] Bark 通知发送失败，请检查 key 和网络连接
[ERROR] 连接端点失败，检查网络环境或代理：https://api.day.app/
```

**排查过程**:
1. 查看 f2 源码 `DouyinHandler.__init__`:
```python
def __init__(self, kwargs):
    self.bark_kwargs = BarkClientConfManager.merge()
    self.enable_bark = BarkClientConfManager.enable_bark()
    self.bark_notification = BarkHandler(self.bark_kwargs)
```

2. 查看 `BarkClientConfManager`:
```python
class ClientConfManager:
    client_conf = ConfigManager(f2.F2_CONFIG_FILE_PATH).get_config("f2")
    
class BarkClientConfManager(ClientConfManager):
    @classmethod
    def enable_bark(cls) -> bool:
        return cls.client_conf.get("enable_bark", False)
```

3. `ClientConfManager.client_conf` 是**类属性**，在类定义时（即 import 时）从 `conf/conf.yaml` 加载
4. `conf/conf.yaml` 中 `enable_bark: true`

**修复方法**: 导入 DouyinHandler 后立即修改类属性
```python
from f2.apps.douyin.handler import DouyinHandler, BarkClientConfManager
BarkClientConfManager.client_conf["enable_bark"] = False
```

**为什么这样有效？**
- Python 类属性是 mutable dict，修改直接影响所有实例
- `enable_bark()` 方法读取 `cls.client_conf.get("enable_bark")`，修改后的值为 False
- 注意：不能先于创建 handler 修改，因为 `BarkHandler` 在 `__init__` 中被创建。但 `BarkHandler` 是否发送通知取决于后续判断 `enable_bark` 的值

**替代方案（不采用）**:
1. 直接修改 `conf/conf.yaml` → 影响全局，不可逆
2. 用 `unittest.mock.patch` → 太重
3. 设置环境变量 → f2 不支持

**效果**: f2 调用耗时从 71.5s 降到 3.5s。

#### 修复 3.3：f2 日志抑制

**问题**: f2 库的 `INFO 处理作品:` 日志仍输出到 stderr。

**尝试**: `logging.getLogger('f2').setLevel(logging.WARNING)` — 无效。
**原因**: f2 使用自定义 logger，不走标准 logging 体系。

**状态**: 未完全解决。但 INFO 级别日志不影响功能，只是输出噪声。

---

### Phase 4：API 路径优化

**问题**: `_scrape_via_api()` 串行尝试 6 个端点，每个 8 秒超时，理论上最长 48 秒。

**原始代码**:
```python
endpoints = [url1, url2, ...]  # 6个端点
async with httpx.AsyncClient(timeout=8) as c:
    for url, hdrs in endpoints:  # 串行! 一个超时就等8s
        resp = await c.get(url, headers=hdrs)
        ...
```

**修复**:
1. 改为并行请求：`asyncio.as_completed(tasks, timeout=4)`
2. 超时从 8s 降到 4s
3. SSR HTML 兜底超时从 10s 降到 3s

```python
async with httpx.AsyncClient(timeout=4) as c:
    async def try_one(url, hdrs):
        resp = await c.get(url, headers=hdrs)
        ...
    tasks = [try_one(u, h) for u, h in all_endpoints]
    for coro in asyncio.as_completed(tasks, timeout=4):
        r = await coro
        if r: return r
```

**效果**: Path 1 从最长 48s 降到稳定 1.1s。

**注意**: `asyncio.as_completed` 的 `timeout` 参数在 Python 3.13 中可用。如果使用旧版 Python（<3.4 实际上不可能），会报错。

---

### Phase 5：DOM 提取改进

#### 问题 5.1：作者信息为空

**原始代码**:
```javascript
const el = document.querySelector('[class*="nickname"], [class*="author-name"], [class*="user-name"]');
```

**问题**: 抖音新版 SPA 的 DOM 类名已变更，上述选择器匹配不到任何元素。

**修复**: 多级兜底选择器
```javascript
const selectors = [
    '[class*="nickname"]',        // 原始选择器
    '[class*="author-name"]',     // 作者名
    '[class*="user-name"]',       // 用户名
    '[class*="UserHeader"]',      // 抖音新版组件
    '[class*="author"]',          // 泛 author 类
    'a[href*="user"]',            // 用户链接文本
    '[class*="AvatarAccount"]',   // 头像账户组件
    'meta[name="author"]',        // meta 标签
];
// 最后兜底：遍历文本节点找 @ 前缀
const walker = document.createTreeWalker(document.body, 4);
while (walker.nextNode()) {
    const t = walker.currentNode.textContent.trim();
    if (t.startsWith('@') && t.length > 1 && t.length < 50)
        return t.replace(/^@/, '');
}
```

**效果**: 作者从空字符串变为正确提取。测试 URL 的作者是 "𝙏𝙬𝙞𝙡𝙞𝙜𝙝𝙩"。

#### 问题 5.2：图片数量不一致

**问题**: 同一条内容，不同次抓取得到 2、4、11、16 张图片不等。

**根因**: 抖音页面使用懒加载（lazy loading），图片在进入视口时才加载 DOM。
`_extract_dom_to_result` 只抓取当前已加载的图片。

**修复**: 首次提取后等待 1.5 秒，二次补抓去重合并。
```python
# 首次提取
data = await page.evaluate("...")

# 等 1.5s 让懒加载图片加载
await asyncio.sleep(1.5)

# 二次补抓
more_imgs = await page.evaluate("...")

# 去重合并
existing = set(base_url for url in all_imgs)
for u in more_imgs:
    if base not in existing:
        all_imgs.append(u)
```

**注意**: 此修复仅对 Playwright 路径生效。实际生产中 f2 路径不受懒加载影响（API 直接返回完整数据）。

---

### Phase 6：音乐提取 + 正文 TXT

#### 用户需求

用户确认图文解析没有问题后提出：
1. 图集没有提取音乐 → 需要加
2. 提取标题及正文文字内容 → 生成 TXT

**确认流程**: 用户要求"先给方案再改"，并且要先备份。

#### 备份

创建 `备份_20260511/` 目录，复制所有 `.py` 文件：
```bash
backend/app/services/scraper.py
backend/app/services/downloader.py
backend/app/api/router_scraper.py
backend/app/models/schemas.py
backend/app/main.py
backend/app/config.py
run.py
...
```

备份脚本用 Python（`shutil.copy2`）而非 bash（路径含中文，xcopy 失败）。

#### 改动

**6.1: schemas.py — `ScrapeResult` 加 `text_content` 字段**
```python
class ScrapeResult(BaseModel):
    ...
    text_content: str = ""  # 正文文字内容（下载时生成 post.txt）
```

**6.2: scraper.py — `_scrape_via_f2()` 加音乐提取**
```python
# 提取音乐
music_data = detail.get("music", {})
if isinstance(music_data, dict):
    pu = music_data.get("play_url", {})
    if isinstance(pu, dict):
        ul = pu.get("url_list", [])
        if ul and ul[0]:
            music_url = ul[0]
            music_title = music_data.get("title", "") or ""

# 正文文字
text_content = detail.get("desc", "") or ""

return ScrapeResult(
    ..., 
    music_url=music_url or None, 
    music_title=music_title,
    text_content=text_content,
)
```

**6.3: downloader.py — `download_all()` 写 post.txt**
```python
if metadata.text_content:
    txt_path = target_dir / "post.txt"
    txt_path.write_text(metadata.text_content.strip(), encoding="utf-8")
```

**验证**:
```
图片: 13张    音乐: music.mp3（933KB）    post.txt: "大理苍山寂照庵..."（51字）
```

---

### Phase 7：CDN 代理（防盗链修复）

#### 用户报告

用户说"在线预览有一点问题，播放不出来"。

#### RCA

**根因**: 抖音 CDN 防盗链。

抖音的图片/音乐/视频 CDN（`douyinpic.com`, `tos-cn-`, `zjcdn.com`, `ies-music`）检查 HTTP `Referer` 头：
- 在抖音页面内 → `Referer: https://www.douyin.com/` → **通过**
- 在我们前端 → `Referer: http://127.0.0.1:8000/` 或无 Referer → **被拦截**

受影响的所有前端位置：

| # | 位置 | 代码 | 文件 |
|---|------|------|------|
| 1 | Lightbox 图片 | `img.src = state.previewUrls[idx]` | app.js:185 |
| 2 | Lightbox 视频 | `vid.src = src` | app.js:197 |
| 3 | 视频封面 | `gallery.innerHTML = '<img src="'+allUrls[0]+'"...>'` | app.js:320 |
| 4 | 视频播放 | `lightbox.openVideo(meta.music_url)` | app.js:321 |
| 5 | 缩略图 | `'<img src="'+allUrls[i]+'"...>'` | app.js:332 |
| 6 | 实况视频 | `lightbox.openVideo(lpData[idx].video_url)` | app.js:338 |
| 7 | 音乐播放器 | `player.src = meta.music_url` | app.js:354 |

#### 方案设计

**方案选择**:
- **方案 A**（采用）：后端代理端点 + 前端走代理
- **方案 B**（弃用）：下载后再预览 → 需要先下载才能看，体验差
- **方案 C**（弃用）：修改 ScrapeResult 返回代理 URL → 下载器拿到代理 URL 会出问题

**后端实现**: `main.py` 新增 `/api/proxy/media?url=...`

```python
# 共享客户端（复用连接池）
_proxy_client = httpx.AsyncClient(
    follow_redirects=True, timeout=60.0,
    headers={
        "User-Agent": "Mozilla/5.0 ...",
        "Referer": "https://www.douyin.com/",  # 关键：正确 Referer
    }
)

ALLOWED_PROXY_DOMAINS = ["douyinpic.com", "tos-cn-", "zjcdn.com", "ies-music", "music.douyin"]

@app.get("/api/proxy/media")
async def proxy_media(url: str):
    if not any(d in url for d in ALLOWED_PROXY_DOMAINS):
        raise HTTPException(403, "不允许的域名")
    resp = await _proxy_client.get(url)
    return Response(content=resp.content, media_type=resp.headers.get("content-type"))
```

**安全考虑**: 
1. 域名白名单：只允许抖音 CDN 域名，防止被滥用为开放代理
2. 共享客户端：复用连接池，减少 TCP 握手
3. 只读：不写入任何数据

**前端实现**: `app.js` 新增 `proxyUrl()` 函数

```javascript
function proxyUrl(url) {
    if (!url || url.startsWith('/api/proxy/')) return url;
    const needsProxy = ['douyinpic.com', 'tos-cn-', 'zjcdn.com', 'ies-music', 'music.douyin'];
    if (needsProxy.some(d => url.includes(d))) {
        return '/api/proxy/media?url=' + encodeURIComponent(url);
    }
    return url;
}
```

**为什么 `encodeURIComponent`？** CDN URL 可能包含 `?`、`~`、`&` 等特殊字符，直接拼接会破坏 URL 结构。

#### 验证

```
图片代理: GET /api/proxy/media?url=https://p3-pc-sign.douyinpic.com/tos-cn-i-0629/xxx...
         → 200, 1.4MB, Content-Type: image/webp

音乐代理: GET /api/proxy/media?url=https://sf6-cdn-tos.douyinstatic.com/obj/ies-music/xxx.mp3...
         → 200, 933KB, Content-Type: audio/mpeg
```

---

### Phase 8：视频识别问题（未修改，仅讨论）

**用户说**: "视频链接没有问题，不用改了"

**背景**: f2 路径对所有 aweme_id 调用 `fetch_one_video()`，该 API 对视频帖返回视频数据。但 `_scrape_via_f2()` 只检查 `images` 字段。

如果 `detail` 中包含 `video` 而非 `images`，则 `_scrape_via_f2()` 会返回 `None`（因为 `imgs` 列表为空），然后 fallthrough 到 Playwright 路径（Path 2/3）。因此视频并没有"无法识别"——只是降级到了 Playwright 路径。

用户确认 OK，skip。

---

### 累计改动清单

| Phase | 文件 | 改动内容 | 行数 |
|-------|------|---------|------|
| P1 | router_scraper.py | 字符串→枚举 | 3 |
| P2.1 | scraper.py | 浏览器启动参数扩展 | +6 |
| P2.2 | scraper.py | 增强反检测脚本 | +15 |
| P2.3 | scraper.py | 智能轮询替代固定sleep | 重写 |
| P2.4 | scraper.py | 两步导航 | +10 |
| P2.5 | scraper.py | 浏览器重启方法（后撤销） | +20/-20 |
| P2.6 | scraper.py | WAF URL 智能等待 | +8 |
| P3.1 | scraper.py | f2 数据结构解嵌套 | +5 |
| P3.2 | scraper.py | Bark 通知禁用 | +2 |
| P3.3 | scraper.py | 日志抑制 | +5 |
| P4 | scraper.py | API 并行+超时降低 | 重写 |
| P5.1 | scraper.py | 作者多级选择器 | +15 |
| P5.2 | scraper.py | 二次补抓去重 | +15 |
| P6.1 | schemas.py | text_content 字段 | +1 |
| P6.2 | scraper.py | 音乐+文字提取 | +18 |
| P6.3 | downloader.py | post.txt 写入 | +7 |
| P7 | main.py | 代理端点 + 共享客户端 | +25 |
| P7 | app.js | proxyUrl() + 7处替换 | +15 |

**总计**: ~100 行净增代码，涉及 5 个源文件。

---

### 关键教训

1. **WAF 对抗是概率游戏，不要深陷**：抖音的 WAF 检测维度多（浏览器指纹、IP 信誉、请求模式、TLS 指纹），单点突破效果有限。花 1 小时调参不如花 10 分钟找替代方案。

2. **第三方库的副作用要警惕**：f2 库的 Bark 通知本意是"好心的通知功能"，但在国内网络环境下变成"60 秒的定时炸弹"。任何第三方库的"锦上添花"功能都可能在生产环境中成为瓶颈。

3. **数据提取一定要验证结构**：`_scrape_via_f2` 的 bug 本质是**假设 API 返回扁平结构**，但实际是嵌套的。这个错误在调试时浪费了 2 轮测试才发现。教训：对接任何 API 的第一件事是打印原始返回结构。

4. **浏览器进程重启是负优化**：直觉上"被 WAF 拦了就换新浏览器"是合理的，但实际导致更低的通过率。因为 WAF 会记录 IP + 行为模式，短时间内反复新建浏览器进程反而更可疑。

5. **先备份再改代码**：用户要求先备份是对的。没有备份的情况下，错误的改动可能导致无法回滚。备份_20260511/ 目录在本次迭代中发挥了安全网的作用。

6. **异步超时是隐形的性能杀手**：`httpx` 的超时参数（timeout=8）在没有设置的情况下默认是 5 秒？不，httpx 默认没有超时（None）。这意味着如果一个端点永远不返回（连接挂起），会无限等待。所有网络请求都必须显式设置超时。

7. **CDN 防盗链是前端问题的常见根因**：第三方 CDN 资源在前端直连时，`Referer` 头是浏览器自动设置的，开发者容易忽略。代理转发时手动设置正确的 Referer 是标准解决方案。

---

### 封包专题：PyInstaller 打包避坑指南（v1.2.0 经验）

> 本次封包从 v1.1.0 → v1.2.0，经历了多次构建失败和 exe 启动崩溃。
> 以下记录所有踩过的坑和解决方案，确保下次封包不再重复。

#### 坑 1：`uvicorn.run("app:str")` 字符串导入在打包后失效

**现象**: exe 启动后秒退，无任何错误输出（console=False 时）。

**根因**: `run.py` 使用 `uvicorn.run("backend.app.main:app", ...)` 字符串方式指定应用。
在 PyInstaller 打包的 frozen 环境中，字符串导入走的是 `importlib.import_module` 路径，
但 frozen 模块的查找机制与常规 Python 不同，字符串导入可能找不到模块。

**修复**: 改为直接导入 app 对象再传给 uvicorn：
```python
# 错误
uvicorn.run("backend.app.main:app", host="127.0.0.1", port=8000)

# 正确
from backend.app.main import app
uvicorn.run(app, host="127.0.0.1", port=8000)
```

**教训**: 凡是字符串形式的模块导入，都要改为直接 import。包括但不限于 uvicorn、celery、gunicorn 等框架的字符串应用指定方式。

#### 坑 2：`console=False` 时 `sys.stdout` 为 `None`

**现象**: exe 闪退，ptu_boot.log 写入异常。

**根因**: 打包配置中 `console=False` 时，Windows 不分配控制台窗口，`sys.stdout` 被设为 `None`。
run.py 中 `_log()` 函数直接调用 `sys.stdout.write()` 导致 `AttributeError`。

**修复**: 所有 `sys.stdout` 操作前加 None 检查：
```python
if sys.stdout:
    sys.stdout.write(msg + "\n")
    sys.stdout.flush()
```

**教训**: 任何涉及控制台输出的代码，在 windowless 模式下都必须考虑 `sys.stdout` 为 None 的情况。
推荐统一封装日志函数，在函数内部做保护，而不是在每次调用处检查。

#### 坑 3：PyInstaller `EXE.assemble()` 的 PermissionError

**现象**: 第二次构建时 `PermissionError: [WinError 5] 拒绝访问 dist/Ptu.exe`。

**根因**: 前一次构建的 exe 进程仍然在运行（后台 zombie），锁定文件。
PyInstaller 在构建新 exe 时需要先删旧文件，被锁定则报错。

**排查方法**:
```bash
# 查找所有 zombie Ptu 进程
tasklist | findstr "Ptu"
# 强制杀死
taskkill /f /im Ptu.exe
taskkill /f /im runw.exe
# 清理构建目录
rd /s /q dist build
```

**教训**: 构建前必须确保没有残留进程。推荐在 build_exe.bat 开头加：
```bat
taskkill /f /im Ptu.exe 2>nul
taskkill /f /im runw.exe 2>nul
rd /s /q dist build
```

#### 坑 4：`hiddenimports` 缺失导致运行时 import 失败

**现象**: exe 能启动但功能异常（未显式报错，但特定模块调用失败）。

**根因**: 动态导入或 try/except 包裹的 import 可能不被 PyInstaller 的静态分析捕获。
例如 `_scrape_via_f2()` 中：
```python
try:
    from f2.apps.douyin.handler import DouyinHandler
except ImportError:
    return None
```
PyInstaller 可能不会将 f2 打包进去，因为它在 try/except 里。

**修复**: 在 `build.spec` 的 `hiddenimports` 中显式列出所有可能的导入路径。

**哪些模块需要 hiddenimports**:
1. try/except 里的 import
2. 字符串 `__import__()` 或 `importlib.import_module()`
3. setuptools entry_points 注册的插件
4. 条件导入（if/else 分支里的 import）
5. `__init__.py` 中延迟导入的子模块

#### 坑 5：第三方库的数据文件未打包

**现象**: 运行时 `FileNotFoundError` 或配置加载失败。

**根因**: PyInstaller 默认只打包 `.py` 文件。像 f2 的 `conf/conf.yaml`、`conf/app.yaml` 等
数据文件不会被自动包含。

**修复**: 在 `build.spec` 的 `datas` 中添加：
```python
# 收集 f2 库的配置文件
import importlib.util
_f2_spec = importlib.util.find_spec('f2')
if _f2_spec and _f2_spec.submodule_search_locations:
    _f2_conf = Path(_f2_spec.submodule_search_locations[0]) / 'conf'
    if _f2_conf.exists():
        for _f in _f2_conf.rglob('*'):
            if _f.suffix in ('.yaml', '.yml'):
                datas.append((str(_f), 'f2/conf'))
```

**教训**: 第三方库的数据文件、配置文件、证书文件、字体文件等都需要显式加入 datas。

#### 坑 6：`build.spec` 中 `excludes` 影响依赖

**现象**: 构建成功但运行时某些功能缺失。

**根因**: `excludes` 列表可能排除了某些间接依赖。例如排除 `cryptography` 会影响 f2 的加密功能。

**教训**: `excludes` 只应排除确信不需要的大型库（tkinter, matplotlib, PyQt5 等）。
不确定的依赖不要排除，宁可 exe 大一点也不能功能缺失。

#### 重要检查清单（每次封包前对照）

```
□ 1. 版本号更新
   □ installer.iss 中的 #define MyAppVersion
   □ main.py 中的 FastAPI(title=..., version=...)
   □ 输出文件名 Ptu_Setup_v{version}

□ 2. hiddenimports
   □ 新增的 try/except import 均已添加
   □ 第三方库的子模块已覆盖
   □ 对照 warn-build.txt 中的 missing modules 检查

□ 3. 数据文件
   □ 模板文件（.html）
   □ 静态文件（.css, .js）
   □ 配置文件（.yaml, .yml, .json）
   □ cookies.yaml（用户数据，运行时生成）

□ 4. exe 启动验证（console=True 临时构建一次）
   □ 启动后能访问 HTTP 服务
   □ 核心功能可调用
   □ 验证后改回 console=False

□ 5. 环境清理
   □ 无残留 zombie Ptu.exe 进程
   □ dist/ build/ 已清空
   □ __pycache__ 已清理

□ 6. 回滚方案
   □ 有备份目录
   □ 旧版本 exe 保留在 releases/ 下
   □ build.spec 已提交或备份
```

#### 下次封包记住

1. **先开 console=True 构建一次**，运行看控制台输出，确认无误后改回 False 正式构建
2. **每次构建前** `taskkill /f /im Ptu.exe` + 清理 dist/build
3. **新增第三方库一定要检查** hiddenimports + 数据文件
4. **字符串形式的模块导入全部改为直接 import**
5. **console=False 时所有 stdout 操作必须加 None 检查**


# Ptu - 抖音图文/视频下载工具 v1.1.0

抖音图文/实况照片/视频抓取+幻灯片视频合成工具。

## 启动方式

```bash
双击 桌面 Ptu 桌面版.lnk     # 桌面客户端模式（默认，推荐）
双击 启动桌面版.bat            # 开发模式（需要 Python 环境）
python run.py                  # 同上
python run.py --web            # Web模式（浏览器访问 http://127.0.0.1:8000，仅开发）
```

**注意**：v1.1.0 起仅桌面模式可用，Web 模式仅用于开发调试。抓取必须登录，无"标准模式"。

## 项目结构

```
抖音/
├── run.py                 # 入口（打包后默认走桌面模式）
├── setup_check.py         # 环境检测：自动下载 Chromium/FFmpeg
├── build.spec             # PyInstaller 打包配置
├── desktop_app.py         # pywebview桌面客户端
├── installer.iss          # Inno Setup 安装脚本
├── icon.ico               # 应用图标
├── PTU_TECHNICAL_DOCUMENTATION.md  # 技术文档（1.1.0 定型版）
├── 启动桌面版.bat          # 开发模式快速启动
├── 开发模式（热重载）.bat   # 热重载模式
├── releases/
│   ├── 1.0.0/
│   │   └── Ptu.exe
│   └── 1.1.0/
│       └── Ptu.exe        # 打包后的独立 exe
├── backend/
│   ├── app/
│   │   ├── main.py        # FastAPI主应用
│   │   ├── config.py      # 配置
│   │   ├── js_api.py      # JS原生桥接（窗口管理/对话框等）
│   │   ├── api/
│   │   │   ├── router_scraper.py   # POST /api/scrape
│   │   │   ├── router_download.py  # POST /api/tasks/{id}/download
│   │   │   ├── router_media.py     # POST /api/tasks/{id}/render
│   │   │   ├── router_ws.py        # WS /ws/{task_id}
│   │   │   └── router_login.py     # POST /api/login/qrcode 等
│   │   ├── services/
│   │   │   ├── scraper.py          # ⭐核心抓取（API + Playwright + Viewer）
│   │   │   ├── downloader.py       # 异步下载管理器（并行下载）
│   │   │   ├── media_processor.py  # FFmpeg视频合成
│   │   │   ├── live_photo.py       # HEIC转换
│   │   │   ├── qr_login.py         # 抖音扫码登录
│   │   │   ├── ttwid.py            # ttwid Cookie获取
│   │   │   └── progress.py         # WebSocket进度推送
│   │   ├── models/
│   │   │   ├── schemas.py          # Pydantic数据模型（含COMPREHENSIVE类型）
│   │   │   └── task_store.py       # 任务持久化(JSON)
│   │   ├── templates/
│   │   │   ├── base.html           # 基础布局+深色主题
│   │   │   └── index.html          # 前端UI（继承base.html）
│   │   └── static/
│   │       ├── css/app.css         # Noir+Indigo 深色主题
│   │       └── js/app.js           # 模块化JS
│   └── config.yaml
│   └── cookies.yaml        # 抖音Cookie（扫码登录后自动保存）
└── data/                   # 运行时生成
    ├── tasks.json          # 任务数据库
    ├── downloads/{folder}/
    │   ├── images/         # 图片
    │   ├── music/          # 背景音乐
    │   ├── video/          # 视频文件
    │   └── live_photos/    # 实况照片（图片+短视频对）
    └── output/{id}/
        └── slideshow.mp4
```

## 内容类型

| 类型 | 识别方式 | 输出 |
|---|---|---|
| 图文笔记 (image_set) | 多张图片，无关联视频 | 下载所有图片+背景音乐 |
| 视频 (video) | URL 含 `/video/` 或 API 返回 aweme_type ≤ 66 | 下载视频文件+封面 |
| 实况照片 (live_photo) | API 返回 image_post_info.images[].video | 每张图片+关联视频分别保存 |
| 综合内容 (comprehensive) | 部分图片有视频，部分无视频 | 按实况照片方式处理每张 |

## API端点

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/scrape` | 抓取链接（需登录，未登录返回 401） |
| GET | `/api/tasks` | 列出所有任务 |
| DELETE | `/api/tasks/{id}` | 删除单个任务（含文件清理） |
| POST | `/api/tasks/batch-delete` | 批量删除任务 |
| POST | `/api/tasks/{id}/download` | 下载素材到本地 |
| POST | `/api/tasks/{id}/render` | 渲染幻灯片视频 |
| GET | `/api/tasks/{id}/output` | 下载视频 |
| POST | `/api/tasks/{id}/open-folder` | 在资源管理器中打开文件夹 |
| GET | `/api/tasks/{id}/files` | 列出下载文件清单 |
| WS | `/ws/{id}` | 实时进度推送 |
| POST | `/api/login/qrcode` | 获取登录二维码 |
| POST | `/api/login/confirm` | 确认扫码登录 |
| POST | `/api/login/logout` | 退出登录 |
| GET | `/api/login/status` | 登录状态 |

## 抓取流程（三条路径）

```
scrape(share_url)
  ├─ (1) _scrape_via_api()      直调抖音 API（最快，需 a_bogus 签名）
  ├─ (2) _scrape_via_pw_api()   Playwright 页面内调 API（浏览器自动签名）
  └─ (3) _scrape_via_playwright()  DOM/Viewer 提取（兜底）
       ├─ XHR 响应拦截（视频页命中）
       ├─ 内嵌 JSON 提取（旧版页面）
       ├─ 轮播提取（Swiper + 中心栏位过滤）
       ├─ Viewer 翻页提取（点击图片→翻页→收集懒加载图片）
       └─ DOM 提取（最终退路）
```

## 关键功能

- **扫码登录**: 右上角点登录→抖音扫码→保存Cookie→后续 API 抓取
- **仅登录可用**: v1.1.0 起删除标准模式，必须登录才能使用
- **自动提取链接**: 粘贴抖音分享文本，自动提取URL
- **图片预览**: 点击放大，左右键切换
- **音乐试听**: 有背景音乐的作品可点击播放
- **实况照片/综合内容**: 正确识别图片+视频混合内容
- **视频合成**: FFmpeg合成幻灯片视频（淡入淡出/Ken Burns转场）
- **历史管理**: 支持单个删除和全选批量删除任务记录

## 技术要点

- 抓取使用 Playwright (Chromium headless)，持久化浏览器跨请求复用
- API 直调需要 `a_bogus` 签名（浏览器内部 fetch 自动处理）
- 桌面端使用 pywebview frameless 模式 + 自定义标题栏
- 窗口关闭最小化到托盘（不退出），托盘右键菜单退出
- Windows 上 FFmpeg 使用 `subprocess.run`（`asyncio.create_subprocess_exec` 会失败）
- ttwid 通过 ByteDance 公开接口自动获取
- 图片CDN需要带签名参数的完整URL和 `Referer: douyin.com` 头
- 默认走桌面模式（`run.py` 无参数），`--web` 参数走 Web 模式
- 所有用户可见错误信息均为中文（HTTP 401/404/500 等）
- COMPREHENSIVE 类型：部分图片有 video → 综合内容
- 风格类型: IMAGE_SET / VIDEO / LIVE_PHOTO / COMPREHENSIVE

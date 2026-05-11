# Ptu - 抖音图文/视频下载工具 v1.0.0

抖音图文笔记/视频抓取+幻灯片视频合成工具。

## 启动方式

```bash
python run.py              # Web 模式（浏览器访问 http://127.0.0.1:8000）
python run.py --web        # 同上
```

## 项目结构

```
├── run.py                 # 入口
├── setup_check.py         # 环境检测
├── build.spec             # PyInstaller 打包配置
├── installer.iss          # Inno Setup 安装脚本
├── icon.ico               # 应用图标
├── backend/
│   ├── app/
│   │   ├── main.py        # FastAPI主应用
│   │   ├── config.py      # 配置
│   │   ├── api/
│   │   │   ├── router_scraper.py   # POST /api/scrape
│   │   │   ├── router_download.py  # POST /api/tasks/{id}/download
│   │   │   ├── router_media.py     # POST /api/tasks/{id}/render
│   │   │   ├── router_ws.py        # WS /ws/{task_id}
│   │   │   └── router_login.py     # POST /api/login/qrcode 等
│   │   ├── services/
│   │   │   ├── scraper.py          # 核心抓取
│   │   │   ├── downloader.py       # 异步下载管理器
│   │   │   ├── media_processor.py  # FFmpeg视频合成
│   │   │   ├── qr_login.py         # 抖音扫码登录
│   │   │   ├── ttwid.py            # ttwid Cookie获取
│   │   │   └── progress.py         # WebSocket进度推送
│   │   ├── models/
│   │   │   ├── schemas.py          # Pydantic数据模型
│   │   │   └── task_store.py       # 任务持久化
│   │   ├── templates/
│   │   │   ├── base.html           # 基础布局+深色主题
│   │   │   └── index.html          # 前端UI
│   │   └── static/
│   │       ├── css/app.css         # Noir深色主题
│   │       └── js/app.js           # 前端逻辑
│   └── config.yaml
└── releases/              # 发布版本
```

## 内容类型

| 类型 | 说明 |
|------|------|
| 图文笔记 (image_set) | 多张图片，支持下载原图+背景音乐 |
| 视频 (video) | 单个视频，支持下载视频文件+封面 |

## 抓取流程

```
scrape(share_url)
  ├─ (1) _scrape_via_api()      直调抖音 API
  └─ (2) _scrape_via_playwright()  Playwright 兜底提取
```

## 技术要点

- 抓取使用 Playwright (Chromium headless)
- 支持标准模式（无需登录）和快速模式（扫码登录）
- Windows 上 FFmpeg 使用 `subprocess.run`
- ttwid 通过 ByteDance 公开接口自动获取
- 图片CDN需要带签名参数的完整URL和 `Referer: douyin.com` 头

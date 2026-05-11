# Ptu 开发对话记录

## 2026-05-04

### 需求提出
用户想要一个抖音爬图工具，能够：
- 爬取抖音图片
- 配合背景音乐合成视频
- 处理实况照片

### 技术方案设计
- **后端**: Python FastAPI + Playwright + FFmpeg
- **前端**: Jinja2 + Tailwind CSS + Alpine.js
- **桌面端**: pywebview
- **抓取**: Playwright (Chromium headless)

### Phase 1: 基础搭建
1. 创建项目目录结构
2. 编写 requirements.txt
3. 安装 FFmpeg
4. 编写 config.py、main.py
5. 编写 HTML 模板基础框架

### Phase 2: 抓取模块
1. 编写 models（schemas.py, task_store.py）
2. 编写 scraper.py（f2 封装）
3. 编写 scrape API 端点

### Phase 3: 下载模块
1. 编写 progress.py（WebSocket 管理器）
2. 编写 downloader.py
3. 编写下载 API 端点和 WebSocket 端点

### Phase 4: 媒体处理
1. 编写 live_photo.py（HEIC 转换）
2. 编写 media_processor.py（FFmpeg 命令构建）
3. 编写渲染 API 端点

### Phase 5: 前端完善
1. 图片画廊预览
2. 音乐预览/选择
3. 渲染选项弹窗
4. 下载按钮（ZIP + MP4）

### Phase 6: 错误处理
1. Cookie 过期提示
2. 限流保护

---

### Windows 桌面客户端
用户要求做成 Windows 桌面客户端，使用 pywebview 包装 FastAPI。

新增文件：
- `desktop_app.py` - 桌面客户端主程序
- `backend/app/js_api.py` - JS ↔ Python 桥接
- `build.spec` - PyInstaller 打包配置
- `build_exe.bat` - 一键构建脚本

桌面客户端特性：
- 原生 Windows 窗口（Edge WebView2）
- 系统托盘
- 原生文件对话框
- 系统通知
- 自动端口

---

### 抓取问题排查
用户测试链接 `https://v.douyin.com/_YwGJCQjPfc/` 时报错：
- f2 库 API 请求返回空（状态码 200 但内容为空）
- 原因是抖音需要登录 Cookie 才能访问 API

解决方案：
- 安装 Playwright + Chromium
- 通过 Playwright 渲染页面提取数据
- 自动获取 ttwid

---

### Chromium 安装问题
用户反复遇到 Chromium 未安装错误，原因是：
1. `python -m playwright install chromium` 只装了普通 Chromium
2. Playwright 的 async API 需要 `chromium_headless_shell`
3. `python -m playwright install`（不带参数）才能装全

修复：
- 更新启动脚本自动检查并安装
- 改用 `playwright install` 全量安装
- 错误提示加上引导

---

### 实况照片支持
用户链接有 13 张实况照片，工具最初只能识别为普通图文。

方案：
- 检测页面轮播图指示器（如 "1/13"）
- 点击切换每张幻灯片
- 拦截网络请求捕获视频 URL
- 返回图片+视频对

---

### 扫码登录 + 快速模式
用户要求添加扫码登录和快速/标准模式切换。

SSO 扫码登录流程：
1. Playwright 打开 `sso.douyin.com/get_qrcode/`
2. 拦截 `passport/web/get_qrcode` API 响应
3. 提取 `data.qrcode` 字段（base64 PNG）
4. 前端展示二维码
5. 轮询 Playwright 页面 Cookie
6. 检测到 `sessionid`/`sid_tt` 即登录成功

快速模式：有登录 Cookie 时直调 API，2-3 秒完成
标准模式：Playwright 浏览器抓取，15-25 秒

---

### UI 美化
- 紫色渐变主题
- 毛玻璃卡片
- 启动 splash 页
- 深色/浅色切换（后续版本改为 Noir + Indigo）

---

### 更名为 Ptu
工具正式定名为 Ptu。

---

## 文件清单

```
抖音/
├── run.py                 # 入口
├── desktop_app.py         # pywebview 桌面客户端
├── 一键启动.bat            # 双击启动
├── install_ffmpeg.ps1     # FFmpeg 安装脚本
├── 安装必要组件.bat         # Chromium + FFmpeg 一键安装
├── build_exe.bat          # PyInstaller 打包脚本
├── CLAUDE.md              # 项目文档
├── build.spec             # PyInstaller 配置
├── backend/
│   ├── app/
│   │   ├── main.py        # FastAPI 主应用
│   │   ├── config.py      # 配置
│   │   ├── js_api.py      # JS-Python 桥接
│   │   ├── api/
│   │   │   ├── router_scraper.py
│   │   │   ├── router_download.py
│   │   │   ├── router_media.py
│   │   │   ├── router_ws.py
│   │   │   └── router_login.py
│   │   ├── services/
│   │   │   ├── scraper.py
│   │   │   ├── downloader.py
│   │   │   ├── media_processor.py
│   │   │   ├── live_photo.py
│   │   │   ├── qr_login.py
│   │   │   ├── ttwid.py
│   │   │   └── progress.py
│   │   ├── models/
│   │   │   ├── schemas.py
│   │   │   └── task_store.py
│   │   ├── templates/
│   │   │   ├── base.html
│   │   │   └── index.html
│   │   └── static/
│   │       ├── css/app.css
│   │       └── js/app.js
│   ├── config.yaml
│   ├── cookies.yaml
│   └── requirements.txt
└── data/
    ├── downloads/{id}/
    └── output/{id}/
```

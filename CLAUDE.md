# Ptu - 抖音图文/视频下载工具 v1.4.2

抖音图文/实况照片/视频抓取+幻灯片视频合成工具。支持用户主页全量抓取。

## AI 进入项目先读

任何 AI/Agent 接手本项目，先读本文件，再读 `github-ptu/PTU_TECHNICAL_DOCUMENTATION底层数据记录.md`。后者记录了真实踩坑和失败路径，不要重复走已经证明无效的路线。

开发规则：

- 修 bug 必须先建立可复现测试或最小探针，再改代码。
- 单作品抓取目前主力是 f2/API；主页抓取主力是 httpx 直调主页 API。不要把主页抓取重新改回 Playwright WAF 对抗主路径。
- 主页批量下载优先使用主页接口已返回的 `video_url/image_urls/music_url`，不要对每条作品重新走 `scrape(share_url)` 慢路径；只有字段缺失时才兜底抓详情。
- 桌面壳必须使用 Windows 原生标题栏；不要把主窗口改回 `frameless=True`。无边框窗口会破坏拖拽缩放、最大化和右上角关闭。
- 开发版通过不等于封包版可发布。封包前必须执行 `python scripts/release_check.py`，封包后必须按 `docs/release_checklist.md` 冒烟。
- GitHub 上传必须等用户确认测试完成。默认流程是：本机测试通过 -> 干净运行时冒烟 -> Windows Sandbox 测试 -> 用户确认 -> 再 commit/tag/push/Release。
- 涉及路径、日志、Cookie、浏览器、FFmpeg、动态 import 的改动，都必须同时考虑开发版和 PyInstaller `sys.frozen` 环境。
- 用户可见错误必须中文，并且要能帮助判断是链接类型错误、未登录、Cookie 失效、接口空响应还是封包依赖缺失。

## v1.4.2 更新记录

- Chromium/headless shell 从“首次启动时下载”改为随安装包内置：`build.spec` 会把本机 `%LOCALAPPDATA%\ms-playwright\chromium_headless_shell-1217` 打进 `_internal/ms-playwright/`，封包版优先从内置目录查找浏览器，降低国内网络环境下二维码登录失败概率。
- `setup_check.py` 和 `qr_login.py` 必须同时识别 `chrome-headless-shell.exe`、`headless_shell.exe`、`chromium-headless-shell.exe`、`chrome.exe`、`chromium.exe`；Playwright 官方 headless shell 当前文件名是 `chrome-headless-shell.exe`，不要只写旧的 `headless_shell.exe`。
- 安装器/卸载器界面改为中文优先：本机 Inno Setup 没有 `ChineseSimplified.isl` 时，通过 `installer.iss` 的 `[Messages]`、`[CustomMessages]` 和 `[LangOptions]` 覆盖常用安装向导文案。
- 卸载时弹出选择：用户点“是”会同时清理 `%LOCALAPPDATA%\Ptu` 和 `%LOCALAPPDATA%\ms-playwright`，适合彻底重装；点“否”只卸载程序文件，保留日志、下载内容和登录数据。
- 打包配置继续排除 `.env`、`cookies.yaml` 等开发/登录敏感文件，不能把本机 Cookie 或私密配置带进安装包。
- 发版前验证从 16 项提升到 `20 passed`，新增覆盖官方 headless shell 文件名、内置 Playwright 浏览器目录优先级和完整 zip 解压结构。

## v1.4.1 更新记录

- 修复主页分享文本解析：支持类似 `7- 长按复制此条消息... https://v.douyin.com/vAjDKDovzq8/ 0@0.com :0pm` 的完整抖音复制文本；该样例实测应抓到 200+ 作品，不要只用前 5 条冒烟代替全量分页验收。
- 主页抓取 API 请求补齐浏览器上下文参数和 Cookie token，继续沿用 API 直调路线。
- 修复主页批量下载失败/极慢：主页列表阶段保存视频直链、图文图片、音乐和实况数据，批量下载直接使用这些字段；实测该主页前 10 个作品 `10/10` 下载成功。
- 修复详情解析里 `create_time` 未定义导致直连 API 成功后仍被吞掉的问题。
- 修复主页图文作品链接类型判断，图文优先生成 `/note/{aweme_id}`，视频生成 `/video/{aweme_id}`。
- 修复桌面窗口体验：恢复 Windows 原生标题栏和系统窗口边框，支持拖拽调整大小、最大化和右上角直接关闭；发布检查会拦截 `frameless=True/confirm_close=True` 回退。
- 完善运行日志：每次启动自动生成独立运行日志，捕获 `print()` 输出；`runs/` 和 `exports/` 日志超过 7 天自动清理。
- 发布产物改为“单 EXE 安装包”：`build_exe.bat` 先生成稳定的 `dist/Ptu/` onedir，再用 Inno Setup 输出 `installer/Ptu_Setup_v版本号.exe`；不要改成 PyInstaller onefile。
- 主页输入粘贴按钮加固：pywebview 原生剪贴板优先使用 Win32 API，前端读取延长超时并派发 input/change 事件。
- 修复干净机器首次扫码登录失败：浏览器检测必须覆盖 Playwright headless shell 文件名；不能只在已有 `chrome.exe` 的开发机上验收。
- 新增 `tests/test_profile_scraper.py` 和 `tests/test_profile_batch_download.py` 锁定主页解析、API 请求构造和批量下载直连字段行为。
- 新增 `tests/test_setup_check.py` 锁定 Playwright Chromium/headless shell 检测，避免封包后首次启动下载完成但仍提示“浏览器环境未就绪”。
- 新增 `scripts/release_check.py` 和 `docs/release_checklist.md`，将封包前检查和封包后冒烟流程制度化。

## 启动方式

```bash
双击 桌面 Ptu 桌面版.lnk     # 桌面客户端模式（默认，推荐）
双击 启动桌面版.bat            # 开发模式（需要 Python 环境）
python run.py                  # 同上
python run.py --web            # Web模式（浏览器访问 http://127.0.0.1:8000，仅开发）
```

**注意**：v1.2.0 起仅桌面模式可用，Web 模式仅用于开发调试。抓取必须登录。

## 项目结构

```
抖音/
├── run.py                 # 入口（打包后默认走桌面模式）
├── desktop_app.py         # pywebview桌面客户端
├── setup_check.py         # 环境检测：自动下载 Chromium/FFmpeg
├── build.spec             # PyInstaller 打包配置 (--onedir)
├── build_exe.bat          # 打包脚本
├── installer.iss          # Inno Setup 安装脚本
├── icon.ico               # 应用图标
├── CLAUDE.md              # 项目说明（本文件）
├── PTU_TECHNICAL_DOCUMENTATION底层数据记录.md  # 技术文档+完整工作痕迹
├── .gitignore             # Git 忽略规则
├── 启动桌面版.bat          # 开发模式快速启动
├── 开发模式（热重载）.bat   # 热重载模式
├── 一键启动.bat            # 快速启动
├── 安装必要组件.bat        # 依赖安装
├── releases/
│   ├── 1.0.0/
│   │   └── Ptu.exe
│   ├── 1.1.0/
│   │   └── Ptu.exe
│   ├── 1.2.0/
│   │   └── Ptu.exe
│   ├── 1.3.0/
│   │   └── Ptu_v1.3.0.zip
│   └── 1.4.0/
│       ├── Ptu/                  # --onedir 裸目录
│       │   ├── Ptu.exe
│       │   └── _internal/
│       └── Ptu_v1.4.0_YYYYMMDD.zip  # 分发用 ZIP
├── installer/
│   └── Ptu_Setup_v1.4.2.exe      # 对外分发的单 EXE 安装包
├── backend/
│   ├── app/
│   │   ├── main.py        # FastAPI主应用
│   │   ├── config.py      # 配置
│   │   ├── version.py     # ⭐版本集中管理（唯一数据源）
│   │   ├── log_config.py  # ⭐运行日志（轮转+导出）
│   │   ├── js_api.py      # JS原生桥接（窗口管理/对话框等）
│   │   ├── api/
│   │   │   ├── router_scraper.py   # POST /api/scrape
│   │   │   ├── router_download.py  # POST /api/tasks/{id}/download
│   │   │   ├── router_media.py     # POST /api/tasks/{id}/render
│   │   │   ├── router_ws.py        # WS /ws/{task_id}
│   │   │   ├── router_login.py     # POST /api/login/qrcode 等
│   │   │   └── router_profile.py   # ⭐POST /api/profile/scrape + batch-download
│   │   ├── services/
│   │   │   ├── scraper.py          # ⭐核心抓取（API + f2 + Playwright 兜底 + 主页API直调）
│   │   │   ├── downloader.py       # 异步下载管理器（并行下载）
│   │   │   ├── media_processor.py  # FFmpeg视频合成（含实况照片合成）
│   │   │   ├── live_photo.py       # HEIC转换
│   │   │   ├── qr_login.py         # 抖音扫码登录
│   │   │   ├── ttwid.py            # ttwid Cookie获取
│   │   │   └── progress.py         # WebSocket进度推送
│   │   ├── models/
│   │   │   ├── schemas.py          # Pydantic数据模型（含ProfilePost/ProfileResult）
│   │   │   └── task_store.py       # 任务持久化(JSON)
│   │   ├── templates/
│   │   │   ├── base.html           # 基础布局+深色主题+日志面板
│   │   │   └── index.html          # 前端UI（含侧边栏+主页抓取面板）
│   │   └── static/
│   │       ├── css/app.css         # 莫兰迪绿白浅色 + [data-theme=dark] 深色双主题
│   │       └── js/app.js           # 模块化JS（含热重载轮询 + 主题切换 + 粘贴增强）
│   └── config.yaml
│   └── cookies.yaml        # 抖音Cookie（扫码登录后自动保存）
├── 日志/                   # 运行日志（封包版在 %LOCALAPPDATA%\Ptu\日志）
│   ├── ptu_boot.log        # 启动日志
│   ├── ptu.log             # 实时日志（轮转，max 5MB×3）
│   ├── runs/               # 每次运行日志 + 每日汇总（7天自动删除）
│   │   ├── ptu_2026-06-02_011634.log
│   │   └── ptu_2026-06-02.log
│   └── exports/            # 手动导出的日志快照（7天自动删除）
│       └── ptu_run_20260602_011700.log
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
| 实况照片 (live_photo) | API 返回 image_post_info.images[].video | 图片+原视频+合成视频三文件 (live_XXXX_img.jpg / _vid.mp4 / .mp4) |
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
| GET | `/api/tasks/{id}/files/{path}` | 查看下载目录内具体文件 |
| GET | `/api/proxy/media` | CDN 代理（绕过防盗链，前端预览用） |
| WS | `/ws/{id}` | 实时进度推送 |
| POST | `/api/login/qrcode` | 获取登录二维码 |
| POST | `/api/login/confirm` | 确认扫码登录 |
| POST | `/api/login/logout` | 退出登录（同时清浏览器缓存） |
| GET | `/api/login/status` | 登录状态 |
| POST | `/api/browser/clear-cache` | ⭐清除浏览器缓存和Cookie |
| POST | `/api/profile/scrape` | ⭐抓取用户主页所有作品 |
| POST | `/api/profile/batch-download` | ⭐批量抓取并下载主页选中作品 |
| GET | `/api/logs` | ⭐查看最后 N 行运行日志 |
| GET | `/api/logs/export` | ⭐下载日志文件 |
| POST | `/api/logs/save` | ⭐保存当前运行日志快照到 `日志/exports/` 并返回路径 |
| POST | `/api/logs/open-folder` | ⭐在资源管理器中打开日志文件夹 |
| GET | `/api/build-id` | 🔧热重载版本号（前端轮询检测变化自动刷新） |

## 抓取流程（四条路径，按优先级排列）

```
scrape(share_url)
  ├─ (1) _scrape_via_api()      直调抖音 API（最快，需 a_bogus 签名，常失败）
  ├─ (2) _scrape_via_f2()       用 f2 库（内置 a_bogus 签名）直调 API ⭐主力路径
  ├─ (3) _scrape_via_pw_api()   Playwright 页面渲染后 DOM 提取（WAF 对抗，兜底）
  └─ (4) _scrape_via_playwright()  Playwright 完整提取（XHR拦截+轮播+Viewer，最终兜底）

主页抓取（独立路径，v1.4.0 重写）
  scrape_profile(url)
    → 解析短链接提取 sec_uid
    → httpx 直调 /aweme/v1/web/user/profile/other/ 获取用户信息
    → httpx 直调 /aweme/v1/web/aweme/post/ 分页获取作品列表（无需 Playwright）
```

## 关键功能

- **扫码登录**: 右上角点登录→抖音扫码→保存Cookie→后续 API 抓取
- **仅登录可用**: 必须登录才能使用
- **左侧导航侧边栏**: 切换"单个链接抓取"/"主页链接抓取"两种模式
- **用户主页全量抓取**: 输入用户主页链接（或分享短链接），httpx 直调 API 获取作品列表，网格展示+批量下载
- **自动提取链接**: 粘贴抖音分享文本，自动提取URL
- **图片预览**: 点击放大，左右键切换（通过后端 CDN 代理绕过防盗链）
- **音乐试听**: 有背景音乐的作品可点击播放
- **正文文字提取**: 下载后自动生成 post.txt，包含标题+正文+#话题
- **实况照片/综合内容**: 正确识别图片+视频混合内容，下载时自动合成视频（原视频+图片定格→live_XXXX.mp4），支持图片+视频合成渲染
- **下载文件夹命名**: 优先使用作品发布时间（Unix → YYYY-MM-DD_标题），降级用抓取时间
- **开发模式热重载**: 改 CSS/JS/HTML/Python 文件后窗口自动刷新，无需重启
- **深色/浅色模式**: 右上角一键切换，偏好保存到 localStorage
- **视频合成**: FFmpeg合成幻灯片视频（淡入淡出/Ken Burns转场），实况照片可插入视频片段
- **历史管理**: 支持单个删除和全选批量删除任务记录，点击历史条目可重新查看结果
- **浏览器缓存清理**: 一键清除 Playwright 缓存和登录状态，退出登录时自动联动清理
- **运行日志面板**: 左下角可展开的实时日志面板，支持一键导出和打开 `日志` 文件夹
- **干净机测试**: `docs/clean_machine_testing.md` 记录标准流程；`scripts/clean_runtime_for_smoke.ps1` 用于本机非破坏式清运行时冒烟；`scripts/Ptu_Sandbox_Test.wsb` 用于 Windows Sandbox 干净机安装测试。
- **主题**: 莫兰迪绿白 (Morandi Sage Light) 主色调 + macOS Ventura 玻璃风格 + 一键切换深色/浅色模式

## 技术要点

- **主力抓取路径**：f2 库（v0.0.1.7）直调抖音 API，内置 `a_bogus` 签名，绕过 WAF
- **兜底抓取**：Playwright (Chromium headless) 渲染页面后 DOM 提取，受 WAF 限制（~40%通过率）
- **WAF 对抗**：抖音 WAF（`mon.zijieapi.com`）JS 挑战检测 headless，`add_init_script` 可部分绕过，两步导航可预置 WAF cookie
- **f2 库注意**：`DouyinHandler.__init__` 会创建 BarkHandler（`api.day.app` 通知），国内网络环境会导致 60s+ 超时，需运行时设置 `BarkClientConfManager.client_conf["enable_bark"] = False`
- **CDN 防盗链**：图片/音乐/视频 CDN 检查 `Referer: https://www.douyin.com/`，前端预览通过 `/api/proxy/media` 代理绕过
- **桌面端**：pywebview 原生 Windows 标题栏和系统边框；必须支持拖边缩放、最大化和右上角关闭直接退出
- **窗口位置记忆**：关闭时保存 `x, y, w, h` 到 `.ptu_window_state.json`

- **日志系统**: `backend/app/log_config.py`，开发版写入项目根目录 `日志/`；封包安装版写入 `%LOCALAPPDATA%\Ptu\日志\`，避免 `C:\Program Files\Ptu` 无写入权限。日志包含 `ptu_boot.log`（启动日志）+ `ptu.log`（轮转 5MB×3）+ `runs/ptu_YYYY-MM-DD_HHMMSS.log`（每次运行自动保存）+ `runs/ptu_YYYY-MM-DD.log`（每日汇总）+ `exports/`（手动快照）；runs/exports 超过 7 天自动清理。
- **外部测试日志位置**: 安装目录 `C:\Program Files\Ptu` 只包含程序文件，通常没有运行日志。让测试者回传问题时，优先让对方点击日志面板里的“打开文件夹”，或直接打包 `%LOCALAPPDATA%\Ptu\日志\` 和 `%LOCALAPPDATA%\ms-playwright\` 的目录清单。
- **Chromium 内置与兜底下载**: v1.4.2 起封包版优先使用 `_internal/ms-playwright/` 内置的 Playwright Chromium headless shell，避免用户首次启动时依赖外网下载。`setup_check.py` 必须同时识别 `chrome-headless-shell.exe`、`headless_shell.exe`、`chromium-headless-shell.exe`、`chrome.exe`、`chromium.exe`；开发机已有 `chrome.exe` 时不会暴露干净机器问题。
- **FFmpeg**：Windows 上使用 `subprocess.run`（`asyncio.create_subprocess_exec` 会失败）
- **ttwid**：通过 ByteDance 公开接口 `ttwid.bytedance.com/union/register/` 自动获取
- **打包**：PyInstaller 仍使用 `--onedir` 模式（稳定），输出 `dist/Ptu/Ptu.exe + _internal/`；对外分发使用 Inno Setup 生成单个 `installer/Ptu_Setup_vX.Y.Z.exe` 安装包。
- **不要改成 PyInstaller onefile**：本项目包含 pywebview/FastAPI/Playwright/f2/模板/证书等资源，onefile 启动慢、解压路径复杂、误报风险更高；“只发一个 exe”通过 Inno Setup 安装包实现。
- **打包常见陷阱**：
  - `sys.frozen` 下 `__file__` 指向 `_internal/`，只读资源可用 `sys.executable.parent`，运行时可写数据必须用 `%LOCALAPPDATA%\Ptu`
  - `certifi` 的 `cacert.pem` 需作为 data 文件打包 + 启动时设 `SSL_CERT_FILE` 环境变量
  - 所有 `open("filename")` / `Path("filename")` 需适配 frozen（exe 同级目录 vs CWD）
  - `console=False` 下 `sys.stdout` 为 None，`print()` 静默失败，`setup_check.py` 输出需重定向到日志
  - `cookies.yaml` 路径必须用 `settings.cookies_path` 而非硬编码 `Path("cookies.yaml")`
- **版本管理**: `backend/app/version.py` 集中管理，`run.py` 通过 `from backend.app.version import VERSION` 导入
- **所有用户可见错误信息均为中文**（HTTP 401/404/500 等）
- **媒体类型**: IMAGE_SET / VIDEO / LIVE_PHOTO / COMPREHENSIVE

## 开发版 vs 封包版差异

**PyInstaller `--onedir` + `console=False` 导致的行为变化。** 每次封包后必须逐项检查：

| 差异点 | 开发版 | 封包版 | 已修复 |
|--------|--------|--------|--------|
| `sys.stdout` | 控制台可用 | `None`（`print()` 崩溃） | ✅ `setup_check.py` 重定向到 `%LOCALAPPDATA%\Ptu\日志\ptu_boot.log` |
| `sys.frozen` | `False` | `True`（`__file__`→`_internal/`） | ✅ 只读资源用 `sys.executable.parent`，可写数据用 `%LOCALAPPDATA%\Ptu` |
| uvicorn `reload` | `True`（热重载） | **必须 `False`**（否则反复重启杀 Playwright） | ✅ `is_dev` 判断 |
| SSL 证书 | certifi 自动找到 | 找不到 `cacert.pem` | ✅ 启动设 `SSL_CERT_FILE` |
| CWD | 项目根 | 用户双击位置 | ✅ `Path("file")` 全部适配 |
| 安装目录写权限 | 项目目录可写 | `C:\Program Files\Ptu` 普通用户不可写 | ✅ `日志/cookies/downloads/output` 写入 `%LOCALAPPDATA%\Ptu` |
| Playwright | 系统 Chrome/Edge | 需 `setup_check` 下载 Chromium | ✅ 首次启动后台下载 |
| FFmpeg | config.yaml 路径 | 同上 | ✅ 下载到 exe 同级目录 |
| f2 库 Bark | 可能超时 60s+ | 同开发版 | ✅ `enable_bark=False` |
| 窗口缩放/关闭 | 原生窗口可缩放和关闭 | `frameless=True` 会锁死拖边缩放，关闭按钮可能只隐藏到托盘 | ✅ `frameless=False` + `confirm_close=False` |
| `cookies.yaml` | settings 解析 | 原硬编码 `Path("cookies.yaml")` | ✅ 改用 `self._cookies_path` |

**封包后抓取速度诊断**：`scraper.py` 加计时日志，控制台输出 `[Scrape] 路径X 成功，耗时 X.Xs` → 查看 `%LOCALAPPDATA%\Ptu\日志\ptu.log` 和 `%LOCALAPPDATA%\Ptu\日志\ptu_boot.log` 确认走了哪条路径。路径2（f2库）应 <5s；路径3/4（Playwright）10-30s 正常。如果始终走 Playwright 说明 f2 在封包环境有问题。

## v1.4.2 实际打包记录（2026-06-02）

本次 v1.4.2 已按“PyInstaller onedir + Inno Setup 单 EXE 安装包”路线完成出包，并把 Playwright Chromium headless shell 内置进安装包。最终对外分发文件为：

```text
installer\Ptu_Setup_v1.4.2.exe
大小：325,983,491 字节（约 311 MB）
生成时间：2026-06-02 20:09
```

内部可执行文件为：

```text
dist\Ptu\Ptu.exe
大小：198,483,518 字节（约 189 MB）
生成时间：2026-06-02 19:56
```

本次已确认：

- `dist\Ptu\_internal\ms-playwright\chromium_headless_shell-1217\chrome-headless-shell-win64\chrome-headless-shell.exe` 存在。
- `dist\Ptu\_internal\backend\.env` 和 `dist\Ptu\_internal\backend\cookies.yaml` 不存在。
- Inno Setup 安装包编译成功，且无未识别消息键警告。
- 已验证命令：`python -m pytest tests -q` -> `20 passed`；`python scripts\release_check.py` -> 通过；`python -m compileall -q run.py desktop_app.py setup_check.py backend\app scripts` -> 通过；`node --check backend\app\static\js\app.js` -> 通过。
- 用户确认安装/卸载、扫码登录、主页抓取和下载均正常后，已发布 GitHub Release `v1.4.2`。Release: https://github.com/Fairc11/Ptu-Fairc11/releases/tag/v1.4.2；安装包: https://github.com/Fairc11/Ptu-Fairc11/releases/download/v1.4.2/Ptu_Setup_v1.4.2.exe

## v1.4.1 实际打包记录（2026-06-02）

本次 v1.4.1 已按“PyInstaller onedir + Inno Setup 单 EXE 安装包”路线完成出包。最终对外分发文件为：

```text
installer\Ptu_Setup_v1.4.1.exe
大小：120.97 MB
生成时间：2026-06-02 17:06
```

内部可执行文件为：

```text
dist\Ptu\Ptu.exe
大小：78.30 MB
生成时间：2026-06-02 01:45
```

本次打包踩坑和结论：

- 本机缺少 Inno Setup 时，使用 `winget install --id JRSoftware.InnoSetup -e --accept-source-agreements --accept-package-agreements` 安装；实测安装版本为 Inno Setup 6.7.3。
- Inno 编译器路径在本机是 `%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe`，`build_exe.bat` 已加入该路径探测。
- `build_exe.bat` 必须保持 ASCII 友好输出；中文 `echo` 在 Windows `cmd` 下可能因为编码导致脚本被错误解析，出现类似 `'n' is not recognized` 的问题。
- `installer.iss` 当前只启用默认英文安装器界面，因为本机 Inno Setup 未自带 `ChineseSimplified.isl`；这只影响安装向导语言，不影响 Ptu 应用内中文界面。
- `[Tasks]` 不要使用 Inno 不支持的 `checkedbydefault` flag；默认任务无需额外 flag。
- `[UninstallRun]` 的 `taskkill` 需要带 `RunOnceId: "KillPtu"`，避免 Inno 编译警告。
- 自动化打包可使用 `$env:PTU_NO_PAUSE='1'; cmd /c build_exe.bat`，避免批处理结束时停在 `pause`。
- v1.4.1 首次安装到 `C:\Program Files\Ptu` 后曾出现 `PermissionError: [Errno 13] Permission denied: 'C:\\Program Files\\Ptu\\ptu_boot.log'`；根因是封包后把启动日志/运行数据写进安装目录。已改为封包版统一写入 `%LOCALAPPDATA%\Ptu`，日志集中放在 `%LOCALAPPDATA%\Ptu\日志`。
- WebView2 检测必须包含 32 位注册表分支和 `Program Files (x86)\Microsoft\EdgeWebView` 目录；否则已安装 WebView2 的机器也可能被误提示下载。

本次已验证命令：

```powershell
python scripts\release_check.py
python -m pytest tests -q
python -m compileall -q run.py desktop_app.py setup_check.py backend\app scripts
$env:PTU_NO_PAUSE='1'; cmd /c build_exe.bat
& "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" .\installer.iss
```

结果：发布检查通过、测试 `16 passed`、编译检查通过、安装包编译成功。2026-06-02 17:06 替换构建已修复干净机器首次扫码登录和日志文件夹明显化问题；GitHub Release `v1.4.1` 已在用户确认后替换安装包资产，线上文件大小为 `126848606` 字节。

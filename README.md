# Ptu

Ptu 是一个 Windows 桌面工具，用于下载抖音图文、视频和实况照片素材，并把图文/实况素材合成为干净的 9:16 竖屏 MP4。

当前版本：`v1.5.0`

下载地址：[GitHub Releases](https://github.com/Fairc11/Ptu-Fairc11/releases)

## 适合做什么

- 下载单条抖音图文、视频、实况照片素材
- 保存作品文案到 `post.txt`
- 主页作品按每批最多 30 条手动分页加载
- 将图文/实况素材和背景音乐合成为 `douyin_slideshow.mp4`
- 导出脱敏诊断包，方便排查朋友电脑上的问题

## 安装使用

1. 打开 [Releases](https://github.com/Fairc11/Ptu-Fairc11/releases/latest)
2. 下载 `Ptu_Setup_v1.5.0.exe`
3. 双击安装并启动 Ptu
4. 在右上角扫码登录抖音
5. 粘贴抖音分享链接，点击抓取
6. 下载素材，按需点击生成视频

安装包已内置 FFmpeg、FFprobe 和 Playwright Chromium。普通用户不需要安装 Python、FFmpeg、Playwright 或 Chromium。

## v1.5.0 亮点

- 新图标已同步到应用、安装器和打包产物
- 右侧抖音预览内嵌在主窗口中，不再打开第二个窗口
- 扫码登录、右侧预览、抓取和下载共用 Ptu 自己的登录状态
- 新增退出登录和清除登录痕迹，只清理 Ptu 本地数据，不影响 Edge/Chrome
- 右侧预览移除“复制当前链接”按钮，改为手动复制教程
- 点击抖音作者主页或新页面时仍留在右侧预览，不跳系统浏览器
- 生成视频直接保存到本次素材文件夹
- 修复实况照片误判和 WebP/JPG 重复暴露问题
- 优化实况照片/翻页视频清晰度，减少绿边和糊的问题
- 下载、生成、探测等子进程隐藏命令行闪窗
- 日志导出改为脱敏 zip，不包含真实 cookie、密钥和环境变量

## 安全边界

Ptu 是用户本机主动操作的桌面辅助工具，不是全量采集器。

- 不做点赞、评论、关注、私信、发布、转发、收藏等账号互动自动化
- 不做关注、粉丝、喜欢、收藏、话题、搜索、音乐原声等大范围采集入口
- 不后台自动刷页面，不自动翻页，不自动扫描主页或搜索结果
- 不绕过验证码、人机校验、风控页、登录限制或接口限制
- 不读取用户 Edge/Chrome 个人资料
- 不保存账号密码，不上传 cookie
- 不把真实 cookie 写进日志、诊断包、安装包、Git 或 Release
- 批量下载必须有限量、限并发、可取消

更完整的风险规则见 [风险管控策略](docs/superpowers/plans/2026-06-03-ptu-risk-control-policy.md)。

## 输出位置

默认素材目录位于 Ptu 的运行数据目录中。单条作品下载完成后，素材文件夹通常包含：

- 图片、视频、实况片段或背景音乐
- `post.txt`
- 生成后的视频 `douyin_slideshow.mp4`

在任务结果区点击“打开文件夹”只会打开素材文件夹；播放视频需要点击“打开视频”或手动打开文件。

## 开发运行

```powershell
pip install -r backend/requirements.txt
python run.py
```

Web 调试模式：

```powershell
python run.py --web
```

打包：

```powershell
$env:PTU_NO_PAUSE='1'
cmd /c build_exe.bat
```

## 验证

v1.5.0 发布前已通过：

```powershell
python -m pytest tests -q
python scripts\release_check.py
python -m compileall -q run.py desktop_app.py setup_check.py backend\app scripts tests
node --check backend\app\static\js\app.js
powershell -ExecutionPolicy Bypass -File scripts\v1_5_installed_smoke_check.ps1 -InstallDir dist\Ptu -StartApp -WaitSeconds 90
```

结果记录见 [v1.5 完成审计](docs/v1.5_completion_audit.md)。

## 项目结构

```text
backend/app/                 FastAPI 后端、桌面桥接、抓取下载和视频合成逻辑
backend/app/static/          前端 CSS、JS、图标资源
backend/app/templates/       pywebview 页面模板
docs/                        发布检查、干净机测试和阶段计划
scripts/                     发布检查、安装版冒烟脚本
tests/                       自动化测试
vendor/ffmpeg/               打包用 FFmpeg/FFprobe
run.py                       应用入口
build.spec                   PyInstaller 配置
installer.iss                Inno Setup 安装器配置
```

## 更新日志

### v1.5.0 — 2026-06-06

**新增**

- 安装包目标改为小白零前置条件：内置 Playwright Chromium headless shell、`ffmpeg.exe` 和 `ffprobe.exe`，普通用户无需手动安装 Python、Chromium 或 FFmpeg。
- 替换新版 PTU 图标，安装器、EXE、应用内标题栏和启动页保持一致。
- 生成视频改为固定抖音式 preset：竖屏、原声、无绿边横向翻页、素材循环到音乐结束，不再让小白用户选择转场和分辨率。
- 扫码登录状态更清楚：显示倒计时、已扫码待手机确认、二维码过期和网络异常状态。
- 二维码获取使用 Ptu 自己的内置浏览器安全容器；不读取用户 Edge/Chrome 个人资料，避免正常登录路径触发系统浏览器。
- 内置浏览改为主界面右侧常驻预览 Dock：扫码登录在右侧内联完成，登录成功后抖音直接显示在主窗口右侧内置 WebView2 区域。
- 主页抓取改为每批最多 30 个作品，用户可主动点击“下一批 30 个”继续分页加载。
- 新增退出登录/清除登录痕迹：只清除 Ptu 自己保存的抖音 cookie 和内置浏览器会话，不影响用户 Edge、Chrome 或系统浏览器。
- 新增干净版抖音节奏成片：图文/实况素材按顺序播放，背景音乐未结束时自动循环素材，输出 `douyin_slideshow.mp4`。
- 生成视频直接放回本次素材下载文件夹；结果区显示“已保存到素材文件夹”，提供打开视频、打开文件夹和复制路径。
- 日志导出升级为脱敏诊断包，直接打包下载目录、输出目录、任务记录和日志，便于排障且不包含真实 cookie。
- 首次启动新增免责声明，用户勾选同意后才进入主界面。

**修复**

- 修复右侧抖音预览打开第二个顶层窗口的问题，现在严格保持单窗口。
- 修复点击抖音作者主页或新页面时跳到系统 Edge、并丢失登录态的问题。
- 修复预览第二个链接时仍显示第一个视频的问题，打开预览会强制刷新内嵌 WebView2。
- 修复生成视频后点击“打开文件夹”会顺便打开视频的问题，现在只打开文件夹。
- 修复粘贴按钮读取剪贴板时调用 PowerShell 导致黑色命令行窗口一闪的问题。
- 修复下载素材、生成视频、FFprobe 探测等子进程在 Windows 打包态反复闪命令行窗口的问题。
- 修复实况照片识别过宽导致普通图片被当作实况照片、WebP/JPG 重复暴露的问题。
- 修复普通视频和实况短视频可能被错误保存为 `.jpg` 的问题。

**优化**

- 右侧预览移除“复制当前链接”按钮，改为手动复制教程：打开作品，点击分享，再复制链接并粘贴到左侧。
- 单张实况照片或单张普通图片成片时不套翻页动画，会持续播放或显示到 BGM 结束；两个及以上素材才使用横向翻页。
- 实况照片和翻页视频渲染改用更高质量参数：lanczos 缩放、CRF 18、preset medium，减少糊和绿边。
- 进度条移动到结果卡片后面，更靠近下载、生成和打开文件夹操作区。
- 右侧抖音预览区补齐暗色模式。
- 下载素材时所有媒体类型都会生成 `post.txt`；视频、图文、实况和主页批量下载都保留作品文案。

**发布**

- 对外分发文件：`Ptu_Setup_v1.5.0.exe`
- 安装后无需 Python 环境，也不需要用户手动安装 Chromium、Playwright、FFmpeg 或 FFprobe；如果目标电脑缺少 WebView2，安装器仍会提示安装。

**验证**

- `python -m pytest tests -q`：`68 passed`
- `python scripts\release_check.py`：通过
- `python -m compileall -q run.py desktop_app.py setup_check.py backend\app scripts tests`：通过
- `node --check backend\app\static\js\app.js`：通过
- 安装版 smoke check：通过
- dist 敏感文件审计：通过

### v1.4.2 — 2026-06-02

**修复**
- 修复国内/干净机器首次扫码登录时 Chromium 下载失败导致二维码空白的问题：安装包内置 Playwright Chromium headless shell，启动时优先使用内置浏览器。
- 修复 Playwright 官方 headless shell 文件名差异：同时识别 `chrome-headless-shell.exe`、`headless_shell.exe`、`chromium-headless-shell.exe`、`chrome.exe`、`chromium.exe`。
- 修复安装包可能携带开发机 `.env` 或 `cookies.yaml` 的风险，打包时继续排除敏感配置和登录数据。

**优化**
- 安装器/卸载器常用界面改为中文。
- 卸载时可选择是否同时清理日志、下载记录、登录数据和浏览器运行缓存，方便彻底重装。
- 发版检查新增内置 Chromium、中文安装器、卸载清理选择和干净机验证要求。

**发布**
- 对外分发文件：`Ptu_Setup_v1.4.2.exe`
- 安装后无需 Python 环境，也不需要用户手动安装 Chromium；如果目标电脑缺少 WebView2，安装器仍会提示安装。

**开发者小记**
- 哇哇哇，我真的很开心，哇哇哇，我真的很开心。做成一个工具的开心，真的真的真的真的真的真的真的很开心。

<details>
<summary>历史版本更新日志（v1.4.1 及更早）</summary>

### v1.4.1 — 2026-06-02

**修复**
- 修复抖音主页分享文本提取：支持完整复制文本中的 `v.douyin.com` 短链，主页分页抓取不再只停在前 5 条
- 修复主页批量下载失败：列表阶段保留 `video_url`、`image_urls`、`music_url`、实况照片数据，下载时优先使用已返回字段
- 修复详情解析中 `create_time` 未定义导致直连 API 成功后仍被丢弃的问题
- 修复安装版写入 `C:\Program Files\Ptu\ptu_boot.log` 导致普通用户启动报 `PermissionError` 的问题
- 修复安装器 WebView2 误报：检测 32 位注册表和 `Program Files (x86)\Microsoft\EdgeWebView`
- 修复桌面窗口不能拖拽缩放、不能最大化、右上角关闭无效的问题
- 修复干净机器首次扫码登录时 Chromium headless shell 已下载但未被识别的问题

**优化**
- 桌面端恢复 Windows 原生标题栏和窗口边框
- UI 保持莫兰迪绿色主题，增加更现代的动效和交互反馈
- 运行日志集中到 `%LOCALAPPDATA%\Ptu\日志`，日志面板新增“打开文件夹”，`runs/` 和 `exports/` 超过 7 天自动清理
- 新增干净机测试流程：本机清运行时冒烟 + Windows Sandbox 测试
- 封包流程改为 PyInstaller onedir + Inno Setup 单 EXE 安装包
- 安装版运行时数据统一写入 `%LOCALAPPDATA%\Ptu`

**发布**
- 对外分发文件：`Ptu_Setup_v1.4.1.exe`
- 安装后无需 Python 环境；如果目标电脑缺少 WebView2，安装器会提示安装

### v1.4.0 — 2026-05-27

**新增**
- 主页作品批量下载：勾选已加载主页作品后一键批量下载，支持全选/反选，单次不超过 30 个
- 主页抓取改用 httpx API 直调（绕过 WAF，成功率从 ~0% 提升至 100%）
- 支持分享短链接自动识别：粘贴 `v.douyin.com` 链接自动解析为用户主页
- 运行日志自动存文件夹：`日志/runs/ptu_YYYY-MM-DD.log`，7 天自动删除
- 剪贴板粘贴按钮：点击后聚焦输入框，Ctrl+V 粘贴自动提取 URL
- 历史日志文件查看：日志面板新增"历史文件"按钮

**修复**
- 修复打包后扫码登录成功但抓取报"未登录"的问题（cookies 路径相对/绝对不一致）
- 修复 Playwright DOM 提取从未成功返回结果的 Bug（`_extract_dom_to_result` 类型错误）
- 修复 Playwright 路径误抓登录用户"喜欢"视频封面的问题（收紧位置过滤阈值 + URL 排除）
- 修复 `install_playwright()` 重复定义导致打包环境下安装逻辑走错分支
- 修复兜底路径返回空结果而非 None 的问题
- 修复登录后 scraper 未重载 cookies 导致首次抓取失败

**优化**
- UI 整体更紧凑简约：侧边栏/卡片/输入框/网格/状态徽章/Toast 全面收紧
- Topbar 提供可见的“退出登录 / 清除登录痕迹”入口，便于用户主动清除 Ptu 本地登录状态
- 侧边栏 active tab 增加左边框指示条
- 主页作品网格增加 checkbox 支持批量操作
- 登录检查：主页抓取前自动检查登录状态，未登录弹出登录框
- Splash 未登录提示改为自动弹出登录框（替代过时的"仅限标准模式"）

### v1.3.0 Beta — 2026-05-14

**新增**
- 用户主页分页抓取：输入抖音主页链接，每批最多加载 30 个作品，点击“下一批 30 个”继续翻页
- 内置抖音浏览面板：用户在主窗口右侧 WebView2 区域正常浏览，按教程手动复制分享链接后粘贴到左侧输入框，不自动扫页、不自动复制、不自动填入
- 左侧导航栏：支持"单个链接抓取"和"主页链接抓取"两种模式切换
- 左下角运行日志面板：实时显示后端日志，支持一键导出
- 实况照片视频合成：图片 + 短视频 + 背景音乐合成完整视频
- 浏览器缓存清理按钮：一键清除登录状态

**修复**
- 修复登录按钮点击无响应的问题
- 修复主页抓取时 JavaScript 报错
- 修复表情包和推荐封面被误当作内容图抓取的问题
- 退出登录时同步清除浏览器缓存
- 实况照片背景音乐提取恢复正常
- 控制台日志不再被大量调试信息刷屏

**优化**
- 版本号统一管理，便于后续维护
- 启动日志增加时间戳，方便性能分析
- 打包方式优化，启动更稳定
- 图片过滤算法增强，内容识别更准确

### v1.2.0 Beta — 2026-05-11

**修复**
- 修复部分图文抓取不到图片的问题
- 修复抓取速度极慢的问题（从 78 秒降至 4.6 秒）
- 修复图集背景音乐未能提取的问题
- 修复图片/音乐在线预览播放失败（防盗链导致）

**新增**
- 下载完成后自动生成文字说明文件（post.txt），包含标题、正文和话题
- 新增图片/音乐/视频代理播放，绕过防盗链限制

**优化**
- 抓取速度大幅提升，API 请求从串行改为并行
- 作者信息提取更准确，懒加载图片更好捕获
- 轮播翻页速度加快
- 打包后崩溃问题修复，整体稳定性增强

### v1.1.0 Beta — 2026-05-10

**新增**
- 实况照片支持（LIVE_PHOTO）：图片与关联视频分别保存
- 综合内容类型识别（COMPREHENSIVE）：混合内容自动处理
- pywebview 桌面原生客户端：无边框窗口 + 系统托盘，关闭最小化至托盘
- 多路径抓取架构：API 直调 → f2 库 → Playwright API → DOM 提取 → 轮播提取 → Viewer 翻页 → 兜底
- WAF 绕过增强：两步导航 + 智能轮询 + 浏览器指纹隔离 + 自动重置
- 三倍去重机制：URL base + CDN 签名 + 分辨率归一化
- 原生文件对话框 + 系统通知
- 窗口位置/大小状态记忆 + 单实例运行
- 环境检测自动安装 Chromium/FFmpeg
- 自动端口选择，前端 JS 模块化重构
- Task store 新增 API：open-folder / files / batch-delete
- 全局错误信息中文化

**移除**
- 标准模式（无需登录）：抓取功能现要求扫码登录
- Web 模式不再作为默认入口，仅用于开发调试

**变更**
- 桌面模式为默认启动方式
- 打包流程优化（PyInstaller + Inno Setup）
- 图片 CDN 请求增加 Referer 头，修复 403 问题

### v1.0.0 Beta — 2026-05-08

**新增**
- 抖音图文笔记抓取（IMAGE_SET）
- 抖音视频抓取（VIDEO）
- 一键下载素材（图片 + 背景音乐）
- FFmpeg 抖音式竖屏视频合成（固定横向滑动转场，素材循环到音乐结束）
- 标准模式（无需登录）+ 快速模式（扫码登录）
- Web 模式浏览器访问
- 深色主题 UI
- 任务历史管理
- 图片预览 + 音乐试听

</details>

## 许可证

MIT

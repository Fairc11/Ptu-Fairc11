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

## 版本记录

### v1.5.0

- 零前置条件安装包
- 单窗口内嵌抖音预览
- 登录状态统一和清除登录痕迹
- 主页手动分页抓取
- 图文/实况照片竖屏视频生成
- 脱敏日志包导出
- 实况照片识别和视频清晰度优化

### v1.4.2

- 内置 Playwright Chromium，减少首次扫码登录失败
- 修复打包敏感文件排除和中文安装器流程

### v1.4.1

- 修复主页抓取、安装版日志路径和窗口交互问题
- 改为 PyInstaller onedir + Inno Setup 安装包

### v1.4.0 及更早

早期版本完成了单链接抓取、主页批量、扫码登录、实况照片识别、文案保存和桌面端基础能力。完整工程记录见 [底层数据记录](PTU_TECHNICAL_DOCUMENTATION底层数据记录.md)。

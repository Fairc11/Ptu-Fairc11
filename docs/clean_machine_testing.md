# Ptu 干净机测试流程

这份流程用于解决“开发机没问题，朋友电脑有问题”的发布盲区。开发机缓存了 Python、Playwright、Chromium、Cookie、PATH、WebView2、FFmpeg 等依赖，不能代表真实用户环境。

## 测试顺序

1. 开发版测试通过。
2. 本机清运行时冒烟。
3. Windows Sandbox 干净机测试。
4. 用户确认后再上传 GitHub Release。

## 本机清运行时冒烟

这个步骤会把本机运行时目录临时挪走，不会删除：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\clean_runtime_for_smoke.ps1
```

它会备份：

```text
%LOCALAPPDATA%\Ptu
%LOCALAPPDATA%\ms-playwright
```

然后重新安装/启动 Ptu，重点测试：

- 首次启动是否能识别安装包内置的 Chromium/headless shell；即使 `%LOCALAPPDATA%\ms-playwright` 为空，也不应该要求用户手动安装浏览器
- 扫码登录二维码是否能显示
- 日志面板的“打开文件夹”是否打开 `%LOCALAPPDATA%\Ptu\日志`
- `日志/ptu_boot.log`、`日志/ptu.log`、`日志/runs/` 是否生成

测试完要恢复本机原运行时：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\clean_runtime_for_smoke.ps1 -RestoreLatest
```

## Windows Sandbox 测试

适用于 Windows Pro / Enterprise / Education。双击：

```text
scripts\Ptu_Sandbox_Test.wsb
```

Sandbox 会映射：

```text
installer\      -> Sandbox 桌面 PtuInstaller
sandbox-out\    -> Sandbox 桌面 PtuSandboxOut
```

进入 Sandbox 后：

1. 安装器会自动启动；如果没有启动，手动打开桌面 `PtuInstaller\Ptu_Setup_v1.5.0.exe`。
2. 安装到默认目录。
3. 启动 Ptu。
4. 测试扫码登录二维码。
5. 打开左下角“运行日志”，点击“打开文件夹”。
6. 测试主页抓取第一页，点击“下一批 30 个”加载后一页，再勾选 10 个作品批量下载。
7. 抽查下载目录：每个作品目录应有 `post.txt`；视频为 `.mp4`，实况短视频为 `live_XXXX_vid.mp4`。
8. 对一条图文/实况作品点击「生成视频」，确认生成 `douyin_slideshow.mp4`，并且不要求手动安装 FFmpeg。
7. 如果失败，把 Sandbox 内 `%LOCALAPPDATA%\Ptu\日志` 复制到桌面 `PtuSandboxOut`。这个目录会回传到宿主机 `sandbox-out\`。

关闭 Sandbox 后里面的数据会消失，所以失败日志必须先复制到 `PtuSandboxOut`。

## 安装后自动自检

安装候选包后，可以运行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\v1_5_installed_smoke_check.ps1 -StartApp
```

如果不是默认安装目录，显式传入安装目录：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\v1_5_installed_smoke_check.ps1 -InstallDir "C:\Program Files\Ptu" -StartApp
```

这个脚本会检查安装目录中的 `Ptu.exe`、`ffmpeg.exe`、`ffprobe.exe`、内置 Chromium、第三方说明、版本号和敏感文件排除；带 `-StartApp` 时还会启动 Ptu 并确认本地页面返回 200。脚本不能替代扫码登录、真实下载和成片测试，但能快速排除“安装包漏文件”的问题。

## 验收标准

- 应用能启动，窗口能缩放、最大化、右上角关闭。
- 首次启动没有 `Permission denied: C:\Program Files\Ptu\...`。
- 扫码登录二维码能显示。
- 安装器和卸载器常用界面为中文；卸载时能选择是否同时清理 `%LOCALAPPDATA%\Ptu` 和 `%LOCALAPPDATA%\ms-playwright`。
- 日志文件夹可一键打开，路径是 `%LOCALAPPDATA%\Ptu\日志`。
- 主页样例能抓到第一页作品，并能由用户主动点击继续加载下一批 30 个。
- 勾选 10 个主页作品批量下载，成功数等于选择数。
- 安装目录存在 `ffmpeg.exe` 和 `ffprobe.exe`；图文/实况成片日志里能看到 FFmpeg 路径、音乐时长、循环次数和输出路径。
- 生成的视频为竖屏 MP4；背景音乐比素材长时，素材会自动循环到音乐结束。

## 不要做的事

- 不要只在开发机上跑一下就发包。
- 不要只压缩 `C:\Program Files\Ptu` 回传问题；那里通常没有运行日志。
- 不要在未测试干净环境前上传 GitHub Release。

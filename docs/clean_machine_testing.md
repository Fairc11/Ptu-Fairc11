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

- 首次启动是否能下载并识别 Chromium/headless shell
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

1. 安装器会自动启动；如果没有启动，手动打开桌面 `PtuInstaller\Ptu_Setup_v1.4.1.exe`。
2. 安装到默认目录。
3. 启动 Ptu。
4. 测试扫码登录二维码。
5. 打开左下角“运行日志”，点击“打开文件夹”。
6. 测试主页抓取、勾选 10 个作品批量下载。
7. 如果失败，把 Sandbox 内 `%LOCALAPPDATA%\Ptu\日志` 复制到桌面 `PtuSandboxOut`。这个目录会回传到宿主机 `sandbox-out\`。

关闭 Sandbox 后里面的数据会消失，所以失败日志必须先复制到 `PtuSandboxOut`。

## 验收标准

- 应用能启动，窗口能缩放、最大化、右上角关闭。
- 首次启动没有 `Permission denied: C:\Program Files\Ptu\...`。
- 扫码登录二维码能显示。
- 日志文件夹可一键打开，路径是 `%LOCALAPPDATA%\Ptu\日志`。
- 主页样例能抓到完整作品列表。
- 勾选 10 个主页作品批量下载，成功数等于选择数。

## 不要做的事

- 不要只在开发机上跑一下就发包。
- 不要只压缩 `C:\Program Files\Ptu` 回传问题；那里通常没有运行日志。
- 不要在未测试干净环境前上传 GitHub Release。

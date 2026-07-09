# Ptu 开发与封包发布清单

这份清单用于每次版本发布前执行。开发版能跑不代表封包版能发，封包版必须单独验收。

## 1. 开发前规则

- 先读根目录 `CLAUDE.md`、`README.md`、`docs/v1.5_completion_audit.md` 和对应平台迁移/发布计划。
- 抖音主页抓取优先走 API/f2 路线，不要重新堆 Playwright WAF 对抗参数；历史记录已经证明那是概率游戏。
- 修 bug 先写能复现问题的测试或探针，再改代码。
- 涉及封包环境的改动必须考虑 `sys.frozen`、`sys.stdout is None`、CWD 不等于 exe 目录、hiddenimports、datas，以及 `C:\Program Files\Ptu` 普通用户不可写。

## 2. 开发版验收

```powershell
python -m pytest tests -q
python -m compileall -q run.py desktop_app.py setup_check.py backend\app scripts
python scripts\release_check.py
```

主页抓取改动还必须用真实登录态跑一次：

```powershell
@'
import asyncio
from backend.app.services.scraper import DouyinScraper

sample = "7- 长按复制此条消息，打开抖音搜索，查看TA的更多作品。 https://v.douyin.com/vAjDKDovzq8/ 0@0.com :0pm"

async def main():
    s = DouyinScraper()
    result = await s.scrape_profile(sample, max_posts=30)
    print(result.user_name, result.total, result.has_more, result.next_cursor)

asyncio.run(main())
'@ | python -
```

验收标准：输出用户名、第一页最多 30 个作品；如果 `has_more=True`，前端“下一批 30 个”必须能用 `next_cursor` 继续加载。不要把单次上限改回 500 或一次性全量采集。

主页批量下载改动还必须验证真实下载，不允许只看网格显示：

```powershell
$env:PYTHONIOENCODING='utf-8'
@'
import asyncio, time
from backend.app.services.scraper import DouyinScraper
from backend.app.api.router_profile import batch_download

sample = "7- 长按复制此条消息，打开抖音搜索，查看TA的更多作品。 https://v.douyin.com/vAjDKDovzq8/ 0@0.com :0pm"

async def main():
    s = DouyinScraper()
    profile = await s.scrape_profile(sample, max_posts=10)
    posts = [p.model_dump(mode="json") for p in profile.posts[:10]]
    t = time.perf_counter()
    result = await batch_download({"user_name": profile.user_name, "posts": posts})
    print("total", result["total"])
    print("success", result["success"])
    print("base_dir", result["base_dir"])
    print("elapsed", round(time.perf_counter() - t, 2))

asyncio.run(main())
'@ | python -
```

验收标准：`success == total`，10 条不应退回每条 20-30 秒的详情页慢路径。若失败，先看主页返回的 `video_url/image_urls/music_url/live_photo_data` 是否为空，再看下载 URL 是否过期。

## 3. 封包前检查

- 更新 `backend/app/version.py`。
- 更新 `installer.iss` 的 `MyAppVersion`。
- 更新前端版本注释和 README/CLAUDE 更新日志。
- 确认 `setup_check.py` 里 `install_playwright()` 只有一个定义。
- 确认新增的动态/条件 import 已加入 `build.spec` 的 `hiddenimports`。
- 确认第三方配置、证书、模板、静态文件已加入 `datas`。
- 确认 `desktop_app.py` 使用原生窗口：`frameless=False`、`confirm_close=False`。主窗口必须能拖边缩放、最大化，并且右上角关闭直接退出。
- 确认 Chromium 内置和兜底下载路径被测试覆盖：`setup_check.get_chromium_path()` 必须能识别 `chrome-headless-shell.exe`、`headless_shell.exe` 和开发机已有的 `chrome.exe`，并且封包版优先查找 `_internal/ms-playwright/`。
- 确认 `build.spec` 已把 `%LOCALAPPDATA%\ms-playwright\chromium_headless_shell-1217` 打包到 `ms-playwright/chromium_headless_shell-1217`，同时没有把 `.env`、`cookies.yaml` 打进安装包。
- 确认 `installer.iss` 安装/卸载界面为中文文案，卸载时会询问是否清理 `%LOCALAPPDATA%\Ptu` 和 `%LOCALAPPDATA%\ms-playwright`。
- 不要在 `build.spec` 排除不确定依赖；尤其不要排除 `cryptography`。

## 4. 封包流程

```powershell
.\build_exe.bat
```

`build_exe.bat` 会先杀残留 `Ptu.exe` / `runw.exe`，清理 `dist` / `build`，再运行 `scripts/release_check.py`。

默认发布产物是单个安装包 EXE：

```text
installer\Ptu_Setup_v1.5.0.exe
```

对外只分发当前版本安装包。内部仍保留 `dist\Ptu\` onedir 结构用于验收和安装包打包，不要切换到 PyInstaller `onefile`。

如果脚本提示找不到 Inno Setup 6，安装后重新运行：

```text
https://jrsoftware.org/isdl.php
```

如果封包后出现秒退，临时把 `build.spec` 中 `console=False` 改为 `console=True` 构建一次，看控制台错误；确认后再改回 `False`。

## 5. 封包版冒烟

- 双击 `dist\Ptu\Ptu.exe`。
- 确认窗口能打开，能拖动边缘改变宽高，最大化按钮可用，右上角 X 能直接关闭应用。
- 再次打开应用，确认右上角登录状态正常。
- 用干净依赖环境验收一次扫码登录：临时移动或重命名 `%LOCALAPPDATA%\ms-playwright` 后启动封包版，确认内置 `_internal\ms-playwright\chromium_headless_shell-1217\chrome-headless-shell-win64\chrome-headless-shell.exe` 能被识别；不能出现“浏览器环境未就绪”。
- 打开安装包，确认安装向导、任务选项、完成页、WebView2 提示均为中文。
- 从 Windows 设置或卸载程序入口触发卸载，确认会弹出“是否同时删除用户数据和浏览器依赖缓存”的选择；点“否”保留运行数据，点“是”清理 `%LOCALAPPDATA%\Ptu` 和 `%LOCALAPPDATA%\ms-playwright`。
- 打开运行日志面板，确认 `%LOCALAPPDATA%\Ptu\日志\runs\` 生成本次运行日志；点击“打开文件夹”后确认资源管理器打开 `%LOCALAPPDATA%\Ptu\日志`；点击导出诊断包后确认右侧显示 zip 路径并打开 `%LOCALAPPDATA%\Ptu\日志\exports\`。runs/exports 只保留 7 天内日志。
- 扫码登录后抓取一个单作品链接。
- 点击登录获取二维码时，不应读取用户 Edge/Chrome 个人资料；正常兜底应走 Ptu 自己的内置浏览器安全容器，并强制后台/离屏运行。
- 首次启动必须显示免责声明，勾选同意后才能进入主界面。
- 主界面左侧只保留“单个链接抓取 / 主页链接抓取”；右侧常驻抖音预览 Dock，不应再有左侧“内置浏览”模式入口。
- 点击右侧“打开”后，抖音预览应贴靠在主窗口右侧，尽量无独立标题栏割裂感，登录/浏览页面不能只显示半屏。
- 右侧不再提供“复制当前链接”按钮，也不允许自动把当前页面 URL 填入单个/主页输入框；界面只保留手动复制教程：打开作品后点抖音分享按钮，再复制链接并粘贴到左侧抓取框。
- 在主页抓取页点击粘贴按钮，确认能读取剪贴板完整分享文本。
- 抓取主页样例，确认能显示用户信息和作品网格。
- 点击“下一批 30 个”，确认会继续加载后续作品，且每次加载都由用户主动触发。
- 勾选 10 个主页作品批量下载，确认成功数等于选择数，并生成下载目录。
- 抽查下载目录里的视频和实况照片：普通视频必须保存为 `.mp4`，实况短视频必须保存为 `live_XXXX_vid.mp4`；不能出现 `video.jpg`、`video.mp4.jpg`、`live_XXXX_vid.jpg` 这类“MP4 内容被命名为 JPG”的文件。
- 实况照片还要确认 FFmpeg 可用；若只下载出 `live_XXXX_img.*` 和 `live_XXXX_vid.mp4`，但没有合成 `live_XXXX.mp4`，先看日志是否有 `实况合成失败` 或 `[WinError 2] 系统找不到指定的文件`。
- 抽查每个下载目录存在 `post.txt`，普通视频、图文、实况照片和主页批量下载都必须保存作品文案。
- 点击“生成视频”，确认输出 `douyin_slideshow.mp4`；多素材应按抖音式横向翻页，单张实况照片或单张图片不应出现翻页动画；日志中应出现 `app.media` 的渲染排片记录，包含 FFmpeg 路径、素材数、实况视频数、音乐时长、循环次数和输出路径。
- 确认安装目录包含 `ffmpeg.exe` 和 `ffprobe.exe`；音乐时长探测依赖 `ffprobe.exe`，不能只打包 `ffmpeg.exe`。
- 检查 `%LOCALAPPDATA%\Ptu\日志\ptu_boot.log` 和 `%LOCALAPPDATA%\Ptu\日志\ptu.log`，不能有启动崩溃、导入失败、cookies 路径错位、`Permission denied: C:\Program Files\Ptu\...`。
- 外部测试回传问题时，不要只让对方压缩安装目录。让对方点击日志面板里的“打开文件夹”，打包 `%LOCALAPPDATA%\Ptu\日志\`；如涉及扫码登录，再附上 `%LOCALAPPDATA%\ms-playwright\` 是否存在浏览器可执行文件的目录清单。

## 6. 干净机测试

开发机冒烟通过后，必须按 `docs/clean_machine_testing.md` 继续做干净环境验证。

本机清运行时冒烟：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\clean_runtime_for_smoke.ps1
```

验收完成后恢复：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\clean_runtime_for_smoke.ps1 -RestoreLatest
```

Windows Sandbox 测试：

```text
双击 scripts\Ptu_Sandbox_Test.wsb
```

验收重点：

- 默认安装路径 `C:\Program Files\Ptu` 权限正常。
- 首次启动没有任何开发机缓存，扫码二维码仍能显示。
- 日志面板“打开文件夹”能打开 `%LOCALAPPDATA%\Ptu\日志`。
- 主页抓取第一页、主动下一批分页和 10 个作品批量下载通过。

用户未确认前，不要上传 GitHub Release，不要替换线上资产。

## 7. 归档

把 `installer\Ptu_Setup_v<version>.exe` 复制到 `releases/<version>/`。旧版本保留，不覆盖。

## 8. v1.5.0 候选出包记录（2026-06-03，本地待测）

本次 v1.5.0 已完整跑通本地出包链路，但尚未发布：

```powershell
$env:PTU_NO_PAUSE='1'
cmd /c build_exe.bat
```

最终候选产物：

```text
installer\Ptu_Setup_v1.5.0.exe
大小：380,160,451 字节（约 363 MB）
生成时间：2026-06-04 23:08:32
```

本次产物验收：

- `dist\Ptu\ffmpeg.exe` 存在。
- `dist\Ptu\ffprobe.exe` 存在。
- `dist\Ptu\THIRD_PARTY_NOTICES.md` 存在。
- `dist\Ptu\_internal\ms-playwright\chromium_headless_shell-1217\chrome-headless-shell-win64\chrome-headless-shell.exe` 存在。
- `dist\Ptu\_internal\ffmpeg.exe` 和 `dist\Ptu\_internal\ffprobe.exe` 不存在，避免重复打包。
- `dist\Ptu\_internal\backend\.env` 和 `dist\Ptu\_internal\backend\cookies.yaml` 不存在。
- `python -m pytest tests -q` -> `64 passed`。
- `python scripts\release_check.py` -> 通过。
- `python -m compileall -q run.py desktop_app.py setup_check.py backend\app scripts tests` -> 通过。
- `node --check backend\app\static\js\app.js` -> 通过。
- `powershell -ExecutionPolicy Bypass -File scripts\v1_5_installed_smoke_check.ps1 -InstallDir dist\Ptu -StartApp -WaitSeconds 90` -> 通过。
- 使用临时 `PTU_RUNTIME_DIR` 启动 `dist\Ptu\Ptu.exe` 后，进程保持运行，`http://127.0.0.1:18080/` 返回 200 且页面包含 Ptu 文案。
- `scripts\v1_5_installed_smoke_check.ps1 -InstallDir dist\Ptu -StartApp` 已在候选 `dist\Ptu` 上跑通，核心项全为 OK；日志目录只作为非阻塞 WARN。

发布状态：等待用户本机和朋友电脑测试确认；确认前不要提交、打 tag、创建 GitHub Release 或上传安装包。用户测试优先覆盖安装器双击安装、扫码登录、粘贴按钮不闪窗、普通视频 `.mp4`、实况照片、`post.txt`、`douyin_slideshow.mp4`、日志面板和卸载清理。

详细完成审计见 `docs\v1.5_completion_audit.md`。

## 9. v1.4.2 实际出包记录（2026-06-02）

本次 v1.4.2 已完整跑通本地出包链路：

```powershell
$env:PTU_NO_PAUSE='1'
cmd /c build_exe.bat
& "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" .\installer.iss
```

最终产物：

```text
installer\Ptu_Setup_v1.4.2.exe
大小：325,983,491 字节（约 311 MB）
生成时间：2026-06-02 20:09
```

本次产物验收：

- `dist\Ptu\_internal\ms-playwright\chromium_headless_shell-1217\chrome-headless-shell-win64\chrome-headless-shell.exe` 存在。
- `dist\Ptu\_internal\backend\.env` 和 `dist\Ptu\_internal\backend\cookies.yaml` 不存在。
- `python -m pytest tests -q` -> `20 passed`。
- `python scripts\release_check.py` -> 通过。
- `python -m compileall -q run.py desktop_app.py setup_check.py backend\app scripts` -> 通过。
- `node --check backend\app\static\js\app.js` -> 通过。

发布状态：用户确认安装/卸载、扫码登录、主页抓取和下载均正常后，已发布 GitHub Release `v1.4.2`。Release: https://github.com/Fairc11/Ptu-Fairc11/releases/tag/v1.4.2；安装包: https://github.com/Fairc11/Ptu-Fairc11/releases/download/v1.4.2/Ptu_Setup_v1.4.2.exe

## 9. v1.4.1 实际出包记录（2026-06-02）

本次 v1.4.1 已完整跑通出包链路：

```powershell
$env:PTU_NO_PAUSE='1'
cmd /c build_exe.bat
```

最终产物：

```text
installer\Ptu_Setup_v1.4.1.exe
大小：120.97 MB
生成时间：2026-06-02 17:06
```

本机 Inno Setup 安装与路径：

```powershell
winget install --id JRSoftware.InnoSetup -e --accept-source-agreements --accept-package-agreements
& "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" .\installer.iss
```

注意事项：

- `build_exe.bat` 已支持 `%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe`，不要只查 `Program Files`。
- `build_exe.bat` 的输出文字保持英文/ASCII，避免 Windows `cmd` 解析中文批处理时乱码并中断。
- 本机 Inno Setup 6.7.3 未自带 `ChineseSimplified.isl`，所以安装器界面暂用英文；Ptu 应用内仍是中文。
- `installer.iss` 的 `[UninstallRun]` 已给 `taskkill` 增加 `RunOnceId: "KillPtu"`，避免编译警告。
- 这次没有自动执行安装器安装；正式分发前仍需人工双击 `installer\Ptu_Setup_v1.4.1.exe`，完成安装后按第 5 节做冒烟测试。
- 如果安装到 `C:\Program Files\Ptu` 后启动报 `PermissionError: [Errno 13] Permission denied: 'C:\\Program Files\\Ptu\\ptu_boot.log'`，说明运行时数据又写回了安装目录；封包版必须写入 `%LOCALAPPDATA%\Ptu`。
- 如果安装器提示下载 WebView2，但本机 `C:\Program Files (x86)\Microsoft\EdgeWebView\` 已存在，说明 WebView2 检测漏了 32 位注册表/WOW6432Node 分支。
- 如果扫码登录二维码空白并提示“浏览器环境未就绪”，先检查安装目录 `_internal\ms-playwright\` 和 `%LOCALAPPDATA%\ms-playwright`。Playwright headless shell 可能叫 `chrome-headless-shell.exe` 或 `headless_shell.exe`，`setup_check.py` 和 `qr_login.py` 都必须识别；这类问题不能只在已有 Playwright `chrome.exe` 的开发机上复现。
- 如果 Chromium 已内置但实况合成仍提示找不到文件，优先检查启动入口是否同时检测了 FFmpeg。不能只在 Chromium 缺失时才运行 `setup_check.run_setup()`。

本次验证结果：

```text
python scripts\release_check.py                         -> 通过
python -m pytest tests -q                               -> 16 passed
python -m compileall -q run.py desktop_app.py setup_check.py backend\app scripts -> 通过
Inno Setup 编译 installer.iss                            -> Successful compile
```

2026-06-02 17:06 替换构建补充：

- 修复干净机器首次扫码登录的 `headless_shell.exe` 识别问题。
- 日志集中到 `%LOCALAPPDATA%\Ptu\日志`，运行日志面板新增“打开文件夹”。
- 新增 `docs/clean_machine_testing.md`、`scripts/clean_runtime_for_smoke.ps1`、`scripts/Ptu_Sandbox_Test.wsb`。
- GitHub Release `v1.4.1` 已在用户确认后替换安装包资产，线上文件大小为 `126848606` 字节。

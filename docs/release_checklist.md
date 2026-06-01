# Ptu 开发与封包发布清单

这份清单用于每次版本发布前执行。开发版能跑不代表封包版能发，封包版必须单独验收。

## 1. 开发前规则

- 先读根目录 `CLAUDE.md` 和 `github-ptu/PTU_TECHNICAL_DOCUMENTATION底层数据记录.md`。
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
    result = await s.scrape_profile(sample, max_posts=500)
    print(result.user_name, result.total)

asyncio.run(main())
'@ | python -
```

验收标准：输出用户名且 `total >= 200`。如果明显低于 200，先检查分页参数、`has_more/max_cursor`、Cookie 登录态和接口空响应，不要只验证前 5 条。

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
- 不要在 `build.spec` 排除不确定依赖；尤其不要排除 `cryptography`。

## 4. 封包流程

```powershell
.\build_exe.bat
```

`build_exe.bat` 会先杀残留 `Ptu.exe` / `runw.exe`，清理 `dist` / `build`，再运行 `scripts/release_check.py`。

默认发布产物是单个安装包 EXE：

```text
installer\Ptu_Setup_v1.4.1.exe
```

对外只分发这个安装包。内部仍保留 `dist\Ptu\` onedir 结构用于验收和安装包打包，不要切换到 PyInstaller `onefile`。

如果脚本提示找不到 Inno Setup 6，安装后重新运行：

```text
https://jrsoftware.org/isdl.php
```

如果封包后出现秒退，临时把 `build.spec` 中 `console=False` 改为 `console=True` 构建一次，看控制台错误；确认后再改回 `False`。

## 5. 封包版冒烟

- 双击 `dist\Ptu\Ptu.exe`。
- 确认窗口能打开，能拖动边缘改变宽高，最大化按钮可用，右上角 X 能直接关闭应用。
- 再次打开应用，确认右上角登录状态正常。
- 打开运行日志面板，确认 `%LOCALAPPDATA%\Ptu\data\logs\runs\` 生成本次运行日志；点击导出后确认 `%LOCALAPPDATA%\Ptu\data\logs\exports\` 生成快照。runs/exports 只保留 7 天内日志。
- 扫码登录后抓取一个单作品链接。
- 在主页抓取页点击粘贴按钮，确认能读取剪贴板完整分享文本。
- 抓取主页样例，确认能显示用户信息和作品网格。
- 勾选 10 个主页作品批量下载，确认成功数等于选择数，并生成下载目录。
- 检查 `%LOCALAPPDATA%\Ptu\ptu_boot.log` 和 `%LOCALAPPDATA%\Ptu\data\logs\ptu.log`，不能有启动崩溃、导入失败、cookies 路径错位、`Permission denied: C:\Program Files\Ptu\...`。

## 6. 归档

把 `installer\Ptu_Setup_v<version>.exe` 复制到 `releases/<version>/`。旧版本保留，不覆盖。

## 7. v1.4.1 实际出包记录（2026-06-02）

本次 v1.4.1 已完整跑通出包链路：

```powershell
$env:PTU_NO_PAUSE='1'
cmd /c build_exe.bat
```

最终产物：

```text
installer\Ptu_Setup_v1.4.1.exe
大小：120.97 MB
生成时间：2026-06-02 01:49
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

本次验证结果：

```text
python scripts\release_check.py                         -> 通过
python -m pytest tests -q                               -> 12 passed
python -m compileall -q run.py desktop_app.py setup_check.py backend\app scripts -> 通过
Inno Setup 编译 installer.iss                            -> Successful compile
```

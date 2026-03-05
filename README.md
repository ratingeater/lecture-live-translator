# Lecture Live Translator

面向长时间讲座的本地实时听写与翻译工具，实时链路优先，离线批处理作为补充。

## 功能

- 浏览器本地麦克风采集，WebSocket 实时送到 Google Cloud Speech-to-Text V2。
- 识别结果自动翻译，默认输出简体中文。
- 支持 `ru-RU`、`en-US`、`ja-JP` 三种输入语言。
- 自动语言检测模式可在 `ru/en/ja` 三者之间切换。
- 长时间实时流会自动轮换重连，并保留一小段音频重叠，减少 lecture 场景下的断句丢失。
- 离线文件批处理支持音频/视频上传，本地用 `ffmpeg` 转成 FLAC 后走 GCS + BatchRecognize。
- 批处理输出双语 `SRT`、原文 `TXT`、译文 `TXT`，保存在 [`.runtime/outputs`](/e:/projects/lecture-live-translator/.runtime/outputs)。

## 当前环境状态

- 本机已安装 `gcloud`，路径是 `C:\Users\admin\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd`。
- 本机已安装 `ffmpeg`，路径是 `C:\Users\admin\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg.Essentials_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-essentials_build\bin\ffmpeg.exe`。
- 当前还没有可用的 Google Cloud 凭据，`gcloud auth list` 返回空数组，所以第一次运行前仍然必须登录。

## 先决条件

- Python 3.12
- 一个可计费的 Google Cloud 项目
- 已启用以下 API
  - `speech.googleapis.com`
  - `translate.googleapis.com`
  - `storage.googleapis.com`

## 推荐初始化

1. 在项目根目录执行：

```powershell
uv sync --python 3.12
```

2. 复制环境变量模板：

```powershell
Copy-Item .env.example .env
```

3. 用交互式脚本登录，并顺手启用所需服务：

```powershell
.\scripts\gcp-login.ps1
```

这个脚本现在支持两种方式：

- 默认交互：登录后列出你可访问的 projects，让你选一个。
- 参数模式：你直接传 `-ProjectId`、`-AuthMode`、`-CredentialFile`，就可以无提示执行。

常见例子：

```powershell
.\scripts\gcp-login.ps1
.\scripts\gcp-login.ps1 -ProjectId YOUR_PROJECT_ID -NonInteractive
.\scripts\gcp-login.ps1 -AuthMode ServiceAccount -CredentialFile C:\path\key.json -ProjectId YOUR_PROJECT_ID -WriteEnv
.\scripts\gcp-login.ps1 -ListServiceAccounts
```

如果你更习惯手动执行，ADC 模式的等价命令是：

```powershell
& 'C:\Users\admin\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd' auth login --update-adc
& 'C:\Users\admin\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd' config set project YOUR_PROJECT_ID
& 'C:\Users\admin\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd' services enable speech.googleapis.com translate.googleapis.com storage.googleapis.com
```

如果你不想用 ADC，也可以传 `-AuthMode ServiceAccount` 并提供 `-CredentialFile`，脚本也支持把 `GOOGLE_APPLICATION_CREDENTIALS` 写入 `.env`。

## 运行

```powershell
.\scripts\start.ps1
```

或者直接：

```powershell
.\.venv312\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8765 --reload
```

打开 `http://127.0.0.1:8765`。

## 使用说明

### 实时模式

- 填 `GCP Project ID`
- 选择 `Speech 区域`
- 选输入语言
  - `手动指定`：用 `chirp_3`
  - `自动检测（ru/en/ja）`：用 `long`
- 选目标语言
- 点击 `开始监听`

说明：

- 自动语言检测时，页面会禁用“手动语言”，避免配置冲突。
- 当前实时模式采集的是浏览器麦克风。如果你要转写电脑外放里的 lecture，需要系统里提供可选的回采设备，例如 Stereo Mix、虚拟声卡或回环输入。

### 离线模式

- 直接上传音频或视频文件
- 后端会先用 `ffmpeg` 统一转成单声道 16k FLAC
- 然后上传到 GCS 进行批处理
- 结果返回到页面，同时写入本地输出目录

## 已验证内容

- `pytest` 通过
- `ruff check` 通过
- 本地首页可返回 `HTTP 200`
- 实际浏览器检查过桌面和移动窄屏布局，没有出现文字重叠或消失

## 代码结构

- [app/main.py](/e:/projects/lecture-live-translator/app/main.py): FastAPI 入口、WebSocket、批处理 API
- [app/services/realtime.py](/e:/projects/lecture-live-translator/app/services/realtime.py): 实时流式识别与翻译会话
- [app/services/batch.py](/e:/projects/lecture-live-translator/app/services/batch.py): 离线批处理转写与输出
- [app/static/app.js](/e:/projects/lecture-live-translator/app/static/app.js): 前端音频采集与实时 UI
- [app/static/styles.css](/e:/projects/lecture-live-translator/app/static/styles.css): 页面样式

## 已知限制

- 当前没有实现浏览器端系统音频直选，只做了麦克风输入。
- GCP 凭据没有办法替你在当前会话中自动完成授权，必须由你登录 ADC 或提供服务账号。
- 自动语言检测为了兼容 V2 的多语言识别，使用 `long` 模型而不是 `chirp_3`。

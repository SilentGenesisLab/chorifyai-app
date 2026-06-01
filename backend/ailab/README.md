# ailab — ASR + 翻译子系统

chorify-video 的语音识别 / 多语翻译能力层。基于 **OpenAI Whisper-large-v3** + **豆包 (火山方舟 Ark)**，对外暴露 Python 包接口和 HTTP 服务两种用法。

> 主要服务于东南亚（泰国）短视频带货素材的"听写 + 转中文"环节。

---

## 模块结构

```
ailab/
├── __init__.py
├── README.md                ← 本文档 (总览 + 部署)
├── api/
│   ├── server.py            FastAPI HTTP 服务入口
│   └── README.md            HTTP 接口详细文档 (curl 示例 / 字段表)
├── asr/
│   ├── asr_service.py       Python 公开接口: transcribe_audio / transcribe_video /
│   │                                       transcribe_and_translate / extract_audio_to_oss
│   ├── download_whisper.py  预下载 Whisper-large-v3 (带重试 + 绕代理)
│   └── whisper-large-v3.py  冒烟测试 demo
└── llm/
    └── doubao.py            豆包 Ark /responses 封装: complete_text / translate_text
```

### 提供的能力

| 入口 | 类型 | 说明 |
|---|---|---|
| `ailab.asr.transcribe_audio` | Python | 音频 → 文本 + 词级时间戳 |
| `ailab.asr.transcribe_video` | Python | 视频 → ffmpeg 抽音 → 文本 |
| `ailab.asr.transcribe_and_translate` | Python | 视频 → 文本 → 翻译，一站式 |
| `ailab.asr.extract_audio_to_oss` | Python | 视频抽 16k 单声道 WAV 上 OSS，返回公网 URL |
| `ailab.llm.translate_text` | Python | 豆包翻译单段文本 |
| `python -m ailab.asr.asr_service` | CLI | audio / video / extract / translate 四个子命令 |
| `python -m ailab.api.server` | HTTP | FastAPI 服务，端口 8089，自带 Swagger UI |

HTTP 接口详细文档见 [api/README.md](api/README.md)。

---

## 部署指南

### 1. 前置要求

| 项 | 版本 / 说明 |
|---|---|
| OS | Windows 10/11 (项目主用) 或 Linux |
| Python | 3.10 / 3.11 (建议跟 cuda23 环境一致) |
| GPU | NVIDIA, ≥ 8GB 显存 (Whisper-large-v3 用 fp16 约 6GB) |
| CUDA | 11.8 或 12.x，需与 torch 版本对应 |
| ffmpeg | 命令行可调用 (PATH 里要有) |
| 磁盘 | 模型缓存约 3GB |

### 2. 准备 conda 环境 (cuda23)

项目约定使用 `cuda23` 环境名，所有依赖装在其中。

```powershell
# 新建环境 (已有可跳过)
conda create -n cuda23 python=3.11 -y
conda activate cuda23

# 先单独装 torch (要按 CUDA 版本选 index, 不能跟其他包一起 pip install)
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# 装其余全部依赖 (ailab + badge_swap + split_shots + oss + ...)
pip install -r ../requirements.txt
```

> 不要把这些装到 base 环境。`api/README.md` 里所有命令都要求显式用
> `D:\Anaconda3\envs\cuda23\python.exe`，目的是绕开 PATH 干扰。
>
> 完整依赖清单见项目根 [requirements.txt](../requirements.txt)。

### 3. 安装 ffmpeg

Windows:

```powershell
# 任选其一
choco install ffmpeg -y
# 或 scoop install ffmpeg
# 或下载 https://www.gyan.dev/ffmpeg/builds/ 解压后把 bin 加到 PATH
ffmpeg -version  # 验证
```

Linux:

```bash
sudo apt update && sudo apt install -y ffmpeg
```

### 4. 配置 `.env`

在项目根目录 `chorify-video/` 下复制 `.env.example` → `.env` 并填值：

```ini
# 阿里云 OSS (extract_audio_to_oss 需要)
OSS_ACCESS_KEY_ID=...
OSS_ACCESS_KEY_SECRET=...
OSS_BUCKET=...
OSS_ENDPOINT=oss-cn-beijing.aliyuncs.com
OSS_CUSTOM_DOMAIN=oss-imgai.sligenai.cn

# 豆包 / 火山方舟 Ark
ARK_API_KEY=...
ARK_VLM_MODEL=doubao-seed-2-0-pro-260215
ARK_TEXT_MODEL=                          # 可选, 留空则 fallback 到 ARK_VLM_MODEL
ARK_ENDPOINT=https://ark.cn-beijing.volces.com/api/v3/responses
```

`ailab/llm/doubao.py` 启动时会从项目根的 `.env` 自动加载。

### 5. 预下载 Whisper 模型 (可选但建议)

首次冷启动会自动拉 ~3GB 模型，国内网络容易 SSL 报错 (`DECRYPTION_FAILED_OR_BAD_RECORD_MAC`)。建议先单独跑下载脚本：

```powershell
D:\Anaconda3\envs\cuda23\python.exe -m ailab.asr.download_whisper
```

脚本内置：
- 自动清掉 `HTTP_PROXY` / `HTTPS_PROXY` (代理是这里大多数 SSL 报错的根因)
- 最多重试 30 次，每次间隔 5 秒
- 从 ModelScope 拉 `iic/Whisper-large-v3@v2.0.5`

缓存路径默认 `C:\Users\Admin\.cache\modelscope\hub\models\iic\Whisper-large-v3`。OpenAI Whisper 引擎会直接复用同一个 `large-v3.pt`，不会重复下载。

### 6. 冒烟测试

**6.1 先验证 CUDA / GPU 真的能用** (强烈建议第一次部署都跑一遍):

```powershell
# 基础环境 + GPU 计算冒烟测试 (秒级)
D:\Anaconda3\envs\cuda23\python.exe -m ailab.check_cuda

# 顺便验证 Whisper 是不是真的加载到 GPU 上 (会触发模型加载, ~30s)
D:\Anaconda3\envs\cuda23\python.exe -m ailab.check_cuda --with-whisper
```

退出码：`0` = OK / `1` = CUDA 不可用（通常是装了 CPU 版 torch）/ `2` = GPU 算不出来。

> 如果 ASR 速度异常（RTF > 1），先跑这个脚本看是不是模型跑在 CPU 上 —— 那是慢 10× 的最常见原因。

**6.2 端到端冒烟** (启 HTTP 服务前确认链路通):

```powershell
D:\Anaconda3\envs\cuda23\python.exe ailab\asr\whisper-large-v3.py

# 期望输出:
# [asr] 加载 OpenAI Whisper large-v3 ...
# [asr] OpenAI Whisper 加载完成 device=cuda:0
# text = ...
# segments = N
```

### 7. 启动 HTTP 服务

工作目录必须是项目根 `I:\2026AILab\chorify2\chorify-video\`（即 `ailab` 的父目录），`-m ailab.api.server` 才能解析包：

```powershell
# 局域网可访问 (推荐, 生产)
D:\Anaconda3\envs\cuda23\python.exe -m ailab.api.server --host 0.0.0.0 --port 8089

# 仅本机
D:\Anaconda3\envs\cuda23\python.exe -m ailab.api.server --host 127.0.0.1 --port 8089

# 或 uvicorn (server.py 自己会把项目根加到 sys.path)
D:\Anaconda3\envs\cuda23\python.exe -m uvicorn ailab.api.server:app --host 0.0.0.0 --port 8089

# 开发模式 (热重载, 不要用于生产)
D:\Anaconda3\envs\cuda23\python.exe -m ailab.api.server --reload
```

可用参数:

| flag | 默认 | 说明 |
|---|---|---|
| `--host` | `0.0.0.0` | 监听地址 |
| `--port` | `8089` | 监听端口 |
| `--reload` | off | 文件改动热重载, 仅开发 |
| `--workers` | `1` | 进程数 — **注意每个进程会独立加载 3GB 模型, 显存够再开** |

### 8. 验证服务

```powershell
# 心跳
curl http://127.0.0.1:8089/health

# 期望:
# {"code":0,"msg":"ok","data":{"service":"asr","status":"up"}}

# Swagger UI (浏览器打开)
start http://127.0.0.1:8089/docs
```

完整接口列表 / curl 示例见 [api/README.md](api/README.md)。

### 9. 后台常驻 (可选)

#### Windows — NSSM 注册成服务

```powershell
# 装 NSSM: choco install nssm -y

nssm install chorify-asr "D:\Anaconda3\envs\cuda23\python.exe"
nssm set chorify-asr AppParameters "-m ailab.api.server --host 0.0.0.0 --port 8089"
nssm set chorify-asr AppDirectory "I:\2026AILab\chorify2\chorify-video"
nssm set chorify-asr AppStdout "I:\2026AILab\chorify2\chorify-video\logs\asr-stdout.log"
nssm set chorify-asr AppStderr "I:\2026AILab\chorify2\chorify-video\logs\asr-stderr.log"
nssm set chorify-asr Start SERVICE_AUTO_START
nssm start chorify-asr
```

#### Windows — 任务计划程序 (轻量替代)

`taskschd.msc` 里加一个登录时触发的任务，操作填上面那条 `python ... -m ailab.api.server` 命令，工作目录设为项目根。

#### Linux — systemd

`/etc/systemd/system/chorify-asr.service`:

```ini
[Unit]
Description=chorify ASR & Translate Service
After=network.target

[Service]
Type=simple
User=appuser
WorkingDirectory=/opt/chorify-video
Environment=PATH=/opt/conda/envs/cuda23/bin:/usr/bin
ExecStart=/opt/conda/envs/cuda23/bin/python -m ailab.api.server --host 0.0.0.0 --port 8089
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now chorify-asr
sudo systemctl status chorify-asr
journalctl -u chorify-asr -f
```

---

## 性能参考 (RTX 4090)

| 操作 | 耗时 |
|---|---|
| 首次模型加载 | 30–60s |
| ASR 推理 | 100s 视频 ≈ 12–15s (RTF ≈ 0.15) |
| 豆包翻译 | 1–3s / 段 |
| 视频抽音 (ffmpeg) | 100s 视频 ≈ 1–2s |
| `/asr/translate` 端到端 | 100s 视频 ≈ 20–30s |

显存峰值约 6GB (fp16)，关掉 `with_timestamps` 可省 30–50% 推理时间。

---

## 故障排查

| 现象 | 原因 / 解决 |
|---|---|
| `DECRYPTION_FAILED_OR_BAD_RECORD_MAC` 下载模型时 | 系统级代理在拦 TLS。`asr_service` 启动时已清掉常见代理变量，但 Windows 系统代理需要在 `设置 → 网络 → 代理` 里关掉；或先跑 `download_whisper.py` 把模型拉到位 |
| OpenAI Whisper `key.size mismatch` / SDPA 报错 | 已知 PyTorch SDPA bug。`_openai_transcribe_with_fallback` 会自动 3 级回退 (fp16 → fp32 → 关词级时间戳)，看日志确认走的是哪条 |
| `ModuleNotFoundError: ailab` | 没在项目根目录跑 / 没用 `-m`。务必 `cd` 到 `chorify-video/` 再执行命令 |
| `ffmpeg 抽音轨失败` | ffmpeg 不在 PATH，或视频文件损坏。`ffmpeg -version` 自测，再手动跑日志里那条命令看 stderr |
| 显存不够 OOM | 同机不要起 `--workers > 1`；或换 `engine=funasr`，或先 `extract_audio_to_oss` 再走 OpenAI Whisper API |
| 豆包翻译 401/403 | `.env` 里 `ARK_API_KEY` 错或没读到。`doubao.py` 只读项目根的 `.env`，确认文件位置 |

---

## 相关文档

- [api/README.md](api/README.md) — HTTP 接口字段表 + curl 示例
- [../README.md](../README.md) — chorify-video 整体流水线说明
- [../.env.example](../.env.example) — 全部环境变量模板

# VoxCPM2 本地部署

OpenBMB VoxCPM2 的轻量 HTTP 包装服务，作为 chorify 流水线的 TTS / 音色克隆后端。

- **TTS**：文本 → 语音（支持 Voice Design：`text` 里写 `(描述)` 即可造音色）
- **音色克隆**：参考音频 + 目标文本 → 目标语音
- **多语种**：中 / 英 / 泰等
- **GPU**：单卡 4090 推理实时倍率 ~10x（10s 文本约 1s 出音）

## 目录结构

```
voxcpm/
├── server.py                  # FastAPI 服务 (默认 :8190)
├── start_server.bat           # 一键启动 (默认用 tor25 环境)
├── download_model.py          # 下载 VoxCPM2 权重 (ModelScope, 国内直连)
├── download_model.bat         # 双击下载包装
├── test.py                    # 最小可用样例 (本地直调 VoxCPM)
├── test_voxcpm.py             # 更完整的本地测试
├── models/
│   └── VoxCPM2/               # 模型权重 (~8GB, 下载后填入, 已 .gitignore)
├── outputs/                   # 生成的 wav (已 .gitignore)
├── refs/                      # 参考音频 (已 .gitignore)
├── .venv/                     # 独立虚拟环境 (空壳, 当前默认复用 tor25)
├── README.md                  # 本文档 (部署 + 速查)
└── API.md                     # HTTP API 完整字段说明 + 错误码 + 端到端示例
```

## 环境准备

默认**复用 chorify 主项目的 `tor25` 环境**（Python 3.11 + torch 2.5.1+cu124），torch / modelscope / funasr / librosa 等重依赖已就绪，装 voxcpm 是轻量增量。

```powershell
$env:HTTP_PROXY=""; $env:HTTPS_PROXY=""; $env:NO_PROXY="*"
D:\Anaconda3\envs\tor25\python.exe -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple voxcpm
```

> 想用独立 `.venv` 而不是 tor25：先装 torch (cu124) 到 `.venv`，然后 `set VOXCPM_PYTHON=...\.venv\Scripts\python.exe` 即可，两个 .bat 都会自动用这个变量。

## 下载模型

走 ModelScope（国内直连，免代理，约 8GB）：

```powershell
cd voxcpm
download_model.bat
# 或: D:\Anaconda3\envs\tor25\python.exe download_model.py
```

下到 `voxcpm\models\VoxCPM2\`，**正好对应 server.py 的默认 `MODEL_DIR`，无需配置**。

参数：

| 参数 | 说明 |
|---|---|
| 默认（无参数） | ModelScope `OpenBMB/VoxCPM2` |
| `--hf` | 改走 HuggingFace `openbmb/VoxCPM2`（hf-mirror，国内不稳定，**不推荐**） |
| `--dir <path>` | 改保存目录；改了之后启动 server 要设 `VOXCPM_MODEL_DIR=<path>` |

脚本带 30 次自动重试 + 关代理 + 下完列文件校验，不需要人工守。

### 走 Motrix 离线下大文件（兜底）

如果 modelscope SDK 抽风，可去 [modelscope.cn/models/OpenBMB/VoxCPM2/files](https://modelscope.cn/models/OpenBMB/VoxCPM2/files) 用 Motrix 逐个下，全部塞到 `voxcpm\models\VoxCPM2\`。

## 启动服务

```powershell
start_server.bat
```

等价于：

```powershell
D:\Anaconda3\envs\tor25\python.exe server.py --host 0.0.0.0 --port 8190 --preload
```

`--preload` 启动时即加载模型（约 5-10s 显存上车 ~4GB），否则首次请求才加载。

成功后看到：

```
[init] loading VoxCPM2 from .../models/VoxCPM2 ...
[init] ready, sample_rate=16000Hz, cuda=True
INFO:     Uvicorn running on http://0.0.0.0:8190
```

健康检查：

```powershell
curl http://127.0.0.1:8190/health
# {"status":"ok","cuda":true,"model_dir":"...\\models\\VoxCPM2","loaded":true}
```

## 合成模式（4 种）

VoxCPM2 一个 `generate()` 调用支持四种模式，靠传不同参数切换：

| 模式 | 关键参数 | 效果 |
|---|---|---|
| **1. 基础 TTS** | 只传 `text` | 默认音色 |
| **2. Voice Design** | `text="(描述)正文"` | 自然语言造音色, 无需参考音 |
| **3. 普通克隆** | `+ reference_wav_path` | 复制参考音色 |
| **4. 终极克隆** | `+ prompt_wav_path + prompt_text` | 最高保真, 还原细微音色 (官方推荐 `reference_wav_path` 也填同一份) |

> HTTP 接口里 `reference_wav_path` / `prompt_wav_path` 既接受**服务器本地路径**, 也接受**公网 URL** (`http(s)://...`, 自动下载)。Python 库直调只接受本地路径。

### Python 库直调示例（不走 HTTP）

```python
from voxcpm import VoxCPM
import soundfile as sf

model = VoxCPM.from_pretrained("./models/VoxCPM2", load_denoiser=False)
sr = model.tts_model.sample_rate

# 1) 基础 TTS
wav = model.generate(
    text="VoxCPM2 is the current recommended release for realistic multilingual speech synthesis.",
    cfg_value=2.0,
    inference_timesteps=10,
)
sf.write("demo.wav", wav, sr)

# 2) Voice Design (描述造音色)
wav = model.generate(
    text="(A young woman, gentle and sweet voice) Hello, welcome to VoxCPM2!",
    cfg_value=2.0,
    inference_timesteps=10,
)
sf.write("voice_design.wav", wav, sr)

# 3) 普通克隆 (复制参考音色, 仍可在 text 里加 (控制指令) 调语速/情绪/风格)
wav = model.generate(
    text="(slightly faster, cheerful tone) This is a cloned voice with style control.",
    reference_wav_path="path/to/voice.wav",
    cfg_value=2.0,
    inference_timesteps=10,
)
sf.write("clone.wav", wav, sr)

# 4) 终极克隆 (最高保真, prompt_text 必须跟 prompt_wav_path 内容一字不差)
wav = model.generate(
    text="This is an ultimate cloning demonstration using VoxCPM2.",
    prompt_wav_path="path/to/voice.wav",
    prompt_text="The transcript of the reference audio.",
    reference_wav_path="path/to/voice.wav",   # 官方推荐填同一份, 提升相似度
)
sf.write("hifi_clone.wav", wav, sr)
```

## HTTP API 接口

服务返回均为 **`audio/wav` 二进制流**（sample_rate 16000 Hz）。**完整字段说明 + 错误码 + 端到端示例见 [API.md](API.md)**，下面给最小用法。

### `POST /tts` — 基础 TTS / Voice Design

```jsonc
{
    "text": "你好,这是 VoxCPM2 合成的中文语音。",
    "cfg_value": 2.0,             // 可选, 默认 2.0
    "inference_timesteps": 10     // 可选, 默认 10
}
```

Voice Design：`text` 开头加 `(描述)`：

```jsonc
{ "text": "(一位温柔甜美的年轻女性)你好,这是用文字描述生成的全新音色。" }
```

### `POST /clone` — 上传参考音克隆（multipart）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `text` | str | ✅ | 目标文本 |
| `reference` | file | ✅ | 参考音频（≥3s 效果更好）|
| `cfg_value` | float | ❌ | 默认 2.0 |
| `inference_timesteps` | int | ❌ | 默认 10 |
| `prompt_reference` | file | ❌ | **终极克隆**: 额外参考音 |
| `prompt_text` | str | ❌ | **终极克隆**: `prompt_reference` 的精确转写 |

```powershell
# 普通克隆
curl -X POST http://127.0.0.1:8190/clone `
  -F "text=大家好我是新的克隆音色" `
  -F "reference=@refs\speaker_a.wav" `
  -o outputs\cloned.wav

# 终极克隆
curl -X POST http://127.0.0.1:8190/clone `
  -F "text=终极克隆,还原参考音的每个细节" `
  -F "reference=@refs\speaker_a.wav" `
  -F "prompt_reference=@refs\speaker_a.wav" `
  -F "prompt_text=参考音对应的精确文本一字不差" `
  -o outputs\hifi_cloned.wav
```

### `POST /clone_path` — 路径 / URL 克隆（批量推荐）

JSON 字段：

| 字段 | 必填 | 说明 |
|---|---|---|
| `text` | ✅ | 目标文本 |
| `reference_wav_path` | ⚠️ | 普通克隆必填; 终极克隆可选。**接受本地路径或 http(s):// URL** |
| `prompt_wav_path` | ❌ | **终极克隆**: 参考音。**接受本地路径或 http(s):// URL** |
| `prompt_text` | ❌ | **终极克隆**: 配合 `prompt_wav_path` 的精确转写 |
| `cfg_value` | ❌ | 默认 2.0 |
| `inference_timesteps` | ❌ | 默认 10 |

**字段值两种形态**:
- 服务器**本地路径** `"I:/refs/voice.wav"` — `os.path.exists` 校验
- 公网 **URL** `"https://oss-xxx.aliyuncs.com/refs/voice.mp3"` — 自动下载到临时文件, 推理完清理 (≤ 200 MB)

**约束**: `reference_wav_path` 和 `prompt_wav_path` 至少传一个; 传 `prompt_wav_path` 必须配 `prompt_text`。

```jsonc
// 1) 普通克隆 + 本地路径
{
    "text": "目标文本",
    "reference_wav_path": "I:/2026AILab/.../shot11_voice.wav"
}

// 2) 普通克隆 + OSS URL (chorify 批量配音常用)
{
    "text": "目标文本",
    "reference_wav_path": "https://chorify-video.oss-cn-hangzhou.aliyuncs.com/refs/shot11.mp3"
}

// 3) 终极克隆 (官方推荐 reference 和 prompt 同一份)
{
    "text": "目标文本",
    "reference_wav_path": "https://oss.../refs/shot11.mp3",
    "prompt_wav_path":    "https://oss.../refs/shot11.mp3",
    "prompt_text":        "shot11 里说的那句话的精确转写"
}
```

跟 `/clone` 等价，但**不需要客户端上传文件** —— 服务端直接从本地盘或 OSS 拉, **chorify 批量配音场景最省事**。详见 [API.md](API.md)。

## 集成到 chorify 主流水线

VoxCPM2 服务跟 ailab 主服务并排，**两套等价入口**任选：

| 入口 | URL 前缀 | 说明 |
|---|---|---|
| **直连 VoxCPM2** | `http://127.0.0.1:8190/*` | 少一跳网络开销, wav 大文件直传更快 |
| **经 ailab 网关** | `http://127.0.0.1:8089/tts/voxcpm/*` | 跟 ASR/翻译共享 base URL, 前端只接一个地址 |

ailab 网关已经把 4 个端点都转发好了（[ailab/api/server.py](../ailab/api/server.py) 里 `/tts/voxcpm/*`）。

| 直连 | 网关 |
|---|---|
| `POST :8190/tts` | `POST :8089/tts/voxcpm` |
| `POST :8190/clone` | `POST :8089/tts/voxcpm/clone` |
| `POST :8190/clone_path` | `POST :8089/tts/voxcpm/clone_path` |
| `GET  :8190/health` | `GET  :8089/tts/voxcpm/health` |

网关后端地址通过环境变量配置（默认 `http://127.0.0.1:8190`）：

```powershell
$env:VOXCPM_BASE_URL = "http://192.168.1.100:8190"   # 多机部署时改这里
uvicorn ailab.api.server:app --port 8089
```

### 典型混剪流水

```
视频源 → ASR (faster-whisper) → 译文 → VoxCPM2 (clone_path 用原片人声为参考) → 拼接配音
                                          ↑
                                  原片分镜人声 .wav
```

### 端到端示例（Python，经网关）

**OSS URL 版**（生产推荐，**客户端零文件流量**）：

```python
import requests
from pathlib import Path

AILAB    = "http://127.0.0.1:8089"
OSS_BASE = "https://chorify-video.oss-cn-hangzhou.aliyuncs.com"

# 1. 视频 URL -> ASR + 翻译 (ailab 服务端拉 OSS 视频)
r = requests.post(f"{AILAB}/asr/translate", json={
    "url":    f"{OSS_BASE}/raw/shot01.mp4",
    "source": "thai",
    "target": "zh",
}, timeout=300)
r.raise_for_status()
data = r.json()["data"]

# 2. VoxCPM2 终极克隆: 参考音也走 OSS URL, voxcpm 服务端自动下载
ref_url = f"{OSS_BASE}/refs/shot01_voice.mp3"   # 预先抽好的原片人声放 OSS
r = requests.post(f"{AILAB}/tts/voxcpm/clone_path", json={
    "text":               data["target_text"],   # 中文译文 (豆包出)
    "reference_wav_path": ref_url,               # OSS URL, 同一份
    "prompt_wav_path":    ref_url,
    "prompt_text":        data["source_text"],   # ASR 出的泰文原文 (一字不差)
}, timeout=180)
r.raise_for_status()

Path("outputs/shot01_zh.wav").write_bytes(r.content)
```

**本地路径版**（单机调试）：把上面的 `f"{OSS_BASE}/..."` URL 改成 `r"I:\videos\thai\shot01.mp4"` 之类本地路径即可，**字段名不变**，voxcpm 自动识别。

`prompt_text` 用 ASR 出的**原文**（不是翻译后的），跟 `prompt_wav_path` 一字不差，**终极克隆效果最佳**。

更多调用示例见 [API.md](API.md)。

## 性能参考

| 场景 | 4090 实测 |
|---|---|
| 模型加载（`--preload`） | 5-10s |
| 显存占用 | ~4 GB |
| `/tts` 短句（10 字） | <500 ms |
| `/clone_path` 10s 音频 | ~1s |
| 实时倍率 | ~10x |

## 常见问题

**Q: `ModuleNotFoundError: No module named 'voxcpm'`**

tor25 没装 voxcpm，回到[环境准备](#环境准备)那一步。

**Q: 启动卡在 `[init] loading VoxCPM2 ...`**

模型加载本来就要 5-10s。**没**看到 `ready` 之前发请求都会一起等。`--preload` 是把这个等待放到启动期，请求期就秒回。

**Q: `models/VoxCPM2` 找不到 / 模型加载报路径错**

下载脚本失败了。重跑 `download_model.bat`，或检查 `voxcpm/models/VoxCPM2/` 里到底有没有文件。也可以设环境变量 `VOXCPM_MODEL_DIR=<你的实际路径>` 覆盖。

**Q: 端口冲突（8190 被占）**

```powershell
D:\Anaconda3\envs\tor25\python.exe server.py --port 8191 --preload
```

**Q: 想换独立 .venv 跑（不用 tor25）**

在 `voxcpm\.venv` 里装齐 `torch`（cu124）+ `voxcpm`，然后：

```powershell
set "VOXCPM_PYTHON=I:\2026AILab\chorify2\chorify-video\voxcpm\.venv\Scripts\python.exe"
start_server.bat
```

两个 .bat 会读这个环境变量。

**Q: HuggingFace 下载 SSL DECRYPTION_FAILED**

代理 TLS 拦截。**不要用 `--hf`**，默认 ModelScope 国内直连不走代理。实在要用 HF 走 Motrix 离线下 [hf-mirror.com/openbmb/VoxCPM2](https://hf-mirror.com/openbmb/VoxCPM2/tree/main) 再塞到 `models/VoxCPM2/`。

## 相关链接

- 模型主页：[ModelScope OpenBMB/VoxCPM2](https://modelscope.cn/models/OpenBMB/VoxCPM2) ｜ [HF openbmb/VoxCPM2](https://huggingface.co/openbmb/VoxCPM2)
- 上游仓库：[github.com/OpenBMB/VoxCPM](https://github.com/OpenBMB/VoxCPM)
- chorify 主项目 ASR 服务：`../ailab/api/server.py`

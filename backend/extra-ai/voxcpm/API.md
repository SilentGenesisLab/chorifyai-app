# VoxCPM2 TTS API 文档

OpenBMB VoxCPM2 的 HTTP 接口文档。模型支持 **4 种合成模式**，全部通过同一套接口字段切换。返回均为 **`audio/wav` 二进制流**（采样率 **48000 Hz**，单声道 PCM 16-bit）。

> 已在 RTX 4090 + WinPython 3.12 + torch 2.8.0+cu128 + voxcpm 2.0.2 验证通过 (2026-05)。

---

## 0. 四种合成模式速查

| 模式 | 关键字段 | 用途 | 相对耗时 |
|---|---|---|---|
| **1. 基础 TTS** | `text` | 默认音色合成 | 1× |
| **2. Voice Design** | `text="(描述)正文"` | 文字描述造音色, 无需参考音 | 1× |
| **3. 普通克隆** | `+ reference_wav_path` | 复制参考音色 | 1.0–1.2× |
| **4. 终极克隆 (深度克隆)** | `+ prompt_wav_path + prompt_text` | 还原细微音色, 最高保真 | 1.2–1.5× |

> "深度克隆" 是 VoxCPM2 官方称呼的 "Ultimate Cloning" / "终极克隆", 三个词指同一种模式。

**参考音输入** (`reference_wav_path` / `prompt_wav_path`) 既支持**服务器本地路径**, 也支持**公网 URL** (`http://` / `https://`, 自动下载到临时文件; 见 §2.4)。

---

## 1. 两套等价入口

| 入口 | 前缀 | 说明 |
|---|---|---|
| **直连 VoxCPM2** | `http://127.0.0.1:8190/*` | `voxcpm/server.py`, 独立 GPU 进程 |
| **ailab 网关转发** | `http://127.0.0.1:8089/tts/voxcpm/*` | `ailab/api/server.py`, 跟 ASR/翻译同 base URL |

两者字段**完全一致**, 本文档以**直连**为准, 网关只是在前缀加 `/tts/voxcpm`。

| 直连 | 经网关 |
|---|---|
| `GET  :8190/health` | `GET  :8089/tts/voxcpm/health` |
| `POST :8190/tts` | `POST :8089/tts/voxcpm` |
| `POST :8190/clone` | `POST :8089/tts/voxcpm/clone` |
| `POST :8190/clone_path` | `POST :8089/tts/voxcpm/clone_path` |

直连返回原始 wav 二进制 / FastAPI 错误 JSON；
经网关返回相同 wav 二进制, 但**错误**会被包成标准 envelope `{code: -1, msg: "...", data: null}`。

---

## 2. 端点详细

### 2.1 `GET /health` — 健康检查

无 body。

**响应** (200):

```json
{
    "status": "ok",
    "cuda": true,
    "model_dir": "I:\\2026AILab\\chorify2\\chorify-video\\voxcpm\\models\\VoxCPM2",
    "loaded": true
}
```

| 字段 | 含义 |
|---|---|
| `cuda` | GPU 可用 |
| `loaded` | 模型已加载 (启动时 `--preload` 则一开始就 true) |

经网关时外层包标准 envelope:

```json
{"code": 0, "msg": "ok", "data": {"status": "ok", "cuda": true, "loaded": true, ...}}
```

---

### 2.2 `POST /tts` — 基础 TTS / Voice Design

**请求** `Content-Type: application/json`:

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `text` | string | ✅ | — | 待合成文本。开头加 `(描述)` 进入 Voice Design 模式 |
| `cfg_value` | float | ❌ | `2.0` | classifier-free guidance, 越大越遵从 text, 1.5–3.0 |
| `inference_timesteps` | int | ❌ | `10` | diffusion 步数, 越大越精细越慢, 8–15 |

**响应** (200):

- `Content-Type: audio/wav`
- body: wav 二进制 (PCM 16-bit, 48000 Hz, mono)
- 文件大小 ≈ `audio_seconds × 96000 + 44` 字节

**失败**:

```json
// 直连 (400)
{"detail": "text 不能为空"}

// 网关 (500 透传后端 4xx/5xx)
{"code": -1, "msg": "VoxCPM2 后端 400: text 不能为空", "data": null}
```

---

### 2.3 `POST /clone` — 上传参考音克隆 (multipart)

**适合一次性手动调试**。批量配音场景请用 `/clone_path` (不用上传)。

**请求** `Content-Type: multipart/form-data`:

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `text` | str | ✅ | 目标文本 |
| `reference` | file | ✅ | 参考音频 wav/mp3 (≥3s 效果更好) |
| `cfg_value` | float | ❌ | 默认 2.0 |
| `inference_timesteps` | int | ❌ | 默认 10 |
| `prompt_reference` | file | ❌ | **终极克隆**: 额外参考音 (官方推荐填同一份 reference) |
| `prompt_text` | str | ❌ | **终极克隆**: prompt_reference 的精确文本转写, 跟 prompt_reference 一一对应 |

**模式判断**:
- 只填 `reference` → 普通克隆
- 同时填 `prompt_reference + prompt_text` → 终极克隆 (最高保真)

**响应**: 同 `/tts`, 返回 audio/wav。

---

### 2.4 `POST /clone_path` — 本地路径克隆 (推荐, 批量场景)

跟 `/clone` 等价, 但用**服务器本地路径**做参考音, **不上传**, chorify 流水线推荐。

**请求** `Content-Type: application/json`:

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `text` | string | ✅ | — | 目标文本 |
| `reference_wav_path` | string | ⚠️ | — | **本地路径或 URL** (见下) |
| `prompt_wav_path` | string | ❌ | — | **终极克隆**: 本地路径或 URL |
| `prompt_text` | string | ❌ | — | **终极克隆**: prompt_wav_path 对应精确转写 |
| `cfg_value` | float | ❌ | `2.0` | |
| `inference_timesteps` | int | ❌ | `10` | |

**`*_wav_path` 字段接受两种形态**（字段名为兼容历史保留 `_wav_path`，**实际值不限于本地路径**）:

| 形态 | 例子 | 行为 |
|---|---|---|
| 服务器本地路径 | `"I:/refs/voice.wav"` | 直接用, `os.path.exists` 校验 |
| 公网 URL | `"https://oss-cn-hangzhou.aliyuncs.com/.../voice.mp3"` | 自动下载到临时文件, 推理完清理 |

**支持的 URL 格式**:
- `http://` / `https://` 前缀
- Content-Type 推断: wav / mp3 / m4a / aac / ogg / flac / mp4 都识别
- URL 后缀优先于 Content-Type (例 `?key=xx` 也能解析)
- 大小限制: 200 MB

**校验规则** (服务端):

- `reference_wav_path` 和 `prompt_wav_path` **至少传一个**
- 传 `prompt_wav_path` 必须配 `prompt_text` (非空)
- 本地路径必须存在 (`os.path.exists` 校验); URL 必须能下载到 (200 状态码)

**模式判断**:
- 只填 `reference_wav_path` → 普通克隆
- 同时填 `prompt_wav_path + prompt_text` → 终极克隆
  (官方推荐 `reference_wav_path` 也填同一份音频以最大化相似度)

**响应**: 同 `/tts`, 返回 audio/wav。

---

## 3. 四种合成模式详解

### 3.1 基础 TTS

最简单, 用 VoxCPM2 默认音色。

```jsonc
POST /tts
{
    "text": "你好,这是默认音色的合成测试。"
}
```

### 3.2 Voice Design — 文字描述造音色

`text` 开头加 `(描述)`, 模型根据描述即时合成全新音色。

```jsonc
POST /tts
{
    "text": "(一位温柔甜美的年轻女性)你好,我是即时生成的全新音色。"
}
```

更多描述示例:

```
(A young woman, gentle and sweet voice) ...
(slightly faster, cheerful tone) ...
(中年男性,低沉磁性,带轻微沙哑) ...
(深宫太后,威严而沉稳) ...
(暴躁教练,语速快,情绪强烈) ...
```

### 3.3 普通克隆 — 复制参考音色

上传/指定一段参考音频, 模型复制其音色, 用目标 `text` 重新发声。

**API**:
- `/clone` 字段 `reference` (file)
- `/clone_path` 字段 `reference_wav_path` (本地路径)

普通克隆**仍可在 `text` 里加 `(指令)`** 调速度/情感/风格 (官方支持的控制项):

```jsonc
{
    "text": "(语速略快, 情绪欢快) 大家好我是新的克隆音色",
    "reference_wav_path": "I:/refs/speaker_a.wav"
}
```

### 3.4 终极克隆 (Ultimate Cloning / 深度克隆) — 最高保真

**核心理念**: 同时提供参考音频 + 它的**精确文本转写**, 模型基于"音频延续 (audio continuation)"原理还原细微音色 (呼吸、气口、发音习惯等)。

**字段**:
- `prompt_wav_path` (或 `/clone` 的 `prompt_reference` 文件): **样本对前缀** — 参考音, 让模型按这段音频"续写"目标 `text`
- `prompt_text`: 跟 `prompt_wav_path` **一字不差**的转写; 跟 prompt 音频是"成对训练样本"语义
- `reference_wav_path` (推荐): **音色 embedding 锚定** — 提取参考音色特征供 generator 使用

**两个 `*_wav_path` 各自接受**:
- 服务器本地路径 (e.g. `"I:/refs/voice.wav"`)
- 公网 URL (e.g. `"https://oss-xxx.aliyuncs.com/refs/voice.mp3"`, 自动下载)

**两个字段是独立维度**, 可以填同一份音频 (官方推荐, 相似度最大化), 也可以填不同的音频 (高级玩法):

| 填法 | 效果 |
|---|---|
| `prompt = reference` **同一份** (推荐) | 模型对同一段声音做"样本对续写"+"音色锚定"双锚, 相似度 ~95% |
| `prompt = 干净录音` / `reference = 实际目标人声` | 用 prompt 学发音, 用 reference 学场景音色 (高阶, 效果不稳定) |
| 只填 `prompt_wav_path + prompt_text` (无 reference) | 省事版终极克隆, 相似度 ~90% |

**chorify 混剪场景**最佳实践:

```jsonc
{
    "text":               "<中文译文>",      // 翻译后的目标台词 (豆包译出)
    "reference_wav_path": "<原片人声 URL>",  // 跟 prompt 同一份 (路径或 OSS URL 都行)
    "prompt_wav_path":    "<原片人声 URL>",  // ASR 抽出的原片人声
    "prompt_text":        "<ASR 出的原文>"   // 跟原片人声一字不差 (ASR 的 source_text)
}
```

**为什么 `prompt_text` 不能写中文译文**: 终极克隆模式要求 `prompt_text` ↔ `prompt_wav_path` 是**严格对齐**关系 (模型把它们当作训练数据中的成对样本), 译文跟原音频内容对不上 → 还原效果反而变差。

**实测**: 在泰国-中文混剪场景, 终极克隆相似度 ≈ 95%, 普通克隆 ≈ 80%, 听感差异明显。

---

## 4. 调用示例

### 4.1 curl (Linux / WSL / git-bash)

**基础 TTS / Voice Design**:

```bash
curl -X POST http://127.0.0.1:8190/tts \
  -H "Content-Type: application/json" \
  -d '{"text": "(温柔甜美的年轻女性)你好"}' \
  -o demo.wav
```

**普通克隆 (multipart 上传)**:

```bash
curl -X POST http://127.0.0.1:8190/clone \
  -F "text=克隆出来的中文语音" \
  -F "reference=@refs/speaker_a.wav" \
  -o clone.wav
```

**终极克隆 (multipart)**:

```bash
curl -X POST http://127.0.0.1:8190/clone \
  -F "text=终极克隆出来的中文" \
  -F "reference=@refs/speaker_a.wav" \
  -F "prompt_reference=@refs/speaker_a.wav" \
  -F "prompt_text=speaker_a.wav 里说的那句话一字不差的转写" \
  -o hifi.wav
```

**本地路径克隆 (JSON, 推荐批量)**:

```bash
curl -X POST http://127.0.0.1:8190/clone_path \
  -H "Content-Type: application/json" \
  -d '{
    "text": "目标文本",
    "reference_wav_path": "I:/path/to/voice.wav",
    "prompt_wav_path":    "I:/path/to/voice.wav",
    "prompt_text":        "voice.wav 对应的精确转写"
  }' \
  -o ultimate.wav
```

### 4.2 PowerShell (Windows)

中文 UTF-8 body 在 PowerShell 5 必须**先写文件再用 `--data-binary`**, 直接 `-d` 会被 cmd shell 转码破坏:

```powershell
$body = @{
    text = "你好,这是 VoxCPM2 中文测试"
    cfg_value = 2.0
    inference_timesteps = 10
} | ConvertTo-Json
$body | Out-File -Encoding utf8 -NoNewline "$env:TEMP\req.json"

curl.exe -X POST http://127.0.0.1:8190/tts `
  -H "Content-Type: application/json; charset=utf-8" `
  --data-binary "@$env:TEMP\req.json" `
  -o "$env:TEMP\out.wav"

Start-Process "$env:TEMP\out.wav"   # 播放
```

### 4.3 Python (requests)

**普通克隆**:

```python
import requests

r = requests.post(
    "http://127.0.0.1:8190/clone_path",
    json={
        "text": "克隆这段中文",
        "reference_wav_path": r"I:\refs\speaker_a.wav",
    },
    timeout=60,
)
r.raise_for_status()
open("clone.wav", "wb").write(r.content)
```

**终极克隆**:

```python
import requests

ref = r"I:\refs\speaker_a.wav"
r = requests.post(
    "http://127.0.0.1:8190/clone_path",
    json={
        "text":               "终极克隆出来的中文目标台词",
        "reference_wav_path": ref,   # 官方推荐: prompt 和 reference 同一份
        "prompt_wav_path":    ref,
        "prompt_text":        "ref 里说的那句话的精确转写一字不差",
        "cfg_value": 2.0,
        "inference_timesteps": 10,
    },
    timeout=120,
)
r.raise_for_status()
open("ultimate.wav", "wb").write(r.content)
```

**经 ailab 网关** (推荐生产用):

```python
import requests

AILAB = "http://127.0.0.1:8089"
r = requests.post(
    f"{AILAB}/tts/voxcpm/clone_path",
    json={"text": "...", "reference_wav_path": "...", ...},
    timeout=120,
)
r.raise_for_status()
# 检查是不是直接 wav (HTTP 200) 还是错误 JSON envelope
if r.headers.get("content-type", "").startswith("audio/wav"):
    open("out.wav", "wb").write(r.content)
else:
    print("错误:", r.json())
```

**参考音从 OSS / 远程 URL 拉** (chorify 场景常用; 服务端自动下载, 不用先拷到本地):

```python
import requests

# OSS 上的参考音
REF_URL = "https://chorify-video.oss-cn-hangzhou.aliyuncs.com/refs/speaker_a.mp3"

r = requests.post("http://127.0.0.1:8190/clone_path", json={
    "text":               "克隆这段中文,参考音从 OSS 自动下载",
    "reference_wav_path": REF_URL,    # 直接传 URL
    "prompt_wav_path":    REF_URL,    # 终极克隆同一份
    "prompt_text":        "OSS 那段音频里说的原文一字不差",
}, timeout=180)
r.raise_for_status()
open("out.wav", "wb").write(r.content)
```

URL 拉取在服务端完成 (避免大文件经客户端中转), 推理结束自动清理临时文件。

---

## 5. 端到端: chorify 混剪流水线

ASR + 翻译 + 终极克隆配音一条龙 (实战用例)。参考音支持**本地路径或 OSS URL**, 这里以 OSS URL 版为例 (生产场景更常用):

```python
import requests
from pathlib import Path

AILAB    = "http://127.0.0.1:8089"
OSS_BASE = "https://chorify-video.oss-cn-hangzhou.aliyuncs.com"


def make_dub(video_url: str, ref_voice_url: str, output_wav: str):
    """视频 URL -> ASR + 翻译 -> 用原片人声 URL 做参考终极克隆 -> 中文配音 wav。"""

    # 1) ASR + 豆包翻译 (ailab 内部从 OSS 拉视频)
    r = requests.post(f"{AILAB}/asr/translate", json={
        "url":    video_url,            # OSS URL, 服务端拉
        "source": "thai",
        "target": "zh",
    }, timeout=300)
    r.raise_for_status()
    data = r.json()["data"]
    src_text = data["source_text"]    # ASR 出的泰文原文 -> prompt_text
    tgt_text = data["target_text"]    # 豆包译出的中文 -> text
    print(f"原文: {src_text}")
    print(f"译文: {tgt_text}")

    # 2) 终极克隆: 用原片人声 URL + 原文做 prompt, 还原音色 + 说出中文译文
    r = requests.post(f"{AILAB}/tts/voxcpm/clone_path", json={
        "text":               tgt_text,
        "reference_wav_path": ref_voice_url,   # OSS URL, voxcpm 服务端自动下载
        "prompt_wav_path":    ref_voice_url,   # 同一份 (官方推荐)
        "prompt_text":        src_text,
    }, timeout=180)
    r.raise_for_status()
    Path(output_wav).write_bytes(r.content)
    print(f"配音完成: {output_wav}")


if __name__ == "__main__":
    make_dub(
        video_url     = f"{OSS_BASE}/raw/shot01.mp4",
        ref_voice_url = f"{OSS_BASE}/refs/shot01_voice.mp3",  # 预抽好的原片人声
        output_wav    = "shot01_zh.wav",
    )
```

**关键设计**:
- `prompt_text = src_text` (ASR 出的**原文**, 不是译文): 跟 prompt_wav_path 一字不差
- `text = tgt_text` (翻译后的**中文**): 模型读这个但用 prompt 音色
- `reference_wav_path = prompt_wav_path` (同一份): 官方推荐, 进一步提升相似度
- **全程 URL**: 客户端只传 JSON 字段, 大文件 (视频几十 MB / 人声几 MB) 都由服务端从 OSS 拉, 客户端流量极低

**本地路径版本** (单机调试):

```python
make_dub(
    video_url     = r"I:\videos\thai\shot01.mp4",            # 改成本地路径
    ref_voice_url = r"I:\videos\thai\shot01_voice.wav",
    output_wav    = "shot01_zh.wav",
)
```
> ailab 的 `/asr/translate` 字段名是 `url` 或 `path` 二选一 (见 ailab API 文档); voxcpm 这边 `*_wav_path` **同一个字段**自动识别路径或 URL, 不用切字段名。

---

## 6. 性能参考 (RTX 4090 + WinPython torch 2.8.0+cu128 实测)

| 操作 | 耗时 |
|---|---|
| 模型加载 (`--preload`) | 5–10 s |
| 显存占用 | ~4 GB |
| Warmup (10 步 diffusion) | ~2 s (~4.8 it/s) |
| `/tts` 短句 (10–20 字, 5s 音频) | **8–10 s** (RTF ~2.0) |
| `/tts` warm (后续相同长度) | **3–4 s** |
| `/clone_path` 普通克隆 (5s 音频) | ~9 s |
| `/clone_path` 终极克隆 (5s 音频) | ~10 s |
| 经 ailab 网关额外开销 | < 50 ms |

> 当前 WinPython 包**没装 triton**, voxcpm 内部自动关 `torch.compile` 走 eager 模式。装上 `triton-windows>=3.4` 后可恢复 `torch.compile` 加速, RTF 降到 ~0.3-0.5 (10s 文本 3-5s 出)。

---

## 7. 错误码

### 直连 (`:8190`)

FastAPI 默认错误格式:

```json
{"detail": "<错误信息>"}
```

| HTTP | 触发条件 |
|---|---|
| **400** | `text` 为空; `prompt_wav_path` 没配 `prompt_text`; `/clone_path` 既无 reference 也无 prompt |
| **404** | `reference_wav_path` / `prompt_wav_path` **本地文件不存在** (值不是 URL 时) |
| **413** | URL 下载内容 **超过 200 MB** (大小限制保护) |
| **422** | pydantic 字段类型错 (例: `cfg_value` 传了字符串; `/clone` 给 `reference` 塞字符串而非 file) |
| **500** | 推理异常 (OOM, CUDA error, 模型未加载) — 服务端会把 `detail + traceback` 写进 JSON body 方便排错 |
| **502** | URL 下载失败 (DNS 解析不到, 远端 4xx/5xx, 网络断, 超时) — `detail` 含完整错误链 |

### 经网关 (`:8089/tts/voxcpm/*`)

ailab 标准化错误信封:

```json
{"code": -1, "msg": "<错误信息>", "data": null}
```

| HTTP | 含义 |
|---|---|
| **502** | VoxCPM2 后端不可达 (服务挂了, 端口不通, supervisor 没启起来) |
| **其它** | 透传 VoxCPM2 后端状态码, msg 字段含上游 detail |

---

## 8. 启动 / 部署

### 8.1 本地开发 (supervisor)

```powershell
cd I:\2026AILab\chorify2\chorify-video
D:\Anaconda3\envs\tor25\python.exe main.py
```

启动后看到:

```
[supervisor] Job Object: 已创建 (父死必然带子死)
[supervisor] [preflight] 端口 8089 可用
[supervisor] [preflight] 端口 8190 可用
[ailab:sup] 启动: ...uvicorn ailab.api.server:app --host 0.0.0.0 --port 8089
[voxcpm:sup] 启动: ...WPy64-312101\python\python.exe server.py ...
...
[voxcpm] [init] ready, sample_rate=48000Hz, cuda=True
[voxcpm:sup] /health OK (60s 内就绪)
[ailab:sup] /health OK (60s 内就绪)
```

main.py 自动:
- **检测仓库内的 WinPython** (torch 2.8 + voxcpm 2.0.2) 作为 voxcpm 解释器 (兼容上没有 torch 2.5.1 的 CUDA 段错误问题)
- **Windows Job Object**: 父进程死亡时 kernel 强杀所有子进程, 不会留孤儿
- **端口预检** + 占用诊断

### 8.2 单跑 voxcpm (调试)

```powershell
cd voxcpm
D:\Anaconda3\envs\tor25\python.exe ..\main.py --only voxcpm
# 或直接用 WinPython 跑 server.py:
I:\2026AILab\chorify2\chorify-video\ailab2026\VoxCPM2\WPy64-312101\python\python.exe server.py --host 0.0.0.0 --port 8190 --preload
```

### 8.3 生产部署 (docker-compose)

见 [deploy/README.md](../deploy/README.md)。Linux + nvidia-container-toolkit, voxcpm 走独立容器 (`deploy/docker/voxcpm.Dockerfile`), GPU passthrough。

---

## 9. 常见问题

**Q: `/tts` 返回 500 + `BackendCompilerFailed`**

torch 版本不对 (2.5.x Windows inductor cache bug)。当前已用 WinPython torch 2.8.0+cu128 + monkey-patch 解决。如果你强行用 tor25 (torch 2.5.1) 跑 voxcpm 会段错误 (rc=3221225477), 必须用 WinPython。

**Q: `/health` 直连通但网关 502**

ailab 服务没起来。`netstat -ano | findstr :8089` 看端口是否 LISTENING。如果空, supervisor 没拉起来 ailab — 看 main.py 日志。

**Q: `/clone_path` 返回 404 "音频文件不存在"**

值被识别为**本地路径**但服务端找不到。两种修法:
1. 用 URL: 改成 `http(s)://...` 让服务端自动下载
2. 用本地路径: 确认路径在 **voxcpm 服务进程**所在机器上真实存在 (不是客户端的机器)

**Q: `/clone_path` 返回 502 "下载 ... 失败"**

值被识别为 URL 但下载失败. detail 里会写具体原因:
- `HTTP Error 404` → URL 对应的对象不存在 / 路径拼错
- `HTTP Error 403` → OSS / CDN 鉴权失败, 检查签名或公开权限
- `Bad Gateway` → DNS 解析失败, host 拼错 / 内网无法访问该域名
- `timed out` → 远端响应慢 (默认 60s 超时), 检查网络

**Q: `/clone_path` 返回 413 "音频过大"**

URL 内容超过 200 MB 大小限制. 检查是不是 URL 指向了**视频**而不是参考音 (chorify 场景容易拿错 URL). 如果确实要传大音频, 改 `voxcpm/server.py` 里 `_download_to_temp(max_bytes=...)` 上限。

**Q: 既要 URL 又要文件上传, 怎么选?**

| 场景 | 推荐 |
|---|---|
| 客户端只有 OSS URL 或公网链接 | `POST /clone_path` JSON, 字段填 URL |
| 客户端本地有 wav, 服务端不能访问 | `POST /clone` multipart 上传文件 |
| 服务端能直接访问的本地路径 (单机 / 共享盘) | `POST /clone_path` JSON, 字段填本地路径 |
| 批量配音 (chorify 流水线) | **`/clone_path` + OSS URL**, 客户端零流量, 服务端拉取 |

**Q: 终极克隆相似度还是不高**

检查:
- `prompt_text` 跟 `prompt_wav_path` 是不是**真的一字不差** (常见: ASR 转写漏掉了语气词)
- 参考音 ≥ 3s 且**只有一个说话人**
- 参考音是干净的 (无 BGM / 无噪声 / 无回声)
- `reference_wav_path` 也填同一份 prompt_wav_path
- 如果上述都满足, 试着把 `cfg_value` 从 2.0 降到 1.5 或升到 2.5

**Q: 怎么试听返回的 wav?**

PowerShell:
```powershell
Start-Process "$env:TEMP\out.wav"     # 系统默认播放器
explorer.exe $env:TEMP                # 文件管理器双击
```

---

## 10. 相关链接

- **上游模型**: [github.com/OpenBMB/VoxCPM](https://github.com/OpenBMB/VoxCPM)
- **官方最佳实践**: [voxcpm.readthedocs.io](https://voxcpm.readthedocs.io/zh-cn/latest/cookbook.html)
- **本地服务实现**: [voxcpm/server.py](./server.py)
- **ailab 网关转发**: [ailab/api/server.py](../ailab/api/server.py) 的 `/tts/voxcpm/*` 路由
- **生产部署**: [deploy/README.md](../deploy/README.md)
- **supervisor 启动**: [main.py](../main.py)

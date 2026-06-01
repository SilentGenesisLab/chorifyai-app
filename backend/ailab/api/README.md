# ailab HTTP 服务 (FastAPI)

基于 OpenAI Whisper-large-v3 + 豆包翻译 + ElevenLabs，提供视频/音频转写、翻译、TTS 配音、AI 音乐生成的 HTTP 接口。

## 启动

```powershell
# 必须用 cuda23 环境（whisper/modelscope/torch 等都装在这里）
D:\Anaconda3\envs\cuda23\python.exe -m ailab.api.server --host 0.0.0.0 --port 8089

# 仅本机访问
D:\Anaconda3\envs\cuda23\python.exe -m ailab.api.server --host 127.0.0.1 --port 8089

# 或直接 uvicorn
D:\Anaconda3\envs\cuda23\python.exe -m uvicorn ailab.api.server:app --host 0.0.0.0 --port 8089
```

首次请求时加载 Whisper-large-v3 模型 (~3GB)，约 30-60 秒；模型权重直接复用 FunASR 缓存里的 `large-v3.pt`，无需重新下载。后续请求复用内存中的模型。

**Swagger UI**: 启动后访问 http://127.0.0.1:8089/docs 可视化调试。

## 公共响应格式

```json
{
  "code": 0,
  "msg": "ok",
  "data": { ... }
}
```

失败:
```json
{
  "code": -1,
  "msg": "错误信息",
  "data": null
}
```

---

## 1. `GET /health` 心跳

```bash
curl http://127.0.0.1:8089/health
```

返回:
```json
{"code": 0, "msg": "ok", "data": {"service": "asr", "status": "up"}}
```

---

## 2. `POST /asr/audio` 识别音频

**body**:
| 字段 | 必填 | 说明 |
|---|---|---|
| `url` 或 `path` | 二选一 | 公网音频 URL / 服务器本地路径 |
| `language` | 否 | `thai` / `zh` / `en`，留空自动检测 |
| `engine` | 否 | `openai` (默认, 带时间戳) 或 `funasr` |
| `with_timestamps` | 否 | 默认 `true` (仅 openai 引擎) |

**curl**:
```bash
curl -X POST http://127.0.0.1:8089/asr/audio \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://oss-imgai.sligenai.cn/chorify-video/audio/abc.wav",
    "language": "thai"
  }'
```

返回:
```json
{
  "code": 0,
  "msg": "ok",
  "data": {
    "text": "ในตอนออกเดท คุณไม่จำเป็นต้องพกอะไรไปเลย ...",
    "segments": [
      {"start": 0.0, "end": 2.3, "text": "ในตอนออกเดท ..."}
    ]
  }
}
```

---

## 3. `POST /asr/video` 识别视频

会自动下载视频 → ffmpeg 抽 16k 单声道 WAV → 喂给 Whisper。

**body**: 同 `/asr/audio`，但 `url`/`path` 是视频文件。

**curl**:
```bash
curl -X POST http://127.0.0.1:8089/asr/video \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://oss-imgai.sligenai.cn/chorify-video/video/abc.mp4",
    "language": "thai"
  }'
```

返回结构同 `/asr/audio`。

---

## 4. `POST /asr/extract` 抽音频上传 OSS

视频 → ffmpeg 抽 16k 单声道 WAV → 上 OSS → 返回公网 URL。

**body**:
| 字段 | 必填 | 说明 |
|---|---|---|
| `url` 或 `path` | 二选一 | 视频地址 |
| `prefix` | 否 | OSS key 前缀，默认 `chorify-video/audio` |

**curl**:
```bash
curl -X POST http://127.0.0.1:8089/asr/extract \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://oss-imgai.sligenai.cn/chorify-video/video/clip.mp4"
  }'
```

返回:
```json
{
  "code": 0,
  "msg": "ok",
  "data": {
    "audio_url": "https://oss-imgai.sligenai.cn/chorify-video/audio/<md5>.wav"
  }
}
```

---

## 5. `POST /asr/translate` 一站式: 视频 → ASR → 翻译

视频 → 抽音 → Whisper 转写 (泰语等) → 豆包翻译成中文。

**body**:
| 字段 | 必填 | 说明 |
|---|---|---|
| `url` 或 `path` | 二选一 | 视频地址 |
| `source` | 否 | 原语种，默认 `thai` |
| `target` | 否 | 目标语种，默认 `zh` |

**curl**:
```bash
curl -X POST http://127.0.0.1:8089/asr/translate \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://oss-imgai.sligenai.cn/chorify-video/video/thai_ad.mp4",
    "source": "thai",
    "target": "zh"
  }'
```

返回:
```json
{
  "code": 0,
  "msg": "ok",
  "data": {
    "source_text": "ในตอนออกเดท ...",
    "target_text": "约会的时候啥都不用带，带它就够了！...",
    "source_language": "thai",
    "target_language": "zh",
    "segments": [
      {"start": 0.0, "end": 2.3, "text": "..."}
    ]
  }
}
```

---

## 6. `POST /tts/speech` 文本转语音 (ElevenLabs)

把文本通过 ElevenLabs 合成为 mp3 音频，自动上传到 OSS，返回公网 URL。适合短视频配音 / AI 主播台词 / 通知音播报。

**body**:
| 字段 | 必填 | 默认值 | 说明 |
|---|---|---|---|
| `text` | 是 | — | 要合成的文本，1-5000 字 |
| `voice_id` | 否 | `EST9Ui6982FZPSi7gCHi` | ElevenLabs voice id |
| `model_id` | 否 | `eleven_multilingual_v2` | TTS 模型，支持中/泰/英等 29 种语言 |
| `stability` | 否 | `0.5` | 0-1，越高越平稳；越低越富有情感波动 |
| `similarity_boost` | 否 | `0.75` | 0-1，越高越贴近参考音色 |
| `style` | 否 | `0.0` | 0-1，v2 模型情感强度 |
| `use_speaker_boost` | 否 | `true` | 增强音色辨识度 |
| `output_format` | 否 | `mp3_44100_128` | `mp3_44100_128` / `mp3_44100_64` / `mp3_22050_32` / `pcm_16000` / `pcm_22050` / `pcm_44100` |
| `upload` | 否 | `true` | 是否上传 OSS。`false` 时只在服务器本地落临时文件 |

**切换音色**:
默认 `voice_id` 是 `EST9Ui6982FZPSi7gCHi`。要换音色，让最终用户去 [ElevenLabs Developers 控制台](https://elevenlabs.io/app/developers) 复制目标音色的 voice id 后再调接口即可——无需改服务端配置。

**curl**:
```bash
curl --location --request POST 'http://localhost:8089/tts/speech' \
  --header 'Content-Type: application/json' \
  --data-raw '{
    "text": "Night Hawk professional high-definition night vision scope delivers clear vision in dim light. Equipped with premium optical lenses, it offers wide field of view and smooth, noise-free imaging.",
    "voice_id": "EST9Ui6982FZPSi7gCHi",
    "model_id": "eleven_multilingual_v2",
    "stability": 0.5,
    "similarity_boost": 0.75,
    "style": 0.3,
    "use_speaker_boost": true,
    "output_format": "mp3_44100_128",
    "upload": true
  }'
```

最小调用（仅传必填字段，其它走默认值）:
```bash
curl -X POST http://localhost:8089/tts/speech \
  -H "Content-Type: application/json" \
  -d '{"text":"大家好，欢迎来到 Chorify"}'
```

**返回**:
```json
{
  "code": 0,
  "msg": "ok",
  "data": {
    "audio_url": "https://oss-imgai.sligenai.cn/chorify-video/tts/<md5>.mp3",
    "local_path": null,
    "voice_id": "EST9Ui6982FZPSi7gCHi",
    "model_id": "eleven_multilingual_v2",
    "bytes": 86432,
    "cost_ms": 2150,
    "output_format": "mp3_44100_128"
  }
}
```

- `audio_url`: 上传成功时返回 OSS 公网 URL，浏览器直接打开即可播放
- `local_path`: 仅在 `upload=false` 或 OSS 上传失败时返回（兜底用，方便人工取走文件）
- `cost_ms`: ElevenLabs 接口往返耗时，不含 OSS 上传时间

---

## 7. `POST /tts/music` 文本生成音乐 (ElevenLabs)

把文本提示词通过 ElevenLabs Music 生成背景音乐，自动上 OSS。适合短视频 BGM / 开场片头 / 转场音乐（不想买版权曲库时）。

**body**:
| 字段 | 必填 | 默认值 | 说明 |
|---|---|---|---|
| `prompt` | 是 | — | 音乐描述，**英文效果更佳** |
| `music_length_ms` | 否 | `30000` | 时长毫秒，10000-300000（即 10-300 秒） |
| `model_id` | 否 | `music_v1` | 音乐模型 |
| `output_format` | 否 | `mp3_44100_128` | `mp3_44100_128` / `mp3_44100_64` |
| `upload` | 否 | `true` | 是否上传 OSS |

**curl**:
```bash
curl --location --request POST 'http://localhost:8089/tts/music' \
  --header 'Content-Type: application/json' \
  --data-raw '{
    "prompt": "upbeat lofi hip hop with rain ambience, chill, no vocals",
    "music_length_ms": 30000,
    "model_id": "music_v1",
    "output_format": "mp3_44100_128",
    "upload": true
  }'
```

**prompt 写作建议**:
- 用英文：训练数据以英文为主，中文 prompt 效果差很多
- 写风格 + 情绪 + 乐器：`"upbeat electronic dance music with synth lead"`、`"calm piano with strings, sad mood"`
- 加 `"no vocals"` / `"instrumental"` 避免出现人声
- 加节奏：`"120 BPM"` / `"slow tempo"`

**返回**:
```json
{
  "code": 0,
  "msg": "ok",
  "data": {
    "audio_url": "https://oss-imgai.sligenai.cn/chorify-video/music/<md5>.mp3",
    "local_path": null,
    "music_length_ms": 30000,
    "model_id": "music_v1",
    "bytes": 491520,
    "cost_ms": 18230,
    "output_format": "mp3_44100_128"
  }
}
```

**耗时参考**: 30 秒音乐约 15-25 秒生成，时长越长越慢。

---

## 8. `GET /tts/voices` 列出账户可用音色

透传 ElevenLabs `GET /v1/voices`，返回原始 JSON。用于前端做音色选择下拉框，或开发时查 voice_id。

**curl**:
```bash
curl http://localhost:8089/tts/voices
```

**返回结构**（节选）:
```json
{
  "code": 0,
  "msg": "ok",
  "data": {
    "voices": [
      {
        "voice_id": "EST9Ui6982FZPSi7gCHi",
        "name": "...",
        "category": "premade",
        "labels": {"accent": "...", "gender": "..."},
        "preview_url": "https://storage.googleapis.com/eleven-public-prod/..."
      }
    ]
  }
}
```

**实际场景下推荐流程**: 不要直接调这个接口给用户挑——音色太多且需要试听。让用户去 [ElevenLabs Developers 控制台](https://elevenlabs.io/app/developers) 自己挑、试听、复制 voice_id，然后调 `/tts/speech` 时传进来即可。

---

## 本地 path 调用 (服务器同机器才能用)

如果客户端和服务器在同一台 Windows 主机，可以直接传本地 path 省去上传:

```bash
curl -X POST http://127.0.0.1:8089/asr/translate \
  -H "Content-Type: application/json" \
  -d "{
    \"path\": \"K:/商业订单/AI混剪素材/需替换视频/2026-05-11 18_27/260411+NE发热凝胶A+靖文+烊坤+拼T+不知道+泰国-1.mp4\",
    \"source\": \"thai\"
  }"
```

**注意 Windows 路径**:
- JSON 里反斜杠 `\` 要写成 `\\` 或者直接用正斜杠 `/`
- PowerShell 单引号字符串里可以原样写 Windows 路径，curl.exe 转发 OK

---

## 性能参考

- ASR 推理: 100 秒视频约 12-15 秒 (RTF ≈ 0.15, GPU)
- 翻译: 平均 1-3 秒/段
- 视频下载: 取决于网络 (OSS 内网快)
- 模型加载: 仅首次启动需要，30-60 秒
- TTS: 短句 (50 字以内) 1-2 秒，长文 (500 字) 5-10 秒
- 音乐生成: 30 秒成品约 15-25 秒，60 秒约 30-50 秒（云端调用 ElevenLabs，GPU 不影响）

## ElevenLabs 配置

`.env` 里相关变量：

```
ELEVENLABS_API_KEY=sk_xxx                              # 必填
ELEVENLABS_TTS_MODEL=eleven_multilingual_v2            # 可选，默认即此
ELEVENLABS_MUSIC_MODEL=music_v1                        # 可选
ELEVENLABS_DEFAULT_VOICE=EST9Ui6982FZPSi7gCHi          # 默认 voice_id
```

切换全局默认音色：改 `ELEVENLABS_DEFAULT_VOICE`。
**单次切换音色**：调用 `/tts/speech` 时传 `voice_id` 字段即可——不用改服务端。
**怎么找 voice_id**：让用户去 https://elevenlabs.io/app/developers ，挑好音色后复制 voice id，发给后端用作请求参数。

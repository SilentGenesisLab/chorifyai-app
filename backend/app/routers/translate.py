"""视频翻译 — ASR → 翻译 → TTS(深度克隆 VoxCPM) → 变速对齐 → ffmpeg 合成。

流程（异步 job + 轮询，同 split/mix）：
1. 下载已上传到 OSS 的视频
2. ffmpeg 抽取音轨 → wav，上传 OSS（ASR 需公网 URL）
3. 豆包 ASR（bigmodel flash）识别，取 utterances 逐句时间轴；无 utterances 则整段兜底
4. 取最长一句作为克隆参考音（深度克隆 prompt），逐句翻译为目标语言（火山方舟豆包）
5. 逐句用 VoxCPM 深度克隆合成译文配音
6. 关键：合成音时长 T 与原句时长 D 不一致时 → atempo 变速到一致（夹在可懂区间），
   再裁/补到恰好 D，保证落点精确、不串句
7. 按各句起点 adelay 落到全长静音轨上 amix 成配音轨
8. 与原视频音轨叠加（原声压低保留 BGM/环境声）或替换 → mux 回视频
9. 可选：生成新字幕（译文 SRT）烧录
"""
import json
import os
import shutil
import subprocess
import tempfile
import threading
import uuid
from datetime import datetime, timezone

import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.config import settings
from app.services import ark, voxcpm
from app.services.oss import put_object

router = APIRouter(prefix="/api/translate", tags=["translate"])

_HAS_FFMPEG = shutil.which("ffmpeg") is not None
_HAS_FFPROBE = shutil.which("ffprobe") is not None

# 直连字节/火山，忽略本机代理（与 voice/ark 同策略）
_session = requests.Session()
_session.trust_env = False

# 单句配音的变速可懂区间：超出则夹住（再裁/补到精确时长，保证落点）
_TEMPO_MIN, _TEMPO_MAX = 0.6, 2.0
_MAX_SEGMENTS = 60  # 句数上限（约束 6min 视频的克隆耗时）
_REF_MAX_SEC = 12.0  # 参考音最长截取秒数

# job_id -> {status, stage, progress:{done,total}, url?, sourceText?, targetText?, error?}
_JOBS: dict[str, dict] = {}


class TranslateRequest(BaseModel):
    url: str  # 已上传到 OSS 的视频 URL
    source: str = "auto"  # 源语言 code（auto=自动识别）
    target: str = "en"  # 目标语言 code
    keep_bgm: bool = True  # 译文配音叠加在压低的原声上（保留 BGM/环境声）
    generate_subtitles: bool = False  # 烧录译文字幕
    erase_subtitles: bool = False  # 擦除原硬字幕（v1 暂未实现，占位）
    lip_sync: bool = False  # 对口型（v1 暂未实现，占位）


# ----------------------------------------------------------------------------
# 基础 helper
# ----------------------------------------------------------------------------
def _download(url: str, suffix_default: str = ".mp4") -> str:
    suffix = os.path.splitext(url.split("?")[0])[1] or suffix_default
    fd, path = tempfile.mkstemp(suffix=suffix)
    try:
        with requests.get(url, stream=True, timeout=180) as r:
            r.raise_for_status()
            with os.fdopen(fd, "wb") as f:
                for chunk in r.iter_content(1 << 16):
                    if chunk:
                        f.write(chunk)
        return path
    except Exception as e:  # noqa: BLE001
        try:
            os.remove(path)
        except OSError:
            pass
        raise HTTPException(status_code=400, detail=f"下载视频失败：{e}")


def _ffmpeg(args: list[str], timeout: int = 600) -> tuple[bool, str]:
    try:
        p = subprocess.run(
            ["ffmpeg", "-y", *args], capture_output=True, text=True, timeout=timeout
        )
        if p.returncode == 0:
            return True, ""
        return False, (p.stderr or "")[-500:].strip()
    except subprocess.TimeoutExpired:
        return False, "ffmpeg 处理超时"
    except Exception as e:  # noqa: BLE001
        return False, str(e)


def _ffprobe_duration(path: str) -> float:
    if not _HAS_FFPROBE:
        return 0.0
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", path],
            capture_output=True, text=True, timeout=30,
        ).stdout.strip()
        return float(out) if out else 0.0
    except Exception:  # noqa: BLE001
        return 0.0


def _has_audio(path: str) -> bool:
    if not _HAS_FFPROBE:
        return True
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a",
             "-show_entries", "stream=index", "-of", "csv=p=0", path],
            capture_output=True, text=True, timeout=30,
        ).stdout
        return bool(out.strip())
    except Exception:  # noqa: BLE001
        return True


def _put_audio(audio: bytes, fmt: str, prefix: str) -> str:
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    key = f"{prefix}/{day}/{uuid.uuid4().hex}.{fmt}"
    ct = "audio/mpeg" if fmt == "mp3" else f"audio/{fmt}"
    return put_object(key, audio, ct)


# ----------------------------------------------------------------------------
# 豆包 ASR（bigmodel flash）—— 取 utterances 逐句时间轴
# ----------------------------------------------------------------------------
def _asr_segments(audio_url: str) -> tuple[list[dict], str, float]:
    """返回 (segments[{start,end,text}] 单位秒, 全文, 时长秒)。"""
    headers = {
        "X-Api-Key": settings.doubao_asr_api_key,
        "X-Api-Resource-Id": settings.doubao_asr_resource_id,
        "X-Api-Sequence": "-1",
        "X-Api-Request-Id": str(uuid.uuid4()),
        "Content-Type": "application/json",
    }
    body = {
        "user": {"uid": "chorify"},
        "audio": {"url": audio_url},
        "request": {"model_name": "bigmodel", "enable_itn": True, "show_utterances": True},
    }
    try:
        r = _session.post(settings.doubao_asr_url, headers=headers, json=body, timeout=120)
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"ASR 请求失败: {e}")
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"ASR 失败 HTTP {r.status_code}: {r.text[:200]}")

    data = r.json()
    result = data.get("result") or {}
    full_text = (result.get("text") or "").strip()
    duration = float((data.get("audio_info") or {}).get("duration") or 0) / 1000.0

    segs: list[dict] = []
    for u in result.get("utterances") or []:
        text = (u.get("text") or "").strip()
        start = float(u.get("start_time") or 0) / 1000.0  # ms → s
        end = float(u.get("end_time") or 0) / 1000.0
        if text and end - start >= 0.25:
            segs.append({"start": round(start, 3), "end": round(end, 3), "text": text})

    # 无逐句时间轴：整段兜底
    if not segs and full_text:
        dur = duration or _REF_MAX_SEC
        segs = [{"start": 0.0, "end": round(dur, 3), "text": full_text}]
    return segs, full_text, duration


def _atempo_chain(speed: float) -> str:
    """atempo 单滤镜仅支持 0.5–2.0，超出则级联。speed>1 加速变短，<1 减速变长。"""
    speed = max(0.25, min(speed, 4.0))
    parts: list[float] = []
    f = speed
    while f > 2.0:
        parts.append(2.0)
        f /= 2.0
    while f < 0.5:
        parts.append(0.5)
        f /= 0.5
    parts.append(f)
    return ",".join(f"atempo={p:.5f}" for p in parts)


# ----------------------------------------------------------------------------
# 主流程
# ----------------------------------------------------------------------------
def _set(job_id: str, **kw) -> None:
    job = _JOBS.get(job_id) or {}
    job.update(kw)
    _JOBS[job_id] = job


def _build_srt(items: list[dict]) -> str:
    def ts(sec: float) -> str:
        sec = max(0.0, sec)
        h = int(sec // 3600)
        m = int((sec % 3600) // 60)
        s = int(sec % 60)
        ms = int(round((sec - int(sec)) * 1000))
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    lines = []
    for i, it in enumerate(items, 1):
        lines.append(str(i))
        lines.append(f"{ts(it['start'])} --> {ts(it['end'])}")
        lines.append(it.get("translated") or "")
        lines.append("")
    return "\n".join(lines)


def _run_job(job_id: str, req: TranslateRequest) -> None:
    if not _HAS_FFMPEG:
        _set(job_id, status="failed", error="服务器未安装 ffmpeg，无法合成")
        return
    if not voxcpm.available():
        _set(job_id, status="failed", error="语音克隆服务未配置（VOXCPM_URL），无法深度克隆配音")
        return

    work = tempfile.mkdtemp(prefix="tr_")
    video_path: str | None = None
    try:
        # 1) 下载视频
        _set(job_id, stage="下载视频")
        video_path = _download(req.url)
        total_dur = _ffprobe_duration(video_path)

        # 2) 抽取音轨（16k 单声道 wav，利于 ASR）
        _set(job_id, stage="抽取音轨")
        audio_path = os.path.join(work, "audio.wav")
        ok, err = _ffmpeg(["-i", video_path, "-vn", "-ac", "1", "-ar", "16000", audio_path])
        if not ok or not os.path.exists(audio_path):
            raise RuntimeError(f"抽取音轨失败：{err or '未知'}")
        with open(audio_path, "rb") as f:
            audio_url = _put_audio(f.read(), "wav", "translate/asr")

        # 3) ASR 逐句
        _set(job_id, stage="识别原声")
        segments, full_text, asr_dur = _asr_segments(audio_url)
        if not segments:
            raise RuntimeError("未能从视频中识别到语音")
        if total_dur <= 0:
            total_dur = asr_dur or (segments[-1]["end"] if segments else 0.0)
        if len(segments) > _MAX_SEGMENTS:
            segments = segments[:_MAX_SEGMENTS]
        _set(job_id, sourceText=full_text)

        # 4) 取最长一句做深度克隆参考音（+其原文作 prompt → 终极克隆）
        _set(job_id, stage="提取参考音色")
        ref = max(segments, key=lambda s: s["end"] - s["start"])
        ref_dur = min(ref["end"] - ref["start"], _REF_MAX_SEC)
        ref_path = os.path.join(work, "ref.wav")
        ok, _e = _ffmpeg(["-ss", f"{ref['start']}", "-i", audio_path, "-t", f"{ref_dur}",
                          "-ac", "1", "-ar", "24000", ref_path])
        if not ok or not os.path.exists(ref_path):
            raise RuntimeError("提取参考音色失败")
        with open(ref_path, "rb") as f:
            ref_url = _put_audio(f.read(), "wav", "translate/ref")
        ref_text = ref["text"]

        # 5) 逐句翻译 + 深度克隆配音 + 变速到一致
        seg_files: list[tuple[float, str]] = []  # (start_sec, wav_path)
        n = len(segments)
        for i, seg in enumerate(segments):
            _set(job_id, stage="翻译并克隆配音", progress={"done": i, "total": n})
            d = max(0.2, seg["end"] - seg["start"])
            # 5a 翻译
            try:
                translated = ark.translate_text(seg["text"], req.source, req.target).strip()
            except RuntimeError as e:
                raise RuntimeError(f"翻译失败：{e}")
            seg["translated"] = translated
            if not translated:
                continue
            # 5b 深度克隆（VoxCPM 终极克隆：参考音 + 其精确转写）
            try:
                wav = voxcpm.clone(translated, ref_url, prompt_text=ref_text)
            except Exception as e:  # noqa: BLE001
                raise RuntimeError(f"语音克隆失败：{e}")
            raw = os.path.join(work, f"s{i}_raw.wav")
            with open(raw, "wb") as f:
                f.write(wav)
            t = _ffprobe_duration(raw)
            if t <= 0:
                continue
            # 5c 变速到一致：speed=T/D（夹在可懂区间），再裁/补到恰好 D
            speed = max(_TEMPO_MIN, min(t / d, _TEMPO_MAX))
            fitted = os.path.join(work, f"s{i}.wav")
            ok, err = _ffmpeg([
                "-i", raw,
                "-af", f"{_atempo_chain(speed)},apad",
                "-t", f"{d}", "-ac", "1", "-ar", "24000", fitted,
            ])
            if not ok or not os.path.exists(fitted):
                raise RuntimeError(f"配音变速失败：{err or '未知'}")
            seg_files.append((seg["start"], fitted))
        _set(job_id, stage="翻译并克隆配音", progress={"done": n, "total": n})

        if not seg_files:
            raise RuntimeError("没有可合成的配音片段")

        # 6) 落到全长静音轨上：每句 adelay 到起点后 amix
        _set(job_id, stage="合成配音轨")
        dub_path = os.path.join(work, "dub.wav")
        inputs: list[str] = []
        filt: list[str] = []
        labels: list[str] = []
        for idx, (start, path) in enumerate(seg_files):
            inputs += ["-i", path]
            ms = int(round(start * 1000))
            filt.append(f"[{idx}:a]adelay={ms}|{ms}[a{idx}]")
            labels.append(f"[a{idx}]")
        filt.append(f"{''.join(labels)}amix=inputs={len(seg_files)}:normalize=0:dropout_transition=0[dub]")
        ok, err = _ffmpeg([
            *inputs, "-filter_complex", ";".join(filt),
            "-map", "[dub]", "-t", f"{total_dur}", "-ac", "2", "-ar", "44100", dub_path,
        ])
        if not ok or not os.path.exists(dub_path):
            raise RuntimeError(f"合成配音轨失败：{err or '未知'}")

        # 7) 与原视频叠加/替换音轨；可选烧录字幕
        _set(job_id, stage="合成成片")
        srt_path = None
        if req.generate_subtitles:
            srt_path = os.path.join(work, "sub.srt")
            with open(srt_path, "w", encoding="utf-8") as f:
                f.write(_build_srt([s for s in segments if s.get("translated")]))

        out_path = os.path.join(work, "out.mp4")
        ok, err = _mux(video_path, dub_path, req.keep_bgm, srt_path, out_path)
        if not ok or not os.path.exists(out_path):
            raise RuntimeError(f"合成成片失败：{err or '未知'}")

        # 8) 上传成片
        _set(job_id, stage="上传成片")
        day = datetime.now(timezone.utc).strftime("%Y%m%d")
        key = f"translate/{day}/{uuid.uuid4().hex}.mp4"
        with open(out_path, "rb") as f:
            url = put_object(key, f.read(), "video/mp4")

        _set(
            job_id,
            status="done",
            stage="完成",
            url=url,
            key=key,
            target=req.target,
            targetText="\n".join(s.get("translated", "") for s in segments if s.get("translated")),
            segments=segments,
        )
    except HTTPException as e:
        _set(job_id, status="failed", error=str(e.detail))
    except Exception as e:  # noqa: BLE001
        print(f"[translate] 任务 {job_id} 失败：{e}")
        _set(job_id, status="failed", error=f"{e}")
    finally:
        if video_path:
            try:
                os.remove(video_path)
            except OSError:
                pass
        shutil.rmtree(work, ignore_errors=True)


def _mux(video: str, dub: str, keep_bgm: bool, srt: str | None, out: str) -> tuple[bool, str]:
    """把配音轨合回视频。keep_bgm=叠加压低的原声；有 srt 则烧录（需重编码视频）。"""
    args = ["-i", video, "-i", dub]
    vmap = "0:v:0"
    # 视频处理：烧字幕需重编码，否则直接 copy
    if srt:
        srt_esc = srt.replace("\\", "/").replace(":", "\\:")
        vfilter = f"subtitles='{srt_esc}':force_style='FontSize=18,Outline=1,Shadow=0'"
        vcodec = ["-vf", vfilter, "-c:v", "libx264", "-preset", "veryfast", "-crf", "23"]
    else:
        vcodec = ["-c:v", "copy"]

    if keep_bgm and _has_audio(video):
        # 原声压低叠加配音
        afilter = "[0:a]volume=0.12[o];[1:a]volume=1.0[d];[o][d]amix=inputs=2:duration=first:normalize=0[a]"
        amap = ["-filter_complex", afilter, "-map", vmap, "-map", "[a]"]
    else:
        amap = ["-map", vmap, "-map", "1:a:0"]

    args += amap + vcodec + ["-c:a", "aac", "-ar", "44100", "-shortest", "-movflags", "+faststart", out]
    return _ffmpeg(args)


@router.post("")
def start_translate(req: TranslateRequest) -> dict:
    """启动视频翻译任务，立即返回 job_id（请求很短，不触发代理超时）。"""
    if not (req.url or "").strip():
        raise HTTPException(status_code=400, detail="缺少视频 URL")
    job_id = uuid.uuid4().hex
    _JOBS[job_id] = {"status": "processing", "stage": "排队中"}
    threading.Thread(target=_run_job, args=(job_id, req), daemon=True).start()
    return {"ok": True, "job_id": job_id, "status": "processing"}


@router.get("/{job_id}")
def get_translate(job_id: str) -> dict:
    job = _JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")
    return {"ok": job.get("status") == "done", **job}

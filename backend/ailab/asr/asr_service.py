# -*- coding: UTF-8 -*-
"""
ASR 服务接口 (默认 faster-whisper, 备用 OpenAI Whisper + FunASR)

公开 3 个接口:
    transcribe_audio(audio, language=None)
        识别音频 (URL 或本地路径)，返回 {text, segments, raw}
    transcribe_video(video, language=None)
        从视频抽音频再识别，返回同上
    extract_audio_to_oss(video, prefix="chorify-video/audio")
        从视频抽 16k 单声道 WAV，上传 OSS，返回公网 URL

特性:
  - URL / 本地路径都支持
  - 自动绕开 HTTP_PROXY (解决 SSL DECRYPTION_FAILED_OR_BAD_RECORD_MAC)
  - 模型 pipeline 单例，第二次调用不重新加载
  - 临时文件用完即删

CLI 示例:
    python -m ailab.asr.asr_service audio   "https://.../foo.wav"
    python -m ailab.asr.asr_service video   "https://.../clip.mp4" --language thai
    python -m ailab.asr.asr_service extract "K:\\path\\to\\local.mp4"
"""

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Optional, Union

# ---- 必须在 import requests 之前清掉代理 ----
for _k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
    os.environ.pop(_k, None)
os.environ["NO_PROXY"] = (
    "modelscope.cn,*.modelscope.cn,*.aliyuncs.com,*.aliyun.com,oss-imgai.sligenai.cn"
)

# 强制 urllib 不走任何代理 (Windows 系统级代理也忽略)
_no_proxy_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
urllib.request.install_opener(_no_proxy_opener)

# 让 oss_util 可被导入 (项目根)
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from oss_util import upload_file  # noqa: E402


# ============ 模型单例 ============

# 引擎 1: FunASR / ModelScope (无时间戳)
_PIPELINE_FUNASR = None
MODEL_ID = "iic/Whisper-large-v3"
MODEL_REVISION = "v2.0.5"

# 引擎 2: OpenAI Whisper 原版 (带秒级 + 词级时间戳, 备用)
_PIPELINE_OPENAI = None
OPENAI_WHISPER_MODEL = "large-v3"
# 直接复用 FunASR 缓存里的 large-v3.pt, 省 3GB 重复下载
OPENAI_WHISPER_CACHE = r"C:\Users\Admin\.cache\modelscope\hub\models\iic\Whisper-large-v3"

# 引擎 3: faster-whisper (CTranslate2 实现, RTF 0.1-0.15, 比 openai 引擎快 4-5x, 默认引擎)
_PIPELINE_FASTER = None
# 优先用本地权重路径 (Motrix 离线下完丢这, 绕开 HF 大文件 SSL 不稳).
# 设成 None 或填模型名 (如 "large-v3") 则走 HuggingFace 自动下载.
FASTER_WHISPER_MODEL_LOCAL = r"D:\models\faster-whisper-large-v3"
FASTER_WHISPER_MODEL = FASTER_WHISPER_MODEL_LOCAL if Path(FASTER_WHISPER_MODEL_LOCAL).is_dir() else "large-v3"
# fp16 在 4090 上质量速度均衡; 显存紧张换 int8_float16 (速度类似, 显存减半, 精度几乎无损)
FASTER_WHISPER_COMPUTE_TYPE = "float16"

DEFAULT_ENGINE = "faster"  # "faster" (默认) | "openai" | "funasr"

# language code 转换: 'thai' -> 'th', 'chinese'/'zh' -> 'zh', 'english' -> 'en'
_LANG_TO_ISO = {
    None: None, "": None,
    "thai": "th", "th": "th",
    "chinese": "zh", "zh": "zh", "cn": "zh",
    "english": "en", "en": "en",
    "japanese": "ja", "ja": "ja",
    "korean": "ko", "ko": "ko",
}


def _get_pipeline_funasr():
    global _PIPELINE_FUNASR
    if _PIPELINE_FUNASR is None:
        from modelscope.pipelines import pipeline
        from modelscope.utils.constant import Tasks
        print(f"[asr] 加载 FunASR pipeline {MODEL_ID}@{MODEL_REVISION} ...")
        _PIPELINE_FUNASR = pipeline(
            task=Tasks.auto_speech_recognition,
            model=MODEL_ID,
            model_revision=MODEL_REVISION,
        )
        print("[asr] FunASR pipeline 加载完成")
    return _PIPELINE_FUNASR


def _get_pipeline_openai():
    global _PIPELINE_OPENAI
    if _PIPELINE_OPENAI is None:
        import whisper
        print(f"[asr] 加载 OpenAI Whisper {OPENAI_WHISPER_MODEL} ...")
        _PIPELINE_OPENAI = whisper.load_model(
            OPENAI_WHISPER_MODEL,
            download_root=OPENAI_WHISPER_CACHE,
        )
        print(f"[asr] OpenAI Whisper 加载完成 device={_PIPELINE_OPENAI.device}")
    return _PIPELINE_OPENAI


def _get_pipeline_faster():
    global _PIPELINE_FASTER
    if _PIPELINE_FASTER is None:
        from faster_whisper import WhisperModel
        print(f"[asr] 加载 faster-whisper {FASTER_WHISPER_MODEL} ({FASTER_WHISPER_COMPUTE_TYPE}) ...")
        # 第一次跑会从 HuggingFace 下载 ~1.5GB CT2 格式权重到 ~/.cache/huggingface/hub/
        # 国内访问 huggingface.co 慢时, 可设环境变量 HF_ENDPOINT=https://hf-mirror.com
        _PIPELINE_FASTER = WhisperModel(
            FASTER_WHISPER_MODEL,
            device="cuda",
            compute_type=FASTER_WHISPER_COMPUTE_TYPE,
        )
        print("[asr] faster-whisper 加载完成")
    return _PIPELINE_FASTER


# 旧接口兼容
def _get_pipeline():
    return _get_pipeline_funasr()


# ============ 工具函数 ============

def _is_url(s: str) -> bool:
    return isinstance(s, str) and s.startswith(("http://", "https://"))


def _download_url(url: str, suffix: str = "", retries: int = 5, timeout: int = 120) -> Path:
    """用 urllib 下载 URL 到临时文件 (绕开 requests 的代理坑)。"""
    suffix = suffix or Path(url.split("?")[0]).suffix or ".bin"
    fd, tmp_path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as resp:
                with open(tmp_path, "wb") as f:
                    while True:
                        chunk = resp.read(1 << 20)
                        if not chunk:
                            break
                        f.write(chunk)
            return Path(tmp_path)
        except Exception as e:
            last_err = e
            print(f"[asr] 下载失败 ({attempt}/{retries}): {type(e).__name__}: {str(e)[:200]}")
            time.sleep(2)
    try:
        os.unlink(tmp_path)
    except OSError:
        pass
    raise RuntimeError(f"下载失败: {url}\n最后一次错误: {last_err}")


def _ensure_local(src: Union[str, Path], suffix: str = "") -> tuple[Path, bool]:
    """
    保证拿到本地文件路径。
    返回 (local_path, is_temp)；is_temp 用于后续判断要不要删。
    """
    if isinstance(src, Path) or not _is_url(str(src)):
        return Path(src), False
    return _download_url(str(src), suffix=suffix), True


def _extract_audio(video_path: Path) -> Path:
    """ffmpeg 抽 16kHz 单声道 PCM WAV (Whisper 友好格式) 到临时目录。"""
    tmp_dir = Path(tempfile.mkdtemp(prefix="asr_audio_"))
    out = tmp_dir / f"{video_path.stem}.wav"
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(video_path),
        "-vn",                  # 不要视频
        "-ac", "1",             # 单声道
        "-ar", "16000",         # 16 kHz
        "-c:a", "pcm_s16le",
        str(out),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg 抽音轨失败 {video_path}:\n{proc.stderr[:500]}")
    return out


def _safe_unlink(p: Path):
    try:
        if p.is_file():
            p.unlink()
            # 顺手清空临时父目录 (如果是我们建的)
            parent = p.parent
            if parent.name.startswith("asr_audio_") and not any(parent.iterdir()):
                parent.rmdir()
    except OSError:
        pass


def _normalize_funasr_result(raw) -> dict:
    """FunASR 的返回标准化。"""
    text = ""
    segments = []
    item = None
    if isinstance(raw, list) and raw:
        item = raw[0] if isinstance(raw[0], dict) else None
    elif isinstance(raw, dict):
        item = raw

    if item is not None:
        text = item.get("text", "") or ""
        sentence_info = item.get("sentence_info") or item.get("sentences")
        if isinstance(sentence_info, list):
            for s in sentence_info:
                if not isinstance(s, dict):
                    continue
                try:
                    start_ms = float(s.get("start", s.get("ts", 0)))
                    end_ms = float(s.get("end", s.get("te", 0)))
                    segments.append({
                        "start": start_ms / 1000.0,
                        "end": end_ms / 1000.0,
                        "text": s.get("text", "") or "",
                    })
                except (TypeError, ValueError):
                    pass
        if not segments:
            ts = item.get("timestamp") or item.get("timestamps") or []
            for entry in ts:
                if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                    try:
                        segments.append({
                            "start": float(entry[0]) / 1000.0,
                            "end": float(entry[1]) / 1000.0,
                            "text": "",
                        })
                    except (TypeError, ValueError):
                        pass
    elif isinstance(raw, str):
        text = raw
    return {"text": text, "segments": segments, "raw": raw}


def _normalize_openai_result(raw) -> dict:
    """OpenAI Whisper 的返回标准化 (已经是秒，且带 words 词级时间戳)。"""
    text = (raw or {}).get("text", "") or ""
    segments = []
    for seg in (raw or {}).get("segments", []) or []:
        words = []
        for w in seg.get("words", []) or []:
            words.append({
                "start": float(w.get("start", 0)),
                "end": float(w.get("end", 0)),
                "word": w.get("word", ""),
                "probability": float(w.get("probability", 0)),
            })
        segments.append({
            "start": float(seg.get("start", 0)),
            "end": float(seg.get("end", 0)),
            "text": (seg.get("text", "") or "").strip(),
            "words": words,
        })
    return {"text": text.strip(), "segments": segments, "raw": raw}


def _normalize_faster_result(segments_gen, info) -> dict:
    """
    faster-whisper 返回 (Generator[Segment], TranscriptionInfo)。
    消费 generator, 拼装成跟 OpenAI 引擎一致的格式 {text, segments, raw}。
    raw 不保留 (generator 已消费, 也没必要), 信息全在 segments 里。
    """
    segments_out = []
    text_parts = []
    for seg in segments_gen:
        words = []
        if seg.words:
            for w in seg.words:
                words.append({
                    "start": float(w.start),
                    "end": float(w.end),
                    "word": w.word,
                    "probability": float(w.probability),
                })
        segments_out.append({
            "start": float(seg.start),
            "end": float(seg.end),
            "text": (seg.text or "").strip(),
            "words": words,
        })
        text_parts.append(seg.text or "")
    return {
        "text": "".join(text_parts).strip(),
        "segments": segments_out,
        "raw": {
            "language": getattr(info, "language", None),
            "language_probability": getattr(info, "language_probability", None),
            "duration": getattr(info, "duration", None),
        },
    }


# ============ 公开接口 ============

def _openai_transcribe_with_fallback(model, audio_path: str, language: Optional[str], with_timestamps: bool):
    """
    跑 OpenAI Whisper transcribe。
    对已知 PyTorch SDPA bug 做 3 级 fallback:
      1. 用户请求的设置
      2. fp32 (fp16=False, 解决某些 attention 数值精度问题)
      3. 关掉 word_timestamps (兜底, 转写本身一定能拿到)
    """
    # 抑制 hallucination + temperature fallback 重试 -- 这是 Whisper 慢的真正大头.
    # 默认 Whisper 在 logprob 低时会从 t=0.0 一路重试到 1.0 共 5 档, 单段耗时 x5-x6.
    # 我们关掉跨窗口的 prompt 传染, 用更激进的静音/复读检测, 只保留 2 档 temperature.
    _common = dict(
        condition_on_previous_text=False,   # 前一窗口的 hallucination 不污染后续
        no_speech_threshold=0.6,            # 静音/无语音段更激进跳过
        compression_ratio_threshold=2.4,    # 复读机式 hallucination 检测
        temperature=(0.0, 0.2),             # 只重试 1 次温度, 不要 0.0~1.0 全跑
    )

    attempts = [
        dict(language=language, word_timestamps=with_timestamps, verbose=False, **_common),
    ]
    if with_timestamps:
        # bug 经常出在 fp16 + word_timestamps，先试 fp32
        attempts.append(dict(language=language, word_timestamps=True, verbose=False, fp16=False, **_common))
        # 还失败就关掉词级时间戳, 保留转写
        attempts.append(dict(language=language, word_timestamps=False, verbose=False, **_common))

    last_err = None
    for i, kw in enumerate(attempts, start=1):
        try:
            return model.transcribe(audio_path, **kw)
        except RuntimeError as e:
            msg = str(e)
            last_err = e
            # 已知错误才走 fallback, 否则直接抛
            if "key.size" in msg or "value.size" in msg or "SDPA" in msg or "scaled_dot_product" in msg:
                print(f"[asr] OpenAI Whisper attempt {i} failed ({msg[:120]}), retrying with looser config...")
                continue
            raise
    raise last_err  # type: ignore[misc]


def transcribe_audio(
    audio: Union[str, Path],
    language: Optional[str] = None,
    engine: str = DEFAULT_ENGINE,
    with_timestamps: bool = True,
) -> dict:
    """
    识别音频内容。

    :param audio: 音频文件本地路径 或 公网 URL
    :param language: 'thai'/'th' / 'chinese'/'zh' / 'english'/'en' / None 自动检测
    :param engine:
        'faster' (默认, CTranslate2 实现, RTF ~0.1, 比 openai 快 4-5x)
        'openai' (原版, RTF ~0.5-0.8, 跟 PyTorch 链路最兼容)
        'funasr' (无时间戳但启动快)
    :param with_timestamps: faster / openai 引擎生效, 是否要词级时间戳
    :return: {"text": str, "segments": [...], "raw": ...}
    """
    local, is_temp = _ensure_local(audio, suffix=".wav")
    try:
        iso_lang = _LANG_TO_ISO.get((language or "").lower(), language)
        if engine == "faster":
            model = _get_pipeline_faster()
            segments_gen, info = model.transcribe(
                str(local),
                language=iso_lang,
                word_timestamps=with_timestamps,
                beam_size=5,
                # 跟 openai 引擎用同一套 hallucination 抑制策略
                condition_on_previous_text=False,
                no_speech_threshold=0.6,
                compression_ratio_threshold=2.4,
                temperature=[0.0, 0.2],
                vad_filter=True,            # 内置 silero VAD, 跳过静音段, 又快又稳
            )
            return _normalize_faster_result(segments_gen, info)
        elif engine == "openai":
            model = _get_pipeline_openai()
            raw = _openai_transcribe_with_fallback(model, str(local), iso_lang, with_timestamps)
            return _normalize_openai_result(raw)
        elif engine == "funasr":
            pipe = _get_pipeline_funasr()
            raw = pipe(input=str(local), language=language)
            return _normalize_funasr_result(raw)
        else:
            raise ValueError(f"unknown engine: {engine}")
    finally:
        if is_temp:
            _safe_unlink(local)


def transcribe_video(
    video: Union[str, Path],
    language: Optional[str] = None,
    engine: str = DEFAULT_ENGINE,
) -> dict:
    """
    下载视频 -> ffmpeg 抽音轨 -> 识别音频 -> 返回文本。

    :param video: 视频本地路径 或 公网 URL
    :param language: 同 transcribe_audio
    :param engine: 同 transcribe_audio
    :return: 同 transcribe_audio
    """
    local_video, is_temp_video = _ensure_local(video, suffix=".mp4")
    audio_path = None
    try:
        audio_path = _extract_audio(local_video)
        return transcribe_audio(audio_path, language=language, engine=engine)
    finally:
        if audio_path is not None:
            _safe_unlink(audio_path)
        if is_temp_video:
            _safe_unlink(local_video)


def transcribe_and_translate(
    video: Union[str, Path],
    source_language: str = "thai",
    target_language: str = "zh",
    engine: str = DEFAULT_ENGINE,
) -> dict:
    """
    一站式: 视频 -> 抽音频 -> Whisper 识别 -> 豆包翻译。

    :param video: 视频本地路径 或 公网 URL
    :param source_language: 原始语种 (Whisper 用) — 'thai'/'th' / 'chinese'/'zh' / None 自动
    :param target_language: 翻译目标语种 (豆包用) — 默认 'zh'
    :param engine: 'openai' (默认带时间戳) | 'funasr'
    :return: {
        "source_text": str,
        "target_text": str,
        "source_language": str,
        "target_language": str,
        "segments": [{"start": float, "end": float, "text": str, "words": [...]}, ...],
        "raw_asr": ...,
    }
    """
    asr = transcribe_video(video, language=source_language, engine=engine)
    src_text = asr["text"]

    from ailab.llm import translate_text
    tgt_text = translate_text(src_text, source_lang=source_language, target_lang=target_language)

    return {
        "source_text": src_text,
        "target_text": tgt_text,
        "source_language": source_language,
        "target_language": target_language,
        "segments": asr["segments"],
        "raw_asr": asr["raw"],
    }


def extract_audio_to_oss(
    video: Union[str, Path],
    prefix: str = "chorify-video/audio",
) -> str:
    """
    下载视频 -> ffmpeg 抽 16k 单声道 WAV -> 上传 OSS -> 返回公网 URL。

    :param video: 视频本地路径 或 公网 URL
    :param prefix: OSS key 前缀
    :return: 公网音频 URL
    """
    local_video, is_temp_video = _ensure_local(video, suffix=".mp4")
    audio_path = None
    try:
        audio_path = _extract_audio(local_video)
        url = upload_file(audio_path, prefix=prefix)
        return url
    finally:
        if audio_path is not None:
            _safe_unlink(audio_path)
        if is_temp_video:
            _safe_unlink(local_video)


# ============ CLI ============

def _main():
    import argparse
    # 关键: Windows 控制台默认 GBK 编不出泰文。强制切到 UTF-8。
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

    parser = argparse.ArgumentParser(description="ASR 服务 CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("audio", help="识别音频 (URL/本地)")
    p1.add_argument("input")
    p1.add_argument("--language", default=None, help="thai / zh / en / ...")
    p1.add_argument("--save", default=None, help="把完整 JSON 结果写到该文件")

    p2 = sub.add_parser("video", help="从视频抽音频并识别")
    p2.add_argument("input")
    p2.add_argument("--language", default=None)
    p2.add_argument("--save", default=None)

    p3 = sub.add_parser("extract", help="从视频抽音频上传 OSS")
    p3.add_argument("input")
    p3.add_argument("--prefix", default="chorify-video/audio")

    p4 = sub.add_parser("translate", help="视频 ASR + 翻译 (一站式)")
    p4.add_argument("input")
    p4.add_argument("--source", default="thai", help="原语种, 默认 thai")
    p4.add_argument("--target", default="zh", help="目标语种, 默认 zh")
    p4.add_argument("--save", default=None)

    args = parser.parse_args()

    if args.cmd == "audio":
        r = transcribe_audio(args.input, language=args.language)
        out = {"text": r["text"], "segments_count": len(r["segments"])}
        print(json.dumps(out, ensure_ascii=False, indent=2))
        if args.save:
            Path(args.save).write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"完整结果已写到 {args.save}")

    elif args.cmd == "video":
        r = transcribe_video(args.input, language=args.language)
        out = {"text": r["text"], "segments_count": len(r["segments"])}
        print(json.dumps(out, ensure_ascii=False, indent=2))
        if args.save:
            Path(args.save).write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"完整结果已写到 {args.save}")

    elif args.cmd == "extract":
        url = extract_audio_to_oss(args.input, prefix=args.prefix)
        print(url)

    elif args.cmd == "translate":
        r = transcribe_and_translate(args.input, source_language=args.source, target_language=args.target)
        # 先存盘 —— 即使下面打印炸了，结果也已落地
        if args.save:
            out = {k: v for k, v in r.items() if k != "raw_asr"}
            Path(args.save).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            print("\n===== 原文 (" + r["source_language"] + ") =====")
            print(r["source_text"])
            print("\n===== 译文 (" + r["target_language"] + ") =====")
            print(r["target_text"])
            print(f"\nsegments: {len(r['segments'])}")
            if args.save:
                print(f"\n已写入 {args.save}")
        except UnicodeEncodeError as e:
            print(f"[警告] 控制台编码不支持，文本已写入 {args.save}: {e}")


if __name__ == "__main__":
    _main()

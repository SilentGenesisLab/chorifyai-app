"""VoxCPM 语音克隆 —— 调用自建 GPU 服务（voxcpm/server.py 或 ailab 网关）。

接口契约见 chorify-video/voxcpm/API.md：
    POST {base}/clone_path  JSON: {text, reference_wav_path(可为 URL),
                                    prompt_wav_path?, prompt_text?, cfg_value, inference_timesteps}
    返回 audio/wav 二进制；出错返回 {detail|msg}。

本服务返回 wav 二进制，由调用方上传 OSS。配置 VOXCPM_URL 指向服务地址。
"""
import requests

from app.core.config import settings

# voxcpm 通常在局域网 / 本机 GPU 机器，关闭代理直连
_session = requests.Session()
_session.trust_env = False


def _base() -> str:
    return (settings.voxcpm_url or "").rstrip("/")


def available() -> bool:
    return bool(_base())


def health() -> dict:
    base = _base()
    if not base:
        return {"ok": False, "configured": False, "reason": "未配置 VOXCPM_URL"}
    try:
        r = _session.get(f"{base}/health", timeout=8)
    except requests.RequestException as e:
        return {"ok": False, "configured": True, "reason": str(e)}
    if r.status_code != 200:
        return {"ok": False, "configured": True, "reason": f"HTTP {r.status_code}"}
    try:
        data = r.json()
    except ValueError:
        return {"ok": False, "configured": True, "reason": "响应非 JSON"}
    # 网关包了一层 {code,msg,data}，直连则是原始对象
    inner = data
    if isinstance(data, dict) and isinstance(data.get("data"), dict):
        inner = data["data"]
    return {"ok": True, "configured": True, **(inner or {})}


def clone(
    text: str,
    reference_url: str,
    *,
    prompt_text: str | None = None,
    prompt_url: str | None = None,
    cfg_value: float = 2.0,
    inference_timesteps: int = 10,
) -> bytes:
    """调用 /clone_path，返回 wav 二进制。

    - 只给 reference_url -> 普通克隆
    - 给 prompt_text(+prompt_url 或复用 reference_url) -> 终极克隆（最高保真）
    """
    base = _base()
    if not base:
        raise RuntimeError("未配置 VOXCPM_URL，语音克隆服务暂不可用")

    payload: dict = {
        "text": text,
        "reference_wav_path": reference_url,
        "cfg_value": cfg_value,
        "inference_timesteps": inference_timesteps,
    }
    # 终极克隆：prompt 音频 + 其精确转写
    if prompt_text and (prompt_url or reference_url):
        payload["prompt_wav_path"] = prompt_url or reference_url
        payload["prompt_text"] = prompt_text

    try:
        r = _session.post(
            f"{base}/clone_path", json=payload, timeout=settings.voxcpm_timeout
        )
    except requests.RequestException as e:
        raise RuntimeError(f"voxcpm 服务不可达: {e}") from e

    ctype = r.headers.get("content-type", "")
    if r.status_code == 200 and ctype.startswith("audio/"):
        return r.content

    # 错误：直连是 {detail}，网关是 {code,msg,data}
    msg: str
    try:
        j = r.json()
        msg = j.get("msg") or j.get("detail") or str(j)
    except ValueError:
        msg = r.text[:300]
    raise RuntimeError(f"voxcpm 克隆失败 (HTTP {r.status_code}): {msg}")

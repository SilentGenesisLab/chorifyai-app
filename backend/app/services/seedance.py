"""Seedance 视频生成 —— 火山方舟 Ark contents/generations/tasks。

AI影棚「上传产品图 → 一键生成商品大片」：图生视频(i2v) / 文生视频(t2v)。
异步：submit() 提交任务拿 task_id → get_task() 轮询直到出片，返回视频 URL。
密钥全在后端封装，复用 ARK_API_KEY（已验证有视频生成权限）。
"""
import requests

from app.core.config import settings

# 直连火山，忽略本机代理（与 ark/voice 同策略，避免代理破坏请求）
_session = requests.Session()
_session.trust_env = False


def available() -> bool:
    return bool(settings.ark_api_key)


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.ark_api_key}",
        "Content-Type": "application/json",
    }


def submit(
    prompt: str,
    image_url: str | None = None,
    *,
    ratio: str = "9:16",
    resolution: str = "720p",
    duration: int = 5,
    watermark: bool = False,
) -> str:
    """提交 Seedance 生成任务，返回 task_id。给 image_url 即图生视频(首帧)。"""
    if not settings.ark_api_key:
        raise RuntimeError("未配置 ARK_API_KEY，视频生成不可用")

    # Seedance 文本命令参数拼到 prompt 末尾
    cmd = (
        f" --resolution {resolution} --ratio {ratio} --duration {int(duration)}"
        f" --watermark {'true' if watermark else 'false'}"
    )
    content: list[dict] = [{"type": "text", "text": (prompt or "").strip() + cmd}]
    if image_url:
        content.append({"type": "image_url", "image_url": {"url": image_url}})

    body = {"model": settings.seedance_model, "content": content}
    try:
        r = _session.post(settings.ark_video_endpoint, json=body, headers=_headers(), timeout=60)
    except requests.RequestException as e:
        raise RuntimeError(f"Seedance 提交请求失败: {e}") from e
    if r.status_code != 200:
        raise RuntimeError(f"Seedance 提交失败 HTTP {r.status_code}: {r.text[:300]}")
    task_id = (r.json() or {}).get("id")
    if not task_id:
        raise RuntimeError(f"Seedance 未返回 task id: {r.text[:200]}")
    return task_id


def get_task(task_id: str) -> dict:
    """查询任务状态。返回 {status, video_url?, error?}。
    Ark status: queued / running / succeeded / failed / cancelled。"""
    try:
        r = _session.get(
            f"{settings.ark_video_endpoint}/{task_id}", headers=_headers(), timeout=30
        )
    except requests.RequestException as e:
        raise RuntimeError(f"查询任务失败: {e}") from e
    if r.status_code != 200:
        raise RuntimeError(f"查询任务失败 HTTP {r.status_code}: {r.text[:200]}")
    d = r.json() or {}
    content = d.get("content") or {}
    video_url = content.get("video_url") or d.get("video_url")
    err = (d.get("error") or {}).get("message") if isinstance(d.get("error"), dict) else None
    return {"status": d.get("status", ""), "video_url": video_url, "error": err}

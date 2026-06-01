# -*- coding: UTF-8 -*-
"""
豆包视觉模型 (Doubao VLM, 火山方舟 Ark) 单图目标检测.

公开:
    detect_logo_in_image(frame_bgr, reference_images=None, prompt=None) -> dict
        在一张图里检测产品 logo, 返回 {present, bbox, score, raw_response}.

环境变量 (.env, 跟 doubao.py 共用):
    ARK_API_KEY     豆包 API Key
    ARK_VLM_MODEL   视觉模型 ID (默认 doubao-seed-2-0-pro-260215)
    ARK_ENDPOINT    https://ark.cn-beijing.volces.com/api/v3/responses

实现要点:
    - 图片直接 base64 嵌入 (不上 OSS, 省去 1-2s 上传开销)
    - bbox 用归一化坐标 [x_min, y_min, x_max, y_max] (0~1), 内部转回像素
    - 容错: 模型可能输出 0-100 范围, 自动检测并归一化
"""

import base64
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

# 关闭代理 (与 doubao.py 一致)
for _k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
    os.environ.pop(_k, None)
_no_proxy_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
urllib.request.install_opener(_no_proxy_opener)

# 加载 .env
_env_path = Path(__file__).resolve().parents[2] / ".env"
if _env_path.exists():
    for _line in _env_path.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if not _line or _line.startswith("#") or "=" not in _line:
            continue
        _k, _v = _line.split("=", 1)
        os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))


SIDES_PROMPT = """下面这张图是从一段视频里截取的左下角和右下角两个候选水印区域, 左右并排拼接而成:
- 左半边 (标 "LEFT" 标签) 是视频左下角的候选区域
- 右半边 (标 "RIGHT" 标签) 是视频右下角的候选区域

请判断 LEFT 和 RIGHT 两个区域里, 是否分别含有 N-EASE 品牌产品的图标 / 水印 / 包装小图.
参考前几张图就是 N-EASE 产品的样子 (橙色 RelaxTouch 或绿色 N-EASE 包装).

判定要求:
- 必须能看到 N-EASE 产品瓶/包装的清晰轮廓
- 只是颜色相近但不是 N-EASE 产品, 不算
- 模糊到看不出产品轮廓的, 不算
- 该侧背景是纯色画面/无产品, 也算 false

输出严格 JSON, 不要 markdown 代码块, 不要解释:
{"left": true 或 false, "right": true 或 false}
"""


def classify_sides(
    combined_image: np.ndarray,
    reference_images: Optional[list] = None,
    prompt: Optional[str] = None,
    timeout: int = 60,
) -> dict:
    """
    给一张左右拼接图, 问豆包: 左/右 各自是否有 N-EASE 产品.

    Returns:
        {"left": bool, "right": bool, "raw_response": str}
    """
    use_prompt = prompt or SIDES_PROMPT

    content = []
    if reference_images:
        content.append({
            "type": "input_text",
            "text": f"以下 {len(reference_images)} 张是 N-EASE 产品参考图:",
        })
        for ref in reference_images:
            content.append({
                "type": "input_image",
                "image_url": _encode_image_base64(ref),
            })
        content.append({
            "type": "input_text",
            "text": "下面是待检测的左右拼接图:",
        })

    content.append({
        "type": "input_image",
        "image_url": _encode_image_base64(combined_image),
    })
    content.append({"type": "input_text", "text": use_prompt})

    resp = _call_ark_vision(content, timeout=timeout)
    text = _extract_text(resp)
    parsed = _parse_lenient_json(text)

    out = {"left": False, "right": False, "raw_response": text}
    if parsed:
        out["left"] = bool(parsed.get("left"))
        out["right"] = bool(parsed.get("right"))
    return out


DEFAULT_PROMPT = """你是产品 logo 目标检测助手. 任务: 判断给定视频截图里是否存在 N-EASE 品牌的产品 logo / 水印, 如有则定位 bbox.

产品特征 (前几张图是参考):
- 橙色版: "RELAXTOUCH GEL" 或 "N-EASE" 字样的橙白配色管装产品 + 包装盒
- 绿色版: "N-EASE" 或 "Soothing Pain Relief Massage Gel" 字样的绿白配色管装产品 + 包装盒

判定标准 (严格):
1. 必须是 "产品水印 / 角标 / 包装小图" 形式 (通常在画面右下/左下角)
2. 产品的轮廓与文字应该清晰可辨, 即使尺寸很小
3. 真人手里拿着或在使用的实际产品 也算 (但要清晰可见)
4. 部分遮挡 / 模糊 / 只有边角 不算

bbox 要求 (非常重要, 不满足就当作 present=false):
- bbox 必须紧密包围**整个产品**, 不能只框文字、只框瓶口、只框边角
- bbox 面积应占整幅画面的 1% ~ 30% (太小或太大都不算)
- bbox 四个坐标必须明显不同 (不要给出 [0.5, 0.5, 0.51, 0.51] 这种退化框)
- bbox 必须在合理位置 (画面下半部分 y > 0.4 的区域居多)

输出 (严格 JSON, 不要 markdown 代码块, 不要解释):
{
  "present": true,
  "bbox": [x_min, y_min, x_max, y_max]
}
其中 4 个数都是 [0.0, 1.0] 归一化坐标 (相对待检测图的宽和高), 满足 x_min < x_max, y_min < y_max.

如果未检测到或无法给出合理 bbox:
{"present": false}
"""


def _encode_image_base64(img_bgr: np.ndarray, max_side: int = 1280,
                         quality: int = 85) -> str:
    """BGR ndarray -> JPEG base64 data URL. 长边超过 max_side 时先缩小."""
    h, w = img_bgr.shape[:2]
    if max(h, w) > max_side:
        scale = max_side / max(h, w)
        new_w = int(w * scale)
        new_h = int(h * scale)
        img_bgr = cv2.resize(img_bgr, (new_w, new_h), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode('.jpg', img_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not ok:
        raise RuntimeError("cv2.imencode 失败")
    b64 = base64.b64encode(buf.tobytes()).decode('ascii')
    return f"data:image/jpeg;base64,{b64}"


def _call_ark_vision(content: list, timeout: int = 60) -> dict:
    body = {
        "model": os.environ["ARK_VLM_MODEL"],
        "input": [{"role": "user", "content": content}],
        "thinking": {"type": "disabled"},
    }
    req = urllib.request.Request(
        os.environ["ARK_ENDPOINT"],
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {os.environ['ARK_API_KEY']}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"豆包 HTTP {e.code}: {err_body[:400]}") from e


_JSON_RE = re.compile(r"\{.*\}", re.S)


def _parse_lenient_json(text: str) -> Optional[dict]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    m = _JSON_RE.search(text)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return None
    return None


def _extract_text(resp: dict) -> str:
    for item in resp.get("output", []):
        for c in item.get("content") or []:
            if c.get("type") == "output_text":
                return c.get("text", "")
    return ""


def detect_logo_in_image(
    frame_bgr: np.ndarray,
    reference_images: Optional[list] = None,
    prompt: Optional[str] = None,
    timeout: int = 60,
) -> dict:
    """
    在一张图里检测产品 logo.

    Args:
        frame_bgr: 待检测的视频帧 (BGR ndarray)
        reference_images: 产品参考图列表 (BGR ndarray 列表), 给 VLM 当 few-shot
        prompt: 自定义 prompt, 默认 DEFAULT_PROMPT (N-EASE 检测)
        timeout: API 超时

    Returns:
        {
          "present": bool,
          "bbox": (x, y, w, h) | None,   # 像素坐标
          "score": float | None,         # 当前 VLM 通常不返回, 留 None
          "raw_response": str            # 模型原文 (调试用)
        }
    """
    H, W = frame_bgr.shape[:2]
    use_prompt = prompt or DEFAULT_PROMPT

    content = []
    if reference_images:
        content.append({
            "type": "input_text",
            "text": f"以下是 {len(reference_images)} 张产品参考图, 帮你识别 logo 形态:",
        })
        for ref in reference_images:
            content.append({
                "type": "input_image",
                "image_url": _encode_image_base64(ref),
            })
        content.append({
            "type": "input_text",
            "text": "下面是待检测的视频截图:",
        })

    content.append({
        "type": "input_image",
        "image_url": _encode_image_base64(frame_bgr),
    })
    content.append({"type": "input_text", "text": use_prompt})

    resp = _call_ark_vision(content, timeout=timeout)
    text = _extract_text(resp)
    parsed = _parse_lenient_json(text)

    out = {"present": False, "bbox": None, "score": None, "raw_response": text}
    if not parsed:
        return out

    out["present"] = bool(parsed.get("present"))
    if not out["present"]:
        return out

    bbox_n = parsed.get("bbox")
    if not bbox_n or len(bbox_n) != 4:
        return out

    try:
        x_min, y_min, x_max, y_max = [float(v) for v in bbox_n]
    except (TypeError, ValueError):
        return out

    # 豆包返回 [0.0, 1.0] 归一化坐标. clamp + 排序 (兼顾 x_min > x_max 之类的颠倒情况).
    x_min = max(0.0, min(1.0, x_min))
    y_min = max(0.0, min(1.0, y_min))
    x_max = max(0.0, min(1.0, x_max))
    y_max = max(0.0, min(1.0, y_max))
    x_min, x_max = sorted([x_min, x_max])
    y_min, y_max = sorted([y_min, y_max])

    px = int(round(x_min * W))
    py = int(round(y_min * H))
    pw = max(1, int(round((x_max - x_min) * W)))
    ph = max(1, int(round((y_max - y_min) * H)))
    px = max(0, min(px, W - 1))
    py = max(0, min(py, H - 1))
    pw = max(1, min(pw, W - px))
    ph = max(1, min(ph, H - py))

    # bbox 健全性检查 (VLM 容易给退化 bbox 比如 1x1 像素 或者占满全图)
    MIN_SIDE = 30          # 边长至少 30 px (水印再小也不会这么小)
    MAX_AREA_RATIO = 0.5   # 不超过画面一半 (logo 不会占这么大)
    MIN_AREA_RATIO = 0.002  # 至少占画面 0.2%

    if pw < MIN_SIDE or ph < MIN_SIDE:
        out["present"] = False
        out["bbox"] = None
        out["raw_response"] += f"\n[bbox 过滤] 边长太小 {pw}x{ph} (要求 >= {MIN_SIDE})"
        return out

    area_ratio = (pw * ph) / float(W * H)
    if area_ratio > MAX_AREA_RATIO:
        out["present"] = False
        out["bbox"] = None
        out["raw_response"] += f"\n[bbox 过滤] 面积太大 {area_ratio:.1%} > {MAX_AREA_RATIO:.0%}"
        return out
    if area_ratio < MIN_AREA_RATIO:
        out["present"] = False
        out["bbox"] = None
        out["raw_response"] += f"\n[bbox 过滤] 面积太小 {area_ratio:.2%} < {MIN_AREA_RATIO:.1%}"
        return out

    out["bbox"] = (px, py, pw, ph)
    return out


def detect_logo_in_video_clip(
    video_path,
    reference_images: Optional[list] = None,
    n_samples: int = 3,
    prompt: Optional[str] = None,
    early_stop: bool = True,
) -> dict:
    """
    对一个分镜均匀采样 n_samples 帧, 调 VLM 检测 logo, 多帧投票.

    Args:
        video_path: 分镜 mp4 路径
        reference_images: 参考图
        n_samples: 采样帧数 (默认 3)
        early_stop: 检测到第一个 present=True 帧就停 (省 API 调用)

    Returns:
        {
          "present": bool,
          "bbox": (x, y, w, h) | None,   # 多帧 bbox 中位数
          "hits": int,                    # 命中帧数
          "total": int,                   # 实际采样帧数
          "best_frame": ndarray | None,   # 命中分数最高那帧 (后续可截 runtime 模板)
        }
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return {"present": False, "bbox": None, "hits": 0, "total": 0, "best_frame": None}
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if total < 1:
        cap.release()
        return {"present": False, "bbox": None, "hits": 0, "total": 0, "best_frame": None}

    sample_idx = np.linspace(0, max(0, total - 1), n_samples, dtype=int)
    hits = []          # list of (bbox, frame)
    sampled = 0
    for idx in sample_idx:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
        ret, frame = cap.read()
        if not ret:
            continue
        sampled += 1
        try:
            r = detect_logo_in_image(frame, reference_images=reference_images, prompt=prompt)
        except Exception as e:
            print(f"    [VLM 错误] idx={idx}: {e}")
            continue
        if r["present"] and r["bbox"]:
            hits.append((r["bbox"], frame))
            if early_stop:
                break
    cap.release()

    if not hits:
        return {"present": False, "bbox": None, "hits": 0, "total": sampled, "best_frame": None}

    bboxes = np.array([h[0] for h in hits])
    median_bbox = tuple(int(x) for x in np.median(bboxes, axis=0))
    return {
        "present": True,
        "bbox": median_bbox,
        "hits": len(hits),
        "total": sampled,
        "best_frame": hits[0][1],   # 第一个命中帧
    }

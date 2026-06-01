# -*- coding: UTF-8 -*-
"""
豆包 (火山方舟 Ark) 文本接口封装。

公开:
    complete_text(prompt, system=None, model=None) -> str
        简单的"问一次答一次"，返回模型输出文本。
    translate_text(text, source_lang="thai", target_lang="zh", model=None) -> str
        翻译文本，返回目标语言文本。

环境变量 (.env):
    ARK_API_KEY     豆包 API Key
    ARK_ENDPOINT    https://ark.cn-beijing.volces.com/api/v3/responses
    ARK_TEXT_MODEL  优先使用 (没设就 fallback 到 ARK_VLM_MODEL)
    ARK_VLM_MODEL   备选
"""

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

# 关闭代理 (与 asr_service 同样的策略)
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


_LANG_NAME = {
    "thai": "泰语",
    "th": "泰语",
    "zh": "中文",
    "cn": "中文",
    "en": "英语",
    "ja": "日语",
    "ko": "韩语",
}


def _model_id(override: Optional[str] = None) -> str:
    if override:
        return override
    return os.environ.get("ARK_TEXT_MODEL") or os.environ["ARK_VLM_MODEL"]


def _extract_output_text(resp: dict) -> str:
    """从 Ark /responses 接口的 JSON 返回里抽出文本。"""
    # Ark 的标准格式：output: [{ content: [{ type: "output_text", text: "..." }] }]
    for item in resp.get("output") or []:
        for c in item.get("content") or []:
            if c.get("type") == "output_text" and c.get("text"):
                return c["text"]
    # 兼容旧字段
    if "output_text" in resp:
        return resp["output_text"]
    return ""


def _call_ark(messages: list, model: Optional[str] = None) -> dict:
    body = {
        "model": _model_id(model),
        "input": messages,
        "thinking": {"type": "disabled"}
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
        with urllib.request.urlopen(req, timeout=180) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"豆包 HTTP {e.code}: {err_body}") from e


def complete_text(prompt: str, system: Optional[str] = None, model: Optional[str] = None) -> str:
    """单轮问答。返回模型输出文本。"""
    messages = []
    if system:
        messages.append({
            "role": "system",
            "content": [{"type": "input_text", "text": system}],
        })
    messages.append({
        "role": "user",
        "content": [{"type": "input_text", "text": prompt}],
    })
    resp = _call_ark(messages, model=model)
    return _extract_output_text(resp).strip()


def translate_text(
    text: str,
    source_lang: str = "thai",
    target_lang: str = "zh",
    model: Optional[str] = None,
) -> str:
    """翻译文本。空字符串直接返回。"""
    if not text or not text.strip():
        return ""
    src_name = _LANG_NAME.get(source_lang.lower(), source_lang)
    tgt_name = _LANG_NAME.get(target_lang.lower(), target_lang)
    system = (
        f"你是专业翻译。把用户给的{src_name}原文翻译成{tgt_name}，"
        f"只输出译文本身，不要任何解释、不要重复原文、不要加引号。"
        f"保持口语化和自然，符合广告/短视频文案的风格。"
    )
    return complete_text(text, system=system, model=model)

"""豆包大模型（火山方舟 Ark /responses 接口）封装 —— AI 写文案 + 文本翻译。

所有 AI 能力都在后端封装，前端只调用本服务的 HTTP 接口，密钥不下发。

公开函数:
    complete_text(prompt, system=None) -> str      单轮问答，返回模型文本
    translate_text(text, source, target) -> str     翻译文本，返回目标语言译文
    language_name(code) -> str                       语言代码 → 中文名
"""
import requests

from app.core.config import settings

# 直连火山方舟，忽略本机 HTTP(S)_PROXY（与 voice 模块同策略，避免代理破坏请求）
_session = requests.Session()
_session.trust_env = False

# 翻译/识别支持的语言（code -> 中文名）
LANGUAGES: list[dict] = [
    {"code": "auto", "name": "自动识别"},
    {"code": "zh", "name": "中文"},
    {"code": "en", "name": "英语"},
    {"code": "ja", "name": "日语"},
    {"code": "ko", "name": "韩语"},
    {"code": "th", "name": "泰语"},
    {"code": "vi", "name": "越南语"},
    {"code": "id", "name": "印尼语"},
    {"code": "es", "name": "西班牙语"},
    {"code": "fr", "name": "法语"},
    {"code": "de", "name": "德语"},
    {"code": "ru", "name": "俄语"},
    {"code": "pt", "name": "葡萄牙语"},
    {"code": "ar", "name": "阿拉伯语"},
]
_LANG_NAME = {item["code"]: item["name"] for item in LANGUAGES}
# 常见别名
_LANG_NAME.update({"cn": "中文", "jp": "日语", "english": "英语", "thai": "泰语"})


def language_name(code: str) -> str:
    return _LANG_NAME.get((code or "").lower(), code or "")


def _extract_output_text(resp: dict) -> str:
    """从 Ark /responses 的 JSON 里抽出文本。"""
    for item in resp.get("output") or []:
        for c in item.get("content") or []:
            if c.get("type") == "output_text" and c.get("text"):
                return c["text"]
    if resp.get("output_text"):
        return resp["output_text"]
    return ""


def complete_text(prompt: str, system: str | None = None) -> str:
    """单轮问答。返回模型输出文本。"""
    if not settings.ark_api_key:
        raise RuntimeError("未配置 ARK_API_KEY（豆包文本服务）")

    messages: list[dict] = []
    if system:
        messages.append(
            {"role": "system", "content": [{"type": "input_text", "text": system}]}
        )
    messages.append(
        {"role": "user", "content": [{"type": "input_text", "text": prompt}]}
    )

    body = {
        "model": settings.ark_model,
        "input": messages,
        "thinking": {"type": "disabled"},
    }
    try:
        r = _session.post(
            settings.ark_endpoint,
            json=body,
            headers={
                "Authorization": f"Bearer {settings.ark_api_key}",
                "Content-Type": "application/json",
            },
            timeout=180,
        )
    except requests.RequestException as e:
        raise RuntimeError(f"豆包请求失败: {e}") from e

    if r.status_code != 200:
        raise RuntimeError(f"豆包 HTTP {r.status_code}: {r.text[:300]}")
    return _extract_output_text(r.json()).strip()


def translate_text(text: str, source: str = "auto", target: str = "zh") -> str:
    """翻译文本。空字符串直接返回。"""
    if not text or not text.strip():
        return ""
    tgt = language_name(target) or target
    if source in ("", "auto"):
        src_clause = "用户给的原文（自动判断语种）"
    else:
        src_clause = f"用户给的{language_name(source) or source}原文"
    system = (
        f"你是专业翻译。把{src_clause}翻译成{tgt}，只输出译文本身，"
        f"不要任何解释、不要重复原文、不要加引号。"
        f"保持口语化、自然，符合广告 / 短视频文案的风格。"
    )
    return complete_text(text, system=system)

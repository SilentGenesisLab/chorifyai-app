# -*- coding: UTF-8 -*-
"""
预下载 Whisper-large-v3 模型到本地，带重试 + 自动绕代理。
跑一次成功后，主脚本 (whisper-large-v3.py) 会直接命中缓存。

用法:
    python download_whisper.py
"""

import os
import time

# 关键：绕开代理 (DECRYPTION_FAILED_OR_BAD_RECORD_MAC 多半是代理 TLS 拦截导致)
for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
    os.environ.pop(k, None)
os.environ["NO_PROXY"] = "modelscope.cn,*.modelscope.cn,*.aliyuncs.com,*.aliyun.com"

from modelscope import snapshot_download

MODEL_ID = "iic/Whisper-large-v3"
REVISION = "v2.0.5"

MAX_RETRY = 30
SLEEP = 5  # 秒

for attempt in range(1, MAX_RETRY + 1):
    try:
        print(f"\n[尝试 {attempt}/{MAX_RETRY}] 下载 {MODEL_ID}@{REVISION} ...")
        local_dir = snapshot_download(MODEL_ID, revision=REVISION)
        print(f"\n下载完成: {local_dir}")
        break
    except Exception as e:
        print(f"[失败 {attempt}] {type(e).__name__}: {str(e)[:300]}")
        if attempt == MAX_RETRY:
            print("已达最大重试次数，放弃。")
            raise
        time.sleep(SLEEP)

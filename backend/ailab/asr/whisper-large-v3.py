# -*- coding: UTF-8 -*-
"""
@Describe: 快速 demo / 冒烟测试
真正的 API 已经移到 ailab.asr.asr_service。
此文件保留以方便手动跑一次确认模型 + 网络都 OK。
"""

import sys
from pathlib import Path

# 让 from ailab.asr import * 在直接运行时也可用
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from ailab.asr import transcribe_audio

TEST_URL = (
    "https://bucket-silge-internal-products.oss-cn-shenzhen.aliyuncs.com/audio/"
    "%E4%B9%8C%E9%B8%A6%E5%92%8C%E7%8B%90%E7%8B%B8.wav"
)

if __name__ == "__main__":
    result = transcribe_audio(TEST_URL, language=None)
    print("text =", result["text"])
    print("segments =", len(result["segments"]))
    print(result)

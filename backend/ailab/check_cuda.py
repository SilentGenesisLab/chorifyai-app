# -*- coding: UTF-8 -*-
"""
CUDA / GPU 环境自检脚本。

用法:
    D:\\Anaconda3\\envs\\cuda23\\python.exe -m ailab.check_cuda
    # 或
    D:\\Anaconda3\\envs\\cuda23\\python.exe ailab\\check_cuda.py

依次检查:
    1. Python / OS / torch 版本
    2. CUDA 是否可用、cuDNN 是否启用
    3. 每张 GPU 的名字 / 显存 / 算力
    4. 跑一次小张量 matmul 验证 GPU 真的能算
    5. (可选) 加载 Whisper-large-v3, 确认实际 device
    6. ffmpeg 是否在 PATH

退出码:
    0 = 一切 OK
    1 = CUDA 不可用 (最常见: 装了 CPU 版 torch)
    2 = CUDA 可用但 GPU 算不出来 (驱动/显存问题)
"""

import os
import platform
import shutil
import subprocess
import sys
import time

# Windows 控制台 UTF-8
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass


# ---------- 输出工具 ----------

_OK = "[OK]   "
_WARN = "[WARN] "
_FAIL = "[FAIL] "
_INFO = "[..]   "


def _section(title: str):
    print()
    print("=" * 60)
    print(title)
    print("=" * 60)


# ---------- 1. 基础环境 ----------

def check_basics():
    _section("1. 基础环境")
    print(f"{_INFO}Python      : {sys.version.split()[0]} ({sys.executable})")
    print(f"{_INFO}OS          : {platform.platform()}")
    try:
        import torch
        print(f"{_OK}torch       : {torch.__version__}")
        print(f"{_INFO}torch built : CUDA={torch.version.cuda}  cuDNN={torch.backends.cudnn.version()}")
        return torch
    except ImportError:
        print(f"{_FAIL}torch 没装。先在 cuda23 环境装 GPU 版:")
        print("       pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121")
        sys.exit(1)


# ---------- 2. CUDA 可用性 ----------

def check_cuda(torch):
    _section("2. CUDA 可用性")
    avail = torch.cuda.is_available()
    if not avail:
        print(f"{_FAIL}torch.cuda.is_available() = False")
        print()
        print("可能原因 (按概率排):")
        print("  - 装的是 CPU 版 torch (torch.version.cuda 会是 None)")
        print("  - NVIDIA 驱动太旧, 跟 torch 编译的 CUDA 版本不匹配")
        print("  - 没装 NVIDIA 驱动")
        print()
        print("修复:")
        print("  1) pip uninstall torch torchvision torchaudio -y")
        print("  2) pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121")
        print("     (CUDA 11.8 选 cu118, CUDA 12.x 选 cu121)")
        print("  3) 装/升级 NVIDIA 驱动到 >= 525 (CUDA 12) 或 >= 450 (CUDA 11)")
        return False

    print(f"{_OK}torch.cuda.is_available() = True")
    print(f"{_INFO}device 数量 : {torch.cuda.device_count()}")
    print(f"{_INFO}cuDNN 启用  : {torch.backends.cudnn.enabled}  (version={torch.backends.cudnn.version()})")
    return True


# ---------- 3. GPU 详情 ----------

def check_gpus(torch):
    _section("3. GPU 详情")
    n = torch.cuda.device_count()
    for i in range(n):
        props = torch.cuda.get_device_properties(i)
        total_gb = props.total_memory / (1024 ** 3)
        print(f"{_OK}GPU {i}: {props.name}")
        print(f"       显存       : {total_gb:.1f} GB")
        print(f"       算力       : sm_{props.major}{props.minor}")
        print(f"       SM 数量    : {props.multi_processor_count}")
        if total_gb < 6:
            print(f"{_WARN}显存 < 6GB, Whisper-large-v3 fp16 可能 OOM, 考虑用 fp32+CPU 或换 medium 模型")


# ---------- 4. 真跑一次算子 ----------

def check_gpu_compute(torch):
    _section("4. GPU 计算冒烟测试 (matmul)")
    try:
        device = torch.device("cuda:0")
        torch.cuda.synchronize()
        t0 = time.time()
        a = torch.randn(2048, 2048, device=device, dtype=torch.float16)
        b = torch.randn(2048, 2048, device=device, dtype=torch.float16)
        c = a @ b
        torch.cuda.synchronize()
        dt = (time.time() - t0) * 1000
        print(f"{_OK}fp16 2048x2048 matmul 完成, 耗时 {dt:.1f} ms")
        print(f"{_INFO}结果范数   : {c.float().norm().item():.2f}")
        free, total = torch.cuda.mem_get_info(0)
        print(f"{_INFO}显存可用   : {free / 1024**3:.2f} / {total / 1024**3:.2f} GB")
        return True
    except Exception as e:
        print(f"{_FAIL}GPU 算不出来: {type(e).__name__}: {e}")
        print("  - 显存可能被其他进程吃光, 用 nvidia-smi 看一下")
        print("  - 驱动/CUDA runtime 不匹配, 重装驱动")
        return False


# ---------- 5. Whisper device 验证 (可选, 慢) ----------

def check_whisper():
    _section("5. Whisper 加载 device 验证")
    if "--skip-whisper" in sys.argv:
        print(f"{_INFO}跳过 (传了 --skip-whisper)")
        return
    if "--with-whisper" not in sys.argv:
        print(f"{_INFO}跳过. 加 --with-whisper 启用 (会下载/加载 3GB 模型, ~30s)")
        return

    # 跟 asr_service 一样, 先清代理避免 SSL 错
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
        os.environ.pop(k, None)

    try:
        import whisper
    except ImportError:
        print(f"{_FAIL}openai-whisper 没装: pip install -U openai-whisper")
        return

    cache = r"C:\Users\Admin\.cache\modelscope\hub\models\iic\Whisper-large-v3"
    print(f"{_INFO}加载 large-v3 (cache={cache}) ...")
    t0 = time.time()
    try:
        model = whisper.load_model("large-v3", download_root=cache)
    except Exception as e:
        print(f"{_FAIL}加载失败: {type(e).__name__}: {str(e)[:200]}")
        return
    dt = time.time() - t0
    print(f"{_OK}加载完成, 耗时 {dt:.1f}s, device={model.device}")
    if str(model.device) == "cpu":
        print(f"{_FAIL}模型跑在 CPU 上 -- 这就是 ASR 慢 10x 的根因")
    else:
        print(f"{_OK}模型在 GPU 上, ASR 应能跑出 RTF ~0.15")


# ---------- 6. ffmpeg ----------

def check_ffmpeg():
    _section("6. ffmpeg")
    exe = shutil.which("ffmpeg")
    if not exe:
        print(f"{_FAIL}ffmpeg 不在 PATH. transcribe_video / extract_audio_to_oss 会炸")
        print("       choco install ffmpeg -y   (Windows)")
        print("       sudo apt install ffmpeg   (Linux)")
        return
    print(f"{_OK}ffmpeg     : {exe}")
    try:
        out = subprocess.run([exe, "-version"], capture_output=True, text=True, timeout=5)
        first = (out.stdout or out.stderr).splitlines()[0]
        print(f"{_INFO}version    : {first}")
    except Exception as e:
        print(f"{_WARN}ffmpeg -version 失败: {e}")


# ---------- 主流程 ----------

def main():
    torch = check_basics()
    cuda_ok = check_cuda(torch)
    if not cuda_ok:
        check_ffmpeg()
        sys.exit(1)
    check_gpus(torch)
    compute_ok = check_gpu_compute(torch)
    check_whisper()
    check_ffmpeg()
    print()
    if not compute_ok:
        sys.exit(2)
    print("=" * 60)
    print("环境检查通过. 如果 ASR 仍慢, 用 `--with-whisper` 再跑一遍确认模型加载在 GPU")
    print("=" * 60)


if __name__ == "__main__":
    main()

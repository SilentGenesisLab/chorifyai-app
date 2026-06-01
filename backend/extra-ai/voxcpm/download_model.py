# -*- coding: UTF-8 -*-
"""
预下载 VoxCPM2 权重到 voxcpm/models/VoxCPM2 (server.py 默认就从这里加载)。

默认走 ModelScope (阿里, 国内直连, 不需要代理, 不会 DECRYPTION_FAILED_OR_BAD_RECORD_MAC)。
HF 老是 SSL 失败就别加 --hf。

用法 (复用 tor25 环境; 或双击 download_model.bat):
    D:\\Anaconda3\\envs\\tor25\\python.exe download_model.py            # ModelScope (推荐)
    D:\\Anaconda3\\envs\\tor25\\python.exe download_model.py --hf       # 改走 HuggingFace (hf-mirror)
    D:\\Anaconda3\\envs\\tor25\\python.exe download_model.py --dir D:\\models\\VoxCPM2
"""
import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DIR = os.path.join(HERE, "models", "VoxCPM2")

MS_MODEL_ID = "OpenBMB/VoxCPM2"   # ModelScope
HF_MODEL_ID = "openbmb/VoxCPM2"   # HuggingFace
MAX_RETRY = 30
SLEEP = 5  # 秒, 失败后重试间隔


def _clear_proxy(no_proxy: str):
    # 关键: 绕开代理 (DECRYPTION_FAILED_OR_BAD_RECORD_MAC 多半是代理 TLS 拦截导致)
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
        os.environ.pop(k, None)
    os.environ["NO_PROXY"] = no_proxy


def _download_modelscope(target: str) -> str:
    _clear_proxy("modelscope.cn,*.modelscope.cn,*.aliyuncs.com,*.aliyun.com")
    from modelscope import snapshot_download
    return snapshot_download(MS_MODEL_ID, local_dir=target)


def _download_hf(target: str) -> str:
    # 走 hf-mirror, 仍可能被代理 TLS 拦截; 实在不行用 Motrix 手动下大文件
    os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
    _clear_proxy("hf-mirror.com,*.hf-mirror.com,huggingface.co,*.huggingface.co")
    from huggingface_hub import snapshot_download
    return snapshot_download(HF_MODEL_ID, local_dir=target)


def _list_files(root: str):
    out = []
    for dirpath, _, names in os.walk(root):
        for n in names:
            p = os.path.join(dirpath, n)
            try:
                out.append((os.path.relpath(p, root), os.path.getsize(p)))
            except OSError:
                pass
    return out


def main():
    parser = argparse.ArgumentParser(description="下载 VoxCPM2 权重")
    parser.add_argument("--dir", default=DEFAULT_DIR, help=f"保存目录, 默认 {DEFAULT_DIR}")
    parser.add_argument("--hf", action="store_true", help="改用 HuggingFace (默认 ModelScope)")
    args = parser.parse_args()

    os.makedirs(args.dir, exist_ok=True)
    src = "HuggingFace (hf-mirror)" if args.hf else "ModelScope"
    download = _download_hf if args.hf else _download_modelscope

    print(f"目标目录: {args.dir}")
    print(f"下载源  : {src}")
    print(f"模型大小约 ~8GB (2B 参数), 国内 ModelScope 通常 10-50 MB/s")

    last_err = None
    for attempt in range(1, MAX_RETRY + 1):
        try:
            print(f"\n[尝试 {attempt}/{MAX_RETRY}] 下载 VoxCPM2 ...")
            local_dir = download(args.dir)
            print(f"\n下载完成: {local_dir}")
            break
        except KeyboardInterrupt:
            print("\n用户中断。")
            sys.exit(130)
        except Exception as e:
            last_err = e
            print(f"[失败 {attempt}] {type(e).__name__}: {str(e)[:300]}")
            if attempt == MAX_RETRY:
                print("已达最大重试次数, 放弃。")
                raise
            time.sleep(SLEEP)

    files = _list_files(args.dir)
    if not files:
        print("\n[警告] 目录为空, 下载可能失败。")
        if last_err:
            print(f"最后错误: {last_err}")
        sys.exit(1)

    files.sort()
    total = sum(s for _, s in files)
    print(f"\n共 {len(files)} 个文件, 合计 {total / 1e9:.2f} GB:")
    for name, size in files:
        print(f"  {size / 1e6:9.1f} MB  {name}")

    print(f"\n[完成] server.py 默认从这里加载 (MODEL_DIR={args.dir})")
    print("       启动服务:  .venv\\Scripts\\python.exe server.py --preload")


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""
VoxCPM2 本地部署自检脚本。
依次验证三条链路:
  1) 普通文本转语音 (TTS)
  2) Voice Design(纯文字描述造音色,无需参考音)
  3) 声音克隆(用第 1 步生成的 wav 作为参考音)
全部成功并能在 GPU 上出 wav,即视为部署成功。
"""
import os
import time
import torch
import soundfile as sf
from voxcpm import VoxCPM

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(HERE, "models", "VoxCPM2")
OUT_DIR = os.path.join(HERE, "outputs")
os.makedirs(OUT_DIR, exist_ok=True)


def main():
    print("=" * 60)
    print(f"CUDA available : {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"GPU            : {torch.cuda.get_device_name(0)}")
    print(f"Model dir      : {MODEL_DIR}")
    print("=" * 60)

    t0 = time.time()
    model = VoxCPM.from_pretrained(MODEL_DIR, load_denoiser=False)
    sr = model.tts_model.sample_rate
    print(f"[load] 模型加载完成,用时 {time.time() - t0:.1f}s,采样率 {sr}Hz")

    # 1) 普通 TTS
    t0 = time.time()
    wav = model.generate(
        text="欢迎使用 VoxCPM2,这是一次本地部署的语音合成测试。",
        cfg_value=2.0,
        inference_timesteps=10,
    )
    p1 = os.path.join(OUT_DIR, "01_tts.wav")
    sf.write(p1, wav, sr)
    print(f"[1/3] TTS 完成 -> {p1}  ({time.time() - t0:.1f}s)")

    # 2) Voice Design(描述造音色)
    t0 = time.time()
    wav = model.generate(
        text="(一位温柔甜美的年轻女性声音)你好,这是用文字描述生成的全新音色。",
        cfg_value=2.0,
        inference_timesteps=10,
    )
    p2 = os.path.join(OUT_DIR, "02_voice_design.wav")
    sf.write(p2, wav, sr)
    print(f"[2/3] Voice Design 完成 -> {p2}  ({time.time() - t0:.1f}s)")

    # 3) 声音克隆(用第 1 步的输出当参考音)
    t0 = time.time()
    wav = model.generate(
        text="这是克隆出来的声音,用来验证音色复刻链路是否正常工作。",
        reference_wav_path=p1,
        cfg_value=2.0,
        inference_timesteps=10,
    )
    p3 = os.path.join(OUT_DIR, "03_clone.wav")
    sf.write(p3, wav, sr)
    print(f"[3/3] 克隆 完成 -> {p3}  ({time.time() - t0:.1f}s)")

    print("=" * 60)
    print("全部通过 ✅  请试听 outputs/ 下的三个 wav。")


if __name__ == "__main__":
    main()

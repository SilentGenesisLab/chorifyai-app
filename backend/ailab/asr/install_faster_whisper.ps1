# 安装 faster-whisper + 预下载 CT2 权重 (Windows PowerShell)
#
# 用法:
#   .\ailab\asr\install_faster_whisper.ps1
#   .\ailab\asr\install_faster_whisper.ps1 -Python "D:\Anaconda3\envs\cuda23\python.exe"
#   .\ailab\asr\install_faster_whisper.ps1 -SkipDownload          # 只装 pip 包, 不预下载权重
#   .\ailab\asr\install_faster_whisper.ps1 -Model large-v3-turbo  # 换 turbo 模型 (体积更小)
#
# 脚本会做:
#   1. 清掉代理环境变量 (避免 SSL DECRYPTION_FAILED_OR_BAD_RECORD_MAC)
#   2. 设 HF_ENDPOINT=https://hf-mirror.com (国内拉 HuggingFace 必备)
#   3. 多源 fallback 装 faster-whisper (清华 -> 阿里 -> 中科大 -> 官方)
#   4. (默认) 触发一次模型加载, 提前下载 ~1.5GB CT2 权重到 ~/.cache/huggingface/hub/

[CmdletBinding()]
param(
    [string]$Python = "D:\Anaconda3\envs\tor25\python.exe",
    [string]$Model = "large-v3",
    [switch]$SkipDownload
)

$ErrorActionPreference = "Stop"

function Write-Section($title) {
    Write-Host ""
    Write-Host "=" * 60 -ForegroundColor Cyan
    Write-Host $title -ForegroundColor Cyan
    Write-Host "=" * 60 -ForegroundColor Cyan
}

# --- 1. 检查 Python ---
Write-Section "1. 检查 Python"
if (-not (Test-Path $Python)) {
    Write-Error "Python 不存在: $Python  (用 -Python 参数指定正确路径)"
    exit 1
}
& $Python --version
if ($LASTEXITCODE -ne 0) {
    Write-Error "Python 不能运行: $Python"
    exit 1
}

# --- 2. 清代理 + 配 HF 镜像 ---
Write-Section "2. 准备网络环境"
$env:HTTP_PROXY = ""
$env:HTTPS_PROXY = ""
$env:ALL_PROXY = ""
$env:http_proxy = ""
$env:https_proxy = ""
$env:NO_PROXY = "*"
$env:HF_ENDPOINT = "https://hf-mirror.com"
Write-Host "[OK] 关掉代理 (HTTP_PROXY/HTTPS_PROXY/ALL_PROXY = '')"
Write-Host "[OK] HF_ENDPOINT = $env:HF_ENDPOINT"

# --- 3. 多源 fallback 装 pip 包 ---
Write-Section "3. 安装 faster-whisper (多镜像源 fallback)"

$mirrors = @(
    @{ url = "https://pypi.tuna.tsinghua.edu.cn/simple"; host = "pypi.tuna.tsinghua.edu.cn"; name = "清华" },
    @{ url = "https://mirrors.aliyun.com/pypi/simple";   host = "mirrors.aliyun.com";        name = "阿里" },
    @{ url = "https://pypi.mirrors.ustc.edu.cn/simple";  host = "pypi.mirrors.ustc.edu.cn";  name = "中科大" },
    @{ url = "https://pypi.org/simple";                  host = "pypi.org";                  name = "官方" }
)

$installed = $false
foreach ($m in $mirrors) {
    Write-Host ""
    Write-Host "尝试 $($m.name) 源: $($m.url)" -ForegroundColor Yellow

    $args = @(
        "-m", "pip", "install",
        "-i", $m.url,
        "--trusted-host", $m.host
    )
    if ($m.host -eq "pypi.org") {
        # 官方源还要信任 files.pythonhosted.org (实际下载文件的域名)
        $args += @("--trusted-host", "files.pythonhosted.org")
    }
    $args += "faster-whisper"

    & $Python @args
    if ($LASTEXITCODE -eq 0) {
        $installed = $true
        Write-Host "[OK] 从 $($m.name) 源装好了" -ForegroundColor Green
        break
    }
    Write-Host "[FAIL] $($m.name) 源失败, 试下一个..." -ForegroundColor Red
}

if (-not $installed) {
    Write-Host ""
    Write-Host "所有镜像源都失败. 建议手动下载 wheel:" -ForegroundColor Red
    Write-Host "  浏览器打开 https://pypi.org/project/faster-whisper/#files"
    Write-Host "  下 *.whl, 然后: $Python -m pip install <下载的wheel路径>"
    exit 1
}

# --- 4. import 验证 ---
Write-Section "4. import 验证"
& $Python -c "from faster_whisper import WhisperModel; import faster_whisper; print('faster_whisper version:', faster_whisper.__version__)"
if ($LASTEXITCODE -ne 0) {
    Write-Error "faster_whisper 装上了但 import 失败"
    exit 1
}

# --- 5. (可选) 预下载 CT2 权重 ---
if ($SkipDownload) {
    Write-Section "5. 跳过权重下载 (-SkipDownload)"
    Write-Host "首次调用 API 时会自动下载 ~1.5GB 权重到 ~/.cache/huggingface/hub/"
    exit 0
}

Write-Section "5. 预下载 CT2 权重 ($Model)"
Write-Host "约 1.5GB, 走 hf-mirror.com, 国内下行速度通常 5-20 MB/s"
Write-Host "缓存路径: $env:USERPROFILE\.cache\huggingface\hub\"
Write-Host ""

# 用 CPU + float32 加载只为触发权重下载, 不实际推理. 避免显存抢占当前可能在跑的 uvicorn.
& $Python -c @"
import os
os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'
# 关 huggingface_hub 自带代理
for k in ('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy'):
    os.environ.pop(k, None)
print('[..] 触发模型下载/加载...')
from faster_whisper import WhisperModel
m = WhisperModel('$Model', device='cpu', compute_type='float32')
print('[OK] 权重已就绪')
"@

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "权重下载失败. 可能原因:" -ForegroundColor Red
    Write-Host "  - 网络抽风, 重跑脚本一般就好 (HF 镜像会断点续传)"
    Write-Host "  - HF mirror 当前不通, 试设 `$env:HF_ENDPOINT='https://hf.api.bayes.com'"
    Write-Host "  - 磁盘空间不够 (需要 ~1.5GB)"
    exit 1
}

# --- 6. 结束 ---
Write-Section "完成"
Write-Host "[OK] faster-whisper 装好"
Write-Host "[OK] 权重已缓存到 $env:USERPROFILE\.cache\huggingface\hub\"
Write-Host ""
Write-Host "下一步: 重启 uvicorn, 默认引擎已经是 faster"
Write-Host "  uvicorn ailab.api.server:app --host 0.0.0.0 --port 8089"

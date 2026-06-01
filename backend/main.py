# -*- coding: UTF-8 -*-
"""
chorify-video 本地开发 supervisor。

进程模型 (跟生产 docker-compose 对齐):
    main.py (守护父进程, 不加载任何模型)
       ├─ subprocess: ailab uvicorn  (:8089)  — ASR + 翻译 + ElevenLabs + voxcpm 网关
       └─ subprocess: voxcpm server  (:8190)  — VoxCPM2 TTS

特性:
  - 每个子进程 stdout/stderr 加 [name] 前缀实时输出, 一个窗口看全
  - 子进程非 0 退出 -> 指数退避自动重启 (1s, 2s, 4s, ..., 60s 封顶)
  - Ctrl+C 优雅终止 (terminate 5s, 兜底 kill)
  - 启动后 60s 拉一次 /health 报告状态
  - 跨平台 (Windows / Linux)

用法:
    python main.py                          # 启全部服务
    python main.py --only ailab             # 只启 ailab
    python main.py --only voxcpm            # 只启 voxcpm
    SERVICES=ailab python main.py           # 环境变量也可
    python main.py --no-restart             # 子进程崩了不自动重启 (调试用)
    python main.py --python <path>          # 指定 python 解释器
"""
import argparse
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path


# ============================================================================
# Windows Job Object: 父进程死亡时 kernel 自动强杀所有子进程
# ----------------------------------------------------------------------------
# 必须的原因: Python subprocess.Popen 在 Windows 上启动的子进程跟父进程没有 cgroup
# 一样的耦合, 父进程 Ctrl+C / 崩溃时子进程变成孤儿, 还占着端口/显存. 之前 taskkill /F
# 因 CUDA driver kernel-mode lock 杀不掉这种孤儿. Job Object 是 Windows kernel
# 提供的强制清理机制, 等价于 Linux cgroup, 父死子必死, 锁也救不了.
# ============================================================================

_WIN_JOB = None  # (kernel32, hJob) 句柄, _create_job_object() 之后非 None


def _create_job_object():
    """创建 Windows Job Object 并设 KILL_ON_JOB_CLOSE; 失败返回 None 不影响主流程。"""
    global _WIN_JOB
    if os.name != "nt" or _WIN_JOB is not None:
        return
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel32.OpenProcess.restype = wintypes.HANDLE

    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        return

    class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_uint64),
            ("WriteOperationCount", ctypes.c_uint64),
            ("OtherOperationCount", ctypes.c_uint64),
            ("ReadTransferCount", ctypes.c_uint64),
            ("WriteTransferCount", ctypes.c_uint64),
            ("OtherTransferCount", ctypes.c_uint64),
        ]

    class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
    JobObjectExtendedLimitInformation = 9

    info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE

    ok = kernel32.SetInformationJobObject(
        job, JobObjectExtendedLimitInformation,
        ctypes.byref(info), ctypes.sizeof(info),
    )
    if not ok:
        kernel32.CloseHandle(job)
        return

    _WIN_JOB = (kernel32, job)


def _assign_pid_to_job(pid: int) -> bool:
    """把子进程 PID 加入 Job Object; 加入后父进程一死 kernel 自动 kill 它。"""
    if _WIN_JOB is None:
        return False
    kernel32, job = _WIN_JOB
    PROCESS_SET_QUOTA = 0x0100
    PROCESS_TERMINATE = 0x0001
    h = kernel32.OpenProcess(PROCESS_SET_QUOTA | PROCESS_TERMINATE, False, pid)
    if not h:
        return False
    try:
        return bool(kernel32.AssignProcessToJobObject(job, h))
    finally:
        kernel32.CloseHandle(h)

HERE = Path(__file__).resolve().parent

# Windows 控制台开 VT100 ANSI 模式 (PowerShell 7 / Windows Terminal / vscode 默认就支持; 老 cmd 兜底)
if os.name == "nt":
    try:
        os.system("")
    except Exception:
        pass

COLORS = {
    "ailab":  "\033[36m",  # 青
    "voxcpm": "\033[35m",  # 紫
    "supervisor": "\033[33m",  # 黄
}
RESET = "\033[0m"


def _resolve_voxcpm_python(default_python: str) -> str:
    """
    选 voxcpm 子进程的 python 解释器:
      1) VOXCPM_PYTHON 环境变量 (用户显式指定)
      2) 仓库自带的 WinPython 包 (ailab2026/VoxCPM2/WPy64-312101/python/python.exe)
         -- torch 2.8 + cu128, voxcpm 2.0.2 已验证能跑
      3) 默认 (sys.executable, 通常 tor25 的 torch 2.5.1 -- 加载 voxcpm 会段错误)
    """
    env = os.environ.get("VOXCPM_PYTHON")
    if env and Path(env).is_file():
        return env
    winpy = HERE / "ailab2026" / "VoxCPM2" / "WPy64-312101" / "python" / "python.exe"
    if winpy.is_file():
        return str(winpy)
    return default_python


def _service_config(default_python: str) -> dict:
    """
    子服务定义。
    每个服务的 python 可单独覆盖:
      - AILAB_PYTHON  环境变量, 没设用 default_python (通常 tor25)
      - VOXCPM_PYTHON 环境变量, 没设自动找仓库内的 WinPython (见 _resolve_voxcpm_python)
    这样 voxcpm 走 torch 2.8 / ailab 走 tor25, 两边互不污染。
    """
    ailab_python  = os.environ.get("AILAB_PYTHON",  default_python)
    voxcpm_python = _resolve_voxcpm_python(default_python)
    return {
        "ailab": {
            # -u 强制 unbuffered stdout/stderr, 避免子进程 print 被 PIPE buffer 吞 (Windows 上 PYTHONUNBUFFERED 不够稳)
            "cmd": [ailab_python, "-u", "-m", "uvicorn", "ailab.api.server:app",
                    "--host", "0.0.0.0", "--port", "8089"],
            "cwd": str(HERE),
            "health_url": "http://127.0.0.1:8089/health",
            "boot_grace_sec": 60,  # 模型加载慢 (faster-whisper 首次), 留够时间
        },
        "voxcpm": {
            "cmd": [voxcpm_python, "-u", "server.py",
                    "--host", "0.0.0.0", "--port", "8190", "--preload"],
            "cwd": str(HERE / "voxcpm"),
            "health_url": "http://127.0.0.1:8190/health",
            "boot_grace_sec": 60,
        },
    }


class Service(threading.Thread):
    def __init__(self, name: str, conf: dict, restart: bool = True):
        super().__init__(daemon=True, name=name)
        self.name = name
        self.conf = conf
        self.restart = restart
        self.stopping = False
        self.proc: subprocess.Popen | None = None
        self.backoff = 1.0  # 指数退避起点 (秒)
        self.color = COLORS.get(name, "")

    # -------- 日志 --------
    def _log_line(self, line: str, tag: str = ""):
        prefix = f"{self.color}[{self.name}{tag}]{RESET}"
        sys.stdout.write(f"{prefix} {line}")
        sys.stdout.flush()

    def _log(self, line: str):
        self._log_line(line + ("\n" if not line.endswith("\n") else ""), tag=":sup")

    def _tail(self, stream):
        try:
            for line in iter(stream.readline, ""):
                if line:
                    sys.stdout.write(f"{self.color}[{self.name}]{RESET} {line}")
                    sys.stdout.flush()
        except Exception as e:
            self._log(f"tail 异常: {e}")
        finally:
            try:
                stream.close()
            except Exception:
                pass

    # -------- 端口预检 --------
    def _health_port(self) -> int:
        """从 health_url 抽出端口号, 用于启动前检测端口是否还被旧进程占着。"""
        return urllib.parse.urlparse(self.conf["health_url"]).port or 0

    def _wait_port_free(self, port: int, timeout: float = 15.0) -> bool:
        """轮询本机 port 是否空闲。True = 已空闲; False = timeout 内仍被占。"""
        deadline = time.time() + timeout
        while time.time() < deadline and not self.stopping:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                s.settimeout(0.3)
                connected = s.connect_ex(("127.0.0.1", port)) == 0
            finally:
                s.close()
            if not connected:
                return True
            time.sleep(0.5)
        return False

    def _kill_port_holder(self, port: int):
        """Windows: 找出 LISTEN 在 port 上的 PID, taskkill /F /T 杀掉 (用于上轮孤儿进程)。"""
        if os.name != "nt":
            return
        try:
            out = subprocess.run(
                ["netstat", "-ano"], capture_output=True, text=True, timeout=5
            ).stdout or ""
        except Exception:
            return
        pids = set()
        token = f":{port} "
        for line in out.splitlines():
            if token in line and "LISTENING" in line:
                parts = line.split()
                if parts and parts[-1].isdigit():
                    pids.add(parts[-1])
        for pid in pids:
            self._log(f"taskkill /F /T /PID {pid} (占用 {port})")
            try:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", pid],
                    timeout=10,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception as e:
                # taskkill 超时 99% 是 CUDA driver 在内核态锁住进程, 用户态 kill 工具全部无效
                self._log(f"taskkill PID {pid} 失败 (大概率 CUDA 锁死内核态): {e}")
                self._log(f"  → 终极解法 (管理员 PowerShell):  Restart-Service NVDisplay.ContainerLocalSystem -Force")

    # -------- 子进程生命周期 --------
    def _start_proc(self):
        self.proc = subprocess.Popen(
            self.conf["cmd"],
            cwd=self.conf["cwd"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            encoding="utf-8",
            errors="replace",
            env={**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"},
        )

        # Windows: 立刻把子进程加入 Job Object, 父死必然带子死 (kernel 强杀)
        if os.name == "nt":
            ok = _assign_pid_to_job(self.proc.pid)
            if not ok:
                self._log(f"[警告] PID {self.proc.pid} 加入 Job Object 失败, Ctrl+C 后可能成孤儿")

        threading.Thread(target=self._tail, args=(self.proc.stdout,), daemon=True).start()

    def _health_check_later(self):
        """子进程启动 boot_grace_sec 秒后拉一次 /health, 报告是否就绪。"""
        grace = self.conf["boot_grace_sec"]
        time.sleep(grace)
        if self.stopping or not self.proc or self.proc.poll() is not None:
            return
        try:
            with urllib.request.urlopen(self.conf["health_url"], timeout=3.0) as r:
                if 200 <= r.status < 300:
                    self._log(f"/health OK ({grace}s 内就绪)")
                    return
                self._log(f"/health 异常状态码 {r.status}")
        except Exception as e:
            self._log(f"/health 探活失败: {type(e).__name__}: {e}")

    def run(self):
        while not self.stopping:
            # 启动前确认端口真空闲, 避免上一轮孤儿进程还占着导致新进程 bind 失败循环重启
            port = self._health_port()
            if port and not self._wait_port_free(port, timeout=15.0):
                self._log(f"[警告] 端口 {port} 仍被占用 (上次未释放). 尝试 taskkill 占用者")
                self._kill_port_holder(port)
                if not self._wait_port_free(port, timeout=5.0):
                    self._log(f"[错误] 端口 {port} 仍未释放, 跳过本轮启动, 退避后再试")
                    self._sleep_backoff()
                    continue

            self._log(f"启动: {' '.join(self.conf['cmd'])}")
            try:
                self._start_proc()
            except Exception as e:
                self._log(f"启动失败: {type(e).__name__}: {e}")
                if not self.restart:
                    return
                self._sleep_backoff()
                continue

            threading.Thread(target=self._health_check_later, daemon=True).start()

            rc = self.proc.wait()
            if self.stopping:
                self._log("收到停止信号, 退出。")
                return
            self._log(f"子进程退出 (rc={rc})")

            if not self.restart:
                return

            self._sleep_backoff()

    def _sleep_backoff(self):
        sleep_for = min(self.backoff, 60)
        self._log(f"{sleep_for:.0f}s 后重启 (指数退避)")
        # 退避也要响应停止信号: 分片 sleep
        slept = 0.0
        while slept < sleep_for and not self.stopping:
            time.sleep(0.5)
            slept += 0.5
        self.backoff *= 2

    # -------- 停止 --------
    def stop(self):
        self.stopping = True
        if not self.proc or self.proc.poll() is not None:
            return
        self._log("发送 terminate ...")

        # Windows 上 proc.terminate() / proc.kill() 调 TerminateProcess(), CUDA driver 锁住的
        # 进程经常"成功返回但其实僵尸化", PID 还在端口不放. 用 taskkill /F /T 杀整个进程树,
        # 比单纯 TerminateProcess 更狠 (能拉起 nvidia driver 强制释放 cuda context).
        if os.name == "nt":
            try:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(self.proc.pid)],
                    timeout=15,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception as e:
                self._log(f"taskkill 失败, 回退 terminate(): {e}")
                try:
                    self.proc.terminate()
                except Exception:
                    pass
        else:
            try:
                self.proc.terminate()
            except Exception as e:
                self._log(f"terminate 失败: {e}")

        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self._log("10s 内未退, 最后一击 kill")
            try:
                self.proc.kill()
            except Exception as e:
                self._log(f"kill 失败: {e}")
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._log("[警告] 进程拒不退出, 可能 CUDA 锁死. 端口未必立刻释放, 重启 NVIDIA 服务可强制清理")


def _sup_log(msg: str):
    color = COLORS["supervisor"]
    sys.stdout.write(f"{color}[supervisor]{RESET} {msg}\n")
    sys.stdout.flush()


def _diagnose_port(port: int):
    """报告占用 port 的进程 PID + 命令行 (Windows)。诊断函数, 绝不抛异常。"""
    if os.name != "nt":
        return
    try:
        try:
            out = subprocess.run(
                ["netstat", "-ano"], capture_output=True, text=True, timeout=5
            ).stdout or ""
        except Exception:
            return
        pids = set()
        for line in out.splitlines():
            if f":{port} " in line and "LISTENING" in line:
                parts = line.split()
                if parts and parts[-1].isdigit():
                    pids.add(parts[-1])
        if not pids:
            return
        _sup_log(f"[preflight] 端口 {port} 已被占用, PID: {', '.join(pids)}")
        # 拿命令行: 优先 PowerShell Get-CimInstance (Win 11 24H2 移除了 wmic)
        for pid in pids:
            cmd_line = None
            try:
                r = subprocess.run(
                    ["powershell", "-NoProfile", "-Command",
                     f"(Get-CimInstance Win32_Process -Filter 'ProcessId={pid}').CommandLine"],
                    capture_output=True, text=True, timeout=10,
                )
                if r.returncode == 0 and r.stdout:
                    cmd_line = r.stdout.strip()
            except Exception:
                pass
            if not cmd_line:
                # 退到 tasklist (只能拿到 image name, 没 commandline)
                try:
                    r = subprocess.run(
                        ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                        capture_output=True, text=True, timeout=5,
                    )
                    if r.stdout:
                        cmd_line = r.stdout.strip()
                except Exception:
                    pass
            _sup_log(f"  PID {pid}: {(cmd_line or '<unknown>')[:160]}")
    except Exception as e:
        _sup_log(f"[preflight] _diagnose_port({port}) 异常 (忽略, 不影响启动): {type(e).__name__}: {e}")


def _can_bind(port: int) -> bool:
    """尝试 bind 0.0.0.0:port 验证端口真可用 (netstat 看不到 port reservation, 这能看到)。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("0.0.0.0", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def main():
    parser = argparse.ArgumentParser(description="chorify-video 本地服务 supervisor")
    parser.add_argument("--only", action="append",
                        choices=["ailab", "voxcpm"],
                        help="只启指定服务 (可重复; 等价于 SERVICES 环境变量)")
    parser.add_argument("--no-restart", action="store_true",
                        help="子进程崩了不自动重启 (调试用)")
    parser.add_argument("--python", default=sys.executable,
                        help=f"子进程 python 解释器, 默认 {sys.executable}")
    args = parser.parse_args()

    # Windows: 创建 Job Object, 后面 spawn 的子进程都加入它, 父死带子死
    _create_job_object()
    if os.name == "nt":
        _sup_log(f"Job Object: {'已创建 (父死必然带子死)' if _WIN_JOB else '创建失败, 退化到 taskkill 兜底'}")

    # 启动前自检 8089/8190 是否真能 bind
    for port in (8089, 8190):
        if _can_bind(port):
            _sup_log(f"[preflight] 端口 {port} 可用")
        else:
            _sup_log(f"[preflight] 端口 {port} 不可用, 启动后大概率 bind 失败")
            _diagnose_port(port)

    configs = _service_config(args.python)

    # 决定要启的服务
    if args.only:
        wanted = list(dict.fromkeys(args.only))   # 去重保序
    elif os.environ.get("SERVICES"):
        wanted = [s.strip() for s in os.environ["SERVICES"].split(",") if s.strip()]
    else:
        wanted = list(configs.keys())

    bad = [s for s in wanted if s not in configs]
    if bad:
        _sup_log(f"未知服务: {bad}; 可用: {list(configs.keys())}")
        sys.exit(2)

    _sup_log(f"启动: {wanted}  (restart={'no' if args.no_restart else 'yes'})")
    _sup_log(f"python: {args.python}")

    services = [Service(name, configs[name], restart=not args.no_restart) for name in wanted]
    for s in services:
        s.start()

    try:
        while any(s.is_alive() for s in services):
            time.sleep(0.5)
    except KeyboardInterrupt:
        _sup_log("收到 Ctrl+C, 正在停止子进程 ...")
        for s in services:
            s.stop()
        for s in services:
            s.join(timeout=10)
        _sup_log("全部退出。")


if __name__ == "__main__":
    main()

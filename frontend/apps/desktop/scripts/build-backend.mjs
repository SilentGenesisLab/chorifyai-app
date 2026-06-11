import { spawnSync } from "node:child_process";
import { existsSync, rmSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(scriptDir, "../../../..");
const backendRoot = path.join(repoRoot, "backend");
const hostPython = process.env.PYTHON ?? "python";
const venvRoot = path.join(backendRoot, ".venv-desktop");
const venvPython = process.platform === "win32"
  ? path.join(venvRoot, "Scripts", "python.exe")
  : path.join(venvRoot, "bin", "python");
const installMarker = path.join(venvRoot, ".desktop-deps-installed");
const condaDllRoot = process.env.CONDA_PREFIX
  ? path.join(process.env.CONDA_PREFIX, "Library", "bin")
  : "D:\\Anaconda3\\Library\\bin";

function run(cmd, args, cwd = backendRoot) {
  const result = spawnSync(cmd, args, {
    cwd,
    stdio: "inherit",
    shell: process.platform === "win32",
    env: {
      ...process.env,
      PIP_CONFIG_FILE: process.platform === "win32" ? "NUL" : "/dev/null",
      PYTHONUTF8: "1",
      PYTHONIOENCODING: "utf-8"
    }
  });
  if (result.error) {
    console.error(result.error);
  }
  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }
}

if (!existsSync(venvPython)) {
  run(hostPython, ["-m", "venv", venvRoot]);
}

if (!existsSync(installMarker)) {
  const pipBase = [
    "-m",
    "pip",
    "install",
    "--index-url",
    "https://pypi.tuna.tsinghua.edu.cn/simple",
    "--retries",
    "10",
    "--timeout",
    "120"
  ];
  run(venvPython, [...pipBase, "--upgrade", "pip"]);
  run(venvPython, [...pipBase, "-r", "requirements.txt", "pyinstaller"]);
  writeFileSync(installMarker, new Date().toISOString());
}

rmSync(path.join(backendRoot, "build", "chorify-backend"), { recursive: true, force: true });
rmSync(path.join(backendRoot, "dist", "chorify-backend"), { recursive: true, force: true });
rmSync(path.join(backendRoot, "chorify-backend.spec"), { force: true });

const args = [
  "-m",
  "PyInstaller",
  "--noconfirm",
  "--clean",
  "--onedir",
  "--console",
  "--name",
  "chorify-backend",
  "--hidden-import=uvicorn.loops.auto",
  "--hidden-import=uvicorn.protocols.http.auto",
  "--hidden-import=uvicorn.protocols.websockets.auto",
  "--hidden-import=uvicorn.lifespan.on",
  "--collect-all",
  "uvicorn",
  "--collect-all",
  "pydantic_settings",
];

for (const dllName of ["ffi.dll", "liblzma.dll", "LIBBZ2.dll"]) {
  const dllPath = path.join(condaDllRoot, dllName);
  if (existsSync(dllPath)) {
    args.push("--add-binary", `${dllPath}${path.delimiter}.`);
  }
}

args.push("desktop_backend.py");

run(venvPython, args);

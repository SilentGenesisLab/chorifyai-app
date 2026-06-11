import { app, BrowserWindow, Menu, dialog, shell } from "electron";
import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import getPort from "get-port";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const isPackaged = app.isPackaged;
const PACKAGED_API_PORT = 8917;
const PACKAGED_WEB_PORT = 8918;

type ManagedProcess = {
  name: string;
  child: ChildProcessWithoutNullStreams;
};

const processes: ManagedProcess[] = [];

function repoRoot() {
  if (isPackaged) {
    return path.join(process.resourcesPath);
  }
  return path.resolve(__dirname, "../../../..");
}

function frontendRoot() {
  return isPackaged ? process.resourcesPath : path.resolve(repoRoot(), "frontend");
}

function backendRoot() {
  return isPackaged ? path.join(process.resourcesPath, "backend") : path.resolve(repoRoot(), "backend");
}

function webRoot() {
  return isPackaged ? path.join(process.resourcesPath, "apps", "web") : path.join(frontendRoot(), "apps", "web");
}

function packagedWebServerScript() {
  const standaloneRoot = path.join(process.resourcesPath, "apps", "web", "standalone");
  const candidates = [
    path.join(standaloneRoot, "server.js"),
    path.join(standaloneRoot, "frontend", "apps", "web", "server.js"),
    path.join(standaloneRoot, "apps", "web", "server.js")
  ];
  const found = candidates.find((candidate) => existsSync(candidate));
  if (!found) {
    throw new Error(`Cannot find packaged Next server.js. Tried: ${candidates.join(", ")}`);
  }
  return found;
}

function defaultLocalStorageRoot() {
  return path.join(app.getPath("documents"), "ChorifyAI", "workspace");
}

function command(name: string) {
  return process.platform === "win32" ? `${name}.cmd` : name;
}

function pythonCommand() {
  return process.platform === "win32" ? "python.exe" : "python";
}

function logProcess(name: string, child: ChildProcessWithoutNullStreams) {
  child.stdout.on("data", (chunk) => console.log(`[${name}] ${chunk.toString().trimEnd()}`));
  child.stderr.on("data", (chunk) => console.error(`[${name}] ${chunk.toString().trimEnd()}`));
  child.on("exit", (code, signal) => console.log(`[${name}] exited code=${code} signal=${signal}`));
}

function spawnManaged(name: string, cmd: string, args: string[], cwd: string, env: NodeJS.ProcessEnv = {}) {
  const child = spawn(cmd, args, {
    cwd,
    env: {
      ...process.env,
      ...env,
      NODE_ENV: env.NODE_ENV ?? process.env.NODE_ENV,
      PYTHONIOENCODING: "utf-8"
    },
    windowsHide: true,
    shell: process.platform === "win32"
  });
  logProcess(name, child);
  processes.push({ name, child });
  return child;
}

async function waitForHttp(url: string, timeoutMs: number) {
  const deadline = Date.now() + timeoutMs;
  let lastError: unknown;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url, { method: "GET" });
      if (response.status >= 200 && response.status < 500) {
        return;
      }
      lastError = new Error(`HTTP ${response.status}`);
    } catch (error) {
      lastError = error;
    }
    await new Promise((resolve) => setTimeout(resolve, 750));
  }
  throw new Error(`Timed out waiting for ${url}: ${lastError instanceof Error ? lastError.message : String(lastError)}`);
}

async function assertPortFree(port: number, label: string) {
  const availablePort = await getPort({ port });
  if (availablePort !== port) {
    throw new Error(`${label} port ${port} is already in use. Close the process using it and restart ChorifyAI.`);
  }
}

async function startBackend(port: number, webPort: number) {
  const cwd = backendRoot();
  spawnManaged(
    "fastapi",
    pythonCommand(),
    ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", String(port)],
    cwd,
    {
      MOCK_MODE: process.env.MOCK_MODE ?? process.env.CHORIFY_MOCK_MODE ?? "true",
      OSS_PROVIDER: process.env.OSS_PROVIDER ?? "local",
      LOCAL_STORAGE_ROOT: process.env.LOCAL_STORAGE_ROOT ?? defaultLocalStorageRoot(),
      LOCAL_STORAGE_CONFIG: process.env.LOCAL_STORAGE_CONFIG ?? path.join(app.getPath("userData"), "local-storage.json"),
      CORS_ORIGINS: process.env.CORS_ORIGINS ?? `http://127.0.0.1:${webPort},http://localhost:${webPort}`
    }
  );
  await waitForHttp(`http://127.0.0.1:${port}/health`, 60_000);
}

async function startWeb(webPort: number, apiPort: number) {
  if (isPackaged) {
    const serverScript = packagedWebServerScript();
    spawnManaged(
      "next",
      process.execPath,
      [serverScript],
      path.dirname(serverScript),
      {
        ELECTRON_RUN_AS_NODE: "1",
        NODE_ENV: "production",
        PORT: String(webPort),
        HOSTNAME: "127.0.0.1",
        AI_SERVICE_URL: `http://127.0.0.1:${apiPort}`,
        NEXT_PUBLIC_APP_NAME: process.env.NEXT_PUBLIC_APP_NAME ?? "ChorifyAI"
      }
    );
  } else {
    const cwd = webRoot();
    spawnManaged(
      "next",
      command("pnpm"),
      ["exec", "next", "dev", "-p", String(webPort)],
      cwd,
      {
        AI_SERVICE_URL: `http://127.0.0.1:${apiPort}`,
        NEXT_DIST_DIR: ".next-desktop-dev",
        NEXT_PUBLIC_APP_NAME: process.env.NEXT_PUBLIC_APP_NAME ?? "ChorifyAI"
      }
    );
  }
  await waitForHttp(`http://127.0.0.1:${webPort}`, 120_000);
}

async function createWindow(url: string) {
  const win = new BrowserWindow({
    width: 1440,
    height: 920,
    minWidth: 1100,
    minHeight: 760,
    title: "ChorifyAI",
    backgroundColor: "#f6f4ef",
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true
    }
  });

  await win.loadURL(url);

  win.webContents.setWindowOpenHandler(({ url: target }) => {
    shell.openExternal(target);
    return { action: "deny" };
  });
}

async function boot() {
  const apiPort = isPackaged
    ? PACKAGED_API_PORT
    : Number(process.env.CHORIFY_API_PORT) || await getPort({ port: 8000 });
  const webPort = isPackaged
    ? PACKAGED_WEB_PORT
    : Number(process.env.CHORIFY_WEB_PORT) || await getPort({ port: 3001 });

  try {
    if (isPackaged) {
      await assertPortFree(apiPort, "Backend");
      await assertPortFree(webPort, "Web");
    }
    await startBackend(apiPort, webPort);
    await startWeb(webPort, apiPort);
    await createWindow(`http://localhost:${webPort}`);
  } catch (error) {
    console.error(error);
    await dialog.showMessageBox({
      type: "error",
      title: "ChorifyAI startup failed",
      message: "Local services failed to start",
      detail: error instanceof Error ? error.stack ?? error.message : String(error)
    });
    app.quit();
  }
}

function stopManagedProcesses() {
  for (const item of processes.splice(0)) {
    if (item.child.exitCode !== null || item.child.killed) continue;
    if (process.platform === "win32") {
      const killer = spawn("taskkill.exe", ["/pid", String(item.child.pid), "/f", "/t"], { windowsHide: true, shell: true });
      killer.on("error", (error) => console.error(`[desktop] failed to stop ${item.name}:`, error));
    } else {
      item.child.kill("SIGTERM");
    }
  }
}

Menu.setApplicationMenu(null);

app.whenReady().then(boot);

app.on("window-all-closed", () => {
  stopManagedProcesses();
  if (process.platform !== "darwin") app.quit();
});

app.on("before-quit", stopManagedProcesses);

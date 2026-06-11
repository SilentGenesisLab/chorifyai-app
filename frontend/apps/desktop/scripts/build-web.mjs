import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const frontendRoot = path.resolve(scriptDir, "../../..");
const pnpm = "pnpm";

const result = spawnSync(pnpm, ["--filter", "@chorify/web", "build"], {
  cwd: frontendRoot,
  stdio: "inherit",
  shell: process.platform === "win32",
  env: {
    ...process.env,
    CHORIFY_DESKTOP_STANDALONE: "true",
    AI_SERVICE_URL: process.env.CHORIFY_DESKTOP_AI_SERVICE_URL ?? "http://127.0.0.1:8917",
    NEXT_DIST_DIR: ".next"
  }
});

if (result.error) {
  console.error(result.error);
}

process.exit(result.status ?? 1);

import { defineConfig } from '@playwright/test'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const frontendDir = path.dirname(fileURLToPath(import.meta.url))
const appDir = path.resolve(frontendDir, '..')
const baseURL = process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:5174/hook-studio/'

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  expect: { timeout: 12_000 },
  reporter: [['list'], ['html', { open: 'never', outputFolder: 'playwright-report' }]],
  outputDir: 'test-results',
  use: {
    baseURL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'off',
    launchOptions: {
      executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
      args: ['--disable-gpu'],
    },
  },
  projects: [
    { name: 'desktop-chrome', use: { viewport: { width: 1440, height: 1000 } } },
    { name: 'mobile-chrome', use: { viewport: { width: 390, height: 844 }, isMobile: true } },
  ],
  webServer: process.env.PLAYWRIGHT_EXTERNAL_SERVERS ? undefined : [
    {
      command: 'powershell -NoProfile -Command "$env:HOOK_STUDIO_BASE_PATH=\'/hook-studio\'; $env:HOOK_STUDIO_DATA_DIR=\'./data/e2e\'; $env:HOOK_STUDIO_ACCESS_CODES_FILE=\'./config/access_codes.yaml\'; $env:HOOK_STUDIO_SESSION_SECRET=\'local-playwright-session-secret-32chars\'; $env:HOOK_STUDIO_PROVIDER_MODE=\'fake\'; python -m uvicorn app.main:app --host 127.0.0.1 --port 8011"',
      cwd: appDir,
      url: 'http://127.0.0.1:8011/healthz',
      reuseExistingServer: true,
      timeout: 30_000,
    },
    {
      command: 'npm run dev -- --host 127.0.0.1',
      cwd: frontendDir,
      url: 'http://127.0.0.1:5174/hook-studio/',
      reuseExistingServer: true,
      timeout: 30_000,
    },
  ],
})

import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

const CLIENT_CODE = process.env.HOOK_STUDIO_E2E_CLIENT_CODE || 'local-client-code'
const ADMIN_CODE = process.env.HOOK_STUDIO_E2E_ADMIN_CODE || 'local-admin-code'


async function login(page: Page, code: string) {
  await page.goto('./')
  await page.getByLabel('访问码').fill(code)
  await page.getByRole('button', { name: '进入工作台' }).click()
}


test('无码 API 为 401，客户可完成图片和视频双队列流程', async ({ page }, testInfo) => {
  const unauthorized = await page.request.get('/hook-studio/api/studio/bootstrap')
  expect(unauthorized.status()).toBe(401)

  await login(page, CLIENT_CODE)
  await expect(page.getByRole('heading', { name: '制作一个新钩子' })).toBeVisible()
  await expect(page.getByText(/今日视频 \d+\/100/)).toBeVisible()

  await page.getByRole('radio', { name: /图片钩子/ }).click()
  await page.getByRole('button', { name: /痛点直击/ }).click()
  await page.getByLabel('一句话产品描述').fill('便携桌面灯，触摸开关，照亮键盘')
  const beforeImage = await page.locator('.gallery-card').count()
  await page.getByRole('button', { name: '开始生成' }).click()
  await expect.poll(() => page.locator('.gallery-card').count()).toBeGreaterThan(beforeImage)
  await expect(page.getByText('图片 9:16').first()).toBeVisible()

  await page.getByRole('radio', { name: /视频钩子/ }).click()
  await page.getByRole('button', { name: /手持动作证明/ }).click()
  await page.getByLabel('一句话产品描述').fill('便携桌面灯，手指按下触摸开关，随后灯光亮起并照亮键盘')
  const beforeVideo = await page.locator('.gallery-card').count()
  await page.getByRole('button', { name: '开始生成' }).click()
  await expect.poll(() => page.locator('.gallery-card').count()).toBeGreaterThan(beforeVideo)
  await expect(page.getByText('视频 9:16').first()).toBeVisible()

  const health = await page.request.get('/hook-studio/api/health')
  expect(health.ok()).toBeTruthy()
  const payload = await health.json()
  expect(payload.queues.image.concurrency).toBe(2)
  expect(payload.queues.video.concurrency).toBe(2)

  await page.screenshot({ path: testInfo.outputPath('customer-workspace.png'), fullPage: true })
})


test('管理员可查看客户、用量和服务状态', async ({ page }, testInfo) => {
  await login(page, ADMIN_CODE)
  await expect(page.getByRole('heading', { name: '今日运行概览' })).toBeVisible()
  await expect(page.getByText('本地测试客户')).toBeVisible()
  await expect(page.getByText('全站视频用量')).toBeVisible()
  await expect(page.getByText('服务健康')).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('admin-dashboard.png'), fullPage: true })
})
